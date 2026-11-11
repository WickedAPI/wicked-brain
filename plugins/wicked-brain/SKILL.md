---
name: wicked-brain
description: A fast, file-based memory vault shared between Claude Code and Codex CLI. Search, save, and maintain a plain-markdown Obsidian vault of projects, entities, decisions, sessions, and concepts - with atomic writes, bi-temporal facts, duplicate detection, freshness linting, and bounded recall.
---

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
   conventions. If no vault is configured yet, offer `/brain-init`.
2. Treat the AI-first vault rule (`references/ai-first-rules.md`) as
   non-negotiable for every note you write: `## For future agent` preamble,
   rich frontmatter (`type`, `date`, `tags`, `ai-first: true`), `[[wikilinks]]`
   for every entity/project/concept, recency markers per external claim,
   sources verbatim, confidence levels where applicable.
3. Search before writing (`references/write-rules.md`) - a duplicate note is
   the exact rot this system exists to prevent.
4. Never fabricate, and never claim a note is absent without an exhaustive
   search - see the anti-fabrication and search-completeness hard rules in
   `references/ai-first-rules.md`.

## Commands

| Command | What it does |
|---|---|
| `/brain-save` | Save everything vault-worthy from this conversation (proactive) |
| `/brain-find` | Search the vault with ranked, context-rich results |
| `/brain-capture` | Zero-friction quick capture to `concepts/` (proactive) |
| `/brain-health` | Audit: duplicates, contradictions, freshness, structural issues |
| `/brain-merge` | Merge a near-duplicate pair found by `/brain-health` (dry run by default) |
| `/brain-fork` | Fork a project note under a new name, linked back to the original |
| `/brain-reindex` | Rebuild the semantic search index and report coverage |
| `/brain-reconcile` | Find and resolve contradictions across the vault |
| `/brain-init` | Bootstrap a new vault: folders, `_CLAUDE.md`/`AGENTS.md`, `index.md`, optionally version history |
| `/brain-sync` | Push/pull the vault across your devices through the encrypted sync server |

## Vault schema (fixed - see `references/vault-schema.md`)

`projects/`, `entities/`, `decisions/`, `sessions/`, `concepts/`, `_trash/`.
No wiki-style/Obsidian-style choice, no folder-map indirection - every script
and command hardcodes these five names.

## Scripts (`scripts/`, invoked via `uv run --directory "SKILL_ROOT" scripts/<name>.py`)

- `note_io.py` - atomic, byte-exact vault read/write (used by every write path)
- `vault_health.py` - the `/brain-health` engine (duplicates, staleness, orphans, structural issues)
- `freshness_lint.py` - enforces `references/freshness-policy.md`
- `link_graph.py` - typed-edge (`relations:`) lint and the graph the dashboard's graph view reads
- `merge_notes.py` / `auto_merge_exact_duplicates.py` - the mechanical half of `/brain-merge`, and this fork's bounded auto-merge upgrade (only similarity >= 0.97, never a judgment call)
- `semantic_search.py` - local, Ollama-backed semantic search (optional - degrades to lexical-only if Ollama isn't running)
- `export_okf.py` - export the vault as an Open Knowledge Format bundle
- `vault_scan.py` - shared exclude-dir/path config used by the scripts above
- `vault_git.py` (Phase 2) - version history: `is_git_vault`, `maybe_commit`, `git_log`, `git_diff`, `git_status_summary`, `init_vault_repo`. A vault opts in per-repo (a `.git/` directory - no env var) via `/brain-init`; every other write path checks for that and stays silent otherwise. See its module docstring for why one shared helper, not a hook-only approach.
- `vault_crypto.py` (Phase 3) - client-side encryption: `derive_key` (scrypt), `encrypt`/`decrypt` (Fernet), `content_hash`. The passphrase (`WICKED_BRAIN_SYNC_PASSPHRASE`) never leaves this device.
- `vault_sync.py` (Phase 3) - the sync client: `sync`/`bootstrap` against `sync_server/` over HTTP. Three-way diff per note against this device's own last-synced cursor (`.sync-state.json`, git-ignored); a genuine conflict (both sides changed and differ) saves the losing edit as a local conflict-copy note rather than dropping it. See its module docstring for the full case breakdown.

## MCP server (`integrations/mcp-server/`)

`server.py` / `vault_ops.py` expose vault search, read, and write as MCP tools
so any MCP-capable client - not just this skill's own commands - can use the
same vault with the same freshness-aware, deduplicating write path. This is
also what `dashboard/server.py` imports directly for the local dashboard.

## Hooks (Claude Code only - see `hooks/`)

- `validate-ai-first.sh` (PostToolUse) - warns on a vault write missing the AI-first shape
- `load_vault_context.py` (SessionStart) - injects `_CLAUDE.md`/`index.md` once per session
- `recall.py` (UserPromptSubmit, opt-in via `WICKED_BRAIN_RECALL_ENABLED=1`) - bounded (max 4 notes, ~900 chars), abstains on low confidence, fails closed
- `bg-agent.sh` (PostCompact, opt-in via `WICKED_BRAIN_BG_AGENT_ENABLED=1`) - propagates a compaction summary into the vault unattended, plus (fork upgrade) auto-merges only near-byte-identical duplicate pairs first

Codex CLI has no hook system - there, the AI-first rule rests on the compiled
skill instructions alone, not automatic injection. See `adapters/codex-cli/`'s
`INSTALL.md` output for what that means in practice.

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
