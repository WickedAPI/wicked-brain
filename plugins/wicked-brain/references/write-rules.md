# Write Rules

How Claude Code and Codex CLI write, link, format, and update notes in the vault.

> **Read `references/ai-first-rules.md` first.** Every note written here must follow the AI-first rule (preamble, rich frontmatter, recency markers, mandatory wikilinks, sources verbatim, confidence levels). The rules below are operational details on top of that foundation.

---

## The Propagation Rule

**Never create a note in isolation.** Every write has ripple effects.

```
New project created
  → Link from today's session note

Entity note updated (new interaction, role change)
  → If the interaction happened today, mention it in today's session note

Decision made
  → Log in the project note's Key Decisions section
  → Log in today's session note

Concept captured or updated
  → Link from today's session note if it came out of this session
```

---

## Internal Linking

Use `[[Note Name]]` syntax. Always link entities, projects, decisions, and concepts referenced in a note. Obsidian resolves `[[Name]]` by filename - avoid hardcoding paths.

If the linked note doesn't exist yet, create a stub (frontmatter + title + one line of context - see Stub Notes below).

---

## Date Formatting

| Context | Format | Example |
|---|---|---|
| Frontmatter `date` / `updated` / `due` | `YYYY-MM-DD` | `2026-03-24` |
| Body text references | Human format | `March 24` or `Mar 24` |
| File names (dated) | `YYYY-MM-DD` | `2026-03-24.md` |

---

## Status Values

Use these consistently:

**Projects:** `active` | `planning` | `completed` | `archived` | `on-hold`
**Concepts:** `active` | `captured` | `archived`
**Decisions (ADR):** `proposed` | `accepted` | `superseded`
**Conflicts:** `open` | `resolved`

---

## Writing Style Calibration

Before writing a new note in a folder you haven't written in before: read 1-2 existing notes in that folder and match heading structure, frontmatter fields present, and section names. Don't introduce new patterns - extend what's there.

---

## Archiving

**Soft archive** (preferred): set `status: archived` in frontmatter. The note stays in its normal folder - normal search and links keep working.

**Retiring a note entirely** (superseded, moved out of scope): move it to `_trash/` rather than deleting. Never hard-delete a vault note - the vault is a permanent record.

---

## Stub Notes

When a link target doesn't exist yet, create a minimal stub:
```yaml
---
date: 2026-03-24
type: entity          # or project, concept, etc.
tags: [entity]
ai-first: true
---

# Note Name

<!-- Created as a stub. Expand when more information is available. -->
```

---

## Section Injection

When updating an existing note (vs creating new): read the full file, find the target section heading, append below the last item in that section (before the next `##`), write the full file back. Never blind-append to the end of a note that has structured sections - it defeats the point of having them.

---

## Concurrent-safe writes (non-negotiable)

Another agent process can be writing this same vault at the same moment - Codex CLI while you're Claude Code, a second session of either, or a background job. Without coordination, two writers can each read the same pre-edit content and the second write silently overwrites the first, with both reporting success and the first edit simply gone (this happened for real - found 2026-09-10).

The MCP server's own write tools (`brain_update_note`, `brain_save_note`, `brain_replace_text`) already guard against this internally. **Your own native Read/Write/edit files does not** - nothing stops it unless you wrap it yourself. Before reading a note you're about to write (or creating a new one), acquire the shared vault lock; release it the moment the write completes:

```bash
uv run --directory "SKILL_ROOT" python scripts/vault_lock.py acquire --path "<vault>"
# ...your Read (if updating), then Write/Edit, for exactly ONE note...
uv run --directory "SKILL_ROOT" python scripts/vault_lock.py release --path "<vault>"
```

One note, one acquire/release pair - acquire immediately before, release immediately after. Never hold it across multiple notes, a subagent's whole turn, or any pause for thinking/review: `acquire` already waits up to 10s for another writer and self-heals a crashed holder's lock after 30s, so holding it longer than one write just serializes other writers (including your own parallel subagents, if the command spawned any) for no reason.

If `acquire` prints an error and exits nonzero, the vault is genuinely busy - wait a moment and retry. Never write anyway; that is exactly the race this exists to prevent.

---

## Sentinel-safe regeneration

For any note a command generates AND a human might hand-edit, use sentinel markers so a refresh never destroys human edits:

```
<!-- @generated:start -->
...machine-generated content - safe to overwrite on the next run...
<!-- @generated:end -->

<!-- @user:start -->
...human notes - NEVER overwritten by a refresh...
<!-- @user:end -->
```

On refresh: replace only the content between `@generated:start`/`@generated:end`; never touch `@user` blocks or anything outside the markers. On the first run (no markers yet), wrap the generated content in `@generated` markers so future refreshes are safe.

---

## Batch writes

A run of many `/brain-save` or `/brain-capture` calls in one sitting has no unit-of-work boundary of its own - every note lands live as it's written. If you want to review a batch before it's "real" (or abandon it cleanly), branch the vault:

```bash
cd "$WICKED_BRAIN_VAULT_PATH"
git checkout -b batch-2026-08-27
# ... run the writes ...
git status && git diff --stat            # review what changed
git checkout main && git merge batch-2026-08-27   # accept
# or: git checkout main && git branch -D batch-2026-08-27   # abandon, nothing reaches main
```

(This is the same git-backed-vault mechanism the version-history phase of this project builds on - see the project plan. Even without that phase built, plain git already gives you this rollback point today if the vault is a git repo.)

---

## Search Before Write

Before creating any note:
```
search(query="keyword from title")
```

If a match is found: same concept → update the existing note, don't create new. Different concept, similar name → proceed with creation but choose a distinct name.

Duplicate detection matters most for entities (same person, different name formats) and projects (same project, different working title).

**Never claim absence from memory.** Before writing "no note exists," search exhaustively - by every plausible name and alias, listing and grepping rather than relying on one query. False absence is the most common failure mode. When unsure, over-include and label the uncertainty. See the anti-fabrication and search-completeness hard rules in `ai-first-rules.md`.

---

## Fork note

Forked from [obsidian-second-brain](https://github.com/eugeniughelbur/obsidian-second-brain)'s `references/write-rules.md` (MIT), trimmed for the fixed vault schema (no kanban boards, no folder-map indirection). See `NOTICE.md` at the repo root.
