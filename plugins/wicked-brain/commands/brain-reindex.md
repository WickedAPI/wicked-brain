---
description: Refresh the vault's semantic search index and report coverage before and after
category: meta
triggers_en: ["reindex memory", "rebuild semantic index", "refresh semantic search"]
---

Use the wicked-brain skill. Execute `/brain-reindex`:

Small gaps close automatically during normal `/brain-find` calls (the fork's auto-reindex upgrade - see `integrations/mcp-server/vault_ops.py`'s `_handle_stale_index`). Run this command for a full rebuild, to check coverage explicitly, or if Ollama was down when an automatic reindex would have fired.

1. Read `_CLAUDE.md` (or `AGENTS.md`) first to find the vault path. The skill root was given at session start as **Skill root**; substitute it for `SKILL_ROOT` below.
2. Measure coverage before changing the index:
   ```bash
   uv run --directory "SKILL_ROOT" python -c 'import json, sys; from pathlib import Path; sys.path.insert(0, str(Path(sys.argv[1]) / "integrations" / "mcp-server")); from vault_ops import index_coverage; print(json.dumps(index_coverage(Path(sys.argv[2]).expanduser().resolve())))' "SKILL_ROOT" "VAULT_PATH"
   ```
   Report `indexed`, `scanned`, `missing`, `pct_missing`. If `index` is false, say no readable semantic index exists yet rather than presenting `0/0` as coverage.
3. Run the incremental build: `uv run --directory "SKILL_ROOT" python scripts/semantic_search.py --path "VAULT_PATH" --build`. If it exits nonzero, stop and show the actionable error rather than claiming success. The common failure is Ollama not running or the embedding model not pulled (`ollama pull bge-m3`).
4. Re-run the coverage check from step 2.
5. Report coverage before/after, the builder's `new` count, and any degraded/dropped/capped paths from its stderr output (those notes are not fully searchable by meaning even after this run - capped means a very long note's middle section was skipped, though its ending is always embedded).

This command updates only the semantic index file; it never modifies markdown notes.

---

**Anti-fabrication:** Report coverage and build counts exactly as the tools emit them. Never infer success from an unchanged file or a zero exit status when the builder itself reports dropped notes.
