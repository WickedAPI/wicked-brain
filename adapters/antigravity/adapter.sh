#!/usr/bin/env bash
# =============================================================================
# adapters/antigravity/adapter.sh - Google Antigravity platform adapter
# =============================================================================
# Writes dist/antigravity/ as a real Antigravity plugin: plugin.json,
# skills/<name>/SKILL.md per command, rules/AGENTS.md (Antigravity's
# "always loaded at the prompt level" mechanism), and mcp_config.json
# bundling the MCP server.
#
# This is the SECOND attempt at this build. The first (commit 38ce5e7) was
# built from docs alone, installed, and reverted the same day - not because
# the plugin schema was wrong, but because the user's own hands-on testing
# found Antigravity didn't support plugins/MCP at all on the build they were
# using then (see commit a89af0c). This attempt is grounded in three
# independent, stronger sources of evidence gathered before writing a line of
# adapter code:
#
#   1. Antigravity's own BUILT-IN documentation skill, read directly off disk
#      at ~/.gemini/antigravity/builtin/skills/agy-customizations/ (docs/
#      plugins.md, mcp_servers.md, hooks.md, skills.md, json_configs.md) -
#      not a web search, the actual shipped skill the app itself uses to
#      explain its own customization system.
#   2. A LIVE end-to-end test on this machine: a hand-written test plugin
#      (plugin.json + mcp_config.json only) was placed at
#      ~/.gemini/config/plugins/engram-test/, Antigravity was restarted, and
#      ~/.gemini/antigravity/mcp/engram-test_engram/ was confirmed to contain
#      real, freshly-timestamped tool manifests matching server.py's actual
#      12 @mcp.tool() functions - genuine live introspection, not a stale or
#      fabricated listing. A real prompt in Antigravity then chained
#      brain_search -> brain_backlinks -> brain_read_note on its own and
#      produced a correct, well-grounded answer about a real vault note.
#   3. Real local evidence for the two things that were pure guesses last
#      time (see the "confirmed, not guessed" notes below on plugin.json,
#      rules/, mcp_config.json's env block, and the write-tool argument key).
#
# What changed from the reverted build, now that real evidence exists:
#   - rules/AGENTS.md, not rules/engram.md (the project's old name) - plugins.md explicitly recommends
#     "AGENTS.md" as the filename under rules/, the old build invented a
#     different name with no doc support for it.
#   - mcp_config.json now ships a real "env" block (WICKED_BRAIN_VAULT_PATH set to
#     an install-time-resolved absolute path) - mcp_servers.md documents env
#     as a supported field for the stdio transport; the old build omitted it
#     entirely because that support was unconfirmed at the time.
#   - mcp_config.json's server path and every skill's SKILL_ROOT are now
#     install-time-resolved ABSOLUTE paths (a placeholder token substituted
#     by scripts/install-antigravity.sh after linking), not the old build's
#     untested relative paths. Absolute is the only form actually proven
#     working (see evidence #2 above); mcp_servers.md never documents what
#     working directory a spawned MCP server process gets, and Antigravity's
#     own agent runs shell commands with the user's PROJECT as cwd, not the
#     plugin's install directory - a relative SKILL_ROOT would almost
#     certainly resolve against the wrong directory.
#   - hooks.json is deliberately NOT shipped in this build (see below) -
#     the old build's biggest guess turned out, on a careful re-read of the
#     now-available real hooks.md, to rest on a real contract mismatch, not
#     just an unconfirmed detail.
#
# ── hooks.json: still not built, for a sharper reason than before ──────────
# hooks.md's own documented PostToolUse contract is:
#   input:  { stepIdx, error?, conversationId, workspacePaths, ... }
#   output: {} (empty object)
# Notice what's absent: no toolCall name, no toolCall.args - PostToolUse's
# documented payload does not carry the tool call that just ran at all, only
# PreToolUse's does. Write-time validation needs to inspect the file AFTER
# the write (its finished frontmatter, body, tags), which is exactly what
# PostToolUse is for semantically - but if the documented payload is
# complete, there is no file path in it to check. Two ways around that were
# considered and both rejected for this build:
#   - Parse stepIdx against transcriptPath (both ARE in the payload) to find
#     the matching tool_calls entry and pull TargetFile out of it - real
#     transcript.jsonl content on this machine confirms `write_to_file` and
#     `replace_file_content` both use "TargetFile" as their exact path key
#     (grepped directly from ~/.gemini/antigravity/brain/*/logs/transcript.jsonl,
#     not guessed - this is the one piece of the old build's guesswork that
#     turned out right). But transcriptPath's JSONL shape is Antigravity's own
#     internal debug log format, undocumented and unversioned - building a
#     write-validation feature on top of it is exactly the kind of silent-
#     breakage risk this project's own hooks/validate-ai-first.sh comments
#     warn about elsewhere (#171).
#   - Use PreToolUse instead, which IS documented to carry toolCall.args -
#     but it fires BEFORE the write, so there is no finished file to inspect
#     yet (replace_file_content's args are a partial diff, not the resulting
#     file).
# Shipping a hook that silently does nothing (or errors) on a documented-but-
# incomplete contract is worse than not shipping one - same call this
# project already made for Codex CLI ("no hook system at all") and for
# Antigravity's own SessionStart/PostCompact gap below. Worth revisiting if
# Antigravity's PostToolUse payload turns out to carry more than hooks.md
# documents (easy to check later: a one-line hook that dumps stdin to a file
# and reads it after one real write).
#
# ── No SessionStart/UserPromptSubmit/PostCompact equivalent ────────────────
# Confirmed again by the real docs (not just absent from the old build's
# research): hooks.md's five events are PreToolUse, PostToolUse,
# PreInvocation, PostInvocation, Stop. PreInvocation is the closest to
# SessionStart but fires before EVERY model call, not once per session -
# using it for recall.py's per-prompt brief would need a same-conversationId
# dedup guard to avoid re-injecting on every internal tool round-trip, which
# is real design work, not a drop-in port. Left unbuilt. rules/AGENTS.md
# covers the one-time "the vault exists" job without needing a hook at all,
# since it is simply always in context.
# =============================================================================

AG_PLATFORM="antigravity"
AG_VERSION="1.0.0"
AG_INSTALL_DIR_TOKEN="__WICKED_BRAIN_ANTIGRAVITY_INSTALL_DIR__"
AG_VAULT_PATH_TOKEN="__WICKED_BRAIN_ANTIGRAVITY_VAULT_PATH__"

adapter_build() {
  local src="$1" dst="$2"

  _antigravity_emit_skills "$src/commands" "$dst/skills"
  _antigravity_emit_rules "$src" "$dst"
  _antigravity_copy_references "$src/references" "$dst/references"
  _antigravity_copy_scripts "$src/scripts" "$dst/scripts"
  _antigravity_copy_mcp_server "$src" "$dst"
  _antigravity_emit_plugin_manifest "$dst"
  _antigravity_emit_mcp_config "$dst"
  _antigravity_emit_install_hint "$dst"
}

# One native Antigravity skill per command: skills/<name>/SKILL.md. Confirmed
# against docs/skills.md (frontmatter needs only name + description) AND
# against five real installed plugins on this machine that ship this exact
# shape (chrome-devtools-plugin, firebase, android-cli-plugin, ...).
#
# SKILL_ROOT is left as an install-time placeholder (see this file's header
# for why relative can't be trusted here) - install-antigravity.sh resolves
# it to the real installed absolute path after linking.
_antigravity_emit_skills() {
  local src="$1" dst="$2"
  [[ -d "$src" ]] || return 0
  local f name desc triggers trigmode out
  for f in "$src"/*.md; do
    [[ -f "$f" ]] || continue
    should_include "$f" "$AG_PLATFORM" || continue

    name="$(basename "$f" .md)"
    desc="$(parse_frontmatter "$f" description)"
    triggers="$(parse_frontmatter "$f" triggers_en)"
    trigmode="$(parse_frontmatter "$f" trigger-mode)"
    [[ -z "$desc" ]] && desc="Run the $name command of the wicked-brain skill."

    if [[ -n "$triggers" ]]; then
      local trig_clean
      trig_clean="$(format_triggers "$triggers")"
      [[ -n "$trig_clean" ]] && desc="$desc Triggers: $trig_clean."
    fi
    desc="$(with_trigger_policy "$desc" "$trigmode")"

    mkdir -p "$dst/$name"
    out="$dst/$name/SKILL.md"
    {
      echo "---"
      echo "name: $name"
      printf 'description: "%s"\n' "${desc//\"/\\\"}"
      echo "---"
      echo
      command_body "$f"
    } > "$out"

    rewrite_tool_neutral "$out"
    rewrite_skill_root "$out" "$AG_INSTALL_DIR_TOKEN"
    rewrite_platform_paths "$out" ""
  done
}

# rules/AGENTS.md - the filename docs/plugins.md explicitly recommends
# ("Placing a consolidated AGENTS.md file under rules/ is recommended over
# separate rule files"), not the old build's invented rules/engram.md. This
# is what covers SessionStart's "announce the vault exists" job: it is
# always loaded at the prompt level per docs/agy-customizations, no hook
# needed at all.
_antigravity_emit_rules() {
  local src="$1" dst="$2"
  [[ -f "$src/SKILL.md" ]] || return 0
  mkdir -p "$dst/rules"
  {
    echo "# Wicked Brain - always-on operating context"
    echo
    echo "(Generated from this project's root SKILL.md by adapters/antigravity/adapter.sh - do not edit manually.)"
    echo
    command_body "$src/SKILL.md"
  } > "$dst/rules/AGENTS.md"
  rewrite_tool_neutral "$dst/rules/AGENTS.md"
  rewrite_skill_root "$dst/rules/AGENTS.md" "$AG_INSTALL_DIR_TOKEN"
  rewrite_platform_paths "$dst/rules/AGENTS.md" ""
}

_antigravity_copy_references() { copy_references_rewritten "$1" "$2" ""; }  # see adapters/lib.sh

_antigravity_copy_scripts() { copy_scripts_with_project "$1" "$2"; }  # see adapters/lib.sh

# Bundled at the same relative depth as the repo (integrations/mcp-server/ two
# levels under the plugin root, scripts/ a sibling of integrations/) so
# vault_ops.py's unmodified `parents[2] / "scripts"` resolution keeps working -
# identical reasoning to the Claude Code plugin's _cc_copy_mcp_server.
_antigravity_copy_mcp_server() {
  local src="$1" dst="$2"
  local mcp_src="$src/integrations/mcp-server"
  [[ -d "$mcp_src" ]] || return 0
  mkdir -p "$dst/integrations/mcp-server"
  cp "$mcp_src/server.py" "$mcp_src/vault_ops.py" "$dst/integrations/mcp-server/"
}

# plugin.json - schema confirmed against real installed plugins on this
# machine (~/.gemini/config/plugins/gemini-api/plugin.json has this exact
# name/version/description/author/license/keywords shape) AND against a
# live test: a minimal {"name": "engram-test"} plugin.json was enough for
# Antigravity to discover and load a real plugin end-to-end, so the extra
# fields here are for the settings-panel plugin listing, not required for
# loading.
_antigravity_emit_plugin_manifest() {
  local dst="$1"
  cat > "$dst/plugin.json" <<EOF
{
  "name": "wicked-brain",
  "version": "$AG_VERSION",
  "description": "A fast, file-based memory vault shared between Claude Code, Codex CLI, and Google Antigravity - search, save, and maintain a plain-markdown memory of projects, entities, decisions, sessions, and concepts, with atomic writes, bi-temporal facts, duplicate detection, and write-time validation.",
  "author": { "name": "Wicked Brain" },
  "license": "MIT",
  "keywords": ["memory", "vault", "notes", "second-brain", "knowledge-base"]
}
EOF
}

# mcp_config.json - local stdio server (command/args/env). Confirmed live on
# this machine: this exact shape (command "uv", the same args below, and an
# env.WICKED_BRAIN_VAULT_PATH pointing at the real vault) was hand-written to
# ~/.gemini/config/plugins/engram-test/mcp_config.json, Antigravity was
# restarted, and it connected - 12/12 tools discovered, a real
# brain_search call against the real vault returned correct results. The
# server path and vault path below are install-time placeholders (see this
# file's header for why absolute, not relative) - install-antigravity.sh
# resolves both to real absolute paths after linking, the same way it
# resolves SKILL_ROOT in the skills above.
_antigravity_emit_mcp_config() {
  local dst="$1"
  cat > "$dst/mcp_config.json" <<EOF
{
  "mcpServers": {
    "wicked-brain": {
      "command": "uv",
      "args": ["run", "--no-project", "--with", "mcp<2", "python", "$AG_INSTALL_DIR_TOKEN/integrations/mcp-server/server.py"],
      "env": {
        "WICKED_BRAIN_VAULT_PATH": "$AG_VAULT_PATH_TOKEN"
      }
    }
  }
}
EOF
}

_antigravity_emit_install_hint() {
  local dst="$1"
  cat > "$dst/INSTALL.md" <<'EOF'
# Install on Google Antigravity

```bash
# From the repo root, after running `bash scripts/build.sh --platform antigravity`:
bash scripts/install-antigravity.sh
```

Copies `dist/antigravity` into `~/.gemini/config/plugins/wicked-brain` (the
directory name is configurable - see `WICKED_BRAIN_ANTIGRAVITY_PLUGIN_NAME` below)
- the global plugin directory Antigravity's own built-in docs name
explicitly (`~/.gemini/config/` under "Global Configuration
(Machine-Local)"), so placing a real plugin there loads it with no
marketplace step.

**Deliberately a plain copy, not a link/junction** - the one place this
build's install diverges from the "skills-directory plugin" trick the
Claude Code build uses. Real, repeated evidence from this project's own
reference machine: every install that used a real Windows junction
(`mklink /J`) was never discovered by Antigravity - not the very first real
install, not two later reinstalls, across many full quit-and-relaunch
cycles, with the underlying files independently verified correct every
time. Every install that used a plain copy connected immediately. Most
likely explanation: Antigravity's plugin scanner does not traverse NTFS
junctions the way it does real directories (MSYS's own `find`/`ls` already
report a junction as a symlink rather than a directory, not a plain one -
Antigravity's own scanner may share that blind spot). The cost: a rebuild
alone does not reach the installed copy - **re-running this script is
required** after every `bash scripts/build.sh`, not just recommended, since
it also resolves two install-time placeholders into real absolute paths for
this machine (see "Why re-running matters" below).

The installer reads `WICKED_BRAIN_VAULT_PATH` from your environment
(or the documented `WICKED_BRAIN_ENV_FILE`/`~/.config/wicked-brain/.env` fallback the
rest of Wicked Brain already uses) and writes it directly into the installed
`mcp_config.json`'s `env` block - confirmed as a supported field by
Antigravity's own `mcp_servers.md` doc. If neither is set, the installer
stops with an error before touching any existing install; set it and re-run.

**Fully QUIT Antigravity and relaunch it** - not just an in-app reload. On
this project's own reference machine, a soft restart was sometimes not
enough for a newly (re)installed plugin to register, while a full quit and
relaunch reliably picked it up. Then confirm: **Additional Options (...) >
MCP Servers** should list `wicked-brain` as connected with 12 tools.

## If the plugin still never appears

This build already defaults to the one install method confirmed to work on
this project's own reference machine (a plain copy, never a junction - see
above), so this should be rare. If it still never appears after a full quit
and relaunch, with the files independently confirmed correct
(`python3 -m json.tool ~/.gemini/config/plugins/wicked-brain/mcp_config.json`),
try installing under a different directory name as a next diagnostic step:

```bash
WICKED_BRAIN_ANTIGRAVITY_PLUGIN_NAME=brain-2 bash scripts/install-antigravity.sh
```

Delete the old, non-working directory under `~/.gemini/config/plugins/`
afterward so it doesn't linger as a dead entry.

## Why re-running matters

Unlike the Claude Code build, Antigravity's `mcp_config.json` schema has no
confirmed plugin-root variable (no `${CLAUDE_PLUGIN_ROOT}` equivalent -
checked directly against `mcp_servers.md`, `plugins.md`, and `hooks.md`, none
mention one). A relative path was tried in the first attempt at this build
and never verified; what IS proven working on this machine is an absolute
path. So this build ships every skill's `SKILL_ROOT` and `mcp_config.json`'s
server/vault paths as literal placeholder tokens
(`__WICKED_BRAIN_ANTIGRAVITY_INSTALL_DIR__`, `__WICKED_BRAIN_ANTIGRAVITY_VAULT_PATH__`),
and `scripts/install-antigravity.sh` resolves them to this machine's real
paths in the installed copy (never in dist/ itself, so re-running with a
different vault path or plugin name always works). If you move the install (a different
`WICKED_BRAIN_ANTIGRAVITY_PLUGINS_DIR`) or change your vault path, re-run the
installer - a plain `bash scripts/build.sh` alone regenerates the
placeholders and needs the installer's pass to resolve them again.

## What's here, and what's deliberately not

- **`skills/<name>/SKILL.md`** (all 10 `/brain-*` commands) - native
  Antigravity Agent Skills, same progressive-disclosure model as Claude
  Code's and Codex's skills, confirmed against `docs/skills.md` and five
  real installed plugins on this machine.
- **`rules/AGENTS.md`** - always loaded at the prompt level (Antigravity's
  own term, confirmed in `docs/plugins.md`), no hook needed. Covers the
  "the vault exists" job `SessionStart` does elsewhere.
- **`mcp_config.json`** - registers the `wicked-brain` MCP server automatically on
  plugin load, no separate config-file edit (unlike Codex). Proven working
  live on this machine (see adapters/antigravity/adapter.sh's header) - 12
  tools discovered, real search/read/backlink calls returned correct data
  from the real vault.
- **Not built - a real, sharply-understood platform gap, not an
  oversight**: no `hooks.json`. Antigravity's own documented `PostToolUse`
  contract (`docs/hooks.md`) does not include the tool call or its
  arguments in its payload - only `PreToolUse` does, and that fires before
  the write happens, too early to validate finished note content. Building
  write-time AI-first validation here would mean parsing Antigravity's
  internal, undocumented transcript log format to recover the written path,
  which is a real breakage risk for a feature meant to be quietly helpful.
  Left unbuilt rather than shipped fragile. Also not built for the same
  underlying reason as Codex CLI's gap: no `SessionStart`/
  `UserPromptSubmit`/`PostCompact` equivalent exists in Antigravity's hook
  model at all (its five events are `PreToolUse`, `PostToolUse`,
  `PreInvocation`, `PostInvocation`, `Stop`), so `recall.py`'s per-prompt
  brief and `bg-agent.sh`'s post-compaction auto-save have no home here yet.

**Sanity-check the JSON before trusting a fresh build**:

```bash
python3 -m json.tool dist/antigravity/plugin.json > /dev/null && \
python3 -m json.tool dist/antigravity/mcp_config.json > /dev/null && \
echo "all valid JSON"
```
EOF
}
