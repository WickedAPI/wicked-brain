"""sync_server/server.py - the Phase 3 sync API, deployed on Railway.

Stores client-side-encrypted note blobs only - this process never sees
plaintext and never holds the encryption key. It knows paths, content hashes,
timestamps, and ciphertext; that is the full extent of what it can see. See
README.md's "Known limitation" section for what that does and doesn't cover
(paths themselves are not encrypted).

Auth is one shared bearer token (SYNC_TOKEN), appropriate for solo
cross-device use - every device you own presents the same token. Not a
multi-user system; see NOTICE.md / the project plan for why that's a
deliberate scope line, not an oversight.

Run locally:
    DATABASE_URL=sqlite:///./sync.db SYNC_TOKEN=dev-token uv run uvicorn sync_server.server:app --reload

On Railway, DATABASE_URL and SYNC_TOKEN are set as service variables.
"""
from __future__ import annotations

import base64
import os
import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Query
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db  # noqa: E402

import sentry_sdk  # noqa: E402


def _scrub_event(event, _hint):
    """Keep ciphertext, the bearer token and note paths out of Sentry.

    Paths are not encrypted at rest (see README "Known limitation"), but they
    are still note titles, so they are not sent to a third party either.
    """
    req = event.get("request")
    if req:
        req.pop("data", None)
        req.pop("cookies", None)
        req.pop("query_string", None)
        req["headers"] = {
            k: v for k, v in (req.get("headers") or {}).items()
            if k.lower() not in {"authorization", "cookie", "x-api-key"}
        }
        url = req.get("url") or ""
        marker = "/notes/"
        if marker in url:
            req["url"] = url.split(marker, 1)[0] + marker + "<redacted>"
    return event


if os.environ.get("SENTRY_DSN"):
    sentry_sdk.init(
        dsn=os.environ["SENTRY_DSN"],
        environment=os.environ.get("SENTRY_ENVIRONMENT") or os.environ.get("RAILWAY_ENVIRONMENT_NAME"),
        release=os.environ.get("RAILWAY_DEPLOYMENT_ID"),
        send_default_pii=False,
        include_local_variables=False,  # frames would otherwise carry ciphertext
        max_request_body_size="never",
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0")),
        before_send=_scrub_event,
    )

app = FastAPI(title="Wicked Brain Sync")
_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        _engine = db.make_engine()
    return _engine


def _require_auth(authorization: Optional[str]) -> None:
    token = os.environ.get("SYNC_TOKEN", "").strip()
    if not token:
        # Misconfiguration, not "open by design" - refuse rather than silently
        # running unauthenticated.
        raise HTTPException(500, "SYNC_TOKEN is not configured on the server")
    presented = (authorization or "").removeprefix("Bearer ").strip()
    if not presented or presented != token:
        raise HTTPException(401, "missing or invalid bearer token")


class SaltIn(BaseModel):
    value: str  # base64


class NoteIn(BaseModel):
    ciphertext: str  # base64
    content_hash: str
    mtime: str
    device_id: str
    # Required, no default - see db.upsert_note's docstring for the 3-state
    # convention (None=force, 0=expect-new, N=expect this exact revision).
    # No implicit default here on purpose: a caller that forgets to think
    # about this should get a clear validation error, not silently land on
    # "force" (None) and reintroduce the exact race this field exists to
    # close. vault_sync.py always sends a real value; there are no other
    # clients of this self-hosted, single-vault API.
    expected_revision: Optional[int]


class DeleteIn(BaseModel):
    device_id: str
    expected_revision: Optional[int]


def _serialize_note_row(row: dict) -> dict:
    return {
        "path": row["path"],
        "ciphertext": base64.b64encode(row["ciphertext"]).decode("ascii"),
        "content_hash": row["content_hash"],
        "mtime": row["mtime"],
        "revision": row["revision"],
        "deleted": row["deleted"],
    }


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/salt")
def get_salt(authorization: Optional[str] = Header(None)):
    _require_auth(authorization)
    value = db.get_salt(_get_engine())
    if value is None:
        raise HTTPException(404, "no salt established yet - the first device to sync sets one")
    return {"value": value}


@app.post("/salt")
def post_salt(body: SaltIn, authorization: Optional[str] = Header(None)):
    _require_auth(authorization)
    created = db.set_salt(_get_engine(), body.value)
    if not created:
        raise HTTPException(409, "a salt already exists for this vault - it is never overwritten")
    return {"created": True}


@app.get("/manifest")
def manifest(since: int = Query(0), authorization: Optional[str] = Header(None)):
    _require_auth(authorization)
    return {"notes": db.manifest_since(_get_engine(), since)}


@app.get("/notes/{rel_path:path}")
def get_note(rel_path: str, authorization: Optional[str] = Header(None)):
    _require_auth(authorization)
    row = db.get_note(_get_engine(), rel_path)
    if row is None:
        raise HTTPException(404, f"no such note: {rel_path}")
    return _serialize_note_row(row)


@app.put("/notes/{rel_path:path}")
def put_note(rel_path: str, body: NoteIn, authorization: Optional[str] = Header(None)):
    _require_auth(authorization)
    try:
        ciphertext = base64.b64decode(body.ciphertext)
    except Exception:
        raise HTTPException(400, "ciphertext must be base64") from None
    try:
        result = db.upsert_note(
            _get_engine(), path=rel_path, ciphertext=ciphertext,
            content_hash=body.content_hash, mtime=body.mtime, device_id=body.device_id,
            expected_revision=body.expected_revision,
        )
    except db.RevisionConflict as exc:
        # 409 carries the CURRENT server state so the client can resolve the
        # conflict (newer-wins + conflict-copy) in one round trip instead of
        # a second GET.
        raise HTTPException(
            409,
            {"conflict": True, "current": _serialize_note_row(exc.current) if exc.current else None},
        ) from None
    return result


@app.delete("/notes/{rel_path:path}")
def delete_note(rel_path: str, body: DeleteIn, authorization: Optional[str] = Header(None)):
    _require_auth(authorization)
    try:
        return db.tombstone_note(
            _get_engine(), path=rel_path, device_id=body.device_id,
            expected_revision=body.expected_revision,
        )
    except db.RevisionConflict as exc:
        raise HTTPException(
            409,
            {"conflict": True, "current": _serialize_note_row(exc.current) if exc.current else None},
        ) from None
