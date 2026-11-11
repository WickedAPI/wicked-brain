---
name: wicked-brain
description: "Operating rules for the user's Wicked Brain memory vault (plain-markdown notes shared by Claude Code, Codex and Antigravity). Use whenever the task is to recall, save, or maintain notes about projects, decisions, people, sessions or concepts, or when a $brain-* skill is invoked."
---

> **Plugin root.** This skill ships inside the Wicked Brain plugin. `<plugin-root>` means the folder two levels above this `SKILL.md` (the folder that contains `skills/`, `references/` and `scripts/`). Resolve every `<plugin-root>/...` path below from this file's own location. The vault itself is wherever `WICKED_BRAIN_VAULT_PATH` (or `~/.config/wicked-brain/.env`) points; if neither is set, run `$brain-setup` first.


# Wicked Brain

A persistent memory vault that belongs to neither model: plain markdown, an
MCP server both Claude Code and Codex CLI read/write through, and a fixed,
personalized schema built for a coding-assistant's actual memory needs -
not a general personal-PKM tool. Forked and trimmed from
[obsidian-second-brain](https://github.com/eugeniughelbur/obsidian-second-brain)
(MIT); see `NOTICE.md` for the full attribution and what changed.

## How to operate

1. Read `_CLAUDE.md` (Claude Code) or `AGENTS.md` (Codex CLI) at the vault
   root first, if it exists - it has the user's real vault path and any local
   conventions. If no vault is configured yet, offer `$brain-init`.
2. Treat the AI-first vault rule (`<plugin-root>/references/ai-first-rules.md`) as
   non-negotiable for every note you write: `## For future agent` preamble,
   rich frontmatter (`type`, `date`, `tags`, `ai-first: true`), `[[wikilinks]]`
   for every entity/project/concept, recency markers per external claim,
   sources verbatim, confidence levels where applicable.
3. Search before writing (`<plugin-root>/references/write-rules.md`) - a duplicate note is
   the exact rot this system exists to prevent.
4. Never fabricate, and never claim a note is absent without an exhaustive
   search - see the anti-fabrication and search-completeness hard rules in
   `<plugin-root>/references/ai-first-rules.md`.

## Commands

| Command | What it does |
|---|---|
| `$brain-save` | Save everything vault-worthy from this conversation (proactive) |
| `$brain-find` | Search the vault with ranked, context-rich results |
| `$brain-capture` | Zero-friction quick capture to `concepts/` (proactive) |
| `$brain-health` | Audit: duplicates, contradictions, freshness, structural issues |
| `$brain-merge` | Merge a near-duplicate pair found by `$brain-health` (dry run by default) |
| `$brain-fork` | Fork a project note under a new name, linked back to the original |
| `$brain-reindex` | Rebuild the semantic search index and report coverage |
| `$brain-reconcile` | Find and resolve contradictions across the vault |
| `$brain-init` | Bootstrap a new vault: folders, `_CLAUDE.md`/`AGENTS.md`, `index.md`, optionally version history |
| `$brain-sync` | Push/pull the vault across your devices through the encrypted sync server |

## Vault schema (fixed - see `<plugin-root>/references/vault-schema.md`)

`projects/`, `entities/`, `decisions/`, `sessions/`, `concepts/`, `_trash/`.
No wiki-style/Obsidian-style choice, no folder-map indirection - every script
and command hardcodes these five names.

## Scripts (`scripts/`, invoked via `uv run --directory "<plugin-root>" scripts/<name>.py`)

- `note_io.py` - atomic, byte-exact vault read/write (used by every write path)
- `vault_health.py` - the `$brain-health` engine (duplicates, staleness, orphans, structural issues)
- `freshness_lint.py` - enforces `<plugin-root>/references/freshness-policy.md`
- `link_graph.py` - typed-edge (`relations:`) lint and the graph the dashboard's graph view reads
- `merge_notes.py` / `auto_merge_exact_duplicates.py` - the mechanical half of `$brain-merge`, and this fork's bounded auto-merge upgrade (only similarity >= 0.97, never a judgment call)
- `semantic_search.py` - local, Ollama-backed semantic search (optional - degrades to lexical-only if Ollama isn't running)
- `export_okf.py` - export the vault as an Open Knowledge Format bundle
- `vault_scan.py` - shared exclude-dir/path config used by the scripts above
- `vault_git.py` (Phase 2) - version history: `is_git_vault`, `maybe_commit`, `git_log`, `git_diff`, `git_status_summary`, `init_vault_repo`. A vault opts in per-repo (a `.git/` directory - no env var) via `$brain-init`; every other write path checks for that and stays silent otherwise. See its module docstring for why one shared helper, not a hook-only approach.
- `vault_crypto.py` (Phase 3) - client-side encryption: `derive_key` (scrypt), `encrypt`/`decrypt` (Fernet), `content_hash`. The passphrase (`WICKED_BRAIN_SYNC_PASSPHRASE`) never leaves this device.
- `vault_sync.py` (Phase 3) - the sync client: `sync`/`bootstrap` against `sync_server/` over HTTP. Three-way diff per note against this device's own last-synced cursor (`.sync-state.json`, git-ignored); a genuine conflict (both sides changed and differ) saves the losing edit as a local conflict-copy note rather than dropping it. See its module docstring for the full case breakdown.

## MCP server (`integrations/mcp-server/`)

`server.py` / `vault_ops.py` expose vault search, read, and write as MCP tools
so any MCP-capable client - not just this skill's own commands - can use the
same vault with the same freshness-aware, deduplicating write path. This is
also what `dashboard/server.py` imports directly for the local dashboard.


## The dashboard (`dashboard/`)

A local FastAPI + vanilla-JS app - search, a wikilink graph view, a note
viewer with backlinks and version history, the health-check findings, and a
light/dark theme. Entirely new in this fork; see `dashboard/README.md`.

## The sync server (`sync_server/`, Phase 3)

A small FastAPI + SQLAlchemy API you self-host (Docker, Railway, Fly, any VPS) that stores
client-side-encrypted note blobs only - it never sees plaintext or holds the
encryption key. Talked to by `scripts/vault_sync.py`. See `sync_server/README.md`
for the API, how to deploy it, and its one documented limitation (paths aren't
encrypted, only content).
