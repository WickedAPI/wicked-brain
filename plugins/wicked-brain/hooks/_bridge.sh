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
