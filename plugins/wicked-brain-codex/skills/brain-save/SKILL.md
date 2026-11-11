---
name: brain-save
description: "Save everything worth remembering from this conversation to the memory vault Triggers: save this, save the conversation, save to memory, remember this. Use proactively: trigger this whenever the conversation produces something worth capturing, without waiting to be asked."
---

> **Plugin root.** This skill ships inside the Wicked Brain plugin. `<plugin-root>` means the folder two levels above this `SKILL.md` (the folder that contains `skills/`, `references/` and `scripts/`). Resolve every `<plugin-root>/...` path below from this file's own location. The vault itself is wherever `WICKED_BRAIN_VAULT_PATH` (or `~/.config/wicked-brain/.env`) points; if neither is set, run `$brain-setup` first.


Use the wicked-brain skill. Execute `$brain-save`:

1. Read `_CLAUDE.md` (or `AGENTS.md`) first if it exists in the vault root.
2. Scan the entire conversation and identify everything vault-worthy: decisions made, projects touched, people/tools/orgs mentioned (entities), reusable knowledge or patterns learned (concepts), and a session summary of what was actually done.
3. Group items by type and, for anything nontrivial, spawn parallel subagents so all types are handled simultaneously:
   - **Entities agent**: search `entities/` for each person/org/tool mentioned; update the existing note's `timeline:` (bi-temporal - never overwrite `role`/`status`, append a new interval per `<plugin-root>/references/vault-schema.md`) or create a new entity note.
   - **Projects agent**: search `projects/` for each project touched; update status, recent activity, and key decisions, or create a new project note.
   - **Decisions agent**: for any decision made in this conversation, append it to the relevant project note's Key Decisions section, or create a standalone note in `decisions/` (ADR) for a decision that doesn't belong to one project.
   - **Concepts agent**: search `concepts/` for related existing notes on anything learned or figured out; append or create.
4. Always write (or update) today's session note at `sessions/YYYY-MM-DD.md`: what was worked on, what was saved and where, and links to everything touched this session.
5. **Version history (if enabled):** if a `.git/` directory exists at the vault root, stage and commit everything you just wrote: `git -C <vault> add -A && git -C <vault> commit -q -m "save: <one-line summary>"`. This is the Codex CLI / no-hook-system path to Phase 2's version history - on Claude Code the same thing already happens automatically per write via `hooks/validate-ai-first.sh`, so this step is a no-op there in practice (nothing left to commit). If there is no `.git/` directory, skip this step silently - version history is opt-in per vault via `$brain-init`.
6. Report back: a clean list of what was saved and where.

Search before creating anything - duplicate notes are the exact rot this system exists to prevent. Never create an orphaned note; link everything from the session note.

**Concurrent-safe writes (non-negotiable):** wrap every individual note write (yours and each subagent's) with the shared vault lock - see `<plugin-root>/references/write-rules.md`'s "Concurrent-safe writes" section for the exact commands. One note, one acquire/release pair; never hold it across more than one write.

---

**AI-first rule:** Every note created or updated by this command MUST follow `<plugin-root>/references/ai-first-rules.md` - `## For future agent` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, confidence levels where applicable. If that path does not resolve from your working directory, search upward for it; if you still cannot read it, say so before writing rather than producing a note that silently skips the rule. The vault is for future agent retrieval - not human reading.

**Anti-fabrication:** Search exhaustively before claiming any note, person, or file is absent - false absence is the most common failure mode - and never invent facts, entities, or dates (mark unknowns as `TBD`). See the anti-fabrication and search-completeness hard rules in `<plugin-root>/references/ai-first-rules.md`.
