#!/usr/bin/env bash
# scripts/install-claude-code.sh - install (or update) the built Claude Code
# skill + commands into ~/.claude/, using the strongest link Windows will
# grant without admin/Developer Mode, falling back to a real copy (with a
# clear "re-run me after rebuilding" warning) only if even that fails.
#
# Why this exists instead of the two `ln -sf` lines the docs used to say to
# copy-paste: on Windows, an unprivileged `ln -s` on a DIRECTORY either fails
# outright or - on some Git-for-Windows builds - silently creates a real
# recursive COPY instead of a link, with no error printed either way. That is
# exactly what happened on this project's own reference machine:
# ~/.claude/skills/wicked-brain was a plain copy, so rebuilding dist/ after a real
# bug fix never reached the live PostCompact hook until someone noticed the
# hook's behavior hadn't changed and manually re-copied every file by hand.
#
# This script instead:
#   - Windows (Git Bash / MSYS / Cygwin): `mklink /J` (directory junction -
#     no admin needed) for the skill directory, `mklink /H` (hardlink - no
#     admin needed, same-volume only) per command file, falling back to a
#     plain copy per item only if that specific link creation fails (e.g.
#     the repo and ~/.claude live on different drives).
#   - macOS/Linux: `ln -sf` (unchanged - symlinks always worked fine here).
# Either way, it VERIFIES what actually landed and tells you plainly whether
# you got a real link (rebuild and forget) or a fallback copy (re-run this
# script after every `bash scripts/build.sh`).
#
# Usage: bash scripts/install-claude-code.sh
#
# Run this from an actual Git Bash terminal (or this repo's own Bash-tool-
# style shell). If your machine also has WSL installed, a bare `bash` typed
# into a plain PowerShell/cmd prompt can resolve to WSL's launcher stub
# (C:\Windows\System32\bash.exe) instead of Git Bash, depending on PATH
# order - confirmed happening here for a subprocess spawned from inside a
# `uv run` process. That stub targets the WSL-side filesystem/$HOME, not
# ~/.claude/, and does not forward arbitrary custom env vars from Windows.
# `bash --version` should print "...-pc-msys" - if it says "-pc-linux-gnu"
# instead, you're in WSL bash; open a real Git Bash window instead.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DIST="$REPO_ROOT/dist/claude-code"

# Normalize a possibly-Windows-style path (backslashes, a bare drive letter)
# to the POSIX form bash's own path builtins expect. Needed because the two
# override env vars below (used by this repo's own tests, and available to
# anyone scripting around this installer) have no guarantee of arriving in
# Git Bash's native form - a `C:\Users\...` string handed in raw would get
# silently mistreated as one big literal path component downstream (`mkdir
# -p`, `dirname`, etc. don't understand backslashes), which is exactly what
# happened the first time this script was exercised from a Python subprocess
# passing a stringified Windows Path.
normalize_path() {
  case "$1" in
    *'\'*|[A-Za-z]:*) command -v cygpath >/dev/null 2>&1 && cygpath -u "$1" || printf '%s' "$1" ;;
    *) printf '%s' "$1" ;;
  esac
}

SKILL_DEST="$(normalize_path "${WICKED_BRAIN_CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}")/wicked-brain"
CMD_DEST="$(normalize_path "${WICKED_BRAIN_CLAUDE_COMMANDS_DIR:-$HOME/.claude/commands}")"

if [[ ! -d "$DIST" ]]; then
  echo "error: $DIST not found - build it first:" >&2
  echo "  bash scripts/build.sh --platform claude-code" >&2
  exit 1
fi

is_windows() {
  [[ "${OS:-}" == "Windows_NT" ]] && return 0
  case "$(uname -s 2>/dev/null)" in MINGW*|MSYS*|CYGWIN*) return 0 ;; esac
  return 1
}

# POSIX path -> Windows backslash path, for cmd.exe's mklink.
winpath() { cygpath -w "$1"; }

# Remove whatever is currently at $1, if anything - safe against a real
# directory, a symlink, or a Windows junction alike (a junction is a reparse
# point; removing it never touches the files it points at - verified before
# this script was written, not assumed).
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
      echo "  [junction]  $dst"
      return 0
    fi
    echo "  [copy]      $dst  (junction failed - no admin rights, cross-volume, or unsupported filesystem)"
    cp -R "$src" "$dst"
    return 1
  else
    ln -sf "$src" "$dst"
    echo "  [symlink]   $dst"
    return 0
  fi
}

# link_file <src> <dst> - same contract as link_dir, for one file.
link_file() {
  local src="$1" dst="$2"
  mkdir -p "$(dirname "$dst")"
  rm -f "$dst" 2>/dev/null || true
  if is_windows; then
    if MSYS_NO_PATHCONV=1 cmd.exe /c mklink /H "$(winpath "$dst")" "$(winpath "$src")" >/dev/null 2>&1; then
      return 0
    fi
    cp "$src" "$dst"
    return 1
  else
    ln -sf "$src" "$dst"
    return 0
  fi
}

echo "Installing Wicked Brain (Claude Code) from $DIST ..."
echo

SKILL_IS_REAL_LINK=1
link_dir "$DIST" "$SKILL_DEST" || SKILL_IS_REAL_LINK=0

mkdir -p "$CMD_DEST"
CMD_TOTAL=0
CMD_FALLBACKS=0
for f in "$DIST"/commands/*.md; do
  [[ -f "$f" ]] || continue
  CMD_TOTAL=$((CMD_TOTAL + 1))
  link_file "$f" "$CMD_DEST/$(basename "$f")" || CMD_FALLBACKS=$((CMD_FALLBACKS + 1))
done
echo "  [commands]  $((CMD_TOTAL - CMD_FALLBACKS))/$CMD_TOTAL linked, $CMD_FALLBACKS copied into $CMD_DEST"

echo
if [[ "$SKILL_IS_REAL_LINK" -eq 1 && "$CMD_FALLBACKS" -eq 0 ]]; then
  echo "Done - real links in place. Future \`bash scripts/build.sh\` runs take effect"
  echo "immediately in every session, no re-run of this script needed."
else
  echo "Done - but at least one item above fell back to a plain copy, which will go"
  echo "stale the next time you rebuild. Re-run this script"
  echo "(bash scripts/install-claude-code.sh) after every \`bash scripts/build.sh\`."
fi

echo
echo "No restart needed for the /brain-* commands - they work in an already-open"
echo "session. Hooks and the MCP server (bundled as a real plugin - see"
echo "$DIST/.claude-plugin/plugin.json) auto-register on your next new session,"
echo "no settings.json editing needed. Open Claude Code's /config panel and fill"
echo "in Wicked Brain's vault location - everything else is optional. See"
echo "$DIST/INSTALL.md for the full field list and how to migrate off an older,"
echo "non-plugin install."
