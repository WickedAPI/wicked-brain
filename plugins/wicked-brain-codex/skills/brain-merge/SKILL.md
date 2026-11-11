---
name: brain-merge
description: "Merge two near-duplicate notes found by /brain-health into one - dry run by default, redirects the retired note rather than deleting it Triggers: merge these notes, merge duplicates, combine these two notes. Use only when the user explicitly asks for it."
---

> **Plugin root.** This skill ships inside the Wicked Brain plugin. `<plugin-root>` means the folder two levels above this `SKILL.md` (the folder that contains `skills/`, `references/` and `scripts/`). Resolve every `<plugin-root>/...` path below from this file's own location. The vault itself is wherever `WICKED_BRAIN_VAULT_PATH` (or `~/.config/wicked-brain/.env`) points; if neither is set, run `$brain-setup` first.


Use the wicked-brain skill. Execute `$brain-merge <arguments the user gave>`:

`$brain-health` finds duplicate pairs and stops - it is read-only by contract. This command does the merge: `scripts/merge_notes.py` (<plugin-root>'s absolute path is the plugin root folder (see the note at the top of this skill); substitute it for `<plugin-root>` below) handles the mechanical half - frontmatter union, alias folding, and replacing the retired note with a `type: redirect` stub - and you compose the merged body, since deciding what actually contradicts between two notes is judgment, not mechanics.

**Nothing is ever deleted.** The surviving note keeps its path; the retired note's file stays in the vault, its content replaced by a short pointer (`<plugin-root>/references/write-rules.md`: never delete vault notes).

1. Read `_CLAUDE.md` (or `AGENTS.md`) first to find the vault path.
2. Resolve which two notes to merge. If `<arguments the user gave>` gives two paths, the first is **canonical** (survives) and the second is **retired** (becomes a redirect). If `<arguments the user gave>` is `--from-health`, run `uv run --directory "<plugin-root>" scripts/merge_notes.py --path <vault> --from-health` with no `--canonical` to list candidate pairs, then ask the user which to merge.
3. Read both notes in full.
4. Compose the merged body per `<plugin-root>/references/ai-first-rules.md`: one `## For future agent` preamble naming both source notes, keep both notes' provenance, list any genuine disagreement explicitly rather than silently picking a winner, carry forward every still-relevant `[[wikilink]]` from both. Write it to a scratch file - the same file is used for the dry run and the `--apply` run so the preview and the actual write are guaranteed identical.
5. Preview (dry run): `uv run --directory "<plugin-root>" scripts/merge_notes.py --path <vault> --canonical "<canonical rel path>" --retire "<retired rel path>" --merged-body-file <scratch file>`. Show the full output to the user - do not summarize it away.
6. Ask for explicit confirmation before applying.
7. Apply, once confirmed, by re-running the exact same command with `--apply` appended. If the vault is a git repo, `merge_notes.py` commits both files in one commit itself (Phase 2, version history) - no separate commit step needed here, on either platform.
8. Report back: which note survived, which became a redirect, frontmatter conflicts and which value won, any alias added, and any contradiction the merged body documented rather than resolved.
9. Append one line to today's session note: `**HH:MM** - merge | <retired> -> <canonical>`. This is a separate write from step 7 (which already locks internally via `merge_notes.py`) - wrap this one yourself per `<plugin-root>/references/write-rules.md`'s "Concurrent-safe writes" section.

If `merge_notes.py` refuses to run (malformed frontmatter, an ambiguous `--from-health` group, a path outside the vault), relay its error rather than retrying blindly or picking a canonical note for the user.

---

**AI-first rule:** The retired note becomes `type: redirect` (the documented exception in `<plugin-root>/references/ai-first-rules.md`) - it carries no preamble, its only job is to point at the canonical note. Every other write follows the full rule.

**Anti-fabrication:** Do not resolve a genuine contradiction between the two notes by picking one side and dropping the other - list it instead.
