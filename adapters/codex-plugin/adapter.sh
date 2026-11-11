#!/usr/bin/env bash
# =============================================================================
# adapters/codex-plugin/adapter.sh - Codex plugin (installable via a git marketplace)
# =============================================================================
# Sourced by scripts/build.sh AFTER adapters/lib.sh.
#
# Distinct from adapters/codex-cli (the vault-local / global-symlink install):
# this emits a real Codex *plugin* that a user adds with
#   codex plugin marketplace add <owner>/<repo>
# and then installs from the Codex app's Plugins directory.
#
# Shape follows the one Codex plugin already running locally (SearchLight):
# a portable root plugin.json (+ extensions.com.openai), mcp.json, and the legacy
# .codex-plugin/plugin.json + .mcp.json overlay, all generated from one place so
# they cannot drift. The MCP server is local stdio, started through ${PLUGIN_ROOT}.
#
# Codex plugins have no slash commands and (for a public install) no hooks, so
#   - every /brain-* command becomes a skill:  skills/<name>/SKILL.md
#   - the shared references/ and scripts/ live at the plugin root, and each skill
#     is told that "<plugin-root>" is two folders above its own SKILL.md, so no
#     hook is needed to inject an install path.
#   - the vault location comes from WICKED_BRAIN_VAULT_PATH or
#     ~/.config/wicked-brain/.env (the MCP server already reads both); the
#     brain-setup skill (also the plugin's onboarding skill) writes that file.
# =============================================================================

CP_PLATFORM="codex-plugin"
CP_VERSION="$(sed -n 's/^version *= *"\([^"]*\)".*/\1/p' "${BASH_SOURCE[0]%/*}/../../pyproject.toml" | head -n1)"
CP_VERSION="${CP_VERSION:-0.0.0}"
CP_REPO_URL="${WICKED_BRAIN_REPO_URL:-https://github.com/WickedAPI/wicked-brain}"
# Where the privacy, terms and support pages (site/*.html) are served. Must be public HTTPS before submitting.
CP_SITE_URL="${WICKED_BRAIN_SITE_URL:-https://brain.wickedlabs.gg}"
CP_ASSETS_DIR="$(cd "${BASH_SOURCE[0]%/*}" && pwd)/assets"
CP_ROOT_NOTE='> **Plugin root.** This skill ships inside the Wicked Brain plugin. `<plugin-root>` means the folder two levels above this `SKILL.md` (the folder that contains `skills/`, `references/` and `scripts/`). Resolve every `<plugin-root>/...` path below from this file'"'"'s own location. The vault itself is wherever `WICKED_BRAIN_VAULT_PATH` (or `~/.config/wicked-brain/.env`) points; if neither is set, run `$brain-setup` first.'

adapter_build() {
  local src="$1" dst="$2"

  _cp_emit_skills "$src/commands" "$dst/skills"
  _cp_emit_umbrella_skill "$src" "$dst/skills/wicked-brain"
  _cp_emit_setup_skill "$dst/skills/brain-setup"
  copy_references_rewritten "$src/references" "$dst/references" ""
  _cp_plugin_root_rewrite_tree "$dst/references"
  copy_scripts_with_project "$src/scripts" "$dst/scripts"
  _cp_copy_mcp_server "$src" "$dst"
  mkdir -p "$dst/assets" && cp "$CP_ASSETS_DIR"/* "$dst/assets/"
  _cp_emit_manifests "$dst"
  _cp_emit_mcp_json "$dst"
  _cp_emit_readme "$dst"
}

# One skill per command. Same name/description/trigger folding as the codex-cli build,
# but paths point at <plugin-root> rather than the vault-relative .codex/ folder.
_cp_emit_skills() {
  local src="$1" dst="$2"
  [[ -d "$src" ]] || return 0
  local f name desc triggers trigmode out
  for f in "$src"/*.md; do
    [[ -f "$f" ]] || continue
    should_include "$f" "$CP_PLATFORM" || continue

    name="$(basename "$f" .md)"
    desc="$(parse_frontmatter "$f" description)"
    triggers="$(parse_frontmatter "$f" triggers_en)"
    trigmode="$(parse_frontmatter "$f" trigger-mode)"
    [[ -z "$desc" ]] && desc="Run the $name command of the wicked-brain skill."
    if [[ -n "$triggers" ]]; then
      local trig_clean; trig_clean="$(format_triggers "$triggers")"
      [[ -n "$trig_clean" ]] && desc="$desc Triggers: $trig_clean."
    fi
    desc="$(with_trigger_policy "$desc" "$trigmode")"

    mkdir -p "$dst/$name"
    out="$dst/$name/SKILL.md"
    # Rewrite the body on its own so the root note below is not itself rewritten.
    command_body "$f" > "$out.body"
    rewrite_tool_neutral "$out.body"
    _cp_plugin_root_rewrite "$out.body"
    {
      echo "---"
      echo "name: $name"
      printf 'description: "%s"\n' "${desc//\"/\\\"}"
      echo "---"
      echo
      echo "$CP_ROOT_NOTE"
      echo
      cat "$out.body"
    } > "$out"
    rm -f "$out.body"
  done
}

# The umbrella skill: SKILL.md's operating rules, so a session that never invokes a
# specific $brain-* skill still knows the AI-first rule and where the vault lives.
_cp_emit_umbrella_skill() {
  local src="$1" dst="$2"
  [[ -f "$src/SKILL.md" ]] || return 0
  mkdir -p "$dst"
  # drop the source frontmatter, keep the body; Claude-only sections do not apply here
  awk 'BEGIN{fm=0} /^---[ \t]*$/ && fm<2 {fm++; next} fm>=2 {print}' "$src/SKILL.md" > "$dst/SKILL.md.body"
  perl -0pi -e 's/## Hooks \(Claude Code only.*?(?=\n## )//s' "$dst/SKILL.md.body"
  rewrite_tool_neutral "$dst/SKILL.md.body"
  _cp_plugin_root_rewrite "$dst/SKILL.md.body"
  {
    echo "---"
    echo "name: wicked-brain"
    printf 'description: "%s"\n' "Operating rules for the user's Wicked Brain memory vault (plain-markdown notes shared by Claude Code, Codex and Antigravity). Use whenever the task is to recall, save, or maintain notes about projects, decisions, people, sessions or concepts, or when a \$brain-* skill is invoked."
    echo "---"
    echo
    echo "$CP_ROOT_NOTE"
    echo
    cat "$dst/SKILL.md.body"
  } > "$dst/SKILL.md"
  rm -f "$dst/SKILL.md.body"
}

# brain-setup: connect the plugin to a vault. Also the plugin's onboarding skill.
_cp_emit_setup_skill() {
  local dst="$1"
  mkdir -p "$dst"
  cat > "$dst/SKILL.md" <<'EOF'
---
name: brain-setup
description: "Connect the Wicked Brain plugin to a memory vault: records the vault location for the MCP server and skills, checks that search works, and offers to create the vault. Run once after installing, or whenever brain search says the vault is not configured. Triggers: set up wicked brain, connect my vault, brain setup."
---

> **Plugin root.** `<plugin-root>` means the folder two levels above this `SKILL.md` (the folder that contains `skills/`, `references/` and `scripts/`).

Connect this plugin to the user's vault.

1. **Find the vault.** Check, in order: the `WICKED_BRAIN_VAULT_PATH` environment variable, then a `WICKED_BRAIN_VAULT_PATH=` line in `~/.config/wicked-brain/.env`. If one is set and the folder exists, say where it points and skip to step 4.
2. **Ask where the vault is (or should be).** Accept an existing folder of markdown notes or a new empty path, such as `~/Vault`. Never guess a path and never pick one for the user.
3. **Record it.** Create `~/.config/wicked-brain/` if needed and write (or update, keeping any other lines) `~/.config/wicked-brain/.env` containing exactly `WICKED_BRAIN_VAULT_PATH=<absolute path, forward slashes>`. On Windows `~` is the user profile folder. Tell the user the file location; it holds a path only, no secrets.
4. **Check it.** Confirm the folder exists. If it has none of `projects/`, `entities/`, `decisions/`, `sessions/`, `concepts/`, it is new: offer to run `$brain-init` to create the structure, and run it only if the user says yes.
5. **Verify search.** Call the `wicked-brain` MCP search tool with a simple query. If the tool is missing, tell the user to restart Codex so the plugin's MCP server restarts and to confirm `uv` is installed (https://docs.astral.sh/uv/); do not try to work around it.
6. **Finish.** Summarise: vault path, whether it is new or existing, whether search works, and the skills now available (`$brain-find`, `$brain-save`, `$brain-capture`, `$brain-health`, `$brain-sync` and the rest).

Optional sync: `$brain-sync` needs `WICKED_BRAIN_SYNC_URL`, `WICKED_BRAIN_SYNC_TOKEN` and `WICKED_BRAIN_SYNC_PASSPHRASE` in the environment. Mention this only if the user asks about syncing across devices; never ask for or write those secrets yourself.
EOF
}

# `<plugin-root>` substitution for a skill body.
_cp_plugin_root_rewrite() {
  local file="$1"
  [[ -f "$file" ]] || return 0
  # "given at session start as **Skill root**" is how the Claude build learns its install path
  # from a hook. Here the path is the plugin root, found from this skill's own location.
  perl -i -pe '
    s{(?:was )?given at session start as \*\*Skill root\*\*}{is the plugin root folder (see the note at the top of this skill)}g;
    s{(?<![\w/.-])/brain-(\w+)}{\$brain-$1}g;
    s{\$ARGUMENTS}{<arguments the user gave>}g;
    s{SKILL_ROOT}{<plugin-root>}g;
    s{(^|[^A-Za-z0-9_./<>-])\.?/?references/}{$1<plugin-root>/references/}g;
  ' "$file"
}
_cp_plugin_root_rewrite_tree() {
  local dir="$1" f
  [[ -d "$dir" ]] || return 0
  # References are only ever read after a skill (which carries the root note) has loaded, so
  # they get the same placeholder, not their own copy of the note.
  while IFS= read -r -d '' f; do
    perl -i -pe 's{\.claude/skills/wicked-brain/}{<plugin-root>/}g' "$f"
    _cp_plugin_root_rewrite "$f"
  done < <(find "$dir" -type f -name '*.md' -print0)
}

# Same relative depth as the repo: vault_ops.py resolves scripts/ via parents[2].
_cp_copy_mcp_server() {
  local src="$1" dst="$2"
  local mcp_src="$src/integrations/mcp-server"
  [[ -d "$mcp_src" ]] || return 0
  mkdir -p "$dst/integrations/mcp-server"
  cp "$mcp_src/server.py" "$mcp_src/vault_ops.py" "$dst/integrations/mcp-server/"
}

_cp_emit_manifests() {
  local dst="$1"
  mkdir -p "$dst/.codex-plugin"
  local desc="Plain-markdown memory vault for Codex: recall, save and maintain notes about projects, decisions, sessions and concepts, with ranked search, duplicate detection, freshness checks and optional encrypted cross-device sync."

  # Portable manifest (root). Mirrors the SearchLight plugin that is installed and working.
  cat > "$dst/plugin.json" <<EOF
{
  "\$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
  "name": "wicked-brain",
  "version": "$CP_VERSION",
  "description": "$desc",
  "author": { "name": "SimpliFixed Technologies, LLC", "url": "$CP_REPO_URL" },
  "homepage": "$CP_REPO_URL",
  "repository": "$CP_REPO_URL",
  "license": "MIT",
  "keywords": ["memory", "vault", "notes", "second-brain", "knowledge-base"],
  "extensions": {
    "com.openai": {
      "requires_local_executor": true,
      "onboardingSkill": "./skills/brain-setup/SKILL.md",
      "interface": {
        "displayName": "Wicked Brain",
        "shortDescription": "Memory vault for your agents",
        "longDescription": "Recall and save notes about your projects, decisions and people in a local markdown vault that Claude Code, Codex and Antigravity can all share. Runs entirely on your machine, with no account and no telemetry. Needs the free uv tool installed. Optional end-to-end-encrypted sync to a server you run.",
        "developerName": "SimpliFixed Technologies, LLC",
        "category": "Productivity",
        "capabilities": ["Read", "Write"],
        "brandColor": "#B8431F",
        "composerIcon": "./assets/icon.svg",
        "logo": "./assets/icon.svg",
        "websiteURL": "$CP_SITE_URL/",
        "privacyPolicyURL": "$CP_SITE_URL/privacy.html",
        "termsOfServiceURL": "$CP_SITE_URL/terms.html",
        "supportURL": "$CP_SITE_URL/support.html",
        "defaultPrompt": [
          "Set up Wicked Brain with my vault.",
          "What do we know about this project?",
          "Save what we decided today to my vault."
        ]
      }
    }
  }
}
EOF

  # Legacy overlay (.codex-plugin) - same content, older field names. Codex reads it
  # only when the root manifest lacks extensions.com.openai; shipping both matches
  # the plugin that already installs here.
  cat > "$dst/.codex-plugin/plugin.json" <<EOF
{
  "name": "wicked-brain",
  "version": "$CP_VERSION",
  "description": "$desc",
  "skills": "./skills/",
  "mcpServers": "./.mcp.json",
  "requires_local_executor": true,
  "interface": {
    "displayName": "Wicked Brain",
    "shortDescription": "Memory vault for your agents",
    "category": "Productivity",
    "capabilities": ["Read", "Write"]
  }
}
EOF
}

# Local stdio server started by `uv` through ${PLUGIN_ROOT}. Both files carry the same
# server; the portable one adds the explicit transport type.
_cp_emit_mcp_json() {
  local dst="$1"
  cat > "$dst/mcp.json" <<'EOF'
{
  "$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
  "mcpServers": {
    "wicked-brain": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "--no-project", "--with", "mcp<2", "python", "${PLUGIN_ROOT}/integrations/mcp-server/server.py"],
      "cwd": "${PLUGIN_ROOT}"
    }
  }
}
EOF
  cat > "$dst/.mcp.json" <<'EOF'
{
  "mcpServers": {
    "wicked-brain": {
      "command": "uv",
      "args": ["run", "--no-project", "--with", "mcp<2", "python", "${PLUGIN_ROOT}/integrations/mcp-server/server.py"],
      "cwd": "${PLUGIN_ROOT}"
    }
  }
}
EOF
}

_cp_emit_readme() {
  local dst="$1"
  cat > "$dst/README.md" <<EOF
# Wicked Brain for Codex

A plain-markdown memory vault your agents share. This is the Codex plugin build.

- **Skills:** \`\$brain-find\`, \`\$brain-save\`, \`\$brain-capture\`, \`\$brain-health\`, \`\$brain-sync\`, \`\$brain-init\`, \`\$brain-setup\` and more. Codex has no slash commands, so each command is a skill.
- **MCP server:** local \`wicked-brain\` stdio server (ranked vault search and reads), started with \`uv\`.
- **Setup:** run \`\$brain-setup\` once; it records your vault path in \`~/.config/wicked-brain/.env\`.
- **Needs:** \`uv\` on your PATH (https://docs.astral.sh/uv/).
- **Not included on Codex:** automatic recall and auto-sync hooks. Those run on Claude Code only; on Codex use \`\$brain-find\` and \`\$brain-sync\`.

Project home: $CP_REPO_URL
EOF
}
