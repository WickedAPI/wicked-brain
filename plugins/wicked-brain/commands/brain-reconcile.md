---
description: Find and resolve contradictions in the vault - the memory maintains its own truth
category: thinking
triggers_en: ["find contradictions", "reconcile my memory", "fix conflicting facts"]
---

Use the wicked-brain skill. Execute `/brain-reconcile $ARGUMENTS`:

The optional argument is a topic or entity to focus on. If not provided, scan the whole vault.

1. Read `_CLAUDE.md` (or `AGENTS.md`) first if it exists. Read `index.md` for the full landscape.
2. Spawn parallel subagents to find contradictions:
   - **Claims agent**: scan `concepts/` and `projects/` for factual claims; find pairs that contradict each other.
   - **Entity agent**: scan `entities/` for outdated roles/status that conflict with a newer `timeline:` entry or a newer source.
   - **Decisions agent**: scan `decisions/` and project Key Decisions sections for a decision that was reversed or superseded but never marked as such.
3. For each contradiction, evaluate: which claim is newer, which source is more authoritative, and whether this is a genuine contradiction or just someone's understanding evolving (evolution is not a contradiction).
4. Resolve each:
   - **Clear winner**: rewrite the outdated note with current info and add a short `## History` note on what changed and why, with dates.
   - **Genuinely ambiguous**: create a note in `decisions/` (`type: conflict`, `status: open`) documenting both sides and the evidence for each, for the user to decide.
   - **Evolution**: update the entity/concept note's `timeline:` to reflect the current state (bi-temporal - append, don't overwrite) and keep the historical context.
5. Rebuild affected sections of `index.md`. Append one line to today's session note: `**HH:MM** - reconcile | X found, Y auto-resolved, Z flagged`.

Every write in steps 4-5 (each rewritten note, each new conflict note, index.md, the session note) is its own critical section - wrap each individually with the shared vault lock per `references/write-rules.md`'s "Concurrent-safe writes" section.
6. **Version history (if enabled):** if `.git/` exists at the vault root, `git -C <vault> add -A && git -C <vault> commit -q -m "reconcile: X found, Y auto-resolved"`. Skip silently if there is no `.git/` directory. (Claude Code users get this automatically via `hooks/validate-ai-first.sh` - this step is the Codex CLI / no-hook-system path.)
7. Report back: auto-resolved (old claim -> new claim and why), flagged for the user (genuinely ambiguous), and stale notes updated.

The vault should never contain two notes that disagree without knowing they disagree.

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md`.

**Anti-fabrication:** Search exhaustively before claiming a contradiction is resolved - and never invent which source is "newer" or "more authoritative" when the note doesn't actually say.
