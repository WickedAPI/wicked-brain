"""vault_git.py - the shared git-commit primitive behind Phase 2 (version history).

One vault, three write paths that don't share a call stack: the agent's own
native Write/Edit tool (Claude Code and Codex CLI both use this for most
command-driven writes), the MCP server's write functions
(integrations/mcp-server/vault_ops.py), and Python scripts that write directly
(merge_notes.py, auto_merge_exact_duplicates.py). Only the first is reachable
by a Claude Code hook, and Codex CLI has no hook system at all - so this
module is the one thing every layer can call into, and it is the single
source of truth for "is this vault under version control" and "what does a
commit here look like."

Design:
- **Per-vault opt-in, no new env var.** A vault becomes version-controlled by
  having a .git/ directory - nothing here ever runs `git init` on its own.
  /brain-init offers to do that once, explicitly, with the user's confirmation.
- **Fail-soft, always.** A commit failing (git not installed, a lock held by
  another process, a detached HEAD, whatever) must never break the write that
  triggered it - these functions catch everything and report failure in their
  return value, never by raising. Mirrors note_io.py and hooks/recall.py.
- **Retry, briefly, on index.lock contention.** Multiple write paths can fire
  in quick succession (bg-agent.sh's headless propagation run is the common
  case - several Write/Edit calls back to back, each triggering its own
  validate-ai-first.sh -> `--commit` subprocess). Losing a race for
  .git/index.lock is not a real failure, just bad timing, so `add`/`commit`
  retry with a short jittered backoff (see `_LOCK_RETRY_*`) before giving up.
  This was a real gap once: a losing commit failed silently (the shell hook
  swallows the error with `|| true`) and its file's edit sat uncommitted in
  the working tree indefinitely, discovered only by manually diffing against
  `git log`.
- **One commit per logical operation, not per byte-write.** Callers pass every
  path touched by one operation (a merge touches two files) so history reads
  as "what happened," not "what write() calls fired."
"""
from __future__ import annotations

import json
import random
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_TIMEOUT = 10  # seconds - a local git op on a personal vault should never take longer

# Retry policy for operations that take .git/index.lock (add, commit). Real
# contention here is brief - one concurrent `git commit` finishing, not a
# stuck process - so a handful of short, jittered retries clears it without
# meaningfully slowing down the caller. See maybe_commit's docstring for why
# this exists: bg-agent.sh's headless run fires several Write/Edit calls back
# to back, each triggering its own validate-ai-first.sh -> vault_git.py
# --commit subprocess, and those raced on the lock before this existed - one
# loser failed silently (`|| true` in the hook) and its file's history gap
# was found only by manually diffing the working tree against `git log`.
_LOCK_RETRY_ATTEMPTS = 5
_LOCK_RETRY_BASE_DELAY = 0.1  # seconds
_LOCK_RETRY_MAX_DELAY = 0.4  # seconds
_LOCK_ERROR_MARKERS = ("index.lock", "Another git process seems to be running")


def is_git_vault(vault: Path) -> bool:
    """True if `vault` is (the root of) a git repository."""
    try:
        return (Path(vault) / ".git").exists()
    except OSError:
        return False


def _run(vault: Path, args: list[str], *, retry_on_lock: bool = False) -> subprocess.CompletedProcess:
    """Run one git subcommand. Pass `retry_on_lock=True` only for calls that
    actually take .git/index.lock (`add`, `commit`) - read-only calls never
    contend for it and should fail (or succeed) on the first try."""
    attempts = _LOCK_RETRY_ATTEMPTS if retry_on_lock else 1
    delay = _LOCK_RETRY_BASE_DELAY
    result = None
    for attempt in range(attempts):
        result = subprocess.run(
            ["git", "-C", str(vault), *args],
            capture_output=True, text=True, timeout=_TIMEOUT,
        )
        if result.returncode == 0 or not any(marker in result.stderr for marker in _LOCK_ERROR_MARKERS):
            return result
        if attempt < attempts - 1:
            time.sleep(delay + random.uniform(0, delay))
            delay = min(delay * 2, _LOCK_RETRY_MAX_DELAY)
    return result


def maybe_commit(vault: Path, paths: str | list[str], message: str) -> dict:
    """Stage and commit `paths` (vault-relative) with `message`, if `vault` is a
    git repo. No-ops safely otherwise - the return value says which happened.

    Returns {"committed": bool, "hash": str | None, "reason": str | None}.
    Never raises: every failure mode (git missing, nothing to commit, a lock
    held by a concurrent write) is reported in the return value instead.
    """
    vault = Path(vault)
    if isinstance(paths, str):
        paths = [paths]
    if not paths:
        return {"committed": False, "hash": None, "reason": "no paths given"}
    if not is_git_vault(vault):
        return {"committed": False, "hash": None, "reason": "not a git vault"}

    try:
        # -A (not plain add) so a path that no longer exists (a move's old
        # location, a delete) is staged as a removal instead of erroring with
        # "did not match any files" - callers pass both sides of a move/rename.
        add = _run(vault, ["add", "-A", "--", *paths], retry_on_lock=True)
        if add.returncode != 0:
            return {"committed": False, "hash": None, "reason": f"git add failed: {add.stderr.strip()}"}

        # Nothing to commit (a re-save that produced byte-identical content,
        # or a race with another commit) is not an error - it is the common
        # case for a no-op write and must not clutter logs as one.
        diff = _run(vault, ["diff", "--cached", "--quiet"])
        if diff.returncode == 0:
            return {"committed": False, "hash": None, "reason": "no changes to commit"}

        commit = _run(vault, ["commit", "-q", "-m", message], retry_on_lock=True)
        if commit.returncode != 0:
            return {"committed": False, "hash": None, "reason": f"git commit failed: {commit.stderr.strip()}"}

        rev = _run(vault, ["rev-parse", "--short", "HEAD"])
        commit_hash = rev.stdout.strip() if rev.returncode == 0 else None
        return {"committed": True, "hash": commit_hash, "reason": None}
    except (OSError, subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
        return {"committed": False, "hash": None, "reason": f"{type(e).__name__}: {e}"}


def git_log(vault: Path, rel_path: str, limit: int = 30) -> list[dict]:
    """Commit history for one note, newest first. Empty list if the vault
    isn't a git repo, the path has no history, or anything else goes wrong."""
    vault = Path(vault)
    if not is_git_vault(vault):
        return []
    try:
        # \x1f (unit separator) as the field delimiter: a commit message will
        # never contain it, unlike a comma or pipe.
        result = _run(vault, [
            "log", "--follow", f"-n{max(1, int(limit))}",
            "--pretty=format:%H\x1f%ad\x1f%s", "--date=iso-strict",
            "--", rel_path,
        ])
        if result.returncode != 0 or not result.stdout.strip():
            return []
        entries = []
        for line in result.stdout.splitlines():
            parts = line.split("\x1f", 2)
            if len(parts) == 3:
                entries.append({"hash": parts[0], "date": parts[1], "message": parts[2]})
        return entries
    except (OSError, subprocess.TimeoutExpired, subprocess.SubprocessError):
        return []


def git_diff(vault: Path, rel_path: str, commit_hash: str) -> str:
    """Unified diff for one note at one commit. Empty string on any failure -
    never raises, since this only ever feeds a dashboard display."""
    vault = Path(vault)
    if not is_git_vault(vault):
        return ""
    # Reject anything that isn't a plausible git revision before it reaches a
    # shell-adjacent subprocess arg - defense in depth, not a real trust
    # boundary here since this only ever runs against the local vault.
    if not commit_hash or not all(c.isalnum() for c in commit_hash):
        return ""
    try:
        result = _run(vault, ["show", "--unified=3", "--pretty=format:", commit_hash, "--", rel_path])
        return result.stdout if result.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired, subprocess.SubprocessError):
        return ""


def git_show_file(vault: Path, rel_path: str, commit_hash: str) -> str | None:
    """The full text content of one note as it existed at one historical
    commit. None on any failure (not a git vault, bad hash, the path didn't
    exist at that commit) - never raises. Feeds the dashboard's "revert to
    this version" action (write this text back as the note's current
    content, then commit that as a new commit - never a hard reset, so the
    version being reverted away from stays fully recoverable in history too).
    Same commit_hash validation as git_diff - defense in depth, not a real
    trust boundary here since this only ever runs against the local vault."""
    vault = Path(vault)
    if not is_git_vault(vault):
        return None
    if not commit_hash or not all(c.isalnum() for c in commit_hash):
        return None
    try:
        result = _run(vault, ["show", f"{commit_hash}:{rel_path}"])
        return result.stdout if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, subprocess.SubprocessError):
        return None


def activity_by_day(vault: Path, days: int = 365) -> list[dict]:
    """Per-day commit/note/line counts for the last `days` days, oldest
    first - the data behind the dashboard's GitHub-style activity heatmap.
    Empty list if the vault isn't a git repo or anything goes wrong.

    Phase 2's design already makes near-every vault write its own commit
    (the write-time hook, the MCP write path, and the Codex/no-hook
    commands all call maybe_commit), so commit count and lines
    inserted/deleted per day are a real, not approximated, measure of
    vault activity - not a synthetic metric invented for the chart.

    One `git log --numstat` call, not `days` separate calls - a numstat
    block is a blank-line-separated group per commit: one "C\\x1f<date>"
    marker line (from --pretty), then one tab-separated
    "<added>\\t<deleted>\\t<path>" line per file that commit touched (or
    "-\\t-\\t<path>" for a binary file, which does not count toward lines).
    """
    vault = Path(vault)
    if not is_git_vault(vault):
        return []
    try:
        result = _run(vault, [
            "log", f"--since={max(1, int(days))} days ago", "--date=short",
            "--pretty=format:C\x1f%ad", "--numstat",
        ])
        if result.returncode != 0:
            return []
        by_day: dict[str, dict] = {}
        current_date = None
        for line in result.stdout.splitlines():
            if line.startswith("C\x1f"):
                current_date = line.split("\x1f", 1)[1]
                entry = by_day.setdefault(current_date, {
                    "date": current_date, "commits": 0, "notes_touched": 0,
                    "insertions": 0, "deletions": 0,
                })
                entry["commits"] += 1
                continue
            if current_date is None or not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) != 3:
                continue
            added, deleted, _path = parts
            entry = by_day[current_date]
            entry["notes_touched"] += 1
            if added.isdigit():
                entry["insertions"] += int(added)
            if deleted.isdigit():
                entry["deletions"] += int(deleted)
        return sorted(by_day.values(), key=lambda e: e["date"])
    except (OSError, subprocess.TimeoutExpired, subprocess.SubprocessError):
        return []


def git_status_summary(vault: Path) -> dict:
    """A small badge's worth of state: is this a git vault, current branch,
    how many files are dirty, how many commits exist."""
    vault = Path(vault)
    if not is_git_vault(vault):
        return {"is_git_vault": False}
    try:
        branch = _run(vault, ["rev-parse", "--abbrev-ref", "HEAD"])
        status = _run(vault, ["status", "--porcelain"])
        count = _run(vault, ["rev-list", "--count", "HEAD"])
        dirty = len([ln for ln in status.stdout.splitlines() if ln.strip()]) if status.returncode == 0 else None
        return {
            "is_git_vault": True,
            "branch": branch.stdout.strip() if branch.returncode == 0 else None,
            "dirty_files": dirty,
            "commit_count": int(count.stdout.strip()) if count.returncode == 0 and count.stdout.strip().isdigit() else None,
        }
    except (OSError, subprocess.TimeoutExpired, subprocess.SubprocessError):
        return {"is_git_vault": True, "branch": None, "dirty_files": None, "commit_count": None}


def init_vault_repo(vault: Path) -> dict:
    """Turn an existing vault into a git repo: `git init`, a vault-appropriate
    .gitignore (only written if absent), and one initial commit. Idempotent -
    safe to call on a vault that's already a repo (returns early).

    This is the only function in this module that ever runs `git init` - and
    even it only runs when a caller (currently just /brain-init, with the user's
    explicit confirmation) decides to. Everything else in this module treats
    "no .git/" as "stay out of it."
    """
    vault = Path(vault)
    if is_git_vault(vault):
        return {"initialized": False, "reason": "already a git vault"}
    try:
        init = _run(vault, ["init", "-q"])
        if init.returncode != 0:
            return {"initialized": False, "reason": f"git init failed: {init.stderr.strip()}"}

        gitignore = vault / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text(
                "# Runtime artifacts, not vault content\n"
                ".claude-runs/\n"
                "*.semantic-index.json\n"
                ".claude-lock\n"
                "# Phase 3 sync - per-device cursor state and salt, never vault content\n"
                ".sync-state.json\n"
                ".sync-salt\n",
                encoding="utf-8",
            )

        result = maybe_commit(vault, ["."], "Initial commit (wicked-brain vault, version history enabled)")
        return {"initialized": True, "first_commit": result}
    except (OSError, subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
        return {"initialized": False, "reason": f"{type(e).__name__}: {e}"}


def _main(argv: list[str]) -> int:
    """CLI wrapper so shell hooks (hooks/validate-ai-first.sh) can call this
    without a Python import - `uv run scripts/vault_git.py --path <vault>
    --commit <rel_path> [<rel_path> ...] --message <msg>`."""
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--path", required=True, help="vault root")
    ap.add_argument("--commit", nargs="+", metavar="REL_PATH", help="paths (vault-relative) to stage and commit")
    ap.add_argument("--message", default="vault update")
    ap.add_argument("--init", action="store_true", help="git init the vault + .gitignore + first commit")
    ap.add_argument("--status", action="store_true", help="print git_status_summary as JSON")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv[1:])
    vault = Path(args.path).expanduser()

    if args.init:
        out = init_vault_repo(vault)
    elif args.status:
        out = git_status_summary(vault)
    elif args.commit:
        out = maybe_commit(vault, args.commit, args.message)
    else:
        ap.error("one of --commit, --init, --status is required")
        return 2

    if args.json:
        print(json.dumps(out))
    else:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
