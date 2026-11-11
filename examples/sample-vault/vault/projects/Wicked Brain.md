---
date: 2026-09-07
updated: 2026-09-07
type: project
status: active
tags: [project]
related-entities: ["[[entities/Sam]]"]
related-projects: []
repo: /path/to/your/brain-checkout
ai-first: true
---

## For future agent
Wicked Brain is a project with status active as of 2026-09-07. The Overview section explains what it is and why it exists. Recent Activity captures the last 30 days. Key Decisions documents major directional choices with rationale.

## Overview

A fast, file-based memory vault shared by Claude Code and Codex CLI, forked
and trimmed from [[entities/obsidian-second-brain]] down to a fixed schema
built for a coding assistant's memory, not general personal note-taking.

## Recent Activity

- 2026-09-07: Researched existing AI memory systems (Mem0, Zep, Letta,
  mcp-memory-service) and obsidian-second-brain specifically. Forked,
  trimmed to 8 commands and 2 platform adapters (Claude Code, Codex CLI),
  personalized the vault schema, shipped two upgrades over upstream
  (auto-reindex, bounded auto-merge), and built the local dashboard.
- 2026-09-08: Shipped Phase 2 (git-backed version history) and Phase 3
  (encrypted cross-device sync via a self-hosted server), bringing the
  upgrade count over upstream to four.
- 2026-09-08: Renamed the project from "Agent Memory" to **Wicked Brain** - full
  rebrand across commands (`/mem-*` -> `/brain-*`), env vars (`MEMORY_*` ->
  `WICKED_BRAIN_*`), MCP tool names, and the repo folder itself.

## Key Decisions

- **2026-09-07**: Fork obsidian-second-brain rather than build from scratch
  (see [[decisions/ADR-2026-09-07 - Fork obsidian-second-brain]]).
