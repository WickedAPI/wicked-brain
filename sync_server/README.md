# Wicked Brain sync server

The Phase 3 sync API - self-hosted by you, talked to by `scripts/vault_sync.py`
on each device. This service stores **client-side-encrypted note content
only**: it never sees plaintext and never holds the encryption key.

## What it can and can't see

It **can** see: note paths (e.g. `entities/Jane Doe.md`), content hashes,
timestamps, device IDs, and ciphertext blobs it cannot decrypt.

It **cannot** see: the plaintext of any note, or the passphrase/key that
would let it decrypt one.

**Known limitation, not an oversight:** paths themselves are not encrypted.
If your vault's folder or file names are sensitive on their own (independent
of their content), that's visible to anyone with access to this service or
its database - a real E2E path-encryption scheme would need a client-side
path-hash mapping, which breaks efficient prefix/folder queries and adds real
complexity. Out of scope for v1; revisit if it matters for your vault.

## Endpoints

All require `Authorization: Bearer <SYNC_TOKEN>` except `/health`.

| Method | Path | What |
|---|---|---|
| GET | `/health` | Liveness check |
| GET | `/salt` | The passphrase-derivation salt (not secret, just needs to be consistent across devices) |
| POST | `/salt` | Establish the salt - only once; rejects if one already exists |
| GET | `/manifest?since=<revision>` | Every note changed after `since` - `[{path, content_hash, mtime, revision, deleted}]` |
| GET | `/notes/{path}` | Fetch one note's ciphertext + metadata |
| PUT | `/notes/{path}` | Upload (upsert) one note's ciphertext + metadata |
| DELETE | `/notes/{path}` | Tombstone one note (soft-delete - `deleted: true`, never a hard row delete) |

## Storage

SQLAlchemy Core over `DATABASE_URL` - Postgres in production (any managed Postgres), SQLite
locally/in tests. Two tables: `notes` (ciphertext + metadata, keyed by path)
and `salt` (one row). `revision` is `time.time_ns()` at write time, not a
database sequence - see `db.py`'s module docstring for why.

## Run locally

```bash
DATABASE_URL=sqlite:///./sync.db SYNC_TOKEN=dev-token uv run uvicorn sync_server.server:app --reload
```

## Deploy

Run it anywhere that can host a container or a Python process (a small VPS with
Docker Compose, Railway, Fly.io). Point `DATABASE_URL` at Postgres (or a SQLite file for a
single-user box) and set `SYNC_TOKEN` to a long random secret; the same value goes into
`WICKED_BRAIN_SYNC_TOKEN` on every device that syncs. Put it behind HTTPS. The server only
ever stores client-side-encrypted content, but the token is what lets a device read and write
it, so keep it private.
