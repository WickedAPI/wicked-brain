---
description: Fork a project note - duplicate it under a new name, linked back to the original, so a derivative project starts with real context instead of a blank page
category: vault
triggers_en: ["fork this project", "clone this project in memory", "start a project based on"]
---

Use the wicked-brain skill. Execute `/brain-fork $ARGUMENTS`:

This forks the project's **memory** - its note in `projects/`. It does not touch code, does not run `git clone`, and does not create or move any repo directory. If the user also wants the actual code cloned, that is a separate, ordinary `git clone`/`cp -R` they do themselves (or ask you to run as a normal shell command) - this command only makes sure the new project's note starts with the parent's real context instead of a blank page, and that the two stay linked in the graph.

1. Read `_CLAUDE.md` (or `AGENTS.md`) first to find the vault path.
2. Resolve the **source** project: if `$ARGUMENTS` names one, search `projects/` for it - by exact name first, then a fuzzy/partial match. If nothing matches, list the closest candidates and ask rather than assuming; never fabricate a source note that doesn't exist (the false-absence rule cuts both ways here - don't claim a match that isn't real either).
3. Ask for (if not already given): the **new project's name**, and optionally its **repo path** if the user already knows where the forked code will live (fine to leave `TBD` - this command doesn't create that directory).
4. Search `projects/` for the new name first - if a note with that name already exists, stop and ask instead of overwriting it silently (same search-before-write rule as everything else).
5. Read the source note in full.
6. Compose the new note at `projects/<new name>.md`:
   - Same frontmatter shape as the source (`references/ai-first-rules.md`'s `type: project` schema), with `date`/`updated` set to today, `status: planning` (a fork is a new direction, not automatically in lockstep with the parent's current status - the user can change this later), `repo:` set to what was given or `TBD`.
   - `relations: { forked_from: ["[[projects/<source>]]"] }` (a documented typed edge - see `references/ai-first-rules.md` Rule 6).
   - `## For future agent` preamble stating plainly it was forked from the source project on today's date, and that Overview below was seeded from the parent and needs review for what's actually different.
   - An **Overview** section carried forward from the source (it's a legitimate, real starting point - not fabrication, since it's genuinely where this project started).
   - Empty **Recent Activity** and **Key Decisions** sections - do NOT carry the parent's history forward into the fork's own sections; that history belongs to the parent, and copying it would misrepresent it as the fork's own.
7. Update the **source** note: add the inverse edge `relations: { forked_by: [...] }`, appending to (not replacing) any existing `relations:` block or `forked_by` list already there.
8. Append one line to today's session note: `**HH:MM** - fork | <source> -> <new name>`.
9. Report back: the new note's path, the source it was forked from, and a reminder that `repo:` is `TBD` if the user hasn't cloned the actual code yet.

**Concurrent-safe writes (non-negotiable):** wrap each of the two note writes (new note, source note update) separately with the shared vault lock - see `references/write-rules.md`. One note, one acquire/release pair.

---

**AI-first rule:** The new note follows `references/ai-first-rules.md` in full - preamble, rich frontmatter, `ai-first: true`. It is not the redirect exception; a fork is a real, independent note from the moment it's created, not a pointer.

**Anti-fabrication:** Never invent a `repo:` path, a status, or history the user didn't state. Leave `repo: TBD` rather than guessing where forked code will live.
