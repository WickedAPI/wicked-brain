#!/usr/bin/env bash
# =============================================================================
# adapters/claude-code/adapter.sh - Claude Code platform adapter
# =============================================================================
# Sourced by scripts/build.sh AFTER adapters/lib.sh.
# Writes dist/claude-code/ containing slash commands and the skill manifest
# in the shape Claude Code expects.
# =============================================================================

CC_PLATFORM="claude-code"
# One version for every build and the marketplace: pyproject.toml is the source of truth
# (Claude Code only offers a plugin update when this string changes).
CC_VERSION="$(sed -n 's/^version *= *"\([^"]*\)".*/\1/p' "${BASH_SOURCE[0]%/*}/../../pyproject.toml" | head -n1)"
CC_VERSION="${CC_VERSION:-0.0.0}"
CC_REPO_URL="${WICKED_BRAIN_REPO_URL:-https://github.com/choaticpixels/wicked-brain}"

# adapter_build <src_root> <dst_root>
#
# dist/claude-code/ is built as a real Claude Code plugin (a
# .claude-plugin/plugin.json manifest + hooks/hooks.json + .mcp.json), not
# just a skill+commands bundle with instructions telling the user to hand-
# edit ~/.claude/settings.json. scripts/install-claude-code.sh already
# junctions this exact directory to ~/.claude/skills/wicked-brain - which Claude
# Code treats as a "skills-directory plugin" (see `claude plugin init`) that
# auto-loads on the next session with no marketplace and no /plugin install
# step. So the one existing install command becomes a real plugin install
# for free; nothing about the install path changes, only what lands there.
adapter_build() {
  local src="$1" dst="$2"

  _cc_copy_commands "$src/commands" "$dst/commands"
  _cc_copy_skill_manifest "$src" "$dst"
  _cc_copy_references "$src/references" "$dst/references"
  _cc_copy_scripts "$src/scripts" "$dst/scripts"
  _cc_copy_hooks "$src/hooks" "$dst/hooks"
  _cc_copy_mcp_server "$src" "$dst"
  _cc_emit_plugin_manifest "$dst"
  _cc_emit_plugin_hooks_json "$dst"
  _cc_emit_plugin_mcp_json "$dst"
  _cc_emit_install_hint "$dst"
}

# Identity copy of slash commands - Claude Code's source format matches ours.
_cc_copy_commands() {
  local src="$1" dst="$2"
  [[ -d "$src" ]] || return 0
  mkdir -p "$dst"
  local f
  for f in "$src"/*.md; do
    [[ -f "$f" ]] || continue
    should_include "$f" "$CC_PLATFORM" || continue
    cp "$f" "$dst/$(basename "$f")"
  done
}

# Copy SKILL.md (the Claude Code skill manifest) verbatim.
_cc_copy_skill_manifest() {
  local src="$1" dst="$2"
  [[ -f "$src/SKILL.md" ]] && cp "$src/SKILL.md" "$dst/SKILL.md"
}

_cc_copy_references() { copy_references_rewritten "$1" "$2" ""; }  # see adapters/lib.sh

_cc_copy_scripts() { copy_scripts_with_project "$1" "$2"; }  # see adapters/lib.sh

_cc_copy_hooks() {
  local src="$1" dst="$2"
  [[ -d "$src" ]] || return 0
  mkdir -p "$dst"
  cp -R "$src/." "$dst/"
  _cc_emit_plugin_bridge "$dst"
}

# The MCP server (integrations/mcp-server/{server.py,vault_ops.py}) is bundled
# at the SAME relative depth it lives at in the repo, not flattened - vault_ops.py
# resolves scripts/ via `Path(__file__).resolve().parents[2] / "scripts"`
# (repo_root/integrations/mcp-server/vault_ops.py -> parents[2] == repo_root),
# and preserving integrations/mcp-server/ two levels under the plugin root next
# to a top-level scripts/ is what keeps that unmodified relative-import logic
# working inside the built plugin too.
_cc_copy_mcp_server() {
  local src="$1" dst="$2"
  local mcp_src="$src/integrations/mcp-server"
  [[ -d "$mcp_src" ]] || return 0
  mkdir -p "$dst/integrations/mcp-server"
  cp "$mcp_src/server.py" "$mcp_src/vault_ops.py" "$dst/integrations/mcp-server/"
}

# hooks/_bridge.sh - the one piece of glue a plugin needs that a manual
# settings.json install didn't: userConfig values reach a plugin hook
# subprocess as CLAUDE_PLUGIN_OPTION_<KEY> env vars (uppercased userConfig
# key), not as the WICKED_BRAIN_* names validate-ai-first.sh/bg-agent.sh/
# load_vault_context.py/recall.py actually read - those four scripts are
# shipped byte-identical to the non-plugin install, unaware they're running
# as a plugin at all. This bridge maps one to the other and then execs the
# real hook, so the shared scripts never need two versions.
#
# Each mapping falls back to a plain WICKED_BRAIN_* env var if the plugin option is
# unset/empty - not just belt-and-suspenders: it's what keeps an existing
# manual install (WICKED_BRAIN_VAULT_PATH etc. already in settings.json's own "env"
# block) working unmodified for anyone who updates dist/ before they've
# filled in the plugin's own userConfig (via `/config`) or removed the old
# manual entries.
_cc_emit_plugin_bridge() {
  local dst="$1"
  cat > "$dst/_bridge.sh" <<'EOF'
#!/usr/bin/env bash
# hooks/_bridge.sh - see adapters/claude-code/adapter.sh's
# _cc_emit_plugin_bridge for why this exists. Do not edit the built copy -
# edit the generator and rebuild.
set -euo pipefail

_bool() { case "${1:-}" in true|True|TRUE|1) echo 1 ;; *) echo 0 ;; esac; }

export WICKED_BRAIN_VAULT_PATH="${CLAUDE_PLUGIN_OPTION_VAULT_PATH:-${WICKED_BRAIN_VAULT_PATH:-}}"
export WICKED_BRAIN_RECALL_ENABLED="$(_bool "${CLAUDE_PLUGIN_OPTION_RECALL_ENABLED:-${WICKED_BRAIN_RECALL_ENABLED:-}}")"
export WICKED_BRAIN_BG_AGENT_ENABLED="$(_bool "${CLAUDE_PLUGIN_OPTION_BG_AGENT_ENABLED:-${WICKED_BRAIN_BG_AGENT_ENABLED:-}}")"
export WICKED_BRAIN_AUTO_SYNC_ENABLED="$(_bool "${CLAUDE_PLUGIN_OPTION_AUTO_SYNC_ENABLED:-${WICKED_BRAIN_AUTO_SYNC_ENABLED:-}}")"
export WICKED_BRAIN_SYNC_URL="${CLAUDE_PLUGIN_OPTION_SYNC_URL:-${WICKED_BRAIN_SYNC_URL:-}}"
export WICKED_BRAIN_SYNC_TOKEN="${CLAUDE_PLUGIN_OPTION_SYNC_TOKEN:-${WICKED_BRAIN_SYNC_TOKEN:-}}"
export WICKED_BRAIN_SYNC_PASSPHRASE="${CLAUDE_PLUGIN_OPTION_SYNC_PASSPHRASE:-${WICKED_BRAIN_SYNC_PASSPHRASE:-}}"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
script="${1:?_bridge.sh: missing target hook script name}"; shift || true

# Windows often has `python` (or only `py`/uv) but no working `python3`; the Microsoft Store
# stub answers to `python3` and then fails. Probe for one that actually runs.
_py() {
  local c
  for c in python3 python; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c "import sys" >/dev/null 2>&1; then echo "$c"; return; fi
  done
}
PY="$(_py)"

case "$script" in
  *.py)
    if [ -n "$PY" ]; then exec "$PY" "$HERE/$script" "$@"; fi
    if command -v uv >/dev/null 2>&1; then exec uv run --no-project python "$HERE/$script" "$@"; fi
    echo "wicked-brain plugin bridge: no working python3/python/uv found" >&2; exit 1 ;;
  *.sh) exec bash "$HERE/$script" "$@" ;;
  *) echo "wicked-brain plugin bridge: don't know how to run '$script'" >&2; exit 1 ;;
esac
EOF
  chmod +x "$dst/_bridge.sh" 2>/dev/null || true
}

# .claude-plugin/plugin.json - the manifest. userConfig fields become the
# `/config` panel rows (and, per Claude Code's plugin docs, the prompt shown
# "when the plugin is enabled") that replace hand-editing settings.json's
# "env" block entirely. Field keys are snake_case on purpose: Claude Code
# exports each as CLAUDE_PLUGIN_OPTION_<KEY-UPPERCASED>, and snake_case is the
# only form where that uppercasing is unambiguous (no camelCase-boundary
# guessing) - see hooks/_bridge.sh, which depends on these exact key names.
_cc_emit_plugin_manifest() {
  local dst="$1"
  mkdir -p "$dst/.claude-plugin"
  cat > "$dst/.claude-plugin/plugin.json" <<EOF
{
  "name": "wicked-brain",
  "displayName": "Wicked Brain",
  "version": "$CC_VERSION",
  "description": "A fast, file-based memory vault shared between Claude Code and Codex CLI - search, save, and maintain a plain-markdown memory of projects, entities, decisions, sessions, and concepts, with atomic writes, bi-temporal facts, duplicate detection, and bounded proactive recall.",
  "author": { "name": "Wicked Brain", "url": "$CC_REPO_URL" },
  "homepage": "$CC_REPO_URL",
  "repository": "$CC_REPO_URL",
  "license": "MIT",
  "keywords": ["memory", "vault", "notes", "second-brain", "knowledge-base"],
  "userConfig": {
    "vault_path": {
      "type": "directory",
      "title": "Vault location",
      "description": "Where your Wicked Brain memory vault lives (or should be created), e.g. C:/Users/you/Vault. Run /brain-init after setup if this is a brand-new path.",
      "required": true
    },
    "recall_enabled": {
      "type": "boolean",
      "title": "Proactive recall",
      "description": "Inject a small brief (max 4 notes, ~900 chars) of relevant vault notes into prompts, in every project, on a confident match. Fail-closed and silent otherwise; every decision is logged to <vault>/.claude-runs/recall-YYYY-MM-DD.jsonl.",
      "default": true
    },
    "bg_agent_enabled": {
      "type": "boolean",
      "title": "Background auto-save after compaction",
      "description": "TRUST CAVEAT: runs an unattended headless agent (filesystem tools only - no Bash, no network) after each conversation compacts, to propagate what happened into the vault. Off by default - turn on only once you trust it.",
      "default": false
    },
    "auto_sync_enabled": {
      "type": "boolean",
      "title": "Auto-sync vault (backup)",
      "description": "Automatically run /brain-sync in the background on session start, after compaction, and at session end, so your vault is backed up off this machine without you remembering to. Needs the three sync fields below. Failures and conflicts are reported at the next session start. Off by default.",
      "default": false
    },
    "sync_url": {
      "type": "string",
      "title": "Sync server URL (optional)",
      "description": "For cross-device sync via /brain-sync. Leave blank if you only use one device.",
      "required": false
    },
    "sync_token": {
      "type": "string",
      "title": "Sync token (optional)",
      "description": "Bearer token for the sync server.",
      "sensitive": true,
      "required": false
    },
    "sync_passphrase": {
      "type": "string",
      "title": "Sync passphrase (optional)",
      "description": "Encrypts vault content client-side before it ever leaves this device - only you know it, never sent to the sync server.",
      "sensitive": true,
      "required": false
    }
  },
  "hooks": "./hooks/hooks.json",
  "mcpServers": "./.mcp.json"
}
EOF
}

# hooks/hooks.json - every hook routed through hooks/_bridge.sh so the bridge's
# env-mapping runs before any real hook logic regardless of hook type.
#
# The script path is DOUBLE-QUOTED inside the command string on purpose. Claude
# Code substitutes ${CLAUDE_PLUGIN_ROOT} textually and then hands the string to
# bash. On Windows that root is a backslash path, and unquoted bash strips the
# backslashes ("C:Usersme.claudeskillsengram/hooks/_bridge.sh: No such file or
# directory", exit 127). Found 2026-10-11: that silently killed the recall,
# write-validation and auto-sync hooks on a Windows install. Quoted, bash keeps
# the backslashes and Git Bash resolves the path. An exec-form {"command","args"}
# entry does NOT avoid this - the harness flattens it into the same shell string.
# Matchers/timeouts/async match what the manual install's settings.json snippet
# used to say.
_cc_emit_plugin_hooks_json() {
  local dst="$1"
  mkdir -p "$dst/hooks"
  cat > "$dst/hooks/hooks.json" <<'EOF'
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "bash \"${CLAUDE_PLUGIN_ROOT}/hooks/_bridge.sh\" validate-ai-first.sh",
            "timeout": 15,
            "statusMessage": "Checking AI-first vault rule..."
          }
        ]
      }
    ],
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "bash \"${CLAUDE_PLUGIN_ROOT}/hooks/_bridge.sh\" load_vault_context.py",
            "timeout": 15
          },
          {
            "type": "command",
            "command": "bash \"${CLAUDE_PLUGIN_ROOT}/hooks/_bridge.sh\" auto_sync.py",
            "timeout": 15
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "bash \"${CLAUDE_PLUGIN_ROOT}/hooks/_bridge.sh\" recall.py",
            "timeout": 15
          }
        ]
      }
    ],
    "PostCompact": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "bash \"${CLAUDE_PLUGIN_ROOT}/hooks/_bridge.sh\" bg-agent.sh",
            "timeout": 20,
            "async": true
          },
          {
            "type": "command",
            "command": "bash \"${CLAUDE_PLUGIN_ROOT}/hooks/_bridge.sh\" auto_sync.py",
            "timeout": 15
          }
        ]
      }
    ],
    "SessionEnd": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "bash \"${CLAUDE_PLUGIN_ROOT}/hooks/_bridge.sh\" auto_sync.py",
            "timeout": 15
          }
        ]
      }
    ]
  }
}
EOF
}

# .mcp.json - bundled MCP server config. Unlike hook shell-form commands,
# ${user_config.*} string substitution IS allowed in MCP server env blocks
# (Claude Code's own restriction is specific to shell-form hook commands),
# so this reaches WICKED_BRAIN_VAULT_PATH straight from userConfig with no bridge
# needed.
_cc_emit_plugin_mcp_json() {
  local dst="$1"
  cat > "$dst/.mcp.json" <<'EOF'
{
  "mcpServers": {
    "wicked-brain": {
      "command": "uv",
      "args": ["run", "--no-project", "--with", "mcp<2", "python", "${CLAUDE_PLUGIN_ROOT}/integrations/mcp-server/server.py"],
      "env": {
        "WICKED_BRAIN_VAULT_PATH": "${user_config.vault_path}"
      }
    }
  }
}
EOF
}

_cc_emit_install_hint() {
  local dst="$1"
  cat > "$dst/INSTALL.md" <<'EOF'
# Install on Claude Code

```bash
# From the repo root, after running `bash scripts/build.sh --platform claude-code`:
bash scripts/install-claude-code.sh
```

That's the whole install. Two things happen:

1. **Commands** are hardlinked into `~/.claude/commands/` (`mklink /H` on
   Windows, a real symlink on macOS/Linux - no admin rights needed either
   way; falls back to a plain copy only if that fails, and says so plainly).
2. **Everything else** - the plugin manifest, hooks, and MCP server - is
   junctioned into `~/.claude/skills/wicked-brain/` (`mklink /J` on Windows). That
   directory is what Claude Code calls a **skills-directory plugin**: having
   a `.claude-plugin/plugin.json` there is enough for it to auto-load on your
   next session, with no marketplace and no `/plugin install` step.

No restart needed for the `/brain-*` commands - they work in an
already-running session. The plugin itself (hooks + MCP server) takes effect
on your next new session.

## Configure it (replaces hand-editing settings.json)

Everything that used to require manually merging JSON into
`~/.claude/settings.json` is now a `userConfig` field on the plugin - open
Claude Code's `/config` panel, find **Wicked Brain**, and fill in:

| Field | Required | What it does |
|---|---|---|
| Vault location | Yes | Where your vault lives (or should be created) - e.g. `C:/Users/you/Vault`. Run `/brain-init` after setup if it's a brand-new path. |
| Proactive recall | No (on by default) | Injects a small, relevant-notes brief into prompts in every project on a confident match. Fail-closed, logged, silent otherwise. |
| Background auto-save after compaction | No (**off** by default) | TRUST CAVEAT: runs an unattended headless agent (filesystem tools only, no Bash/network) after each compaction. Turn on only once you trust it. |
| Auto-sync vault (backup) | No (**off** by default) | Runs `/brain-sync` in the background on session start, after compaction and at session end. Needs the three sync fields below. Failures and conflicts are reported at the next session start. |
| Sync server URL / token / passphrase | No | Only needed for `/brain-sync` across devices - leave blank on a single-device setup. |

Sensitive fields (token, passphrase) are masked and stored in your OS
credential store, not in plain-text `settings.json`.

**Migrating from an older, non-plugin install of Wicked Brain?** If
`~/.claude/settings.json` already has a manually-added `hooks.PostToolUse`
/ `SessionStart` / `UserPromptSubmit` / `PostCompact` entry pointing at
`dist/claude-code/hooks/...`, remove those entries (and the matching
`WICKED_BRAIN_*` keys in its `env` block) once the plugin's `/config` fields are
filled in - otherwise each hook fires twice, once from the old manual wiring
and once from the plugin. Rebuilding and re-running
`install-claude-code.sh` does not do this for you; it's a one-time manual
cleanup on machines that predate this plugin packaging.

## What's inside, for reference

- **`hooks/validate-ai-first.sh`** (PostToolUse on Write/Edit) - warns
  (non-blocking) when a markdown file inside your vault fails the AI-first
  rule (missing frontmatter, missing preamble, banned Unicode substitution
  characters, etc.), and commits the written file via `scripts/vault_git.py`
  if the vault is a git repo (see `/brain-init`). Needs `jq` on `PATH` -
  `brew install jq` / `sudo apt install jq` / `winget install jqlang.jq`.
- **`hooks/load_vault_context.py`** (SessionStart) - announces the plugin
  root every session, and - only when the session's cwd is inside the vault
  - loads `_CLAUDE.md` so the model doesn't have to discover it.
- **`hooks/recall.py`** (UserPromptSubmit, gated by the "Proactive recall"
  field) - the fail-closed recall brief described in the table above; every
  inject/abstain decision is logged to
  `<vault>/.claude-runs/recall-YYYY-MM-DD.jsonl`.
- **`hooks/bg-agent.sh`** (PostCompact, gated by "Background auto-save") -
  propagates a just-compacted session into the vault unattended.
- **`hooks/auto_sync.py`** (SessionStart, PostCompact, SessionEnd, gated by
  "Auto-sync vault") - spawns a detached, debounced `vault_sync.py sync`
  (lock file, 2-minute minimum gap) so a slow network never delays a session.
  Every run is recorded in `<vault>/.claude-runs/auto-sync-last.json` and a
  daily `auto-sync-YYYY-MM-DD.jsonl`; a failed run or sync conflicts are
  announced at the next session start. Credentials reach it through the
  environment only, never a command line.
- **`.mcp.json`** - registers the `wicked-brain` MCP server automatically
  (upgrades search to ranked/semantic results instead of plain grep); no
  separate `claude mcp add` step.
- **`hooks/_bridge.sh`** - internal glue mapping the `/config` panel's
  values (delivered to hook subprocesses as `CLAUDE_PLUGIN_OPTION_*` env
  vars) to the `WICKED_BRAIN_*` names the hook scripts read. Falls back to a plain
  `WICKED_BRAIN_*` env var if the plugin option isn't set yet, which is what makes
  the migration note above a "when convenient" cleanup rather than a
  hard requirement.

**Sanity-check the manifest before trusting a fresh build:**

```bash
claude plugin validate dist/claude-code
```
EOF
}
