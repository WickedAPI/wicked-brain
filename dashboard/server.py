"""dashboard/server.py - local FastAPI backend for the Wicked Brain dashboard.

Imports scripts/ and integrations/mcp-server/ directly (no subprocess
shelling) so the dashboard always reflects the exact same search ranking,
health checks, and graph the MCP server and commands use - there is only one
implementation of each, never a second copy for the UI to drift against.

Run:
    WICKED_BRAIN_VAULT_PATH=/path/to/vault uv run uvicorn dashboard.server:app --reload

With no WICKED_BRAIN_VAULT_PATH set, falls back to examples/sample-vault/vault so
the dashboard has something real to show out of the box.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "integrations" / "mcp-server"))

from fastapi import FastAPI, HTTPException, Query  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

import vault_ops  # noqa: E402
import link_graph  # noqa: E402
import vault_health  # noqa: E402
import vault_git  # noqa: E402
import vault_lock  # noqa: E402
import note_io  # noqa: E402
from export_okf import parse_note  # noqa: E402
from auto_merge_exact_duplicates import find_exact_pairs  # noqa: E402

app = FastAPI(title="Wicked Brain Dashboard")

_DEFAULT_VAULT = REPO_ROOT / "examples" / "sample-vault" / "vault"


def _vault() -> Path:
    raw = os.environ.get("WICKED_BRAIN_VAULT_PATH", "").strip()
    vault = Path(raw).expanduser().resolve() if raw else _DEFAULT_VAULT
    if not vault.is_dir():
        raise HTTPException(500, f"vault path does not exist: {vault}")
    return vault


def _rel_notes(vault: Path):
    """Every markdown note in the vault, as (rel_posix_path, Path)."""
    for md in vault.rglob("*.md"):
        parts = md.relative_to(vault).parts
        if any(p.startswith(".") or p in {"_trash", "node_modules"} for p in parts):
            continue
        if md.is_file():
            yield md.relative_to(vault).as_posix(), md


@app.get("/api/search")
def api_search(q: str = Query(..., min_length=1), limit: int = 20, semantic: Optional[bool] = None):
    os.environ["WICKED_BRAIN_VAULT_PATH"] = str(_vault())
    return {"query": q, "results": vault_ops.search(q, limit=limit, semantic=semantic)}


@app.get("/api/graph")
def api_graph(scope: Optional[str] = None):
    vault = _vault()
    result = link_graph.build_graph(vault, scope=scope)
    # mtime is a presentation concern (the 3D graph's "recency" size/color/glow
    # metric) that link_graph itself has no reason to know about - stat each
    # node's file here rather than teaching the shared graph builder about it.
    for node in result.get("nodes", []):
        try:
            node["mtime"] = (vault / node["path"]).stat().st_mtime
        except OSError:
            node["mtime"] = None
    return result


@app.get("/api/note/{rel_path:path}")
def api_note(rel_path: str):
    vault = _vault()
    target = (vault / rel_path).resolve()
    try:
        target.relative_to(vault)
    except ValueError:
        raise HTTPException(400, "path escapes the vault") from None
    if not target.is_file():
        raise HTTPException(404, f"not found: {rel_path}")
    text = target.read_text(encoding="utf-8-sig", errors="replace")
    fm, body, malformed = parse_note(text)
    os.environ["WICKED_BRAIN_VAULT_PATH"] = str(vault)
    back = vault_ops.backlinks(Path(rel_path).stem)
    # backlinks() returns OS-native separators; normalize to posix so the
    # frontend (which treats "/" as the only separator) works the same on
    # Windows and POSIX.
    backlink_paths = [Path(p).as_posix() for p in back.get("backlinks", [])]
    return {
        "path": rel_path,
        "frontmatter": fm,
        "frontmatter_malformed": malformed,
        "body": body,
        "backlinks": backlink_paths,
        "mtime": target.stat().st_mtime,
    }


@app.get("/api/health")
def api_health():
    result = vault_health.run_health_check(_vault())
    dup_pairs = find_exact_pairs(_vault())
    result["auto_merge_candidates"] = dup_pairs
    return result


@app.get("/api/recent")
def api_recent(limit: int = 20):
    vault = _vault()
    notes = []
    for rel, md in _rel_notes(vault):
        try:
            mtime = md.stat().st_mtime
        except OSError:
            continue
        notes.append({"path": rel, "title": md.stem, "mtime": mtime})
    notes.sort(key=lambda n: n["mtime"], reverse=True)
    return {"notes": notes[:limit]}


@app.get("/api/vault-status")
def api_vault_status():
    return vault_git.git_status_summary(_vault())


@app.get("/api/activity")
def api_activity(days: int = 365):
    return {"days": days, "by_day": vault_git.activity_by_day(_vault(), days=days)}


@app.get("/api/history/{rel_path:path}")
def api_history(rel_path: str, limit: int = 30, commit: Optional[str] = None):
    """Commit log for a note, or (with ?commit=<hash>) its diff at that commit.

    One route, not two - a second `/{rel_path:path}/{commit_hash}` route looks
    natural but doesn't work: the `:path` converter on THIS route is greedy
    and matches any suffix after /api/history/, including a URL meant for the
    more specific route, so the log endpoint always won regardless of
    registration order. A query param sidesteps the ambiguity entirely.
    """
    vault = _vault()
    if commit:
        diff = vault_git.git_diff(vault, rel_path, commit)
        if not diff:
            raise HTTPException(404, "no diff for that path/commit (or the vault isn't a git repo)")
        return {"path": rel_path, "hash": commit, "diff": diff}
    return {"path": rel_path, "commits": vault_git.git_log(vault, rel_path, limit=limit)}


@app.post("/api/history/{rel_path:path}")
def api_revert(rel_path: str, commit: str = Query(...)):
    """Revert one note to its content at one historical commit.

    Same URL as api_history above, distinguished by HTTP method (POST here,
    GET there) rather than a path suffix - a suffix like ".../revert" would
    collide with THIS route's own greedy `:path` converter the same way the
    docstring on api_history already warns about for a second GET route, so
    method-based dispatch sidesteps it entirely instead of re-deriving that
    bug.

    Writes the old content back as a NEW commit - never a hard reset or
    `git checkout <hash>` - so the version being reverted away from stays
    fully recoverable in history too. Wrapped in the same write_lock every
    other write path uses, since this is the dashboard's first write
    endpoint and a concurrent agent write must not be able to interleave
    with it and get silently lost.
    """
    vault = _vault()
    old_text = vault_git.git_show_file(vault, rel_path, commit)
    if old_text is None:
        raise HTTPException(404, "no content for that path/commit (or the vault isn't a git repo)")
    target = vault / rel_path
    if not target.is_file():
        raise HTTPException(404, f"{rel_path} is not a live note in the vault - revert onto an existing note only")
    try:
        with vault_lock.write_lock(vault):
            note_io.write_exact(target, old_text)
            commit_result = vault_git.maybe_commit(vault, [rel_path], f"revert: {rel_path} to {commit[:7]}")
    except TimeoutError as exc:
        raise HTTPException(503, str(exc)) from exc
    return {"path": rel_path, "reverted_to": commit, "commit": commit_result}


@app.get("/api/stats")
def api_stats():
    vault = _vault()
    by_folder: dict[str, int] = {}
    total = 0
    for rel, _ in _rel_notes(vault):
        total += 1
        folder = rel.split("/", 1)[0] if "/" in rel else "(root)"
        by_folder[folder] = by_folder.get(folder, 0) + 1
    coverage = vault_ops.index_coverage(vault)
    return {"vault": str(vault), "total_notes": total, "by_folder": by_folder, "semantic_index": coverage}


# --- static frontend -------------------------------------------------------
STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def index():
    return FileResponse(str(STATIC_DIR / "index.html"))
