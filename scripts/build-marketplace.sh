#!/usr/bin/env bash
# =============================================================================
# scripts/build-marketplace.sh - Assemble the plugin-marketplace tree
# =============================================================================
# Usage:
#   bash scripts/build-marketplace.sh [out_dir]      # default: dist/marketplace
#
# Produces a folder that, committed as the root of a git repo, is both a Claude Code
# and a Codex plugin marketplace:
#
#   <out>/.claude-plugin/marketplace.json     Claude Code marketplace catalog
#   <out>/.agents/plugins/marketplace.json    Codex marketplace catalog
#   <out>/plugins/wicked-brain/               the Claude Code plugin (dist/claude-code)
#   <out>/plugins/wicked-brain-codex/         the Codex plugin (dist/codex-plugin)
#
# Users then install with:
#   claude plugin marketplace add <owner>/<repo>
#   claude plugin install wicked-brain@wicked-brain
#   codex plugin marketplace add <owner>/<repo>      (then install from the Codex app)
#
# Nothing here publishes anything; it only writes files under <out>.
# =============================================================================
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=scripts/lib.sh
source "$SCRIPT_DIR/lib.sh"

OUT="${1:-$REPO_ROOT/dist/marketplace}"
MARKETPLACE_NAME="${WICKED_BRAIN_MARKETPLACE_NAME:-wicked-brain}"
REPO_URL="${WICKED_BRAIN_REPO_URL:-https://github.com/choaticpixels/wicked-brain}"
OWNER_NAME="${WICKED_BRAIN_OWNER_NAME:-Wicked Labs}"

VERSION="$(sed -n 's/^version *= *"\([^"]*\)".*/\1/p' "$REPO_ROOT/pyproject.toml" | head -n1)"
[[ -n "$VERSION" ]] || die "could not read version from pyproject.toml"

info "Building the Claude Code and Codex plugins (v$VERSION)"
WICKED_BRAIN_REPO_URL="$REPO_URL" bash "$SCRIPT_DIR/build.sh" --platform claude-code >/dev/null
WICKED_BRAIN_REPO_URL="$REPO_URL" bash "$SCRIPT_DIR/build.sh" --platform codex-plugin >/dev/null

# Refuse to wipe anything that is not an earlier marketplace build.
if [[ -e "$OUT" && ! -f "$OUT/.claude-plugin/marketplace.json" ]]; then
  [[ -z "$(ls -A "$OUT" 2>/dev/null)" ]] || die "$OUT exists and is not a marketplace build; refusing to overwrite"
fi
rm -rf "$OUT"
mkdir -p "$OUT/.claude-plugin" "$OUT/.agents/plugins" "$OUT/plugins"

# The marketplace copy omits INSTALL.md: it documents the developer junction install.
cp -R "$REPO_ROOT/dist/claude-code" "$OUT/plugins/wicked-brain"
rm -f "$OUT/plugins/wicked-brain/INSTALL.md"
cp -R "$REPO_ROOT/dist/codex-plugin" "$OUT/plugins/wicked-brain-codex"

cat > "$OUT/.claude-plugin/marketplace.json" <<EOF
{
  "name": "$MARKETPLACE_NAME",
  "owner": { "name": "$OWNER_NAME", "url": "$REPO_URL" },
  "metadata": {
    "description": "Wicked Brain: a fast, plain-markdown memory vault that Claude Code, Codex CLI and Google Antigravity share.",
    "version": "$VERSION"
  },
  "plugins": [
    {
      "name": "wicked-brain",
      "source": "./plugins/wicked-brain",
      "description": "Plain-markdown memory vault: search, save and maintain projects, decisions, sessions and concepts, with proactive recall, atomic writes, duplicate detection and optional encrypted cross-device sync.",
      "version": "$VERSION",
      "category": "productivity",
      "tags": ["memory", "vault", "notes", "second-brain", "knowledge-base"],
      "homepage": "$REPO_URL"
    }
  ]
}
EOF

# Codex catalog. Marketplace and plugin names match the Claude side so one name is easy to remember.
cat > "$OUT/.agents/plugins/marketplace.json" <<EOF
{
  "name": "$MARKETPLACE_NAME",
  "interface": { "displayName": "Wicked Brain" },
  "plugins": [
    {
      "name": "wicked-brain",
      "source": { "source": "local", "path": "./plugins/wicked-brain-codex" },
      "policy": { "installation": "AVAILABLE", "authentication": "ON_INSTALL" },
      "category": "Productivity"
    }
  ]
}
EOF

# Shell scripts and JSON must keep LF endings. Without this, a Windows checkout with
# core.autocrlf=true rewrites hooks/_bridge.sh to CRLF and every hook dies with a
# ": command not found". Claude Code and Codex both install by cloning this repo.
cat > "$OUT/.gitattributes" <<'GA'
* text=auto eol=lf
*.sh text eol=lf
*.py text eol=lf
*.json text eol=lf
*.md text eol=lf
*.png binary
*.jpg binary
GA

# Never ship bytecode or local state.
find "$OUT" \( -name "__pycache__" -o -name ".pytest_cache" \) -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "$OUT" -name "*.pyc" -delete 2>/dev/null || true

success "marketplace → $OUT"
