# Wicked Brain

[![tests](https://github.com/choaticpixels/wicked-brain/actions/workflows/tests.yml/badge.svg)](https://github.com/choaticpixels/wicked-brain/actions/workflows/tests.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**One memory for every AI coding agent.** Wicked Brain is a plain-markdown vault that
**Claude Code, Codex and Google Antigravity** all read and write. Save a decision in one
agent, recall it in another. No hosted service, no lock-in: the vault is a folder of
markdown files you own, and it opens in any editor.

- **Fast recall.** Search returns results with context, and Claude Code surfaces relevant notes
  before you even ask.
- **Memory that stays true.** Writes are atomic and dedup-aware, facts carry dates
  (`timeline:`), and a freshness linter flags stale claims, so the vault doesn't rot into a
  pile of duplicates.
- **Safe by construction.** Every write is validated, an optional git history makes any change
  recoverable, and sync never overwrites: a real conflict is saved as a copy note.
- **Optional encrypted sync.** Back up and share a vault across your own devices through a small
  server you host. The server only ever sees ciphertext.

## Install

You need [`uv`](https://docs.astral.sh/uv/) (it brings Python). On Windows, Claude Code's hooks
use Git Bash, which comes with [Git for Windows](https://git-scm.com/download/win).

### Claude Code

```bash
claude plugin marketplace add choaticpixels/wicked-brain
claude plugin install wicked-brain@wicked-brain
```

Restart Claude Code, open `/config`, find **Wicked Brain**, and set your vault location. That's
all. The hooks (write validation, session context, proactive recall), the MCP server and all
ten `/brain-*` commands register themselves. Then run `/brain-init` to create a vault.

### Codex

```bash
codex plugin marketplace add choaticpixels/wicked-brain
```

Then open the Codex app's plugin directory, install **Wicked Brain**, and run `$brain-setup`
once to tell it where your vault is. Each command is a skill: `$brain-find`, `$brain-save`,
`$brain-capture` and so on.

Codex plugins can't run hooks yet, so on Codex there is no automatic recall or auto-sync. Run
`$brain-find` and `$brain-sync` yourself.

### Google Antigravity

```bash
git clone https://github.com/choaticpixels/wicked-brain && cd wicked-brain
export WICKED_BRAIN_VAULT_PATH=/path/to/your/vault
bash scripts/install-antigravity.sh
```

Fully quit and relaunch Antigravity, then check **MCP Servers** for `wicked-brain`. Antigravity
has no hook system, so like Codex it gets the tools and commands but no automatic recall. See
`adapters/antigravity` for the details.

### One vault, three agents

Point all of them at the same folder and they share one memory. The vault path comes from
`WICKED_BRAIN_VAULT_PATH`, or from `~/.config/wicked-brain/.env`, which `$brain-setup` writes.

## Commands

| Command | What it does |
|---|---|
| `/brain-init` | Create a new vault with the fixed folder structure |
| `/brain-save` | Save everything worth keeping from this conversation |
| `/brain-capture` | Zero-friction capture of a fact, pattern or idea |
| `/brain-find` | Smart search that returns context, not just filenames |
| `/brain-health` | Health check: duplicates, contradictions, stale claims, structure |
| `/brain-merge` | Merge two near-duplicate notes (dry run by default) |
| `/brain-fork` | Fork a project note so a derivative project starts with context |
| `/brain-reconcile` | Find and resolve contradictions |
| `/brain-reindex` | Refresh the semantic search index |
| `/brain-sync` | Sync the vault across your devices |

On Codex the same commands are `$brain-*` skills.

## The vault

A vault is plain markdown in five folders:

```
projects/   what you're building, status, key decisions
entities/   people, orgs and tools
decisions/  standalone decision records
sessions/   one note per working day
concepts/   reusable knowledge and patterns
```

Notes follow a small schema (see `references/vault-schema.md`) so agents write them the same
way. `examples/sample-vault/` is a worked example. A local dashboard (`dashboard/`) gives you
search, a wikilink graph, a note viewer with version history and health findings:

```bash
uv run uvicorn dashboard.server:app
```

## Cross-device sync (optional)

`/brain-sync` pushes and pulls your vault through a server you host (`sync_server/`, a small
FastAPI app). Content is encrypted on your machine before upload, with a passphrase the server
never sees. Deletes are tombstones, and three-way conflict detection saves the losing edit as a
`(sync-conflict ...)` note instead of dropping it. One limitation, stated plainly: note
*paths* are not encrypted, only their content. See `sync_server/README.md` to stand one up, then:

```bash
export WICKED_BRAIN_SYNC_URL=https://your-sync-server.example.com
export WICKED_BRAIN_SYNC_TOKEN=...        # the server's SYNC_TOKEN
export WICKED_BRAIN_SYNC_PASSPHRASE=...   # the same on every device, never uploaded
```

Claude Code can also back up automatically at session start, after compaction and at session
end: set `WICKED_BRAIN_AUTO_SYNC_ENABLED=1`. It is off by default.

## How it fits together

```
commands/            the ten command definitions (source; adapters compile per platform)
references/          the write spec, vault schema, freshness policy
scripts/             atomic I/O, health, dedup, freshness, graph, git, crypto and sync engines
adapters/            build pipeline for Claude Code, Codex and Antigravity
hooks/               Claude Code hooks: validation, recall, auto-sync
integrations/        the MCP server every agent reads and writes through
dashboard/           local search, graph, health and history UI
sync_server/         the optional encrypted sync API
examples/            a sample vault
tests/               unit, integration and live-sync tests
```

Build and test from a clone:

```bash
uv sync --all-groups
bash scripts/build.sh          # compile for each platform into dist/
uv run pytest -q
```

## Contributing

Issues and pull requests are welcome. Run the tests before opening a PR. Never commit a real
vault, token or passphrase.

## License and credits

MIT. Wicked Brain started as a fork of
[obsidian-second-brain](https://github.com/eugeniughelbur/obsidian-second-brain) by Eugeniu
Ghelbur and is trimmed and extended from there. `NOTICE.md` lists exactly what came from
upstream and what is new.
