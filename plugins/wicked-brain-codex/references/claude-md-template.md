# _CLAUDE.md template (vault-facing operating manual)

`$brain-init` fills this in with real values and writes it as `_CLAUDE.md` at the
vault root (Claude Code reads it) and as `AGENTS.md` (Codex CLI reads it - same
content, Claude-specific tool names neutralized). Placeholders in `{{...}}` are
replaced; everything else is copied verbatim.

---

```markdown
# {{VAULT_NAME}} - operating manual

This is an **wicked-brain** vault: a plain-markdown memory that Claude Code and
Codex CLI both read and write through the same scripts - and, where the
`wicked-brain` MCP server is registered, the same ranked-search tool - so what one
of them learns the other can use.

## 0. The AI-first rule (non-negotiable)

Every note you write here must follow `<plugin-root>/references/ai-first-rules.md`: a
`## For future agent` preamble, rich frontmatter (`type`, `date`, `tags`,
`ai-first: true`), recency markers on external claims, mandatory
`[[wikilinks]]`, sources verbatim, confidence levels where applicable. This
vault is for future-agent retrieval, not human reading - don't "clean it up"
into prose a human would prefer.

## 1. Concurrent-safe writes (non-negotiable)

Another agent process can be writing this same vault right now - Codex CLI
while you're Claude Code, a second session of either. The MCP server's own
write tools (`brain_update_note`, `brain_save_note`, `brain_replace_text`)
already guard against a lost update internally. **Using your own native
Read/Write/edit files to write a note does not** - wrap it yourself, or a
concurrent writer's edit (or yours) can be silently overwritten with no
error. Before reading a note you're about to write (or creating a new one),
and releasing the instant that one write completes:

```bash
uv run --directory "<plugin-root>" python scripts/vault_lock.py acquire --path "<vault>"
# ...your Read (if updating), then Write/Edit, for exactly ONE note...
uv run --directory "<plugin-root>" python scripts/vault_lock.py release --path "<vault>"
```

One note, one acquire/release pair - see `<plugin-root>/references/write-rules.md` for the
full rule (why, and what NOT to hold the lock across).

## 2. Folder map (fixed - do not invent new top-level folders)

| Folder | Holds |
|---|---|
| `projects/` | One note per project: status, timeline, key decisions |
| `entities/` | People, orgs, tools - bi-temporal `timeline:` facts, never overwritten |
| `decisions/` | ADRs and open conflicts (`type: conflict`) |
| `sessions/` | One note per day: `YYYY-MM-DD.md`, what was worked on |
| `concepts/` | Reusable knowledge, patterns, ideas |
| `_trash/` | Soft-deleted notes only - never hard-delete a note |

## 3. Commands

`$brain-save` (proactive - save this conversation), `$brain-find` (search),
`$brain-capture` (quick capture to concepts/), `$brain-health` (audit),
`$brain-merge` (resolve a duplicate pair found by health), `$brain-fork`
(fork a project note under a new name, linked back to the original),
`$brain-reindex` (rebuild the semantic index), `$brain-reconcile` (find and
resolve contradictions).

If these aren't recognized at all (Claude Code: `/brain-*` not listed; Codex
CLI: `$brain-*` or `/skills` empty), the platform-level install is missing
or incomplete - see `dist/claude-code/INSTALL.md` or `dist/codex-cli/INSTALL.md`
in the wicked-brain repo. This file being present is not proof that install
happened; it's a separate, one-time step.

## 4. Search before writing

Never create a note without searching first - see `<plugin-root>/references/write-rules.md`.
Duplicate notes are the exact rot this system exists to prevent.

## 5. Freshness

Every stored fact is timeless, dated, or a pointer - see
`<plugin-root>/references/freshness-policy.md`. An undated present-tense claim about
something that changes ("the project has 3 open tasks") is the one illegal
form: it reads as true forever and becomes a lie the moment it's stale.

## 6. Critical facts

`CRITICAL_FACTS.md` is small (~100-150 tokens) and always loaded at session
start. Keep it to things worth paying that budget every session: timezone,
current focus, anything that would be actively wrong to forget.
```
