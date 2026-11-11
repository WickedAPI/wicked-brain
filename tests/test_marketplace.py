"""The plugin-marketplace tree that scripts/build-marketplace.sh assembles.

Claude Code installs from this tree by cloning the public repo, so the things that
silently break an install are pinned here: the catalog parses, the version comes from
pyproject.toml, the plugin is self-contained, dev tooling stays out, and .gitattributes
keeps shell scripts on LF endings.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from test_smoke import _git_bash

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_REL = "dist/marketplace-test"


@pytest.fixture(scope="module")
def tree():
    out = REPO_ROOT / OUT_REL
    shutil.rmtree(out, ignore_errors=True)
    result = subprocess.run(
        [_git_bash(), "scripts/build-marketplace.sh", OUT_REL],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stderr
    yield out
    shutil.rmtree(out, ignore_errors=True)


def _pyproject_version() -> str:
    m = re.search(r'^version\s*=\s*"([^"]+)"', (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.M)
    assert m
    return m.group(1)


def test_catalog_lists_the_plugin_at_the_pyproject_version(tree):
    catalog = json.loads((tree / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    assert catalog["name"] == "wicked-brain"
    assert catalog["owner"]["name"]
    (entry,) = catalog["plugins"]
    assert entry["name"] == "wicked-brain"
    assert entry["source"] == "./plugins/wicked-brain"
    assert entry["version"] == _pyproject_version()
    manifest = json.loads((tree / entry["source"] / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["name"] == entry["name"]
    assert manifest["version"] == _pyproject_version()


def test_plugin_is_self_contained_and_leaves_dev_tooling_out(tree):
    plugin = tree / "plugins" / "wicked-brain"
    for needed in ("SKILL.md", "pyproject.toml", "hooks/hooks.json", "hooks/_bridge.sh", ".mcp.json",
                   "integrations/mcp-server/server.py", "scripts/vault_sync.py"):
        assert (plugin / needed).is_file(), needed
    assert len(list((plugin / "commands").glob("brain-*.md"))) == 10
    assert not (plugin / "INSTALL.md").exists()  # documents the developer junction install
    leaked = [p.name for p in (plugin / "scripts").iterdir()
              if p.name in {"build.sh", "build-marketplace.sh", "export-public.sh", "package-submission.sh", "check_submission.py", "lib.sh"} or p.name.startswith("install-")]
    assert leaked == []
    assert not list(tree.rglob("__pycache__"))


def test_gitattributes_forces_lf_for_shell_scripts(tree):
    attrs = (tree / ".gitattributes").read_text(encoding="utf-8")
    assert "*.sh text eol=lf" in attrs
    # the file git will check out must not already contain carriage returns
    assert b"\r" not in (tree / "plugins" / "wicked-brain" / "hooks" / "_bridge.sh").read_bytes()


def test_build_refuses_to_wipe_an_unrelated_directory(tmp_path):
    (tmp_path / "keep.txt").write_text("precious", encoding="utf-8")
    result = subprocess.run(
        [_git_bash(), "scripts/build-marketplace.sh", tmp_path.as_posix()],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
    )
    assert result.returncode != 0
    assert (tmp_path / "keep.txt").read_text(encoding="utf-8") == "precious"


# --------------------------------------------------------------------------- #
# Codex plugin
# --------------------------------------------------------------------------- #

def test_codex_catalog_points_at_the_codex_plugin(tree):
    catalog = json.loads((tree / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8"))
    assert catalog["name"] == "wicked-brain"
    (entry,) = catalog["plugins"]
    assert entry["name"] == "wicked-brain"
    assert entry["source"] == {"source": "local", "path": "./plugins/wicked-brain-codex"}
    # Codex skips a catalog entry that lacks any of these three.
    assert entry["policy"]["installation"] and entry["policy"]["authentication"] and entry["category"]
    assert (tree / "plugins" / "wicked-brain-codex").is_dir()


def test_codex_plugin_manifests_agree_and_match_the_version(tree):
    plugin = tree / "plugins" / "wicked-brain-codex"
    portable = json.loads((plugin / "plugin.json").read_text(encoding="utf-8"))
    legacy = json.loads((plugin / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert portable["name"] == legacy["name"] == "wicked-brain"
    assert portable["version"] == legacy["version"] == _pyproject_version()
    assert portable["extensions"]["com.openai"]["requires_local_executor"] is True
    onboarding = portable["extensions"]["com.openai"]["onboardingSkill"]
    assert (plugin / onboarding).is_file()
    for name in ("mcp.json", ".mcp.json"):
        server = json.loads((plugin / name).read_text(encoding="utf-8"))["mcpServers"]["wicked-brain"]
        assert server["command"] == "uv"
        assert "${PLUGIN_ROOT}/integrations/mcp-server/server.py" in server["args"]


def test_codex_plugin_has_one_skill_per_command_and_no_claude_leftovers(tree):
    plugin = tree / "plugins" / "wicked-brain-codex"
    skills = sorted(p.parent.name for p in (plugin / "skills").glob("*/SKILL.md"))
    assert skills == sorted([f"brain-{n}" for n in (
        "capture", "find", "fork", "health", "init", "merge", "reconcile", "reindex", "save", "setup", "sync")]
        + ["wicked-brain"])
    # the MCP server's skill tools read commands/, which Codex plugins do not have
    for needed in ("references/ai-first-rules.md", "scripts/vault_sync.py", "integrations/mcp-server/server.py",
                   "pyproject.toml"):
        assert (plugin / needed).is_file(), needed
    for md in list((plugin / "skills").glob("*/SKILL.md")) + list((plugin / "references").glob("*.md")):
        text = md.read_text(encoding="utf-8")
        assert "SKILL_ROOT" not in text, md
        assert "$ARGUMENTS" not in text, md
        assert "given at session start" not in text, md
    for md in (plugin / "skills").glob("brain-*/SKILL.md"):
        assert md.read_text(encoding="utf-8").count("Plugin root.") == 1, md  # the note, not rewritten into itself
    sync = (plugin / "skills" / "brain-sync" / "SKILL.md").read_text(encoding="utf-8")
    assert "$brain-sync" in sync or "`$brain-" in sync
    assert not (plugin / "hooks").exists()  # hooks make a Codex plugin ineligible for the public directory


# --------------------------------------------------------------------------- #
# Public export
# --------------------------------------------------------------------------- #

def test_public_export_leaves_out_private_files_and_passes_its_leak_scan():
    if not (REPO_ROOT / "scripts" / "export-public.sh").is_file():
        pytest.skip("maintainer-only: the export script is not shipped in the public repo")
    out_rel = "dist/public-test"
    out = REPO_ROOT / out_rel
    shutil.rmtree(out, ignore_errors=True)
    try:
        result = subprocess.run(
            [_git_bash(), "scripts/export-public.sh", out_rel],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=300,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        for private in ("CLAUDE.md", "AGENTS.md", "HOSTING.md", ".claude", "search_test.txt",
                        "sync_server/DEPLOYMENT.md", "scripts/export-public.sh", "scripts/package-submission.sh", "scripts/check_submission.py", ".git"):
            assert not (out / private).exists(), private
        for needed in ("README.md", "LICENSE", "NOTICE.md", ".gitignore", ".gitattributes",
                       ".claude-plugin/marketplace.json", ".agents/plugins/marketplace.json",
                       "plugins/wicked-brain", "plugins/wicked-brain-codex", "examples/sample-vault"):
            assert (out / needed).exists(), needed
        assert "{{" not in (out / "README.md").read_text(encoding="utf-8")  # placeholders all filled
    finally:
        shutil.rmtree(out, ignore_errors=True)
