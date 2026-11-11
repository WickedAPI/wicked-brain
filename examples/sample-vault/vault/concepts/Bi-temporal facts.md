---
date: 2026-09-07
type: concept
tags: [concept]
status: active
related-projects: ["[[projects/Wicked Brain]]"]
ai-first: true
---

## For future agent
Concept captured on 2026-09-07 about bi-temporal facts. Status: active. The body explains the idea, why it's useful, and where it connects to active projects.

A fact stored with two timestamps: **valid time** (when it was true in the
world - `from`/`until`) and **transaction time** (`learned` - when the vault
recorded it). Lets a note answer "what did you believe on date X" without
losing "what is true now," and lets reconciliation tell an evolving
understanding apart from a genuine contradiction. Originated in Zep/Graphiti's
temporal knowledge graph; [[entities/obsidian-second-brain]] implements the
same idea as a plain YAML `timeline:` list, which this vault kept as-is (see
`references/vault-schema.md`).
