"""Tests for hooks/auto_sync.py - the opt-in automatic vault sync hook."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))


def _load():
    spec = importlib.util.spec_from_file_location("auto_sync", REPO_ROOT / "hooks" / "auto_sync.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


auto_sync = _load()

TOKEN, PASS = "tok-SECRET-123", "pass-SECRET-456"


def _env(vault: Path, **extra) -> dict:
    return {
        "WICKED_BRAIN_AUTO_SYNC_ENABLED": "1",
        "WICKED_BRAIN_VAULT_PATH": str(vault),
        "WICKED_BRAIN_SYNC_URL": "https://sync.example.test",
        "WICKED_BRAIN_SYNC_TOKEN": TOKEN,
        "WICKED_BRAIN_SYNC_PASSPHRASE": PASS,
        **extra,
    }


@pytest.fixture
def spawned(monkeypatch):
    calls = []
    monkeypatch.setattr(auto_sync, "spawn_detached", lambda args: calls.append(args))
    return calls


def _write_last(vault: Path, **fields):
    rec = {"ok": True, "finished_epoch": time.time() - 10_000, "finished_at": "2026-10-05T00:00:00+00:00", **fields}
    auto_sync.write_json_atomic(vault / ".claude-runs" / "auto-sync-last.json", rec)


def test_inert_unless_enabled(tmp_path, spawned):
    env = _env(tmp_path)
    env.pop("WICKED_BRAIN_AUTO_SYNC_ENABLED")
    assert auto_sync.hook_main({"hook_event_name": "SessionStart"}, env=env) is None
    assert spawned == []
    assert not (tmp_path / ".claude-runs").exists()


def test_enabled_but_unconfigured_says_so_and_does_not_spawn(tmp_path, spawned):
    env = _env(tmp_path)
    env.pop("WICKED_BRAIN_SYNC_PASSPHRASE")
    out = auto_sync.hook_main({"hook_event_name": "SessionStart"}, env=env)
    assert "WICKED_BRAIN_SYNC_PASSPHRASE" in out["hookSpecificOutput"]["additionalContext"]
    assert spawned == []
    # Other events stay quiet rather than nagging mid-session.
    assert auto_sync.hook_main({"hook_event_name": "SessionEnd"}, env=env) is None


@pytest.mark.parametrize("event", ["SessionStart", "PostCompact", "SessionEnd"])
def test_spawns_a_detached_run_for_each_event(tmp_path, spawned, event):
    out = auto_sync.hook_main({"hook_event_name": event}, env=_env(tmp_path))
    assert out is None
    assert len(spawned) == 1 and spawned[0][-2:] == ["--run", event]
    assert TOKEN not in " ".join(spawned[0]) and PASS not in " ".join(spawned[0])


def test_debounces_bursts_but_not_old_runs(tmp_path, spawned):
    _write_last(tmp_path, finished_epoch=time.time() - 5)
    auto_sync.hook_main({"hook_event_name": "SessionStart"}, env=_env(tmp_path))
    assert spawned == []
    _write_last(tmp_path, finished_epoch=time.time() - 500)
    auto_sync.hook_main({"hook_event_name": "SessionStart"}, env=_env(tmp_path))
    assert len(spawned) == 1


def test_previous_failure_is_announced_at_session_start(tmp_path, spawned):
    _write_last(tmp_path, ok=False, error="exit 1: connection refused")
    out = auto_sync.hook_main({"hook_event_name": "SessionStart"}, env=_env(tmp_path))
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert "FAILED" in ctx and "connection refused" in ctx
    assert len(spawned) == 1  # and it still retries


def test_conflicts_are_announced(tmp_path, spawned):
    _write_last(tmp_path, conflicts=[{"path": "a.md", "conflict_copy": "a (sync-conflict).md"}])
    out = auto_sync.hook_main({"hook_event_name": "SessionStart"}, env=_env(tmp_path))
    assert "1 conflict" in out["hookSpecificOutput"]["additionalContext"]


def _fake_run(stdout="", stderr="", returncode=0, record=None):
    def run(cmd, **kw):
        if record is not None:
            record.append((cmd, kw))
        return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)
    return run


def test_windows_sync_runs_in_a_hidden_console_that_ignores_ctrl_c(tmp_path, monkeypatch):
    """A detached child has no console, so uv/git would each pop up a visible window the user could
    close or Ctrl-C mid-sync. The child must get a hidden console instead, in its own process group."""
    # Swap in a stand-in os that reports "nt". Patching os.name itself would make pathlib build
    # WindowsPath objects, which cannot exist on Linux and broke this test in CI.
    class _NtOs:
        name = "nt"
        def __getattr__(self, attr):
            return getattr(os, attr)
    monkeypatch.setattr(auto_sync, "os", _NtOs())
    seen = []
    auto_sync.child_main("x", env=_env(tmp_path), run=_fake_run(stdout="{}", record=seen))
    flags = seen[0][1]["creationflags"]
    assert flags & 0x08000000      # CREATE_NO_WINDOW
    assert flags & 0x00000200      # CREATE_NEW_PROCESS_GROUP
    assert not flags & 0x00000008  # never DETACHED_PROCESS (that is what made windows appear)

    popen = []
    monkeypatch.setattr(auto_sync.subprocess, "Popen", lambda args, **kw: popen.append(kw))
    auto_sync.spawn_detached(["x"])
    assert popen[0]["creationflags"] == flags


def test_successful_run_records_result_and_keeps_secrets_out_of_argv(tmp_path):
    seen = []
    result = {"pushed": ["a.md"], "pulled": ["b.md"], "conflicts": [], "trashed_local": []}
    rec = auto_sync.child_main("SessionEnd", env=_env(tmp_path),
                               run=_fake_run(stdout=json.dumps(result), record=seen))
    assert rec["ok"] and rec["pushed"] == ["a.md"] and rec["pulled"] == ["b.md"]
    cmd, kw = seen[0]
    assert TOKEN not in " ".join(cmd) and PASS not in " ".join(cmd)
    assert kw["env"]["WICKED_BRAIN_SYNC_TOKEN"] == TOKEN  # reaches the child via env
    last = json.loads((tmp_path / ".claude-runs" / "auto-sync-last.json").read_text(encoding="utf-8"))
    assert last["ok"] is True
    assert not (tmp_path / ".claude-runs" / "auto-sync.lock").exists()
    assert list((tmp_path / ".claude-runs").glob("auto-sync-*.jsonl"))


def test_failed_run_is_recorded_with_secrets_scrubbed(tmp_path):
    rec = auto_sync.child_main(
        "SessionStart", env=_env(tmp_path),
        run=_fake_run(stderr=f"HTTP 401 for token {TOKEN} / {PASS}", returncode=1),
    )
    assert rec["ok"] is False
    assert TOKEN not in rec["error"] and PASS not in rec["error"] and "***" in rec["error"]
    assert not (tmp_path / ".claude-runs" / "auto-sync.lock").exists()


def test_missing_uv_and_timeout_are_reported_not_raised(tmp_path):
    def no_uv(cmd, **kw):
        raise FileNotFoundError("uv")

    def slow(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 1)

    assert "uv" in auto_sync.child_main("x", env=_env(tmp_path), run=no_uv)["error"]
    assert "timed out" in auto_sync.child_main("x", env=_env(tmp_path), run=slow)["error"]


def test_live_lock_blocks_overlap_and_stale_lock_is_reclaimed(tmp_path):
    lock = tmp_path / ".claude-runs" / "auto-sync.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text("123")
    assert auto_sync.child_main("x", env=_env(tmp_path), run=_fake_run(stdout="{}")) is None
    old = time.time() - auto_sync.LOCK_STALE_SECONDS - 5
    os.utime(lock, (old, old))
    assert auto_sync.child_main("x", env=_env(tmp_path), run=_fake_run(stdout="{}"))["ok"] is True


def test_vault_sync_cli_reads_credentials_from_env(tmp_path, monkeypatch):
    import vault_sync

    captured = {}

    def fake_sync(vault, url, token, passphrase, device, mode):
        captured.update(url=url, token=token, passphrase=passphrase, mode=mode)
        return {"pushed": []}

    monkeypatch.setattr(vault_sync, "sync", fake_sync)
    monkeypatch.setenv("WICKED_BRAIN_SYNC_URL", "https://x.test")
    monkeypatch.setenv("WICKED_BRAIN_SYNC_TOKEN", "t")
    monkeypatch.setenv("WICKED_BRAIN_SYNC_PASSPHRASE", "p")
    assert vault_sync._main(["vault_sync.py", "sync", "--path", str(tmp_path), "--json"]) == 0
    assert captured == {"url": "https://x.test", "token": "t", "passphrase": "p", "mode": "sync"}

    monkeypatch.delenv("WICKED_BRAIN_SYNC_TOKEN")
    with pytest.raises(SystemExit):
        vault_sync._main(["vault_sync.py", "sync", "--path", str(tmp_path)])
