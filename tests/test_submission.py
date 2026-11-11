"""The OpenAI plugin-portal package: what scripts/package-submission.sh builds and checks.

The portal rejects a package for things like a >30-character subtitle or a missing icon,
and its review wants every MCP tool to declare read-only / destructive / open-world hints.
These tests pin both so a regression fails here, not in the portal.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from test_smoke import _git_bash

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_REL = "dist/submission-test"


@pytest.fixture(scope="module")
def package():
    if not (REPO_ROOT / "scripts" / "package-submission.sh").is_file():
        pytest.skip("maintainer-only: packaging scripts are not shipped in the public repo")
    out = REPO_ROOT / OUT_REL
    shutil.rmtree(out, ignore_errors=True)
    result = subprocess.run([_git_bash(), "scripts/package-submission.sh", OUT_REL],
                            cwd=REPO_ROOT, capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, result.stdout + result.stderr
    yield out
    shutil.rmtree(out, ignore_errors=True)


def _version() -> str:
    import re
    return re.search(r'^version\s*=\s*"([^"]+)"', (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.M).group(1)


def test_zip_has_one_manifest_format_an_icon_and_the_local_server(package):
    zpath = package / f"wicked-brain-{_version()}.zip"
    names = set(zipfile.ZipFile(zpath).namelist())
    for needed in ("plugin.json", "mcp.json", "assets/icon.svg", "skills/brain-setup/SKILL.md",
                   "integrations/mcp-server/server.py", "pyproject.toml"):
        assert needed in names, needed
    assert not [n for n in names if n.startswith((".codex-plugin", "hooks/")) or n == ".mcp.json"]
    assert not [n for n in names if "__pycache__" in n or n.endswith(".pyc")]
    assert not [n for n in names if n.startswith("scripts/") and Path(n).name in
                {"export-public.sh", "package-submission.sh", "check_submission.py", "build.sh", "lib.sh"}]
    digest = (package / f"wicked-brain-{_version()}.zip.sha256").read_text().split()[0]
    assert digest == hashlib.sha256(zpath.read_bytes()).hexdigest()


def test_listing_fields_meet_the_published_limits(package):
    zpath = package / f"wicked-brain-{_version()}.zip"
    m = json.loads(zipfile.ZipFile(zpath).read("plugin.json"))
    ui = m["extensions"]["com.openai"]["interface"]
    assert len(ui["displayName"]) <= 30 and len(ui["shortDescription"]) <= 30
    assert ui["developerName"] == "SimpliFixed Technologies, LLC"
    for key in ("websiteURL", "supportURL", "privacyPolicyURL", "termsOfServiceURL"):
        assert ui[key].startswith("https://"), key
    assert m["extensions"]["com.openai"]["requires_local_executor"] is True


def test_the_check_rejects_an_over_long_subtitle(package, tmp_path):
    zpath = package / f"wicked-brain-{_version()}.zip"
    zipfile.ZipFile(zpath).extractall(tmp_path)
    manifest = tmp_path / "plugin.json"
    m = json.loads(manifest.read_text(encoding="utf-8"))
    m["extensions"]["com.openai"]["interface"]["shortDescription"] = "x" * 45
    manifest.write_text(json.dumps(m), encoding="utf-8")
    result = subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "check_submission.py"), str(tmp_path)],
                            capture_output=True, text=True)
    assert result.returncode == 1 and "shortDescription" in result.stdout


def test_every_mcp_tool_declares_explicit_safety_hints():
    sys.path.insert(0, str(REPO_ROOT / "integrations" / "mcp-server"))
    import server  # noqa: PLC0415

    tools = asyncio.run(server.mcp.list_tools())
    assert len(tools) == 12
    for t in tools:
        a = t.annotations
        assert a is not None, t.name
        assert isinstance(a.readOnlyHint, bool) and isinstance(a.destructiveHint, bool) \
            and isinstance(a.openWorldHint, bool), t.name
        assert a.openWorldHint is False, t.name
    by = {t.name: t.annotations for t in tools}
    for ro in ("brain_search", "brain_read_note", "brain_backlinks", "brain_vault_health"):
        assert by[ro].readOnlyHint is True, ro
    for edit in ("brain_update_note", "brain_replace_text", "brain_move_note"):
        assert by[edit].readOnlyHint is False and by[edit].destructiveHint is True, edit
    for add in ("brain_save_note", "brain_capture"):
        assert by[add].readOnlyHint is False and by[add].destructiveHint is False, add
