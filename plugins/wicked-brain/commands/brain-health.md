---
description: Run a memory health check - grouped by severity, detects duplicates, contradictions, stale claims, and structural issues
category: meta
triggers_en: ["memory health", "check the vault", "audit my memory", "memory diagnostics"]
---

Use the wicked-brain skill. Execute `/brain-health`:

1. Read `_CLAUDE.md` (or `AGENTS.md`) first to find the vault path.
2. Run the health scan from the skill root (its absolute path was given at session start as **Skill root**; substitute it for `SKILL_ROOT`): `uv run --directory "SKILL_ROOT" scripts/vault_health.py --path ~/path/to/vault --json` (replace with the real vault path).
3. Also run the freshness lint - `uv run --directory "SKILL_ROOT" scripts/freshness_lint.py --path <vault> --json` - which enforces `references/freshness-policy.md`: every stored fact must be timeless, dated, or a pointer. FRESH-1 errors are present-tense claims about fast facts (counts, statuses, balances) with no `(as of ...)` stamp - the sentences that silently become lies.
4. Also run the typed-edge lint - `uv run --directory "SKILL_ROOT" scripts/link_graph.py --path <vault> --lint` - which validates any `relations:` typed edges (see `references/ai-first-rules.md` Rule 6 § Typed edges). Zero findings on a vault that uses no `relations:` blocks is normal, not an error.
5. Also check for near-identical duplicates the fork's auto-merge would act on: `uv run --directory "SKILL_ROOT" scripts/auto_merge_exact_duplicates.py --path <vault> --json` (dry run - this never writes on its own). These are notes similar enough (>=97%) that the background agent, if enabled, would merge them automatically; report them, but don't re-litigate the ones already merged.
6. Parse the JSON outputs and group findings by severity:
   - **Critical**: unfilled template syntax, contradictions between notes, typed-edge contradiction cycles, code-fence-wrapped notes (frontmatter trapped in a leading fence - fix by unwrapping the fence, never by adding a second frontmatter block).
   - **Warning**: near-duplicates below the auto-merge threshold (offer `/brain-merge` for these), missing required frontmatter fields, freshness violations (undated fast facts, aged `as of` stamps), typed-edge problems (unknown type, dangling target, self-edge).
   - **Info**: orphaned notes, empty folders, missing inverse typed edges.
7. For safe, mechanical fixes (missing frontmatter fields, unwrapping a code-fence-wrapped note), offer to fix automatically. For anything requiring judgment (merging, resolving a contradiction, archiving), list it and ask for explicit confirmation before touching anything - never auto-apply.
8. Append one line to today's session note: `**HH:MM** - health | X critical, Y warnings, Z info`.

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md`.

**Anti-fabrication:** Report findings exactly as the tools emit them - never round a warning up to critical or down to info, and never claim a clean scan when a tool call failed.
