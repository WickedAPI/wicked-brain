# Notice

This repository is a fork and derivative work of
[**obsidian-second-brain**](https://github.com/eugeniughelbur/obsidian-second-brain)
by Eugeniu Ghelbur, licensed under the MIT License (see `LICENSE`, copyright
notice preserved as required).

## What's carried over largely as-is

- `scripts/note_io.py` - atomic byte-exact vault I/O
- `scripts/merge_notes.py`, `scripts/export_okf.py` - mechanical note merge/dedup
- `scripts/vault_health.py`, `scripts/freshness_lint.py`, `scripts/link_graph.py` - health, freshness, and typed-edge linting
- `scripts/semantic_search.py` (originally `scripts/eval/semantic_search.py`) - local Ollama-backed semantic search
- `integrations/mcp-server/{server.py,vault_ops.py}` (originally `integrations/obsidian-mcp-server/`) - the MCP server and vault operations layer
- `hooks/validate-ai-first.sh`, `hooks/load_vault_context.py`, `hooks/recall.py` (originally `hooks/obsidian-recall.py`), `hooks/bg-agent.sh` (originally `hooks/obsidian-bg-agent.sh`) - write validation, session context injection, bounded recall, background propagation
- `adapters/lib.sh`, `adapters/claude-code/`, `adapters/codex-cli/`, `scripts/build.sh` - the platform build pipeline
- `references/ai-first-rules.md`, `references/write-rules.md`, `references/vault-schema.md`, `references/freshness-policy.md` - the core vault-write specification (trimmed/adapted for a fixed schema; `freshness-policy.md` unchanged)

All of the above had environment variable names (`OBSIDIAN_*` → `ENGRAM_*` → `WICKED_BRAIN_*`), the
product name, install paths, and doc cross-references renamed/rebranded for
this fork; most also had their logic trimmed to remove features this fork
doesn't ship (calendar, kanban boards, the 8-source research toolkit, 6 of 8
platform adapters, multiple note types and thinking-tool commands unrelated to
memory).

## What's new in this fork

- `scripts/auto_merge_exact_duplicates.py` - the bounded auto-merge upgrade (only near-byte-identical pairs, similarity >= 0.97)
- The auto-reindex upgrade in `integrations/mcp-server/vault_ops.py` (`_handle_stale_index`, `_auto_reindex_inline`, `_auto_reindex_background`) - upstream only warns on a stale semantic index; this fork closes small gaps inline and large ones via a detached background rebuild
- The fixed, personalized vault schema (`projects/`, `entities/`, `decisions/`, `sessions/`, `concepts/`) replacing upstream's dual wiki-style/Obsidian-style layout and folder-map indirection
- `commands/brain-*.md` - the trimmed 9-command set, rewritten for the fixed schema
- `dashboard/` - the local search/graph/health/version-history dashboard (entirely new, no upstream equivalent)
- `scripts/vault_git.py` (Phase 2) - version history. Upstream has no equivalent - a vault opts in per-repo (`.git/` present) via `/brain-init`, and every write from any of the three write paths (the agent's native tool via the `hooks/validate-ai-first.sh` Claude Code hook, the MCP server's write functions, or a script like `merge_notes.py`) lands as a commit
- `scripts/vault_crypto.py`, `scripts/vault_sync.py`, `sync_server/` (Phase 3) - encrypted cross-device sync. Upstream has no equivalent - client-side encryption (passphrase-derived, via the `cryptography` package), a three-way conflict-aware sync client, and a small FastAPI + SQLAlchemy sync API deployed on Railway that stores ciphertext only
- `NOTICE.md` (this file)

## What's dropped

Research toolkit (8 external API sources), calendar integration, kanban boards, Telegram journal integration, 6 of 8 platform adapters (gemini-cli, opencode, hermes, pi, grok-bot, agent-skills), and roughly 40 of the upstream project's 47 commands that don't serve a coding-assistant memory use case.

Per the MIT License, this notice and the original copyright must be preserved
in copies or substantial portions of the carried-over software.

## Name history

This project is **Wicked Brain**. It was first called "Agent Memory", renamed "Engram" on 2026-09-08, and renamed
"Wicked Brain" on 2026-10-21 because another company already uses the name Engram for an AI memory product.
Commands are `/brain-*`, MCP tools are `brain_*`, environment variables are `WICKED_BRAIN_*`, and the plugin and
package name is `wicked-brain`. Older notes, logs and commit messages may still say "Engram"; they describe the same project.
