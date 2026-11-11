---
description: Smart memory search - returns results with context, not just filenames
category: vault
triggers_en: ["find in memory", "search my memory", "where is", "what did I tell you about", "what do you remember about"]
---

Use the wicked-brain skill. Execute `/brain-find $ARGUMENTS`:

The argument is the search query.

1. Read `_CLAUDE.md` (or `AGENTS.md`) first if it exists in the vault root.
2. Search the vault for the query using the ranked search where it is available: the `brain_search` MCP tool, or `vault_ops.search` directly (`integrations/mcp-server/`). It fuses lexical (stopword-filtered, length-normalized) ranking with local semantic ranking when an embedding index exists, and applies freshness/supersession reranking so a superseded fact does not outrank the note that replaced it. Where no search tool is bound, grep the vault and read the top matches directly, applying the same judgement - ignore filler words, and do not let a long `sessions/` log outrank a canonical `entities/` or `projects/` note.
3. Try variations if results are sparse (synonyms, related terms).
4. Return results with context: note title, folder, a relevant excerpt, and what type of note it is.
5. If results are ambiguous, group them by type (entities, projects, decisions, concepts).
6. Offer to open, update, or link any of the found notes.

Do not just return filenames - return enough context for the user to act on the results.

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` - `## For future agent` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, confidence levels where applicable. The vault is for future agent retrieval - not human reading.

**Anti-fabrication:** Search exhaustively before claiming any note, person, or file is absent - false absence is the most common failure mode - and never invent facts, entities, or dates (mark unknowns as `TBD`). See the anti-fabrication and search-completeness hard rules in `references/ai-first-rules.md`.
