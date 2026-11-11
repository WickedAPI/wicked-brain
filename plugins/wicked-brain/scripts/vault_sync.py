"""vault_sync.py - the Phase 3 sync client. Talks to sync_server/ over HTTP,
encrypting/decrypting locally via vault_crypto.py - the server never sees
plaintext.

Each device keeps a private, git-ignored `.sync-state.json` at the vault
root: its own record of what it last knew to be true ({content_hash,
revision} per path). Every sync is a three-way diff against that cursor -
NOT a raw local-vs-remote comparison, which would treat "I haven't changed
this since we last agreed" as a conflict every time. See sync() below for
the five cases this produces.

Usage (also see commands/brain-sync.md):
    python scripts/vault_sync.py sync --path <vault> --url <base_url> \
        --token <token> --passphrase <passphrase> --device <device_id>
    python scripts/vault_sync.py bootstrap --path <vault> ...   # new device, no local state yet
"""
from __future__ import annotations

import base64
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
import note_io  # noqa: E402
import vault_crypto  # noqa: E402
import vault_git  # noqa: E402
import vault_scan  # noqa: E402

STATE_FILE = ".sync-state.json"
SALT_FILE = ".sync-salt"


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #

def _request(method: str, url: str, token: str, body: Optional[dict] = None) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    # Some fronting proxies (e.g. Cloudflare bot-fight mode, seen on the live
    # sync server's custom domain) fingerprint and 403 Python's default
    # `Python-urllib/x.y` User-Agent as a bot signature. A real UA string
    # avoids that false positive without weakening auth (the bearer token
    # still gates every request).
    req.add_header("User-Agent", "Wicked Brain-Sync-Client/1.0")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _note_url(base_url: str, rel: str) -> str:
    return f"{base_url}/notes/{quote(rel, safe='/')}"


# --------------------------------------------------------------------------- #
# Local vault + state I/O
# --------------------------------------------------------------------------- #

def iter_local_notes(vault: Path):
    excludes = vault_scan.excluded_dirs()
    for md in vault.rglob("*.md"):
        parts = md.relative_to(vault).parts
        if vault_scan.is_excluded(parts, excludes):
            continue
        if md.is_file():
            yield md.relative_to(vault).as_posix()


def _load_state(vault: Path) -> dict:
    f = vault / STATE_FILE
    if not f.exists():
        return {"notes": {}}
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"notes": {}}


def _save_state(vault: Path, state: dict) -> None:
    note_io.write_exact(vault / STATE_FILE, json.dumps(state, indent=2))


def _local_hash(vault: Path, rel: str) -> Optional[str]:
    text = note_io.read_exact(vault / rel)
    if text is None:
        return None
    return vault_crypto.content_hash(text.encode("utf-8"))


def _trash_local(vault: Path, rel: str) -> None:
    """Never a hard delete - move to _trash/, same philosophy as write-rules.md."""
    src = vault / rel
    if not src.exists():
        return
    trash_dir = vault / "_trash"
    trash_dir.mkdir(exist_ok=True)
    dest = trash_dir / Path(rel).name
    i = 1
    while dest.exists():
        dest = trash_dir / f"{Path(rel).stem} (removed remotely {i}){Path(rel).suffix}"
        i += 1
    src.rename(dest)


def _write_conflict_copy(vault: Path, rel: str, text: str, device_label: str) -> str:
    """Save content that lost a conflict, so it's never silently discarded."""
    p = Path(rel)
    date = datetime.now().strftime("%Y-%m-%d")
    conflict_rel = str(p.with_name(f"{p.stem} (sync-conflict, {device_label}, {date}){p.suffix}"))
    dest = vault / conflict_rel
    i = 1
    while dest.exists():
        conflict_rel = str(p.with_name(f"{p.stem} (sync-conflict, {device_label}, {date}) ({i}){p.suffix}"))
        dest = vault / conflict_rel
        i += 1
    dest.parent.mkdir(parents=True, exist_ok=True)
    note_io.write_exact(dest, text)
    vault_git.maybe_commit(vault, [conflict_rel], f"sync: conflict copy for {rel}")
    return conflict_rel


# --------------------------------------------------------------------------- #
# Salt bootstrap
# --------------------------------------------------------------------------- #

def ensure_salt(vault: Path, base_url: str, token: str) -> bytes:
    vault.mkdir(parents=True, exist_ok=True)  # a brand-new device's vault dir may not exist yet
    local = vault / SALT_FILE
    if local.exists():
        local_b64 = local.read_text(encoding="utf-8").strip()
        try:
            remote_b64 = _request("GET", f"{base_url}/salt", token)["value"]
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
            # A replacement server that has never seen this vault's salt (found
            # 2026-10-14 after the old server was lost): register ours. Otherwise
            # the next brand-new device would mint a different salt and derive a
            # different key. A concurrent registration (409) falls through to the
            # comparison below.
            try:
                _request("POST", f"{base_url}/salt", token, {"value": local_b64})
                return base64.b64decode(local_b64)
            except urllib.error.HTTPError as post_err:
                if post_err.code != 409:
                    raise
                remote_b64 = _request("GET", f"{base_url}/salt", token)["value"]
        if remote_b64 != local_b64:
            raise SaltMismatch(
                "this vault's local salt differs from the sync server's salt, so its notes cannot be "
                "decrypted with the key derived here. Do not sync against this server; the server was "
                "probably re-created by a different device. Restore the original .sync-salt, or bootstrap "
                "from the server into a fresh vault directory."
            )
        return base64.b64decode(local_b64)
    try:
        resp = _request("GET", f"{base_url}/salt", token)
        salt = base64.b64decode(resp["value"])
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
        salt = vault_crypto.new_salt()
        _request("POST", f"{base_url}/salt", token, {"value": base64.b64encode(salt).decode("ascii")})
    local.write_text(base64.b64encode(salt).decode("ascii") + "\n", encoding="utf-8")
    return salt


def _verify_passphrase(base_url: str, token: str, key: bytes, remote_by_path: dict) -> None:
    """Decrypt ONE existing remote note before sync() allows any push, so a
    mistyped passphrase fails loudly right here instead of silently
    corrupting the vault.

    Regression (found 2026-09-10 via Codex Astra's report, reproduced
    against a real local server before this fix): _push_one never verified
    the derived key against anything - a device with a one-letter passphrase
    typo would happily re-encrypt its local notes under the wrong key and
    overwrite good remote content, reporting full success. Every OTHER
    device (with the correct passphrase) would then fail with
    WrongPassphrase trying to read that note - the corruption was silent at
    write time and only surfaced, confusingly, on a totally different
    device later.

    The salt alone can't catch this (it's not secret and works arithmetically
    with any passphrase - it's not a verifier). Bootstrap already fails
    loudly because it always decrypts something up front; sync() didn't, on
    a device with nothing new to pull. If the remote is empty (first-ever
    device pushing to a fresh vault), there's nothing to verify against -
    whoever pushes first defines what "correct" means for this vault, same
    as it always has.
    """
    live = [m for m in remote_by_path.values() if not m.get("deleted")]
    if not live:
        return
    sample = min(live, key=lambda m: m["path"])  # deterministic, not security-relevant
    fetched = _request("GET", _note_url(base_url, sample["path"]), token)
    vault_crypto.decrypt(base64.b64decode(fetched["ciphertext"]), key)  # raises WrongPassphrase on mismatch


# --------------------------------------------------------------------------- #
# Push / pull primitives for one note
# --------------------------------------------------------------------------- #

class SaltMismatch(RuntimeError):
    """The local .sync-salt and the server's salt disagree (different keys)."""


class RemoteConflict(Exception):
    """The server rejected a push/delete because expected_revision no longer
    matched (HTTP 409) - someone else's write landed in between this sync's
    manifest fetch and this write. `current` is the server's present state
    for the path (a dict shaped like a manifest/get_note entry, or None),
    straight from the 409 body - no second round trip needed to resolve it."""

    def __init__(self, current: Optional[dict]):
        self.current = current
        super().__init__("remote revision conflict")


def _request_expect_conflict(method: str, url: str, token: str, body: dict) -> dict:
    """Like _request, but a 409 is turned into RemoteConflict (with the
    server's current-state payload already parsed out) instead of propagating
    as an opaque HTTPError."""
    try:
        return _request(method, url, token, body)
    except urllib.error.HTTPError as e:
        if e.code != 409:
            raise
        try:
            payload = json.loads(e.read().decode("utf-8"))
        except Exception:
            payload = {}
        raise RemoteConflict((payload.get("detail") or {}).get("current")) from None


def _push_one(vault: Path, rel: str, base_url: str, token: str, key: bytes, device_id: str,
              *, expected_revision: Optional[int]) -> dict:
    """expected_revision: the revision this device last agreed was current for
    this path (0 if it believes the path is new; None to force-write,
    bypassing the check - only for a write that has already resolved a
    conflict some other way, e.g. saved the loser's content as a conflict
    copy). Raises RemoteConflict if the server's actual current revision no
    longer matches - see RemoteConflict's docstring."""
    text = note_io.read_exact(vault / rel)
    if text is None:
        raise RuntimeError(f"cannot read (not valid UTF-8?): {rel}")
    plaintext = text.encode("utf-8")
    ciphertext = vault_crypto.encrypt(plaintext, key)
    h = vault_crypto.content_hash(plaintext)
    mtime = datetime.fromtimestamp((vault / rel).stat().st_mtime, tz=timezone.utc).isoformat()
    result = _request_expect_conflict("PUT", _note_url(base_url, rel), token, {
        "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
        "content_hash": h, "mtime": mtime, "device_id": device_id,
        "expected_revision": expected_revision,
    })
    # Belt and braces: if this edit happened outside any AI write path (a
    # manual text-editor save), it may not be committed locally yet. A no-op
    # if it already is - maybe_commit only ever commits real changes.
    vault_git.maybe_commit(vault, [rel], f"sync: pushed {rel}")
    return {"content_hash": h, "revision": result["revision"]}


def _pull_one(vault: Path, rel: str, base_url: str, token: str, key: bytes) -> dict:
    resp = _request("GET", _note_url(base_url, rel), token)
    ciphertext = base64.b64decode(resp["ciphertext"])
    plaintext = vault_crypto.decrypt(ciphertext, key)
    (vault / rel).parent.mkdir(parents=True, exist_ok=True)
    note_io.write_exact(vault / rel, plaintext.decode("utf-8"))
    vault_git.maybe_commit(vault, [rel], f"sync: pulled {rel} from {resp.get('device_id') or 'remote'}")
    return {"content_hash": resp["content_hash"], "revision": resp["revision"], "text": plaintext.decode("utf-8")}


def _delete_remote(base_url: str, token: str, rel: str, device_id: str,
                    *, expected_revision: Optional[int]) -> dict:
    """Same expected_revision convention as _push_one."""
    return _request_expect_conflict(
        "DELETE", _note_url(base_url, rel), token,
        {"device_id": device_id, "expected_revision": expected_revision},
    )


def _current_from_conflict(current: Optional[dict]) -> tuple:
    """Normalize a 409's `current` payload (possibly None - see RemoteConflict)
    into (remote_hash, remote_deleted, remote_mtime_iso, remote_device_id,
    remote_revision) for _resolve_conflict. None means the server genuinely
    has nothing for this path, which _resolve_conflict treats the same as an
    ordinary remote deletion (nothing to preserve, local trivially wins)."""
    if current is None:
        return None, True, None, None, 0
    deleted = bool(current.get("deleted"))
    return (
        None if deleted else current.get("content_hash"),
        deleted,
        current.get("mtime"),
        current.get("device_id"),
        current.get("revision"),
    )


def _resolve_conflict(vault: Path, rel: str, base_url: str, token: str, key: bytes, device_id: str,
                       *, local_exists: bool, local_hash: Optional[str],
                       remote_hash: Optional[str], remote_deleted: bool,
                       remote_mtime_iso: Optional[str], remote_device_id: Optional[str],
                       remote_revision: Optional[int]) -> tuple[dict, dict]:
    """Newer mtime wins and is applied everywhere; the losing side's content
    (if any) is preserved as a local conflict-copy note, never silently
    dropped. Shared by both the initial three-way diff (a conflict visible
    up front) and a conflict only discovered via a 409 while pushing/deleting
    (see RemoteConflict) - same resolution either way.

    Once local_wins is decided here, the loser's content has already been
    preserved, so the write-back that applies the winner uses
    expected_revision=None (force) - this write is not itself re-guarded
    against a THIRD write racing in during conflict resolution. That residual
    window is far narrower (three genuinely simultaneous writers) than the
    bug this whole mechanism exists to close, and matches the single-pass
    conflict handling this vault has always used elsewhere.

    Returns (conflict_record, known_entry) - the caller appends/assigns both.
    """
    local_mtime = (vault / rel).stat().st_mtime if local_exists else -1.0
    remote_mtime = datetime.fromisoformat(remote_mtime_iso).timestamp() if remote_mtime_iso else -1.0
    local_wins = local_mtime >= remote_mtime

    if local_wins:
        if remote_hash is not None:  # remote had real content worth preserving
            fetched = _request("GET", _note_url(base_url, rel), token)
            remote_text = vault_crypto.decrypt(base64.b64decode(fetched["ciphertext"]), key).decode("utf-8")
            conflict_path = _write_conflict_copy(vault, rel, remote_text, remote_device_id or "remote")
            conflict_record = {"path": rel, "kept": "local", "conflict_copy": conflict_path}
        else:
            conflict_record = {"path": rel, "kept": "local", "conflict_copy": None}
        if local_exists:
            pushed = _push_one(vault, rel, base_url, token, key, device_id, expected_revision=None)
            known_entry = {"content_hash": pushed["content_hash"], "revision": pushed["revision"]}
        else:
            resp = _delete_remote(base_url, token, rel, device_id, expected_revision=None)
            known_entry = {"content_hash": None, "revision": resp["revision"]}
    else:
        if local_hash is not None:  # local had real content worth preserving
            local_text = note_io.read_exact(vault / rel)
            conflict_path = _write_conflict_copy(vault, rel, local_text, device_id)
            conflict_record = {"path": rel, "kept": "remote", "conflict_copy": conflict_path}
        else:
            conflict_record = {"path": rel, "kept": "remote", "conflict_copy": None}
        if remote_deleted:
            _trash_local(vault, rel)
            known_entry = {"content_hash": None, "revision": remote_revision}
        else:
            pulled = _pull_one(vault, rel, base_url, token, key)
            known_entry = {"content_hash": pulled["content_hash"], "revision": pulled["revision"]}
    return conflict_record, known_entry


# --------------------------------------------------------------------------- #
# The sync algorithm
# --------------------------------------------------------------------------- #

def sync(vault: Path, base_url: str, token: str, passphrase: str, device_id: str,
         *, mode: str = "sync") -> dict[str, Any]:
    """mode: 'sync' (bidirectional, conflict-aware - the default), 'push', 'pull'.

    Three-way diff per path, against this device's own last-synced hash (not
    a raw local-vs-remote comparison):
      - all three agree                          -> skip
      - only remote differs from base             -> pull (or trash, if remote tombstoned)
      - only local differs from base               -> push (or delete remote, if local removed)
      - both differ from base AND from each other  -> conflict: newer mtime wins and is
        applied everywhere; the losing side's content (if any) is saved as a
        local conflict-copy note, never silently dropped
      - both differ from base but agree with each other -> no I/O, just advance the cursor
    """
    base_url = base_url.rstrip("/")
    salt = ensure_salt(vault, base_url, token)
    key = vault_crypto.derive_key(passphrase, salt)

    state = _load_state(vault)
    known: dict[str, dict] = state.get("notes", {})

    manifest = _request("GET", f"{base_url}/manifest?since=0", token)["notes"]
    remote_by_path = {m["path"]: m for m in manifest}
    _verify_passphrase(base_url, token, key, remote_by_path)
    local_paths = set(iter_local_notes(vault))

    all_paths = set(known) | set(remote_by_path) | local_paths
    result: dict[str, Any] = {"pushed": [], "pulled": [], "deleted_remote": [], "trashed_local": [],
                               "conflicts": [], "skipped": 0, "repushed": [], "missing_on_server": []}

    for rel in sorted(all_paths):
        base_entry = known.get(rel)
        base_hash = base_entry["content_hash"] if base_entry else None

        local_exists = (vault / rel).is_file()
        local_hash = _local_hash(vault, rel) if local_exists else None

        remote_entry = remote_by_path.get(rel)
        remote_deleted = bool(remote_entry and remote_entry.get("deleted"))
        remote_hash = None if (remote_entry is None or remote_deleted) else remote_entry["content_hash"]

        # The server has no record at all (not even a tombstone - it never
        # hard-deletes) of an unchanged note this device synced before: the
        # server lost its data (replaced or restored empty). Treat the note as
        # new on the server so it is re-pushed, instead of failing on a pull of
        # something that no longer exists (HTTP 404, found 2026-10-14).
        if base_hash is not None and remote_entry is None and local_exists and local_hash == base_hash:
            if mode == "pull":
                result["missing_on_server"].append(rel)
                continue
            base_entry, base_hash = None, None
            result["repushed"].append(rel)

        if local_hash == base_hash and remote_hash == base_hash:
            result["skipped"] += 1
            continue

        remote_changed = remote_hash != base_hash
        local_changed = local_hash != base_hash

        if mode == "push":
            remote_changed = False  # never act on remote changes in push-only mode
        if mode == "pull":
            local_changed = False   # never act on local changes in pull-only mode

        if remote_changed and not local_changed:
            if remote_deleted:
                _trash_local(vault, rel)
                result["trashed_local"].append(rel)
                known[rel] = {"content_hash": None, "revision": remote_entry["revision"]}
            else:
                pulled = _pull_one(vault, rel, base_url, token, key)
                result["pulled"].append(rel)
                known[rel] = {"content_hash": pulled["content_hash"], "revision": pulled["revision"]}
            continue

        if local_changed and not remote_changed:
            # expected_revision=0 means "I believe this path is new on the
            # server" when this device has never agreed on a revision for it
            # (base_entry is None) - a real N otherwise. Either way, a 409
            # here means someone else's write landed between this sync's
            # manifest fetch and this write: an overlapping sync, not a
            # detected-up-front conflict, but resolved identically.
            expected = base_entry["revision"] if base_entry else 0
            if not local_exists:
                if base_hash is not None:  # was known before, now gone locally -> propagate delete
                    try:
                        resp = _delete_remote(base_url, token, rel, device_id, expected_revision=expected)
                        result["deleted_remote"].append(rel)
                        known[rel] = {"content_hash": None, "revision": resp["revision"]}
                    except RemoteConflict as exc:
                        r_hash, r_deleted, r_mtime, r_device, r_rev = _current_from_conflict(exc.current)
                        conflict_record, known_entry = _resolve_conflict(
                            vault, rel, base_url, token, key, device_id,
                            local_exists=False, local_hash=None,
                            remote_hash=r_hash, remote_deleted=r_deleted,
                            remote_mtime_iso=r_mtime, remote_device_id=r_device, remote_revision=r_rev,
                        )
                        result["conflicts"].append(conflict_record)
                        known[rel] = known_entry
                else:
                    known.pop(rel, None)
            else:
                try:
                    pushed = _push_one(vault, rel, base_url, token, key, device_id, expected_revision=expected)
                    result["pushed"].append(rel)
                    known[rel] = {"content_hash": pushed["content_hash"], "revision": pushed["revision"]}
                except RemoteConflict as exc:
                    r_hash, r_deleted, r_mtime, r_device, r_rev = _current_from_conflict(exc.current)
                    conflict_record, known_entry = _resolve_conflict(
                        vault, rel, base_url, token, key, device_id,
                        local_exists=True, local_hash=local_hash,
                        remote_hash=r_hash, remote_deleted=r_deleted,
                        remote_mtime_iso=r_mtime, remote_device_id=r_device, remote_revision=r_rev,
                    )
                    result["conflicts"].append(conflict_record)
                    known[rel] = known_entry
            continue

        # Both changed since the last sync.
        if local_hash == remote_hash:
            # Identical outcome on both sides - nothing to move, just agree on the cursor.
            latest_rev = remote_entry["revision"] if remote_entry else base_entry["revision"]
            known[rel] = {"content_hash": local_hash, "revision": latest_rev}
            continue

        # Genuine conflict, visible up front: newer mtime wins, loser's
        # content (if any) is preserved. Same resolution _resolve_conflict
        # applies when a conflict is only discovered via a 409 above.
        conflict_record, known_entry = _resolve_conflict(
            vault, rel, base_url, token, key, device_id,
            local_exists=local_exists, local_hash=local_hash,
            remote_hash=remote_hash, remote_deleted=remote_deleted,
            remote_mtime_iso=(remote_entry.get("mtime") if remote_entry else None),
            remote_device_id=(remote_entry.get("device_id") if remote_entry else None),
            remote_revision=(remote_entry["revision"] if remote_entry
                              else (base_entry["revision"] if base_entry else None)),
        )
        result["conflicts"].append(conflict_record)
        known[rel] = known_entry

    state["notes"] = known
    state["last_synced_at"] = datetime.now(tz=timezone.utc).isoformat()
    _save_state(vault, state)
    return result


def bootstrap(vault: Path, base_url: str, token: str, passphrase: str,
              device_id: str = "local") -> dict[str, Any]:
    """A device joining an already-synced vault (or a genuinely brand-new
    vault): fetch and decrypt everything, no diffing against a sync cursor -
    there isn't one yet.

    Unlike a truly from-scratch device, this vault path may already hold
    real, never-synced local content: every device's own /brain-init
    creates its own local _CLAUDE.md/index.md/CRITICAL_FACTS.md before that
    device ever syncs (found 2026-09-10 via Codex Astra's report,
    reproduced before this fix: bootstrapping a second real device silently
    destroyed its own genuinely-local, never-synced content at those exact
    paths, with zero warning and no backup). So a local file that already
    exists and differs from what's about to be pulled is preserved as a
    conflict copy first, never blindly overwritten - the same "never
    silently discard" philosophy sync()'s own conflict handling already
    uses. Identical content needs no conflict copy - nothing would be lost.
    """
    base_url = base_url.rstrip("/")
    salt = ensure_salt(vault, base_url, token)
    key = vault_crypto.derive_key(passphrase, salt)
    manifest = _request("GET", f"{base_url}/manifest?since=0", token)["notes"]
    remote_by_path = {m["path"]: m for m in manifest}
    _verify_passphrase(base_url, token, key, remote_by_path)
    known: dict[str, dict] = {}
    written = []
    preserved = []
    for entry in manifest:
        if entry["deleted"]:
            continue
        rel = entry["path"]
        local_path = vault / rel
        if local_path.is_file() and _local_hash(vault, rel) != entry["content_hash"]:
            local_text = note_io.read_exact(local_path)
            if local_text is not None:  # not valid UTF-8: nothing safe to preserve as text, let it be replaced
                conflict_path = _write_conflict_copy(vault, rel, local_text, device_id)
                preserved.append({"path": rel, "conflict_copy": conflict_path})
        pulled = _pull_one(vault, rel, base_url, token, key)
        known[rel] = {"content_hash": pulled["content_hash"], "revision": pulled["revision"]}
        written.append(rel)
    _save_state(vault, {"notes": known, "last_synced_at": datetime.now(tz=timezone.utc).isoformat()})
    return {"written": written, "preserved": preserved}


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _main(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["sync", "push", "pull", "bootstrap"])
    ap.add_argument("--path", required=True, help="vault root")
    # Each credential falls back to its WICKED_BRAIN_SYNC_* env var so unattended
    # callers (hooks/auto_sync.py) never put a token or passphrase in argv,
    # where any local process listing could read it.
    ap.add_argument("--url", default=os.environ.get("WICKED_BRAIN_SYNC_URL"), help="sync server base URL (or WICKED_BRAIN_SYNC_URL)")
    ap.add_argument("--token", default=os.environ.get("WICKED_BRAIN_SYNC_TOKEN"), help="(or WICKED_BRAIN_SYNC_TOKEN)")
    ap.add_argument("--passphrase", default=os.environ.get("WICKED_BRAIN_SYNC_PASSPHRASE"), help="(or WICKED_BRAIN_SYNC_PASSPHRASE)")
    ap.add_argument("--device", default="unknown-device")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv[1:])
    for flag in ("url", "token", "passphrase"):
        if not getattr(args, flag):
            ap.error(f"--{flag} is required (or set WICKED_BRAIN_SYNC_{flag.upper()})")
    vault = Path(args.path).expanduser()

    if args.command == "bootstrap":
        out = bootstrap(vault, args.url, args.token, args.passphrase, device_id=args.device)
    else:
        mode = args.command  # "sync" | "push" | "pull"
        out = sync(vault, args.url, args.token, args.passphrase, args.device, mode=mode)

    print(json.dumps(out, indent=2) if args.json else out)
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
