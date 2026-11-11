#!/usr/bin/env python3
"""Opt-in automatic vault sync (an off-machine backup of the vault).

Registered on SessionStart, PostCompact and SessionEnd. Ships INERT: nothing
happens unless WICKED_BRAIN_AUTO_SYNC_ENABLED=1 (the plugin's "Auto-sync" /config
toggle, default off) AND the vault path and all three sync credentials are set.

Design rules:
  - The hook itself returns in milliseconds. It spawns a detached child
    (`auto_sync.py --run`) that does the actual `vault_sync.py sync`, so a slow
    network never delays a session start or end.
  - Failures are never silent: every run writes <vault>/.claude-runs/auto-sync-last.json
    plus a daily JSONL log, and the next SessionStart tells the model (and so the
    user) if the last run failed or produced sync conflicts.
  - Safe with several chats open: a lock file prevents overlapping runs and a
    short minimum gap debounces bursts. Genuine edit conflicts are never
    overwritten - vault_sync saves the losing side as a conflict-copy note.
  - Credentials reach the child through the environment only, never argv.

Tunables (env): WICKED_BRAIN_AUTO_SYNC_MIN_GAP_SECONDS (default 120).
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

LOCK_STALE_SECONDS = 600
SYNC_TIMEOUT_SECONDS = 300
DEFAULT_MIN_GAP_SECONDS = 120
REQUIRED = ("WICKED_BRAIN_VAULT_PATH", "WICKED_BRAIN_SYNC_URL", "WICKED_BRAIN_SYNC_TOKEN", "WICKED_BRAIN_SYNC_PASSPHRASE")
SECRET_VARS = ("WICKED_BRAIN_SYNC_TOKEN", "WICKED_BRAIN_SYNC_PASSPHRASE")


def enabled(env) -> bool:
    return env.get("WICKED_BRAIN_AUTO_SYNC_ENABLED", "") == "1"


def missing_config(env) -> list[str]:
    return [name for name in REQUIRED if not env.get(name)]


def runs_dir(vault: str) -> Path:
    return Path(vault) / ".claude-runs"


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_json_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def scrub(text: str, env) -> str:
    for name in SECRET_VARS:
        secret = env.get(name)
        if secret:
            text = text.replace(secret, "***")
    return text


def too_soon(vault: str, now: float, gap: float) -> bool:
    last = read_json(runs_dir(vault) / "auto-sync-last.json")
    return bool(last) and now - float(last.get("finished_epoch", 0)) < gap


def acquire_lock(vault: str, now: float) -> bool:
    lock = runs_dir(vault) / "auto-sync.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                if now - lock.stat().st_mtime < LOCK_STALE_SECONDS:
                    return False
                lock.unlink()  # stale: a crashed run never released it
            except OSError:
                return False
            continue
        with os.fdopen(fd, "w") as f:
            f.write(str(os.getpid()))
        return True
    return False


def release_lock(vault: str) -> None:
    try:
        (runs_dir(vault) / "auto-sync.lock").unlink()
    except OSError:
        pass


def session_notice(vault: str, env) -> str:
    """One line for the model/user at SessionStart, or '' when all is well."""
    missing = missing_config(env)
    if missing:
        return ("Wicked Brain auto-sync is turned on but not configured - missing: "
                + ", ".join(missing) + ". It will not run until these are set (see /config).")
    last = read_json(runs_dir(vault) / "auto-sync-last.json")
    if not last:
        return ""
    if not last.get("ok"):
        return (f"Wicked Brain auto-sync FAILED at {last.get('finished_at', '?')}: "
                f"{last.get('error', 'unknown error')}. Your latest notes may not be backed up. "
                "Run /brain-sync to see the full error.")
    n = len(last.get("conflicts", []))
    if n:
        return (f"Wicked Brain auto-sync finished with {n} conflict(s): the losing version of each was saved "
                "as a '(sync-conflict ...)' note in the vault. Review and merge them (/brain-merge).")
    return ""


# CREATE_NO_WINDOW gives the child its own hidden console, which uv and git then inherit, so no
# window ever appears. DETACHED_PROCESS must NOT be used: the child would have no console and every
# console program it launched (uv, git) would pop up a visible one. CREATE_NEW_PROCESS_GROUP keeps a
# Ctrl-C typed in the user's terminal from reaching the sync.
_WIN_HIDDEN = 0x08000000
_WIN_NEW_PROCESS_GROUP = 0x00000200


def spawn_detached(args: list[str]) -> None:
    kw: dict = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, close_fds=True)
    if os.name == "nt":
        kw["creationflags"] = _WIN_HIDDEN | _WIN_NEW_PROCESS_GROUP
    else:
        kw["start_new_session"] = True
    subprocess.Popen(args, **kw)


def hook_main(payload: dict, env=os.environ, now=time.time) -> dict | None:
    """The hook entry. Returns SessionStart output JSON to print, or None."""
    if not enabled(env):
        return None
    event = payload.get("hook_event_name", "")
    vault = env.get("WICKED_BRAIN_VAULT_PATH", "")
    out = None
    if event == "SessionStart":
        notice = session_notice(vault, env) if vault else ""
        if notice:
            out = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": notice}}
    if missing_config(env):
        return out
    gap = float(env.get("WICKED_BRAIN_AUTO_SYNC_MIN_GAP_SECONDS", DEFAULT_MIN_GAP_SECONDS))
    if too_soon(vault, now(), gap):
        return out
    spawn_detached([sys.executable, str(Path(__file__).resolve()), "--run", event or "unknown"])
    return out


def child_main(trigger: str, env=os.environ, now=time.time, run=subprocess.run) -> dict | None:
    """Run one sync and record the outcome. Returns the record (None if skipped)."""
    if enabled(env) is False or missing_config(env):
        return None
    vault = env["WICKED_BRAIN_VAULT_PATH"]
    started = now()
    if not acquire_lock(vault, started):
        return None
    record: dict = {"trigger": trigger, "started_epoch": started,
                    "started_at": datetime.fromtimestamp(started, tz=timezone.utc).isoformat()}
    try:
        root = Path(__file__).resolve().parents[1]
        cmd = ["uv", "run", "--directory", str(root), "python", "scripts/vault_sync.py", "sync",
               "--path", vault, "--device", env.get("WICKED_BRAIN_DEVICE") or socket.gethostname(), "--json"]
        try:
            flags = {"creationflags": _WIN_HIDDEN | _WIN_NEW_PROCESS_GROUP} if os.name == "nt" else {}
            res = run(cmd, capture_output=True, text=True, timeout=SYNC_TIMEOUT_SECONDS, env=dict(env), **flags)
            result = None
            if res.returncode == 0:
                try:
                    result = json.loads(res.stdout)
                except ValueError:
                    pass
            if result is None:
                tail = (res.stderr or res.stdout or "no output").strip().splitlines()[-1:]
                record.update(ok=False, error=scrub(f"exit {res.returncode}: {' '.join(tail)}"[:300], env))
            else:
                record.update(ok=True, pushed=result.get("pushed", []), pulled=result.get("pulled", []),
                              conflicts=result.get("conflicts", []), trashed=result.get("trashed_local", []))
        except FileNotFoundError:
            record.update(ok=False, error="`uv` was not found on PATH")
        except subprocess.TimeoutExpired:
            record.update(ok=False, error=f"timed out after {SYNC_TIMEOUT_SECONDS}s")
        finished = now()
        record["finished_epoch"] = finished
        record["finished_at"] = datetime.fromtimestamp(finished, tz=timezone.utc).isoformat()
        write_json_atomic(runs_dir(vault) / "auto-sync-last.json", record)
        day = datetime.fromtimestamp(finished, tz=timezone.utc).strftime("%Y-%m-%d")
        with open(runs_dir(vault) / f"auto-sync-{day}.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
        return record
    finally:
        release_lock(vault)


def main(argv: list[str]) -> int:
    try:
        if len(argv) >= 2 and argv[1] == "--run":
            child_main(argv[2] if len(argv) > 2 else "unknown")
            return 0
        try:
            payload = json.load(sys.stdin)
        except ValueError:
            payload = {}
        out = hook_main(payload)
        if out:
            json.dump(out, sys.stdout)
    except Exception as exc:  # a backup helper must never break a session
        print(f"wicked-brain auto-sync hook error: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
