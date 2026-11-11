# Sample Vault - operating manual

This is an **wicked-brain** vault: a plain-markdown memory that Claude Code and
Codex CLI both read and write through the same MCP server and scripts, so what
one of them learns the other can use.

## 0. The AI-first rule (non-negotiable)

Every note you write here must follow `references/ai-first-rules.md`: a
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
Read/Write/Edit tool to write a note does not** - wrap it yourself, or a
concurrent writer's edit (or yours) can be silently overwritten with no
error. Before reading a note you're about to write (or creating a new one),
and releasing the instant that one write completes:

```bash
uv run --directory "SKILL_ROOT" python scripts/vault_lock.py acquire --path "<vault>"
# ...your Read (if updating), then Write/Edit, for exactly ONE note...
uv run --directory "SKILL_ROOT" python scripts/vault_lock.py release --path "<vault>"
```

One note, one acquire/release pair - see `references/write-rules.md` for the
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

`/brain-save` (proactive - save this conversation), `/brain-find` (search),
`/brain-capture` (quick capture to concepts/), `/brain-health` (audit),
`/brain-merge` (resolve a duplicate pair found by health), `/brain-fork`
(fork a project note under a new name, linked back to the original),
`/brain-reindex` (rebuild the semantic index), `/brain-reconcile` (find and
resolve contradictions).

## 4. Search before writing

Never create a note without searching first - see `references/write-rules.md`.
Duplicate notes are the exact rot this system exists to prevent.

## 5. Freshness

Every stored fact is timeless, dated, or a pointer - see
`references/freshness-policy.md`.

## 6. Critical facts

`CRITICAL_FACTS.md` is small (~100-150 tokens) and always loaded at session
start.
