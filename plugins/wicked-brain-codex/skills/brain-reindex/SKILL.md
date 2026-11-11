---
name: brain-reindex
description: "Refresh the vault's semantic search index and report coverage before and after Triggers: reindex memory, rebuild semantic index, refresh semantic search. Use only when the user explicitly asks for it."
---

> **Plugin root.** This skill ships inside the Wicked Brain plugin. `<plugin-root>` means the folder two levels above this `SKILL.md` (the folder that contains `skills/`, `references/` and `scripts/`). Resolve every `<plugin-root>/...` path below from this file's own location. The vault itself is wherever `WICKED_BRAIN_VAULT_PATH` (or `~/.config/wicked-brain/.env`) points; if neither is set, run `$brain-setup` first.


Use the wicked-brain skill. Execute `$brain-reindex`:

Small gaps close automatically during normal `$brain-find` calls (the fork's auto-reindex upgrade - see `integrations/mcp-server/vault_ops.py`'s `_handle_stale_index`). Run this command for a full rebuild, to check coverage explicitly, or if Ollama was down when an automatic reindex would have fired.

1. Read `_CLAUDE.md` (or `AGENTS.md`) first to find the vault path. The skill root is the plugin root folder (see the note at the top of this skill); substitute it for `<plugin-root>` below.
2. Measure coverage before changing the index:
   ```bash
   uv run --directory "<plugin-root>" python -c 'import json, sys; from pathlib import Path; sys.path.insert(0, str(Path(sys.argv[1]) / "integrations" / "mcp-server")); from vault_ops import index_coverage; print(json.dumps(index_coverage(Path(sys.argv[2]).expanduser().resolve())))' "<plugin-root>" "VAULT_PATH"
   ```
   Report `indexed`, `scanned`, `missing`, `pct_missing`. If `index` is false, say no readable semantic index exists yet rather than presenting `0/0` as coverage.
3. Run the incremental build: `uv run --directory "<plugin-root>" python scripts/semantic_search.py --path "VAULT_PATH" --build`. If it exits nonzero, stop and show the actionable error rather than claiming success. The common failure is Ollama not running or the embedding model not pulled (`ollama pull bge-m3`).
4. Re-run the coverage check from step 2.
5. Report coverage before/after, the builder's `new` count, and any degraded/dropped/capped paths from its stderr output (those notes are not fully searchable by meaning even after this run - capped means a very long note's middle section was skipped, though its ending is always embedded).

This command updates only the semantic index file; it never modifies markdown notes.

---

**Anti-fabrication:** Report coverage and build counts exactly as the tools emit them. Never infer success from an unchanged file or a zero exit status when the builder itself reports dropped notes.
