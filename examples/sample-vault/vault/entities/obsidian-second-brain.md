---
date: 2026-09-07
updated: 2026-09-07
type: entity
entity-kind: tool
tags: [entity]
role: "Upstream project this fork is based on"
last-interaction: 2026-09-07
related-projects: ["[[projects/Wicked Brain]]"]
timeline:
  - fact: "1,462+ GitHub stars, 166 forks at the time it was evaluated"
    from: 2026-05-30
    until: present
    learned: 2026-09-07
    source: "https://github.com/eugeniughelbur/obsidian-second-brain"
ai-first: true
---

## For future agent
obsidian-second-brain is a tool - the MIT-licensed upstream project wicked-brain forks from. Current role/status: Upstream project this fork is based on as of 2026-09-07 - see `timeline:` for history. Last interaction: 2026-09-07.

## Notes

- MIT licensed, by Eugeniu Ghelbur (as of 2026-09-07, github.com/eugeniughelbur/obsidian-second-brain).
- Cross-compiles one command source to 8 CLI platforms including both Claude
  Code and Codex CLI - the property that made it worth forking instead of
  building fresh.
- Key ideas kept: atomic byte-exact writes, bi-temporal `timeline:` facts,
  freshness linting, mechanical note-merge/dedup, bounded fail-closed recall.
- Key gaps this fork closes: semantic reindexing was manual-only; the
  background agent could add/update but never merge, even an exact duplicate.
