#!/usr/bin/env bash
# scripts/install-codex-cli.sh - global-install (or update) the built Codex
# CLI skills into ~/.codex/skills/, the same link-first, copy-as-fallback way
# scripts/install-claude-code.sh does - see that script's header for the full
# rationale (a plain `cp -R`, which is what the docs said before this script
# existed, is not wrong so much as silently stale: it works on day one and
# then quietly stops reflecting the repo the moment you fix a bug).
#
# Unlike the Claude Code skill directory, ~/.codex/skills/ is not exclusively
# ours - Codex and other tools keep their own entries there too (verified on
# this project's own reference machine: a `.system` and a `use-railway`
# folder live alongside Wicked Brain's). So this links each `brain-*` folder
# individually rather than the whole skills/ directory, and never touches
# anything else already in there.
#
# Windows: `mklink /J` (directory junction, no admin needed) per skill
# folder, falling back to a plain recursive copy only if that fails.
# macOS/Linux: `ln -sf` per skill folder (unchanged from before).
#
# This script does NOT touch ~/.codex/config.toml (the MCP server
# registration) - that always points straight at this repo's own
# integrations/mcp-server/server.py, so it already reflects the live source
# with no linking or copying involved; see dist/codex-cli/INSTALL.md.
#
# Usage: bash scripts/install-codex-cli.sh
#
# Run this from an actual Git Bash terminal - see
# scripts/install-claude-code.sh's header for why a bare `bash` on a machine
# that also has WSL installed can silently resolve to the wrong shell.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DIST_SKILLS="$REPO_ROOT/dist/codex-cli/.agents/skills"

# See scripts/install-claude-code.sh's normalize_path for why this exists:
# the override env var below has no guarantee of arriving as a Git-Bash-
# native POSIX path.
normalize_path() {
  case "$1" in
    *'\'*|[A-Za-z]:*) command -v cygpath >/dev/null 2>&1 && cygpath -u "$1" || printf '%s' "$1" ;;
    *) printf '%s' "$1" ;;
  esac
}

DEST="$(normalize_path "${WICKED_BRAIN_CODEX_SKILLS_DIR:-$HOME/.codex/skills}")"

if [[ ! -d "$DIST_SKILLS" ]]; then
  echo "error: $DIST_SKILLS not found - build it first:" >&2
  echo "  bash scripts/build.sh --platform codex-cli" >&2
  exit 1
fi

is_windows() {
  [[ "${OS:-}" == "Windows_NT" ]] && return 0
  case "$(uname -s 2>/dev/null)" in MINGW*|MSYS*|CYGWIN*) return 0 ;; esac
  return 1
}

winpath() { cygpath -w "$1"; }

remove_existing() {
  local dst="$1"
  [[ -e "$dst" || -L "$dst" ]] || return 0
  rm -rf "$dst"
}

# link_dir <src> <dst> - returns 0 if a real link/junction was made, 1 if it
# fell back to a plain recursive copy.
link_dir() {
  local src="$1" dst="$2"
  mkdir -p "$(dirname "$dst")"
  remove_existing "$dst"
  if is_windows; then
    if MSYS_NO_PATHCONV=1 cmd.exe /c mklink /J "$(winpath "$dst")" "$(winpath "$src")" >/dev/null 2>&1; then
      return 0
    fi
    cp -R "$src" "$dst"
    return 1
  else
    ln -sf "$src" "$dst"
    return 0
  fi
}

echo "Installing Wicked Brain (Codex CLI, global) from $DIST_SKILLS ..."
echo

mkdir -p "$DEST"
TOTAL=0
FALLBACKS=0
for d in "$DIST_SKILLS"/brain-*; do
  [[ -d "$d" ]] || continue
  name="$(basename "$d")"
  TOTAL=$((TOTAL + 1))
  if link_dir "$d" "$DEST/$name"; then
    echo "  [junction/symlink]  $name"
  else
    echo "  [copy]              $name  (link failed - no admin rights, cross-volume, or unsupported filesystem)"
    FALLBACKS=$((FALLBACKS + 1))
  fi
done

echo
echo "  $((TOTAL - FALLBACKS))/$TOTAL skill folders linked, $FALLBACKS copied, under $DEST"
echo
if [[ "$FALLBACKS" -eq 0 ]]; then
  echo "Done - real links in place. Future \`bash scripts/build.sh --platform codex-cli\`"
  echo "runs take effect on your next Codex session, no re-run of this script needed."
else
  echo "Done - but $FALLBACKS folder(s) above fell back to a plain copy, which will go"
  echo "stale the next time you rebuild. Re-run this script"
  echo "(bash scripts/install-codex-cli.sh) after every \`bash scripts/build.sh\`."
fi

echo
echo "Still needed (this script does not do it): register the MCP server in"
echo "~/.codex/config.toml. See dist/codex-cli/INSTALL.md for the exact block -"
echo "that file always reads straight from this repo, so it never goes stale."
