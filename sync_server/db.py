"""sync_server/db.py - storage layer for the sync server, SQLAlchemy Core (not
ORM) so the exact same code runs against a local SQLite file (tests, local
dev) and Railway's managed Postgres (production) via one DATABASE_URL.

Schema is deliberately tiny: one `notes` table holding ciphertext blobs and
metadata, plus one `salt` table holding the single passphrase-derivation salt
this vault's devices share. The server never sees plaintext and never sees
the encryption key - only `vault_crypto.py`, running on each device, does.

`revision` is a server-assigned `time.time_ns()` at write time, not a
database sequence - nanosecond resolution is monotonic enough for solo
cross-device use without a dialect-specific SEQUENCE (Postgres has one,
SQLite doesn't), and clients only ever need "give me everything newer than
revision X," which a plain integer column with an index supports directly.
"""
from __future__ import annotations

import os
import time
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    Column,
    LargeBinary,
    MetaData,
    String,
    Table,
    BigInteger,
    create_engine,
    select,
    delete,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

metadata = MetaData()

notes = Table(
    "notes",
    metadata,
    Column("path", String, primary_key=True),       # vault-relative path
    Column("ciphertext", LargeBinary, nullable=False),
    Column("content_hash", String, nullable=False),  # sha256 of the PLAINTEXT, computed client-side
    Column("mtime", String, nullable=False),         # ISO 8601, client-supplied
    Column("device_id", String, nullable=False),     # which device wrote this revision
    Column("revision", BigInteger, nullable=False, index=True),
    Column("deleted", Boolean, nullable=False, default=False),
)

salt_table = Table(
    "salt",
    metadata,
    Column("id", String, primary_key=True),  # always "vault" - single row
    Column("value", String, nullable=False),  # base64
)


def make_engine(database_url: Optional[str] = None) -> Engine:
    url = database_url or os.environ.get("DATABASE_URL", "sqlite:///./sync.db")
    # Railway (and most Postgres hosts) hand out "postgres://", which
    # SQLAlchemy's dialect lookup rejects outright - it wants "postgresql://".
    # And plain "postgresql://" resolves to the psycopg2 dialect by default,
    # which isn't installed (pyproject.toml installs psycopg v3, the
    # "psycopg" package, not "psycopg2") - "+psycopg" makes the v3 dialect
    # explicit rather than relying on SQLAlchemy's default guess.
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    engine = create_engine(url, future=True)
    metadata.create_all(engine)
    return engine


def next_revision() -> int:
    return time.time_ns()


def get_salt(engine: Engine) -> Optional[str]:
    with engine.begin() as conn:
        row = conn.execute(select(salt_table.c.value).where(salt_table.c.id == "vault")).first()
        return row[0] if row else None


def set_salt(engine: Engine, value: str) -> bool:
    """Establish the salt, once. Returns False (no-op) if one already exists -
    a vault re-keying itself mid-flight would silently strand every note
    encrypted under the old salt, so this never overwrites."""
    with engine.begin() as conn:
        existing = conn.execute(select(salt_table.c.value).where(salt_table.c.id == "vault")).first()
        if existing:
            return False
        conn.execute(salt_table.insert().values(id="vault", value=value))
        return True


class RevisionConflict(Exception):
    """expected_revision did not match the note's actual current revision on
    the server - see upsert_note's docstring. `current` is the server's
    present row for the path (None if the client expected an existing note
    that turned out to have never been pushed, or was since deleted-then-
    never-recreated) so the caller can resolve this the same way an ordinary
    detected sync conflict is resolved, instead of guessing."""

    def __init__(self, current: Optional[dict[str, Any]]):
        self.current = current
        super().__init__("revision conflict")


def upsert_note(engine: Engine, *, path: str, ciphertext: bytes, content_hash: str,
                 mtime: str, device_id: str, expected_revision: Optional[int] = None) -> dict[str, Any]:
    """Upsert with optimistic concurrency control.

    expected_revision has three states (same convention as tombstone_note):
      - None  - skip the check, force-write regardless of current state. For
                a caller that has ALREADY resolved a conflict (e.g. decided
                local wins, saved the loser's content as a conflict copy) and
                deliberately wants this write to win no matter what landed
                since.
      - 0     - "I believe this path does not exist on the server yet."
      - N > 0 - "the last revision I agreed was current for this path is N."

    Without this, two devices racing an overlapping sync on the same note
    both blindly overwrote whatever was there - both pushes "succeeded", the
    loser's edit vanished with no conflict detected anywhere (found
    2026-09-10 via Codex Astra's report, reproduced against a real local
    server before this fix: device A pushed, device B pushed moments later
    using a manifest snapshot taken before A's push, and A's edit was gone
    with zero trace).

    The actual atomicity guarantee is the UPDATE's WHERE clause + rowcount
    check below, not the SELECT before it (which only builds a friendlier
    conflict payload) - two concurrent transactions can only ever have one
    UPDATE actually match a still-current revision; the database engine
    itself serializes that, regardless of read timing.
    """
    revision = next_revision()
    with engine.begin() as conn:
        row = conn.execute(select(notes).where(notes.c.path == path)).mappings().first()
        if row is None:
            if expected_revision:  # a real N: client thought a note already existed here
                raise RevisionConflict(None)
            try:
                conn.execute(notes.insert().values(
                    path=path, ciphertext=ciphertext, content_hash=content_hash,
                    mtime=mtime, device_id=device_id, revision=revision, deleted=False,
                ))
            except IntegrityError:
                # Another writer's INSERT for this same brand-new path won the
                # race between our SELECT and this INSERT. A force write
                # (expected_revision=None) does not reach this branch at all
                # once a row exists, so this can only fire for a genuine "I
                # thought this was new" collision, never a force.
                conflict_row = conn.execute(
                    select(notes).where(notes.c.path == path)
                ).mappings().first()
                raise RevisionConflict(dict(conflict_row) if conflict_row else None) from None
        elif expected_revision is None:
            conn.execute(
                notes.update().where(notes.c.path == path).values(
                    ciphertext=ciphertext, content_hash=content_hash, mtime=mtime,
                    device_id=device_id, revision=revision, deleted=False,
                )
            )
        else:
            if expected_revision != row["revision"]:
                raise RevisionConflict(dict(row))
            result = conn.execute(
                notes.update()
                .where(notes.c.path == path, notes.c.revision == expected_revision)
                .values(ciphertext=ciphertext, content_hash=content_hash, mtime=mtime,
                        device_id=device_id, revision=revision, deleted=False)
            )
            if result.rowcount != 1:
                # Lost the race between our SELECT and this UPDATE - someone
                # else's write landed in between.
                conflict_row = conn.execute(
                    select(notes).where(notes.c.path == path)
                ).mappings().first()
                raise RevisionConflict(dict(conflict_row) if conflict_row else None)
    return {"path": path, "revision": revision}


def tombstone_note(engine: Engine, *, path: str, device_id: str,
                    expected_revision: Optional[int] = None) -> dict[str, Any]:
    """Same optimistic-concurrency guard as upsert_note: a delete racing a
    concurrent edit is the same class of silent data loss (device B decides
    to delete a note it no longer has locally, while device A just pushed a
    fresh edit to it) and deserves the same protection. expected_revision is
    optional (None skips the check) so this stays backward compatible with
    any caller that genuinely wants a force-delete."""
    revision = next_revision()
    with engine.begin() as conn:
        row = conn.execute(select(notes).where(notes.c.path == path)).mappings().first()
        if row is None:
            if expected_revision:
                raise RevisionConflict(None)
            conn.execute(notes.insert().values(
                path=path, ciphertext=b"", content_hash="", mtime="",
                device_id=device_id, revision=revision, deleted=True,
            ))
        elif expected_revision is None:
            # No CAS requested: unconditional delete-by-path, same as before
            # this guard existed.
            conn.execute(
                notes.update().where(notes.c.path == path).values(
                    ciphertext=b"", content_hash="", deleted=True,
                    device_id=device_id, revision=revision,
                )
            )
        else:
            if expected_revision != row["revision"]:
                raise RevisionConflict(dict(row))
            result = conn.execute(
                notes.update()
                .where(notes.c.path == path, notes.c.revision == expected_revision)
                .values(ciphertext=b"", content_hash="", deleted=True,
                        device_id=device_id, revision=revision)
            )
            if result.rowcount != 1:
                conflict_row = conn.execute(
                    select(notes).where(notes.c.path == path)
                ).mappings().first()
                raise RevisionConflict(dict(conflict_row) if conflict_row else None)
    return {"path": path, "revision": revision}


def get_note(engine: Engine, path: str) -> Optional[dict[str, Any]]:
    with engine.begin() as conn:
        row = conn.execute(select(notes).where(notes.c.path == path)).mappings().first()
        return dict(row) if row else None


def manifest_since(engine: Engine, since: int = 0) -> list[dict[str, Any]]:
    with engine.begin() as conn:
        rows = conn.execute(
            select(
                notes.c.path, notes.c.content_hash, notes.c.mtime,
                notes.c.revision, notes.c.deleted,
            ).where(notes.c.revision > since).order_by(notes.c.revision)
        ).mappings().all()
        return [dict(r) for r in rows]
