# Vault Schema Reference

One fixed schema - not a choice between styles. The vault is a real Obsidian vault (open it in Obsidian any time), but the primary reader is an agent, so the layout is optimized for that: flat folders, one per note type, easy to `grep`/glob.

```
Your Vault/
├── _CLAUDE.md                  ← Claude Code's operating manual
├── AGENTS.md                   ← Codex CLI's operating manual (same content, neutralized)
├── index.md                    ← Catalog of all notes (read this FIRST)
├── CRITICAL_FACTS.md           ← ~100-150 tokens, always loaded: timezone, current focus
│
├── projects/                   ← One note per project: status, timeline, key decisions
├── entities/                   ← People, orgs, tools - flat, one file per entity
├── decisions/                  ← ADRs and open conflicts (type: conflict)
├── sessions/                   ← One note per day: YYYY-MM-DD.md
├── concepts/                   ← Reusable knowledge, patterns, ideas
│
└── _trash/                     ← Soft-deleted notes only - never hard-delete
```

### Key principles
- **Fixed, not configurable.** No wiki-style/Obsidian-style choice, no folder-map indirection to resolve at read time - every command and script can hardcode these five folder names.
- **`index.md` is the front door.** Read it first to navigate; cheaper and faster than searching.
- **Flat folders.** `entities/` is a flat list - harder for a human to browse by category, easy for an agent to glob and grep.
- **Never delete.** A retired or superseded note moves to `_trash/` or becomes a `type: redirect` stub (per `<plugin-root>/references/write-rules.md`); the vault is a permanent record.

---

## Frontmatter schemas

The full schema per note type (with the universal fields every note needs) lives in `<plugin-root>/references/ai-first-rules.md` § Type Schemas. This section covers only the one thing that needs its own explanation: bi-temporal facts.

### Bi-temporal facts (entities and projects)

**Never overwrite** a role, status, or company on an entity note - or a status on a project note. Append a new entry to `timeline:` instead:

```yaml
timeline:
  - fact: "CTO at Acme Corp"
    from: 2024-01-01            # event time: when the fact was true
    until: 2026-04-07
    learned: 2026-02-23         # transaction time: when the vault first recorded this
  - fact: "Architect at Acme Corp"
    from: 2026-04-07
    until: present
    learned: 2026-04-07
    source: "[[sessions/2026-04-07]]"    # optional - where the vault learned it
```

The top-level `role:`/`status:` field always reflects the CURRENT state; `timeline:` preserves the full history. This is what makes "who was CTO in January?" answerable, lets `$brain-reconcile` tell an evolution ("you believed X, then learned Y") apart from a genuine contradiction, and gives every fact an audit trail of when the vault learned it and from where.

---

## Naming conventions

| Type | Pattern | Example |
|---|---|---|
| Session | `YYYY-MM-DD.md` | `2026-03-24.md` |
| Entity | Full name (flat) | `Jane Smith.md`, `Acme Corp.md` |
| Concept | Descriptive title | `LLM memory design.md` |
| Project | Proper name | `Wicked Brain.md` |
| Decision (ADR) | `ADR-YYYY-MM-DD - Title.md` | `ADR-2026-04-06 - Fixed vault schema.md` |
| Trash prefix | `_trashed_` | `_trashed_Old Project.md` |

---

## Dataview query patterns (optional, if you use the Dataview plugin in Obsidian)

```dataview
TABLE status, updated FROM "projects"
WHERE contains(tags, "project") AND status = "active"
SORT file.name ASC
```

```dataview
TABLE entity-kind, role, last-interaction FROM "entities"
WHERE contains(tags, "entity")
SORT last-interaction DESC
```

```dataview
TABLE date FROM "sessions"
SORT date DESC
LIMIT 7
```

---

## Fork note

Forked from [obsidian-second-brain](https://github.com/eugeniughelbur/obsidian-second-brain)'s `<plugin-root>/references/vault-schema.md` (MIT), collapsed from its wiki-style/Obsidian-style dual layout down to one fixed schema. See `NOTICE.md` at the repo root.
