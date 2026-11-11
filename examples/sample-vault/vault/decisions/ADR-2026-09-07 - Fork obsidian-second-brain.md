---
date: 2026-09-07
type: adr
tags: [adr, decision]
decision: "Fork and trim obsidian-second-brain instead of building a memory system from scratch"
status: accepted
related-projects: ["[[projects/Wicked Brain]]"]
ai-first: true
---

## For future agent
Decision made on 2026-09-07 about how to build the wicked-brain vault. Context explains what prompted it. Options Considered lists the alternatives evaluated. Rationale captures why this option won. Consequences documents what changed as a result.

## Context

Wanted a memory system for Claude Code and Codex CLI that fixes the common
failure modes of existing AI memory tools: duplication from append-only
writes, staleness with no invalidation signal, recency-blind search, and
being tied to a single client.

## Options Considered

- Build from scratch.
- Adopt a hosted memory service (Mem0, Zep, Letta) as-is.
- Fork [[entities/obsidian-second-brain]] and trim it.

## Rationale

obsidian-second-brain already solved the hard parts well - atomic writes,
bi-temporal facts, freshness linting, mechanical dedup, a bounded fail-closed
recall hook - and already cross-compiled to both Claude Code and Codex CLI
from one source, which is the actual differentiator (a memory belonging to
neither model). Rebuilding that engineering from zero would very likely land
in the same place at far higher cost.

## Consequences

Forked, dropped everything outside the memory use case (research toolkit,
calendar, kanban, 6 of 8 platform adapters, ~40 of 47 commands), personalized
the vault schema to five fixed folders, and closed two real upstream gaps
(manual-only semantic reindexing; no merge capability in the background
agent). See `NOTICE.md` for the full attribution.
