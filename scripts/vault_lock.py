"""vault_lock.py - the one cross-process advisory write lock every write path
in this vault shares: the MCP server (integrations/mcp-server/vault_ops.py's
_write_lock - a separate literal copy, since the MCP server ships standalone
and must not import scripts/, same reasoning as its _SKIP_DIRS literal), the
scripts/ write paths (merge_notes.py, auto_merge_exact_duplicates.py), and -
via the CLI below - an agent's own native Read/Write tool, wrapped by a shell
step per references/write-rules.md's concurrent-write section.

Same lock file, same protocol, on purpose: two different codebases racing on
the same vault must contend for the SAME lock, or the lock protects nothing.

Found 2026-09-10, in a follow-up review after Codex Astra's original 8-issue
report and its MCP-only fix (vault_ops.py's _write_lock): the primary,
most-commonly-invoked write commands (/brain-save, /brain-capture,
/brain-reconcile) instruct the agent to use its own native Write/Edit tool
directly, not the MCP server's tool functions - so the MCP-only lock left the
actual common case completely unprotected. scripts/merge_notes.py (used by
/brain-merge and the background post-compaction auto-merge) writes directly
too, same gap.

Usage from Python (scripts/):
    from vault_lock import write_lock
    with write_lock(vault):
        ...read, modify, write...

Usage from a shell step (an agent's own native tool call, which no Python
context manager can wrap):
    uv run python scripts/vault_lock.py acquire --path "<vault>"
    # ...agent's own Read, then Write/Edit tool call, then...
    uv run python scripts/vault_lock.py release --path "<vault>"
`acquire` exits 0 once the lock is held (blocking up to --wait seconds) or 1
with a message on stderr if it timed out. `release` always exits 0 (a
missing lock file is not an error - nothing left to release).
"""
from __future__ import annotations

import contextlib
import os
import sys
import time
from pathlib import Path

WRITE_LOCK_TTL = 30    # seconds - a stale lock (holder crashed/killed before
                        # releasing) self-heals after this rather than
                        # wedging the vault forever.
WRITE_LOCK_WAIT = 10   # seconds - how long one acquire attempt blocks before
                        # giving up.


def _lock_path(vault: Path) -> Path:
    return vault / ".claude-runs" / ".write.lock"


def _try_acquire(lock_path: Path, ttl: float) -> bool:
    """One non-blocking attempt. True if acquired, False if held by someone
    else and not yet stale (a stale lock is stolen here, not just detected -
    the caller's next attempt will then succeed)."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
        return True
    except FileExistsError:
        try:
            age = time.time() - lock_path.stat().st_mtime
        except OSError:
            return False  # vanished between our failed create and this stat: treat as still-contended, retry
        if age > ttl:
            try:
                lock_path.unlink()
            except OSError:
                pass  # another waiter may have won the steal race; the next attempt's O_EXCL still decides
        return False


def acquire(vault: Path, *, ttl: float = WRITE_LOCK_TTL, wait: float = WRITE_LOCK_WAIT) -> None:
    """Blocks until the lock is held or `wait` seconds pass, then raises
    TimeoutError. Never leaves a half-acquired state - either this returns
    with the lock genuinely held, or it raised and holds nothing."""
    lock_path = _lock_path(vault)
    deadline = time.time() + wait
    while not _try_acquire(lock_path, ttl):
        if time.time() >= deadline:
            raise TimeoutError("vault is busy (another write is in progress) - retry in a moment")
        time.sleep(0.1)


def release(vault: Path) -> None:
    try:
        _lock_path(vault).unlink()
    except OSError:
        pass  # nothing to release, or another process's stale-lock steal beat us to it - either way, fine


@contextlib.contextmanager
def write_lock(vault: Path, *, ttl: float = WRITE_LOCK_TTL, wait: float = WRITE_LOCK_WAIT):
    """The read-modify-write critical section of a script's own write, guarded
    across every process and codebase that shares this vault. See module
    docstring."""
    acquire(vault, ttl=ttl, wait=wait)
    try:
        yield
    finally:
        release(vault)


def _main(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(
        description="Acquire or release the vault's write lock from a shell step "
                    "(for an agent's own native Read/Write tool call - see module docstring)."
    )
    ap.add_argument("action", choices=["acquire", "release"])
    ap.add_argument("--path", required=True, help="vault root")
    ap.add_argument("--ttl", type=float, default=WRITE_LOCK_TTL)
    ap.add_argument("--wait", type=float, default=WRITE_LOCK_WAIT)
    args = ap.parse_args(argv[1:])
    vault = Path(args.path).expanduser()

    if args.action == "acquire":
        try:
            acquire(vault, ttl=args.ttl, wait=args.wait)
        except TimeoutError as e:
            print(str(e), file=sys.stderr)
            return 1
        return 0
    release(vault)
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
