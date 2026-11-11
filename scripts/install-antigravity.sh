#!/usr/bin/env bash
# scripts/install-antigravity.sh - install (or update) the built Antigravity
# plugin into ~/.gemini/config/plugins/<name> (default "wicked-brain", see
# WICKED_BRAIN_ANTIGRAVITY_PLUGIN_NAME below).
#
# ALWAYS a plain copy, deliberately NOT a link/junction - unlike every other
# installer in this repo. Real, repeated evidence from this project's own
# reference machine: every install that used a real Windows junction
# (`mklink /J`) was NEVER discovered by Antigravity, across the very first
# real install and two later reinstalls, through many full quit-and-relaunch
# cycles, with the underlying files independently verified correct every
# time. Every install that used a plain copy connected immediately. See
# install_copy's own header below for the full reasoning (most likely
# Antigravity's plugin scanner does not traverse NTFS junctions the way it
# does real directories). The tradeoff this costs: a rebuild does not take
# effect until this installer is re-run - already true anyway, since
# resolve_placeholders below requires a re-run after every rebuild regardless.
#
# Unlike ~/.claude/skills/, ~/.gemini/config/plugins/ is not exclusively
# ours either - real plugins already live there on this project's own
# reference machine (firebase, gemini-api, android-cli-plugin,
# google_maps_platform, data-agent-kit-plugin). This only ever
# creates/replaces its own named entry and never touches the others.
#
# After copying, this ALSO resolves two install-time placeholder tokens
# (__WICKED_BRAIN_ANTIGRAVITY_INSTALL_DIR__, __WICKED_BRAIN_ANTIGRAVITY_VAULT_PATH__)
# that adapters/antigravity/adapter.sh leaves in every skill's SKILL_ROOT
# reference and in mcp_config.json - see that file's header for why an
# absolute, install-time-resolved path is used instead of a relative one
# (no confirmed plugin-root variable exists in Antigravity's mcp_config.json
# or skills schema, and this is the one form proven working by a live test
# on this machine).
#
# Usage: bash scripts/install-antigravity.sh
#
# Run this from an actual Git Bash terminal - see
# scripts/install-claude-code.sh's header for why a bare `bash` on a machine
# that also has WSL installed can silently resolve to the wrong shell.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# See scripts/install-claude-code.sh's normalize_path for why this exists.
normalize_path() {
  case "$1" in
    *'\'*|[A-Za-z]:*) command -v cygpath >/dev/null 2>&1 && cygpath -u "$1" || printf '%s' "$1" ;;
    *) printf '%s' "$1" ;;
  esac
}

# Override point for tests: a real, already-running Antigravity may hold a
# live junction pointing at the normal $REPO_ROOT/dist/antigravity - two
# separate junctions to the SAME real files, one held open by Antigravity
# and one this installer is about to perl -i rewrite, deadlocked a Windows
# rename in exactly that situation while building this adapter (a `perl -i`
# on references/ai-first-rules.md hung for over two hours, confirmed via
# Get-CimInstance Win32_Process, not assumed). tests/test_smoke.py points
# this at an isolated copy so a test run can never collide with a live
# install again.
DIST="$(normalize_path "${WICKED_BRAIN_ANTIGRAVITY_DIST_DIR:-$REPO_ROOT/dist/antigravity}")"

# Forward-slash form for embedding in JSON string values - a raw Windows
# backslash path would either break JSON parsing (a lone backslash is not a
# legal escape) or, worse, silently parse as the wrong escape sequence.
# Confirmed this is the form that actually works: the live test on this
# machine used "C:/Users/.../Vault", not "C:\Users\...\Vault".
to_json_path() {
  local p; p="$(normalize_path "$1")"
  if command -v cygpath >/dev/null 2>&1; then
    p="$(cygpath -m -- "$p" 2>/dev/null || printf '%s' "$p")"
  fi
  printf '%s' "${p//\\//}"
}

# Plugin directory name - overridable via WICKED_BRAIN_ANTIGRAVITY_PLUGIN_NAME.
# Originally added while chasing a wrong theory: early on this project's own
# reference machine, the plugin named "wicked-brain" never appeared while a fresh
# name (engram-vault, an old test name) connected immediately, which looked like per-name
# stuck state in Antigravity. That theory was DISPROVEN once the real
# variable was isolated - every "wicked-brain"-named test had also happened to use
# a junction, and every fresh-name test had also happened to use a plain
# copy, confounding the two. Reinstalling the ORIGINAL "wicked-brain" name as a
# plain copy connected immediately, same as any other name - see install_copy's
# header below for the real, confirmed cause (junction vs. copy). This
# override is kept only as a low-cost diagnostic escape hatch (rule out a
# stale/corrupted entry at a given path) - not an expected fix.
PLUGIN_NAME="${WICKED_BRAIN_ANTIGRAVITY_PLUGIN_NAME:-wicked-brain}"
# This name is appended to the plugins dir and later rm -rf'd - reject anything
# that could resolve outside its own directory ("..", ".", "a/b").
if [[ ! "$PLUGIN_NAME" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then
  echo "error: WICKED_BRAIN_ANTIGRAVITY_PLUGIN_NAME='$PLUGIN_NAME' is not a plain directory name" >&2
  echo "       (letters, digits, '.', '_', '-'; must start with a letter or digit)." >&2
  exit 1
fi
PLUGIN_DEST="$(normalize_path "${WICKED_BRAIN_ANTIGRAVITY_PLUGINS_DIR:-$HOME/.gemini/config/plugins}")/$PLUGIN_NAME"

if [[ ! -d "$DIST" ]]; then
  echo "error: $DIST not found - build it first:" >&2
  echo "  bash scripts/build.sh --platform antigravity" >&2
  exit 1
fi

remove_existing() {
  local dst="$1"
  [[ -e "$dst" || -L "$dst" ]] || return 0
  rm -rf "$dst"
}

# install_copy <src> <dst> - ALWAYS a plain copy, deliberately NOT a
# link/junction, unlike install-claude-code.sh. Real, repeated evidence from
# this project's own reference machine: every install that used a real
# `mklink /J` junction was NEVER discovered by Antigravity (first install and
# two reinstalls, many full quit-and-relaunch cycles, files verified correct
# every time), while every plain copy connected immediately. Most likely
# Antigravity's plugin scanner does not traverse NTFS junctions. The cost: a
# rebuild does not reach the installed copy until this script is re-run.
#
# Stages into a temp dir first so a failed copy never destroys a working
# install, and so placeholder resolution (which rewrites files) never touches
# the shared build output in dist/. The staging dir is deliberately NOT inside
# the plugins directory: a running Antigravity scans every directory under it
# and holds the files open, which makes the final rename fail with "Permission
# denied" (found 2026-10-21). Sets $STAGE.
install_copy() {
  local src="$1" dst="$2"
  mkdir -p "$(dirname "$dst")"
  STAGE="$(mktemp -d "${TMPDIR:-/tmp}/wicked-brain-stage.XXXXXX")"
  # `src/.` (contents into STAGE), never `src` itself - see git history for
  # the nested-directory bug the other form caused when a target pre-existed.
  cp -R "$src/." "$STAGE/"
}

# Swap the staged tree into place. If the old install can't be fully removed
# (a live Antigravity MCP process can hold files open - "Device or resource
# busy"), overlay onto it rather than nesting or failing, and say so.
finish_install() {
  local dst="$1"
  remove_existing "$dst"
  if [[ -e "$dst" ]]; then
    echo "  [warn]      could not fully remove the old install (files in use?) - overlaying."
    echo "              Quit Antigravity and re-run if stale skills linger."
    cp -R "$STAGE/." "$dst/"
    rm -rf "$STAGE"
  else
    # mv is a rename on the same volume; across volumes it falls back to copy + delete.
    mv "$STAGE" "$dst" || { mkdir -p "$dst" && cp -R "$STAGE/." "$dst/" && rm -rf "$STAGE"; }
  fi
  echo "  [copy]      $dst"
}

# Same vault-path resolution order hooks/validate-ai-first.sh already uses:
# environment wins, falling back to the documented config .env, so this
# installer finds the same vault a plugin-marketplace-style install would
# have configured, not a second, divergent source of truth.
resolve_vault_path() {
  local v="${WICKED_BRAIN_VAULT_PATH:-}"
  if [[ -n "$v" ]]; then printf '%s' "$v"; return 0; fi
  local home
  case "$(uname -s 2>/dev/null)" in
    MINGW*|MSYS*|CYGWIN*) home="${USERPROFILE:-$HOME}"; home="$(cygpath -u "$home" 2>/dev/null || printf '%s' "${home//\\//}")" ;;
    *) home="$HOME" ;;
  esac
  local env_file="${WICKED_BRAIN_ENV_FILE:-$home/.config/wicked-brain/.env}"
  [[ -r "$env_file" ]] || return 1
  v=$(sed -n 's/^[[:space:]]*WICKED_BRAIN_VAULT_PATH[[:space:]]*=[[:space:]]*//p' "$env_file" \
    | tail -n 1 | tr -d '\r' | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")
  [[ -n "$v" ]] || return 1
  printf '%s' "$v"
}

# Resolve the two install-time placeholders across every shipped file in
# <dir> (the STAGED copy, never dist/ - see install_copy). A plain text
# substitution (not a JSON-library rewrite) is safe because both tokens are
# unique strings and the values are pre-normalized to forward-slash JSON-safe
# form by to_json_path/normalize_path above. Only files that actually contain
# a token are rewritten.
resolve_placeholders() {
  local dir="$1" install_dir="$2" install_dir_json vault_json

  install_dir_json="$(to_json_path "$install_dir")"
  vault_json="$(to_json_path "$VAULT_RAW")"

  # Exported so perl (not just the listing command) sees them - an earlier
  # version scoped them to `find` only, a silent no-op that still printed
  # "[resolved]" and exited 0.
  export WICKED_BRAIN_INSTALL_DIR_JSON="$install_dir_json" WICKED_BRAIN_VAULT_JSON="$vault_json"
  grep -rlZ --include='*.md' --include='*.json' '__WICKED_BRAIN_ANTIGRAVITY_' "$dir" \
    | xargs -0 -r perl -i -pe '
        BEGIN { $inst = $ENV{WICKED_BRAIN_INSTALL_DIR_JSON}; $vault = $ENV{WICKED_BRAIN_VAULT_JSON}; }
        s/__WICKED_BRAIN_ANTIGRAVITY_INSTALL_DIR__/$inst/g;
        s/__WICKED_BRAIN_ANTIGRAVITY_VAULT_PATH__/$vault/g;
      '
  unset WICKED_BRAIN_INSTALL_DIR_JSON WICKED_BRAIN_VAULT_JSON

  echo "  [resolved]  SKILL_ROOT and mcp_config.json -> $install_dir_json"
  echo "  [resolved]  WICKED_BRAIN_VAULT_PATH -> $vault_json"
}

# Fail fast, before touching any existing install: a plugin installed with an
# unresolved vault token would connect "green" while pointing the server at a
# directory literally named __WICKED_BRAIN_ANTIGRAVITY_VAULT_PATH__.
if ! VAULT_RAW="$(resolve_vault_path)"; then
  echo "error: WICKED_BRAIN_VAULT_PATH is not set and no $HOME/.config/wicked-brain/.env was found." >&2
  echo "       Set WICKED_BRAIN_VAULT_PATH to your vault and re-run this script." >&2
  exit 1
fi

echo "Installing Wicked Brain (Antigravity) from $DIST ..."
echo

install_copy "$DIST" "$PLUGIN_DEST"
resolve_placeholders "$STAGE" "$PLUGIN_DEST"
finish_install "$PLUGIN_DEST"

echo
echo "Done - copied (always a plain copy on this platform - see install_copy's"
echo "header for why). Re-run this script after every"
echo "\`bash scripts/build.sh\` - a rebuild alone does not reach the installed copy."

echo
echo "Fully QUIT Antigravity and relaunch it (not just an in-app reload/restart) -"
echo "confirmed on this project's own reference machine that a soft restart is"
echo "sometimes not enough to pick up a (re)installed plugin, while a full quit and"
echo "relaunch reliably is. Then check Additional Options (...) > MCP Servers for"
echo "\"$PLUGIN_NAME\" with 12 tools listed."
echo
echo "If it still never appears after a full quit and relaunch, even with files"
echo "confirmed correct (python3 -m json.tool $PLUGIN_DEST/mcp_config.json), this"
echo "build already defaults to the one install method confirmed to work (always a"
echo "plain copy), so this should be rare. As a next diagnostic step, try a"
echo "different name: WICKED_BRAIN_ANTIGRAVITY_PLUGIN_NAME=brain-2 bash scripts/install-antigravity.sh"
echo "then delete the old, non-working directory under ~/.gemini/config/plugins/."
echo "See $DIST/INSTALL.md for what this build deliberately does not attempt yet"
echo "(no hooks.json - see adapters/antigravity/adapter.sh for the real, sharply-"
echo "understood reason why)."
