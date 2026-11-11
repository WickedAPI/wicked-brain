# Wicked Brain dashboard

A local dashboard for the vault: instant full-text/semantic search, a 3D
WebGL "nebula" wikilink graph, a GitHub-style activity heatmap, a note viewer
with rendered frontmatter, backlinks, and version history (a diff-able commit
log, if the vault is a git repo - see below), vault health findings, and a
light/dark theme with an accent picker. No build step - the frontend is plain
HTML/CSS/JS (plus three.js, loaded from a CDN, for the graph).

## Run it

```bash
WICKED_BRAIN_VAULT_PATH=/path/to/your/vault uv run uvicorn dashboard.server:app --reload --port 8420
```

Then open http://localhost:8420. With no `WICKED_BRAIN_VAULT_PATH` set, it falls
back to `examples/sample-vault/vault` so there's always something to look at.

## How it's built

`dashboard/server.py` is a thin FastAPI layer that imports `vault_ops.py`,
`link_graph.py`, `vault_health.py`, `vault_git.py`, and
`auto_merge_exact_duplicates.py` directly (no subprocess calls) - the
dashboard always reflects the exact same search ranking, health checks, and
git history the MCP server and slash commands use, since there's only one
implementation of each.

| Endpoint | Backed by |
|---|---|
| `GET /api/search?q=` | `vault_ops.search` (lexical + optional semantic fusion, freshness-reranked) |
| `GET /api/graph` | `link_graph.build_graph`, each node enriched with `mtime` (a presentation-only addition for the 3D graph's recency metrics - link_graph itself has no reason to know about file mtimes) |
| `GET /api/note/{path}` | frontmatter/body split + `vault_ops.backlinks` |
| `GET /api/health` | `vault_health.run_health_check` + `auto_merge_exact_duplicates.find_exact_pairs` |
| `GET /api/recent` | mtime scan over the vault |
| `GET /api/stats` | note counts by folder + semantic index coverage |
| `GET /api/vault-status` | `vault_git.git_status_summary` (the sidebar's "Version history on/off" badge) |
| `GET /api/activity?days=` | `vault_git.activity_by_day` - per-day commit/insertion/deletion counts behind the Activity heatmap |
| `GET /api/history/{path}` | `vault_git.git_log` - commit log for one note |
| `GET /api/history/{path}?commit=<hash>` | `vault_git.git_diff` - diff for one commit. Deliberately a query param on the same route rather than a second `/{path}/{hash}` route: the `:path` converter is greedy and would swallow that route's URLs too, so the log endpoint would always win regardless of registration order. |

## Version history

Off by default - a vault only gets version history once it becomes a git
repo, which `/brain-init` offers to do (or run `scripts/vault_git.py --path
<vault> --init`). Once enabled, every write from any of the three write paths
(the agent's native Write/Edit tool via the `hooks/validate-ai-first.sh`
Claude Code hook, the MCP server's write functions, or a script like
`merge_notes.py`) lands as a commit - see `NOTICE.md`'s Phase 2 notes and
`scripts/vault_git.py`'s module docstring for the full design. The note
panel's "Version history" section lists commits for that note and renders a
colored diff on click.

## The 3D graph

Recreated from a reference the vault's owner built and handed over (a
WebGL homage to Obsidian's Advanced Graph View / the Graph Insight
community plugin's Nebula theme) - additive-blended glowing points,
constellation link lines, an orbiting camera, raycasted hover/click. The
rendering technique is close to the reference; the data behind it is not -
`dashboard/static/graph3d-data.js` computes every metric shown (PageRank via
real power iteration over this vault's actual links, hub status from real
degree, a force-directed 3D layout from real connectivity, edit recency from
real file mtimes) from `GET /api/graph`. Nothing is demo data, and nothing
is fabricated to fill a metric the vault doesn't actually track - the
reference's "opened N times" stat, for instance, is simply not offered here,
since Wicked Brain has no such tracking.

Size/color/glow can each be driven by a different real metric (inbound
links, outbound links, PageRank, edit recency), five color schemes, adjustable
link thickness/opacity, a live text/tag/folder filter, a note inspector
drawer (click a node) that opens the real note via the same viewer the rest
of the dashboard uses, and PNG export.

## Activity heatmap

A GitHub-contributions-style calendar under the Activity tab - one square per
day for the last ~53 weeks, shaded by lines changed that day, with a hover
tooltip (commits, lines added, notes touched) and a click-through to that
day's `sessions/YYYY-MM-DD.md` when one exists. It's not a synthetic metric:
since Phase 2 makes near-every vault write its own commit, the heatmap is a
real reflection of `git log`, not an approximation. Empty (all-gray) if the
vault isn't a git repo yet.

## Keyboard

`Ctrl+K` / `Cmd+K` jumps to search. `Esc` closes the note panel.
