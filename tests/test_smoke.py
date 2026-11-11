"""Smoke tests for the trimmed wicked-brain repo.

Not a port of upstream's test suite (which references dropped features and
fixtures) - a small, real suite for what this fork actually ships: the build
pipeline, note I/O, health/merge/freshness/graph scripts, and the two fork
upgrades (auto-reindex's staleness handling, bounded auto-merge).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_VAULT = REPO_ROOT / "examples" / "sample-vault" / "vault"

sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "integrations" / "mcp-server"))
# NOT added to sys.path here: sync_server/ also has no name collision with the
# above (it's "server.py" in THREE different directories - integrations/mcp-server/,
# dashboard/, and sync_server/), so its tests import it explicitly by file path
# (see _import_sync_server_fresh below) rather than relying on sys.path order,
# which would silently pick whichever "server" module got inserted first.


# --------------------------------------------------------------------------- #
# Build pipeline
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("platform", ["claude-code", "codex-cli", "antigravity"])
def test_build_produces_expected_platform_output(platform, tmp_path):
    # Relative, forward-slash path: an absolute Windows path (backslashes)
    # passed as a bash argv element gets its backslashes eaten as escapes by
    # bash's own argument parsing, not by Python - cwd=REPO_ROOT sidesteps it.
    result = subprocess.run(
        [_git_bash(), "scripts/build.sh", "--platform", platform],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    dist = REPO_ROOT / "dist" / platform
    assert dist.is_dir()
    assert (dist / "INSTALL.md").is_file()
    if platform == "claude-code":
        assert (dist / "commands").is_dir()
        assert len(list((dist / "commands").glob("brain-*.md"))) == 10
        assert (dist / "references" / "ai-first-rules.md").is_file()
        assert (dist / "scripts" / "note_io.py").is_file()
        # Plugin packaging (see adapters/claude-code/adapter.sh's
        # adapter_build docstring): the same install command
        # (scripts/install-claude-code.sh) that used to junction a plain
        # skill+commands bundle now junctions a real Claude Code plugin -
        # these are the files that make that true.
        assert (dist / ".claude-plugin" / "plugin.json").is_file()
        assert (dist / "hooks" / "hooks.json").is_file()
        assert (dist / "hooks" / "_bridge.sh").is_file()
        assert (dist / ".mcp.json").is_file()
        assert (dist / "integrations" / "mcp-server" / "server.py").is_file()
        assert (dist / "integrations" / "mcp-server" / "vault_ops.py").is_file()
    elif platform == "codex-cli":
        assert (dist / "AGENTS.md").is_file()
        assert (dist / ".agents" / "skills").is_dir()
        assert len(list((dist / ".agents" / "skills").glob("brain-*"))) == 10
    else:  # antigravity
        assert (dist / "plugin.json").is_file()
        assert (dist / "rules" / "AGENTS.md").is_file()
        assert (dist / "skills").is_dir()
        assert len(list((dist / "skills").glob("brain-*"))) == 10
        assert (dist / "mcp_config.json").is_file()
        assert (dist / "integrations" / "mcp-server" / "server.py").is_file()
        assert (dist / "integrations" / "mcp-server" / "vault_ops.py").is_file()
        # No hooks.json - see adapters/antigravity/adapter.sh's header for why
        # this is a deliberate gap, not an oversight.
        assert not (dist / "hooks").exists()

        plugin_manifest = json.loads((dist / "plugin.json").read_text(encoding="utf-8"))
        assert plugin_manifest["name"] == "wicked-brain"

        mcp_config = json.loads((dist / "mcp_config.json").read_text(encoding="utf-8"))
        server_args = mcp_config["mcpServers"]["wicked-brain"]["args"]
        # Install-time placeholders, not a guessed relative path - see
        # scripts/install-antigravity.sh's resolve_placeholders for why: no
        # confirmed plugin-root variable exists in Antigravity's mcp_config.json
        # schema, and only an absolute path is proven working (live test).
        assert any("__WICKED_BRAIN_ANTIGRAVITY_INSTALL_DIR__" in a for a in server_args)
        assert mcp_config["mcpServers"]["wicked-brain"]["env"]["WICKED_BRAIN_VAULT_PATH"] == \
            "__WICKED_BRAIN_ANTIGRAVITY_VAULT_PATH__"

        skill_text = (dist / "skills" / "brain-health" / "SKILL.md").read_text(encoding="utf-8")
        assert "__WICKED_BRAIN_ANTIGRAVITY_INSTALL_DIR__" in skill_text
        assert "SKILL_ROOT" not in skill_text


@pytest.mark.parametrize("platform,scripts_dir", [
    ("claude-code", "scripts"),
    ("codex-cli", ".codex/scripts"),
    ("antigravity", "scripts"),
])
def test_shipped_semantic_search_imports_without_the_mcp_server(platform, scripts_dir):
    """Regression (found 2026-09-10 via Codex Astra's report, confirmed by
    actually running both shipped builds): semantic_search.py used to import
    vault_ops from integrations/mcp-server/, which the build never copies
    into either dist/ tree - so every packaged install's /brain-reindex
    crashed with ModuleNotFoundError: No module named 'vault_ops', 100% of
    the time, in every real install. Never caught by the rest of this suite
    because every other test imports scripts/ directly from the repo root,
    where integrations/mcp-server/ happens to sit right alongside it.

    This imports semantic_search from the actual BUILT dist/ tree (not the
    repo root) using the current interpreter - no need for a fresh `uv` venv,
    since the only thing this regression is about is whether every file the
    import chain needs is physically present in the shipped bundle."""
    result = subprocess.run(
        [_git_bash(), "scripts/build.sh", "--platform", platform],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    dist_scripts = REPO_ROOT / "dist" / platform / scripts_dir
    assert (dist_scripts / "semantic_search.py").is_file()
    result = subprocess.run(
        [sys.executable, "-c", "import semantic_search"],
        cwd=dist_scripts, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, (
        f"shipped {platform} semantic_search.py failed to import "
        f"(this is the exact failure a real /brain-reindex would hit):\n{result.stderr}"
    )
    assert "vault_ops" not in result.stderr, (
        "semantic_search.py must not depend on integrations/mcp-server/vault_ops - "
        "that directory is never copied into either shipped build"
    )


@pytest.mark.parametrize("platform,scripts_dir", [
    ("claude-code", "scripts"),
    ("codex-cli", ".codex/scripts"),
    ("antigravity", "scripts"),
])
def test_shipped_scripts_exclude_repo_level_build_tooling(platform, scripts_dir):
    """Regression: adapters/lib.sh's copy_scripts_with_project used to do
    `cp -R src/. dst/`, which swept build.sh, lib.sh, and all three
    install-*.sh scripts into every platform's shipped scripts/ - repo-level
    dev tooling nobody installing the plugin needs, and actively misleading
    if anyone ran a shipped install-claude-code.sh from inside their own
    ~/.claude/skills/wicked-brain/scripts/ (its dist/claude-code lookup assumes
    it's running from the real repo checkout). Found by inspecting the
    antigravity build file-by-file, not by any earlier test."""
    result = subprocess.run(
        [_git_bash(), "scripts/build.sh", "--platform", platform],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    dist_scripts = REPO_ROOT / "dist" / platform / scripts_dir
    assert dist_scripts.is_dir()
    leaked = sorted(
        p.name for p in dist_scripts.iterdir()
        if p.name in {"build.sh", "lib.sh"} or p.name.startswith("install-")
    )
    assert leaked == [], f"repo-level build tooling leaked into {dist_scripts}: {leaked}"
    # The actual toolkit must still be there - this isn't just an empty dir.
    assert (dist_scripts / "note_io.py").is_file()


def test_build_rejects_unknown_exclude_platform():
    # Exercises the real path end-to-end (same subprocess pattern proven
    # reliable by the build test above) rather than re-deriving lib.sh's
    # parse_frontmatter behavior in isolation: drop a command with a
    # misspelled exclude: token into the real commands/ dir, confirm
    # scripts/build.sh's validate_excludes refuses to build, then clean up
    # unconditionally even if the assertion fails.
    bad_cmd = REPO_ROOT / "commands" / "_test_bad_exclude.md"
    bad_cmd.write_text(
        "---\ndescription: x\ncategory: vault\nexclude: [not-a-real-platform]\n---\nbody\n"
    )
    try:
        result = subprocess.run(
            [_git_bash(), "scripts/build.sh", "--platform", "claude-code"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
        )
    finally:
        bad_cmd.unlink()
    assert result.returncode != 0
    assert "not-a-real-platform" in result.stderr


# --------------------------------------------------------------------------- #
# Claude Code plugin packaging
# --------------------------------------------------------------------------- #

def test_claude_code_plugin_manifest_is_valid():
    """`claude plugin validate` is the real, authoritative check - the exact
    tool a plugin author is told to run before submitting one (see Claude
    Code's own plugin docs, "Share your plugins"). Skips if the `claude` CLI
    isn't on PATH rather than failing, since not every machine running this
    suite has it installed/authenticated - this is a bonus real-tool check
    layered on top of the structural asserts in
    test_build_produces_expected_platform_output, not a replacement for them."""
    if shutil.which("claude") is None:
        pytest.skip("claude CLI not on PATH")

    build = subprocess.run(
        [_git_bash(), "scripts/build.sh", "--platform", "claude-code"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
    )
    assert build.returncode == 0, build.stderr

    result = subprocess.run(
        ["claude", "plugin", "validate", "--strict", "dist/claude-code"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "Validation passed" in result.stdout


def test_claude_code_plugin_bridge_maps_options_and_falls_back(tmp_path):
    """hooks/_bridge.sh is the glue between the plugin's userConfig-derived
    CLAUDE_PLUGIN_OPTION_* env vars and the WICKED_BRAIN_* names the actual hook
    scripts read (see adapters/claude-code/adapter.sh's
    _cc_emit_plugin_bridge). Exercises both paths for real: the plugin-option
    path, and the backward-compat fallback to a plain WICKED_BRAIN_* env var for
    machines that predate this packaging and haven't filled in `/config` yet."""
    build = subprocess.run(
        [_git_bash(), "scripts/build.sh", "--platform", "claude-code"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
    )
    assert build.returncode == 0, build.stderr
    dist = REPO_ROOT / "dist" / "claude-code"
    bash = _git_bash() if os.name == "nt" else "bash"

    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "_CLAUDE.md").write_text("test vault manual\n", encoding="utf-8")
    stdin_payload = json.dumps({"cwd": str(vault)})

    # Plugin-option path: CLAUDE_PLUGIN_OPTION_VAULT_PATH set, nothing legacy.
    env = {**os.environ, "CLAUDE_PLUGIN_OPTION_VAULT_PATH": str(vault)}
    env.pop("WICKED_BRAIN_VAULT_PATH", None)
    result = subprocess.run(
        [bash, "hooks/_bridge.sh", "load_vault_context.py"],
        cwd=dist, input=stdin_payload, capture_output=True, text=True,
        timeout=15, env=env,
    )
    assert result.returncode == 0, result.stderr
    assert "test vault manual" in result.stdout

    # Backward-compat fallback: no plugin option set, only the legacy env var
    # (exactly the state of an existing machine's settings.json "env" block
    # before anyone touches /config) - must still work unmodified.
    env2 = {**os.environ, "WICKED_BRAIN_VAULT_PATH": str(vault)}
    env2.pop("CLAUDE_PLUGIN_OPTION_VAULT_PATH", None)
    result2 = subprocess.run(
        [bash, "hooks/_bridge.sh", "load_vault_context.py"],
        cwd=dist, input=stdin_payload, capture_output=True, text=True,
        timeout=15, env=env2,
    )
    assert result2.returncode == 0, result2.stderr
    assert "test vault manual" in result2.stdout

    # The opt-in-gated PostCompact hook must stay inert with neither the
    # plugin option nor the legacy env var set - this is the safety property
    # (bg-agent.sh writes to the vault unattended) that must survive
    # repackaging, not just a passthrough detail.
    env3 = {**os.environ}
    env3.pop("CLAUDE_PLUGIN_OPTION_BG_AGENT_ENABLED", None)
    env3.pop("WICKED_BRAIN_BG_AGENT_ENABLED", None)
    env3["CLAUDE_PLUGIN_OPTION_VAULT_PATH"] = str(vault)
    result3 = subprocess.run(
        [bash, "hooks/_bridge.sh", "bg-agent.sh"],
        cwd=dist, input='{"transcript_path": "/nonexistent"}', capture_output=True, text=True,
        timeout=15, env=env3,
    )
    assert result3.returncode == 0, result3.stderr


def test_claude_code_plugin_wires_opt_in_auto_sync(tmp_path):
    """The plugin must register hooks/auto_sync.py on SessionStart,
    PostCompact and SessionEnd, expose an OFF-by-default /config toggle, and
    the bridge must keep the hook inert (no files written, no output) unless
    that toggle or the legacy WICKED_BRAIN_AUTO_SYNC_ENABLED env var is on."""
    build = subprocess.run(
        [_git_bash(), "scripts/build.sh", "--platform", "claude-code"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
    )
    assert build.returncode == 0, build.stderr
    dist = REPO_ROOT / "dist" / "claude-code"

    hooks = json.loads((dist / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
    for event in ("SessionStart", "PostCompact", "SessionEnd"):
        commands = [h["command"] for group in hooks[event] for h in group["hooks"]]
        assert any(c.endswith(" auto_sync.py") for c in commands), f"{event} does not run auto_sync.py: {commands}"

    manifest = json.loads((dist / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    field = manifest["userConfig"]["auto_sync_enabled"]
    assert field["type"] == "boolean" and field["default"] is False
    assert "CLAUDE_PLUGIN_OPTION_AUTO_SYNC_ENABLED" in (dist / "hooks" / "_bridge.sh").read_text(encoding="utf-8")
    assert (dist / "scripts" / "vault_sync.py").is_file()

    vault = tmp_path / "vault"
    vault.mkdir()
    bash = _git_bash() if os.name == "nt" else "bash"
    env = {**os.environ, "CLAUDE_PLUGIN_OPTION_VAULT_PATH": str(vault)}
    for k in ("WICKED_BRAIN_AUTO_SYNC_ENABLED", "CLAUDE_PLUGIN_OPTION_AUTO_SYNC_ENABLED"):
        env.pop(k, None)
    result = subprocess.run(
        [bash, "hooks/_bridge.sh", "auto_sync.py"],
        cwd=dist, input=json.dumps({"hook_event_name": "SessionStart"}),
        capture_output=True, text=True, timeout=15, env=env,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert not (vault / ".claude-runs").exists()


def test_claude_code_hook_commands_survive_a_backslash_plugin_root(tmp_path):
    """Regression (found 2026-10-11): Claude Code substitutes ${CLAUDE_PLUGIN_ROOT}
    textually and hands the command to bash. On Windows the root is a backslash
    path, and an UNQUOTED path loses its backslashes ("C:Users...: No such file
    or directory", exit 127), which silently killed the recall, write-validation
    and auto-sync hooks. Runs every built hook command that way, from a root
    containing a space, and requires it to find the bridge script."""
    build = subprocess.run(
        [_git_bash(), "scripts/build.sh", "--platform", "claude-code"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
    )
    assert build.returncode == 0, build.stderr
    root = tmp_path / "plugin root"
    shutil.copytree(REPO_ROOT / "dist" / "claude-code", root)
    hooks = json.loads((root / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
    bash = _git_bash() if os.name == "nt" else "bash"
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("WICKED_BRAIN_", "CLAUDE_PLUGIN_OPTION_"))}
    for event, groups in hooks.items():
        for group in groups:
            for hook in group["hooks"]:
                command = hook["command"].replace("${CLAUDE_PLUGIN_ROOT}", str(root))
                result = subprocess.run(
                    [bash, "-c", command], input="{}", capture_output=True, text=True,
                    timeout=30, env=env,
                )
                assert result.returncode != 127 and "No such file" not in result.stderr, (
                    f"{event} hook could not find its script: {command}\n{result.stderr}"
                )


# --------------------------------------------------------------------------- #
# Install scripts
# --------------------------------------------------------------------------- #
# Regression coverage for a real bug found 2026-09-15: the docs used to say
# to run `ln -sf` directly, which on Windows without admin rights/Developer
# Mode either errors or - on some Git-for-Windows builds - silently produces
# a real recursive COPY with no error printed. That copy then went stale the
# moment dist/ was rebuilt, so a real fix (retry-on-lock-contention in
# vault_git.py) sat inert in the repo for a full extra day before anyone
# noticed the installed hook's behavior hadn't changed. These tests run the
# actual installer scripts against a scratch destination (via the
# WICKED_BRAIN_*_DIR overrides both scripts read) rather than re-deriving their
# link-vs-copy logic in Python, so a regression there is caught the same way
# the original bug would have been.

def _read_text_via(path: Path) -> str:
    # Read through whatever `path` is - a real dir, a symlink, or a Windows
    # junction - all look like a normal directory to Path.read_text once
    # resolved, no special-casing needed.
    return path.read_text(encoding="utf-8")


def _git_bash() -> str:
    """Resolve the real Git Bash executable rather than trusting a bare
    "bash" PATH lookup. Discovered running these very tests: on a machine
    with WSL also installed, a bare `bash` can resolve to
    C:\\Windows\\System32\\bash.exe (the WSL launcher stub) instead of Git
    Bash - which happened here specifically for subprocess calls made from
    inside `uv run`'s own process (its PATH ordering differs from an
    interactive Git Bash session's). The WSL stub does not forward arbitrary
    custom env vars from the parent Windows process (only WSLENV-listed
    ones), so WICKED_BRAIN_CLAUDE_SKILLS_DIR-style overrides silently vanish and
    $HOME resolves to the WSL distro's own home instead of the Windows one
    - not a bug in the install scripts, but a real ambiguity worth pinning
    down explicitly here so this test reflects what a person running `bash
    scripts/install-claude-code.sh` from an actual Git Bash terminal (the
    documented, supported way) experiences, matching every other bash
    invocation in this repo's own tooling."""
    if os.name != "nt":
        return "bash"
    for d in os.environ.get("PATH", "").split(os.pathsep):
        candidate = Path(d) / "bash.exe"
        low = str(candidate).lower()
        if candidate.is_file() and "system32" not in low and "windowsapps" not in low:
            return str(candidate)
    return "bash"  # best effort - no non-WSL bash found on PATH


def test_install_claude_code_links_not_copies(tmp_path):
    build = subprocess.run(
        [_git_bash(), "scripts/build.sh", "--platform", "claude-code"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
    )
    assert build.returncode == 0, build.stderr

    skills_dir = tmp_path / "skills"
    commands_dir = tmp_path / "commands"
    env = {
        **os.environ,
        "WICKED_BRAIN_CLAUDE_SKILLS_DIR": str(skills_dir),
        "WICKED_BRAIN_CLAUDE_COMMANDS_DIR": str(commands_dir),
    }
    bash = _git_bash()
    result = subprocess.run(
        [bash, "scripts/install-claude-code.sh"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30, env=env,
    )
    assert result.returncode == 0, result.stderr
    assert "fell back to a plain copy" not in result.stdout, (
        "installer fell back to a copy on this machine - expected a real "
        f"symlink/junction:\n{result.stdout}"
    )

    installed = skills_dir / "wicked-brain"
    source = REPO_ROOT / "dist" / "claude-code"
    assert installed.is_dir()
    # Content must be identical to the freshly built source - proves this is
    # a live link, not a snapshot that will drift on the next rebuild.
    assert _read_text_via(installed / "hooks" / "bg-agent.sh") == \
        _read_text_via(source / "hooks" / "bg-agent.sh")
    assert (commands_dir / "brain-find.md").is_file()
    assert len(list(commands_dir.glob("brain-*.md"))) == 10

    # Prove it's live, not a one-time snapshot: edit the source, confirm the
    # installed copy reflects it immediately with no re-run of the installer.
    marker = "\n# regression-test marker - live-link check\n"
    hook = source / "hooks" / "bg-agent.sh"
    original = hook.read_text(encoding="utf-8")
    try:
        hook.write_text(original + marker, encoding="utf-8")
        assert marker in _read_text_via(installed / "hooks" / "bg-agent.sh")
    finally:
        hook.write_text(original, encoding="utf-8")

    # Re-running is safe and idempotent (replaces, doesn't error or nest).
    again = subprocess.run(
        [bash, "scripts/install-claude-code.sh"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30, env=env,
    )
    assert again.returncode == 0, again.stderr
    assert installed.is_dir()


def test_install_codex_cli_links_each_skill_and_leaves_siblings_alone(tmp_path):
    build = subprocess.run(
        [_git_bash(), "scripts/build.sh", "--platform", "codex-cli"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
    )
    assert build.returncode == 0, build.stderr

    skills_dir = tmp_path / "codex-skills"
    skills_dir.mkdir()
    # A pre-existing, unrelated entry - ~/.codex/skills/ is not exclusively
    # Wicked Brain's on a real machine (a `.system` and a `use-railway` folder were
    # both found living there alongside it). The installer must not touch it.
    sibling = skills_dir / "some-other-skill"
    sibling.mkdir()
    (sibling / "SKILL.md").write_text("not wicked-brain's - must survive\n", encoding="utf-8")

    env = {**os.environ, "WICKED_BRAIN_CODEX_SKILLS_DIR": str(skills_dir)}
    result = subprocess.run(
        [_git_bash(), "scripts/install-codex-cli.sh"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30, env=env,
    )
    assert result.returncode == 0, result.stderr
    assert "fell back to a plain copy" not in result.stdout, result.stdout

    assert (skills_dir / "brain-find").is_dir()
    assert len(list(skills_dir.glob("brain-*"))) == 10
    # The unrelated sibling is untouched.
    assert (sibling / "SKILL.md").read_text(encoding="utf-8") == "not wicked-brain's - must survive\n"

    source_skill = REPO_ROOT / "dist" / "codex-cli" / ".agents" / "skills" / "brain-find" / "SKILL.md"
    assert _read_text_via(skills_dir / "brain-find" / "SKILL.md") == _read_text_via(source_skill)


def test_install_antigravity_copies_and_resolves_placeholders(tmp_path):
    """Regression for real bugs found while building this platform, not
    hypotheticals:

    1. The installer's placeholder-resolution step first shipped with the
       env vars exported only into the `find` subprocess listing the files,
       not into the `perl` that actually does the substitution - a no-op
       that still printed "[resolved]" and exited 0. Re-reading the
       installed mcp_config.json (not just trusting the exit code) caught it.
    2. Placeholders must be resolved in the installed copy, never in the
       shared build output - see test_install_antigravity_does_not_mutate_dist.
    3. The install ALWAYS uses a plain copy now, never a link/junction -
       real, repeated evidence on this project's own reference machine
       showed every junction-based install went undiscovered by Antigravity
       (most likely its plugin scanner doesn't traverse NTFS junctions the
       way it does real directories), while every plain-copy install
       connected immediately. This is a deliberate divergence from every
       other installer in this repo (Claude Code, Codex CLI both prefer a
       real link) - asserted explicitly below so it can't silently regress
       back to junction-first.

    Uses an ISOLATED copy of the build output (WICKED_BRAIN_ANTIGRAVITY_DIST_DIR),
    not the shared dist/antigravity a real install might be using - a real,
    running Antigravity holding that directory open via its own copy
    deadlocked one of this test's `perl -i` calls for over two hours the
    first time this test ran for real (confirmed via Get-CimInstance
    Win32_Process, not assumed), before the always-copy fix above existed.
    A hermetic copy can never collide with that."""
    build = subprocess.run(
        [_git_bash(), "scripts/build.sh", "--platform", "antigravity"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
    )
    assert build.returncode == 0, build.stderr

    dist_copy = tmp_path / "dist-antigravity-copy"
    shutil.copytree(REPO_ROOT / "dist" / "antigravity", dist_copy)

    plugins_dir = tmp_path / "gemini-plugins"
    vault = tmp_path / "vault"
    vault.mkdir()
    env = {
        **os.environ,
        "WICKED_BRAIN_ANTIGRAVITY_DIST_DIR": str(dist_copy),
        "WICKED_BRAIN_ANTIGRAVITY_PLUGINS_DIR": str(plugins_dir),
        "WICKED_BRAIN_VAULT_PATH": str(vault).replace("\\", "/"),
    }
    result = subprocess.run(
        [_git_bash(), "scripts/install-antigravity.sh"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30, env=env,
    )
    assert result.returncode == 0, result.stderr
    assert "[copy]" in result.stdout, (
        f"expected the installer to always copy (never link/junction) - see this "
        f"test's docstring for why - but saw:\n{result.stdout}"
    )

    installed = plugins_dir / "wicked-brain"
    assert installed.is_dir()
    # is_symlink() is False for an NTFS junction, so check both explicitly.
    assert not installed.is_symlink()
    assert not installed.is_junction()

    mcp_config = json.loads(_read_text_via(installed / "mcp_config.json"))
    server_args = mcp_config["mcpServers"]["wicked-brain"]["args"]
    assert not any("__WICKED_BRAIN_ANTIGRAVITY" in a for a in server_args), (
        f"install-time placeholder never got resolved in mcp_config.json args: {server_args}"
    )
    assert str(installed).replace("\\", "/") in server_args[-1]
    assert mcp_config["mcpServers"]["wicked-brain"]["env"]["WICKED_BRAIN_VAULT_PATH"] == \
        str(vault).replace("\\", "/")

    skill_text = _read_text_via(installed / "skills" / "brain-health" / "SKILL.md")
    assert "__WICKED_BRAIN_ANTIGRAVITY_INSTALL_DIR__" not in skill_text
    assert str(installed).replace("\\", "/") in skill_text

    # Re-running is safe and idempotent, same contract as the other installers.
    again = subprocess.run(
        [_git_bash(), "scripts/install-antigravity.sh"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30, env=env,
    )
    assert again.returncode == 0, again.stderr
    assert not any(
        "__WICKED_BRAIN_ANTIGRAVITY" in a
        for a in json.loads(_read_text_via(installed / "mcp_config.json"))["mcpServers"]["wicked-brain"]["args"]
    )


def _run_antigravity_install(tmp_path, env_overrides, dist_copy=None):
    if dist_copy is None:
        build = subprocess.run(
            [_git_bash(), "scripts/build.sh", "--platform", "antigravity"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
        )
        assert build.returncode == 0, build.stderr
        dist_copy = tmp_path / "dist-antigravity-copy"
        shutil.copytree(REPO_ROOT / "dist" / "antigravity", dist_copy)
    vault = tmp_path / "vault"
    vault.mkdir(exist_ok=True)
    env = {
        **os.environ,
        "WICKED_BRAIN_ANTIGRAVITY_DIST_DIR": str(dist_copy),
        "WICKED_BRAIN_ANTIGRAVITY_PLUGINS_DIR": str(tmp_path / "gemini-plugins"),
        "WICKED_BRAIN_VAULT_PATH": str(vault).replace("\\", "/"),
        **env_overrides,
    }
    return dist_copy, subprocess.run(
        [_git_bash(), "scripts/install-antigravity.sh"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=60, env=env,
    )


def test_install_antigravity_does_not_mutate_dist_and_supports_a_second_name(tmp_path):
    """Regression (code review 2026-09-30): placeholders used to be resolved
    in the build output itself, so a second install under another name
    (the documented WICKED_BRAIN_ANTIGRAVITY_PLUGIN_NAME=brain-2 fallback) kept
    pointing at the first install's directory, and broke once that old
    directory was deleted as the docs instruct."""
    dist_copy, first = _run_antigravity_install(tmp_path, {})
    assert first.returncode == 0, first.stderr
    assert "__WICKED_BRAIN_ANTIGRAVITY_" in (dist_copy / "mcp_config.json").read_text(encoding="utf-8"), (
        "installer rewrote the build output instead of the installed copy"
    )

    _, second = _run_antigravity_install(
        tmp_path, {"WICKED_BRAIN_ANTIGRAVITY_PLUGIN_NAME": "brain-2"}, dist_copy=dist_copy,
    )
    assert second.returncode == 0, second.stderr
    plugins = tmp_path / "gemini-plugins"
    cfg = json.loads(_read_text_via(plugins / "brain-2" / "mcp_config.json"))
    assert str(plugins / "brain-2").replace("\\", "/") in cfg["mcpServers"]["wicked-brain"]["args"][-1]
    assert "brain-2" in _read_text_via(plugins / "brain-2" / "skills" / "brain-health" / "SKILL.md")


@pytest.mark.parametrize("bad_name", ["..", ".", "a/b", "-x"])
def test_install_antigravity_rejects_unsafe_plugin_names(tmp_path, bad_name):
    """The name is appended to the plugins dir and rm -rf'd on re-install."""
    sentinel = tmp_path / "gemini-plugins" / "other-plugin"
    sentinel.mkdir(parents=True)
    _, result = _run_antigravity_install(tmp_path, {"WICKED_BRAIN_ANTIGRAVITY_PLUGIN_NAME": bad_name})
    assert result.returncode != 0
    assert sentinel.is_dir()


def test_install_antigravity_refuses_to_install_without_a_vault_path(tmp_path):
    """No vault path must fail before touching anything, not install a plugin
    whose MCP server points at a literal placeholder directory."""
    _, result = _run_antigravity_install(
        tmp_path, {"WICKED_BRAIN_VAULT_PATH": "", "WICKED_BRAIN_ENV_FILE": str(tmp_path / "missing.env")},
    )
    assert result.returncode != 0
    assert not (tmp_path / "gemini-plugins" / "wicked-brain").exists()


# --------------------------------------------------------------------------- #
# vault_health.py
# --------------------------------------------------------------------------- #

def test_vault_health_json_on_sample_vault():
    import vault_health
    result = vault_health.run_health_check(SAMPLE_VAULT)
    assert result["total_notes"] >= 6
    assert isinstance(result["total_issues"], int)
    # Must be JSON-serializable end to end, the same contract /brain-health relies on.
    json.dumps(result, default=str)


# --------------------------------------------------------------------------- #
# note_io.py - atomic, byte-exact round-trip
# --------------------------------------------------------------------------- #

def test_note_io_roundtrip_is_byte_exact(tmp_path):
    import note_io
    target = tmp_path / "note.md"
    text = "---\ntype: concept\n---\n\n## For future agent\nhello\r\nworld\n"
    note_io.write_exact(target, text)
    assert note_io.read_exact(target) == text
    # A second write replaces atomically - no stray .tmp files left behind.
    note_io.write_exact(target, text + "\nmore\n")
    leftovers = list(tmp_path.glob(".*.tmp"))
    assert leftovers == []


# --------------------------------------------------------------------------- #
# merge_notes.py / auto_merge_exact_duplicates.py - the fork's bounded upgrade
# --------------------------------------------------------------------------- #

def _write(vault: Path, rel: str, text: str) -> None:
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_auto_merge_finds_only_near_identical_pairs(tmp_path):
    from auto_merge_exact_duplicates import find_exact_pairs

    vault = tmp_path / "vault"
    body = (
        "---\ndate: 2026-01-01\ntype: concept\ntags: [concept]\nai-first: true\n---\n\n"
        "## For future agent\nThis note explains the same idea twice, on purpose,\n"
        "to exercise the near-duplicate detector with enough shared prose to\n"
        "clear the similarity threshold reliably.\n"
    )
    # vault_health's check_duplicates groups candidates by normalized TITLE
    # first, then checks body similarity within a group - so the pair needs
    # the same stem (different folder) to even be considered, same as a real
    # "saved this concept twice" duplicate.
    _write(vault, "concepts/Idea.md", body)
    _write(vault, "archive/Idea.md", body)  # near-byte-identical, same title -> should pair
    _write(
        vault, "concepts/Unrelated.md",
        "---\ndate: 2026-01-01\ntype: concept\ntags: [concept]\nai-first: true\n---\n\n"
        "## For future agent\nCompletely different content about something else.\n",
    )

    pairs = find_exact_pairs(vault)
    paired_files = {f for p in pairs for f in (p["canonical"], p["retire"])}
    assert "concepts/Idea.md" in paired_files
    assert "archive/Idea.md" in paired_files
    assert "concepts/Unrelated.md" not in paired_files


def test_auto_merge_apply_leaves_a_redirect_stub(tmp_path):
    from auto_merge_exact_duplicates import run

    vault = tmp_path / "vault"
    body = (
        "---\ndate: 2026-01-01\ntype: concept\ntags: [concept]\nai-first: true\n---\n\n"
        "## For future agent\nDuplicate content for the apply-path test, long\n"
        "enough and similar enough to clear the 0.97 threshold in both copies.\n"
    )
    _write(vault, "concepts/Note.md", body)
    _write(vault, "archive/Note.md", body)  # same stem, different folder - see the pairing test above

    exit_code = run(vault, apply=True, as_json=True)
    assert exit_code == 0

    survivors = [(vault / "concepts" / "Note.md").read_text(), (vault / "archive" / "Note.md").read_text()]
    redirects = [t for t in survivors if "type: redirect" in t]
    canonicals = [t for t in survivors if "type: redirect" not in t]
    assert len(redirects) == 1
    assert len(canonicals) == 1
    assert "This note was merged into" in redirects[0]


def test_auto_merge_refuses_notes_with_a_long_shared_prefix_but_different_endings(tmp_path):
    """Regression (found 2026-09-10 via Codex Astra's report, reproduced
    before the fix): _max_pairwise_similarity only compares each note's first
    1000 chars, a cheap signal meant for a human reviewing /brain-health's
    output. Two notes sharing 1000+ identical chars of context but reaching
    OPPOSITE decisions past that point scored 1.0 on that capped check and
    auto-merged - the losing decision was gone, overwritten with a redirect
    stub, no backup outside git. find_exact_pairs now also requires a
    full-body ratio (capped at a much larger 50000 chars, not 1000) to clear
    the threshold before treating a pair as safe to auto-merge."""
    from auto_merge_exact_duplicates import find_exact_pairs

    vault = tmp_path / "vault"
    filler = ("We evaluated the tradeoffs at length, weighing read/write patterns, "
              "team familiarity, operational burden, existing vendor relationships, "
              "projected growth over the next two years, the cost of self-hosting "
              "versus a managed offering, compliance requirements around data "
              "residency, the on-call burden for whoever owns this system. ") * 3
    a = (
        "---\ndate: 2026-09-05\ntype: decision\ntags: [decision]\nai-first: true\n---\n\n"
        f"## For future agent\nDecision note about database choice.\n\n## Context\n{filler}\n\n"
        "## Decision\nWe reversed course and chose MongoDB Atlas managed instead of Postgres.\n"
    )
    b = (
        "---\ndate: 2026-09-01\ntype: decision\ntags: [decision]\nai-first: true\n---\n\n"
        f"## For future agent\nDecision note about database choice.\n\n## Context\n{filler}\n\n"
        "## Decision\nWe chose PostgreSQL, self-hosted on Railway, instead of MongoDB.\n"
    )
    _write(vault, "decisions/Database Choice.md", a)
    _write(vault, "decisions/archive/Database Choice.md", b)

    pairs = find_exact_pairs(vault)
    assert pairs == [], (
        f"auto-merged two notes with opposite decisions past the capped-check "
        f"window: {pairs}"
    )


# --------------------------------------------------------------------------- #
# vault_lock.py - the shared lock every write path (MCP server, scripts/,
# and an agent's own native tool via the CLI) contends for on the same file.
# Found in a follow-up review (2026-09-10) after the MCP-only fix for issue
# #2 left the primary agent-native write commands and scripts/merge_notes.py
# completely unprotected - neither goes through vault_ops.py at all.
# --------------------------------------------------------------------------- #

def test_vault_lock_cli_acquire_then_release_round_trips(tmp_path):
    import subprocess
    lock_path = tmp_path / ".claude-runs" / ".write.lock"

    r1 = subprocess.run(
        [sys.executable, "scripts/vault_lock.py", "acquire", "--path", str(tmp_path)],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=15,
    )
    assert r1.returncode == 0, r1.stderr
    assert lock_path.is_file()

    r2 = subprocess.run(
        [sys.executable, "scripts/vault_lock.py", "release", "--path", str(tmp_path)],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=15,
    )
    assert r2.returncode == 0, r2.stderr
    assert not lock_path.exists()


def test_vault_lock_cli_release_of_nothing_is_not_an_error(tmp_path):
    import subprocess
    r = subprocess.run(
        [sys.executable, "scripts/vault_lock.py", "release", "--path", str(tmp_path)],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=15,
    )
    assert r.returncode == 0, r.stderr


def test_vault_lock_shared_across_scripts_and_mcp_server(tmp_path, monkeypatch):
    """The whole point of vault_lock.py: a lock acquired one way (the CLI, as
    an agent's own native-write shell step would) must be visible to and
    respected by vault_ops.py's own _write_lock - same file, same protocol,
    genuinely cross-codebase. Without this, two writers using different
    write paths race exactly like before the fix."""
    import subprocess
    monkeypatch.setenv("WICKED_BRAIN_VAULT_PATH", str(tmp_path))
    import importlib
    import vault_ops
    importlib.reload(vault_ops)
    vault_ops._WRITE_LOCK_WAIT = 2  # keep the test fast

    _write(
        tmp_path, "concepts/Note.md",
        "---\ndate: 2026-09-10\ntype: concept\ntags: [concept]\nai-first: true\n---\n\n"
        "## For future agent\nTest.\n\n## Notes\nOriginal.\n",
    )

    r = subprocess.run(
        [sys.executable, "scripts/vault_lock.py", "acquire", "--path", str(tmp_path)],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=15,
    )
    assert r.returncode == 0, r.stderr
    try:
        result = vault_ops.update_note("concepts/Note.md", append="should be blocked")
        assert "error" in result and "busy" in result["error"]
    finally:
        subprocess.run(
            [sys.executable, "scripts/vault_lock.py", "release", "--path", str(tmp_path)],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=15,
        )

    # Now that the CLI-held lock is released, the same call must succeed.
    result2 = vault_ops.update_note("concepts/Note.md", append="now it should work")
    assert "error" not in result2, result2


def test_merge_notes_apply_holds_the_lock_across_read_and_write(tmp_path):
    """merge_notes.py --apply now locks the whole compute-then-write span
    (not just the write), so a concurrent writer landing between the read
    and the write can't have its edit discarded by a merge computed from
    stale content. This just checks the documented, common case still works
    correctly under the new locked path - the interop test above already
    proves the lock itself is real and shared."""
    import subprocess
    body = (
        "---\ndate: 2026-01-01\ntype: concept\ntags: [concept]\nai-first: true\n---\n\n"
        "## For future agent\nDuplicate content, long enough and similar enough "
        "to clear the merge threshold in both copies once composed identically.\n"
    )
    _write(tmp_path, "concepts/Note.md", body)
    _write(tmp_path, "archive/Note.md", body)
    merged_body_file = tmp_path / "merged-body.txt"
    merged_body_file.write_text("Merged body content.\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "scripts/merge_notes.py", "--path", str(tmp_path),
         "--canonical", "concepts/Note.md", "--retire", "archive/Note.md",
         "--merged-body-file", str(merged_body_file), "--apply"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "Merged." in result.stdout
    assert not (tmp_path / ".claude-runs" / ".write.lock").exists(), "lock must be released after apply"
    assert "type: redirect" in (tmp_path / "archive/Note.md").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# link_graph.py
# --------------------------------------------------------------------------- #

def test_link_graph_on_sample_vault_has_no_dangling_links():
    import link_graph
    graph = link_graph.build_graph(SAMPLE_VAULT)
    assert graph["stats"]["node_count"] >= 6
    assert graph["stats"]["dangling_link_count"] == 0


# --------------------------------------------------------------------------- #
# freshness_lint.py
# --------------------------------------------------------------------------- #

def test_freshness_lint_flags_undated_fast_fact(tmp_path):
    import freshness_lint
    vault = tmp_path / "vault"
    _write(
        vault, "projects/P.md",
        "---\ndate: 2026-01-01\ntype: project\ntags: [project]\nai-first: true\n---\n\n"
        "## For future agent\nA project note.\n\nThe project has 13 open tasks.\n",
    )
    result = freshness_lint.main(["freshness_lint.py", "--path", str(vault), "--json"])
    assert result in (0, 1)  # lint exits nonzero when it finds FRESH-1 errors


# --------------------------------------------------------------------------- #
# vault_ops.py - the shared search/backlinks layer the dashboard also uses
# --------------------------------------------------------------------------- #

def test_vault_ops_search_and_backlinks(monkeypatch):
    monkeypatch.setenv("WICKED_BRAIN_VAULT_PATH", str(SAMPLE_VAULT))
    import importlib
    import vault_ops
    importlib.reload(vault_ops)

    results = vault_ops.search("bi-temporal", limit=5)
    assert any(r["path"] == "concepts/Bi-temporal facts.md" for r in results)

    back = vault_ops.backlinks("Wicked Brain")
    assert back["count"] > 0


def test_reference_weight_boosts_heavily_linked_notes(tmp_path, monkeypatch):
    """The 'this fact keeps getting referenced' ranking signal (Mem0-style
    salience, grounded in this vault's own [[wikilink]] graph via
    link_graph.build_graph rather than a separate access-log heuristic).
    Builds two notes with identical, tied lexical scores for the same
    query - the only thing that should separate them is inbound link count."""
    monkeypatch.setenv("WICKED_BRAIN_VAULT_PATH", str(tmp_path))
    import importlib
    import vault_ops
    importlib.reload(vault_ops)

    # Three referrers link to "hub", none link to "loner" - same body text
    # (and therefore identical lexical score) on both targets.
    body = "Mentions quokka husbandry exactly once for scoring purposes.\n"
    _write(tmp_path, "concepts/hub.md", "---\ndate: 2026-01-01\ntype: concept\ntags: [concept]\nai-first: true\n---\n\n" + body)
    _write(tmp_path, "concepts/loner.md", "---\ndate: 2026-01-01\ntype: concept\ntags: [concept]\nai-first: true\n---\n\n" + body)
    for i in range(3):
        _write(tmp_path, f"concepts/referrer{i}.md",
               f"---\ndate: 2026-01-01\ntype: concept\ntags: [concept]\nai-first: true\n---\n\nSee [[concepts/hub]].\n")

    counts = vault_ops._inbound_link_counts(tmp_path)
    assert counts.get("concepts/hub.md", 0) == 3
    assert counts.get("concepts/loner.md", 0) == 0
    assert vault_ops._reference_weight(3) > vault_ops._reference_weight(0) == 1.0

    results = vault_ops.search("quokka husbandry", semantic=False, limit=10)
    paths = [r["path"] for r in results]
    assert paths.index("concepts/hub.md") < paths.index("concepts/loner.md"), (
        "the heavily-referenced note should outrank its lexically-tied twin"
    )


def test_search_excludes_a_trashed_notes_stale_index_entry(tmp_path, monkeypatch):
    """Regression (found 2026-09-10 via Codex Astra's report): a note's
    semantic-index vector isn't pruned automatically when the note itself is
    deleted/trashed - nothing rebuilds the index until the next full
    /brain-reindex. Before this fix, _semantic_fuse iterated the raw index
    with no check against what the vault walk actually found, so a stale
    entry for a note that's now in _trash/ (or hard deleted) still scored
    and could surface as a top hit. Fixed by requiring semantic hits to be
    in `scanned` - this exact search call's fresh walk of the vault."""
    monkeypatch.setenv("WICKED_BRAIN_VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("WICKED_BRAIN_SEARCH_SEMANTIC", "1")
    import importlib
    import json
    import vault_ops
    importlib.reload(vault_ops)

    (tmp_path / "_trash").mkdir(parents=True, exist_ok=True)
    (tmp_path / "_trash" / "Secret Rotation Policy.md").write_text(
        "---\ndate: 2026-09-01\ntype: concept\ntags: [concept]\nai-first: true\n---\n\n"
        "## For future agent\nRetracted.\n\n## Notes\nThis policy was retracted.\n",
        encoding="utf-8",
    )
    fake_vec = [1.0, 0.0, 0.0]
    index = {"model": "bge-m3", "format": 2, "notes": {
        "_trash/Secret Rotation Policy.md": {
            "hash": "deadbeef", "title": "Secret Rotation Policy", "vecs": [fake_vec],
        },
    }}
    (tmp_path / ".memory-semantic-index.json").write_text(json.dumps(index), encoding="utf-8")
    (tmp_path / "concepts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "concepts" / "Other.md").write_text(
        "---\ndate: 2026-09-10\ntype: concept\ntags: [concept]\nai-first: true\n---\n\n"
        "## For future agent\nUnrelated.\n\n## Notes\nUnrelated content.\n",
        encoding="utf-8",
    )
    vault_ops._embed_query = lambda text, model=None: fake_vec

    results = vault_ops.search("secret rotation policy", limit=10, semantic=True)
    assert "_trash/Secret Rotation Policy.md" not in [r["path"] for r in results]


def test_stale_index_detects_an_edited_note_not_just_a_missing_one(tmp_path, monkeypatch, capsys):
    """Regression (found 2026-09-10 via Codex Astra's report): the original
    staleness check was a pure set difference (scanned - indexed) - it could
    only ever notice a note that was NEVER indexed at all, never one that IS
    in the index but whose CONTENT has since changed in place. An edited
    note kept its stale, pre-edit ranking indefinitely with no signal
    anywhere. Fixed by also comparing each scanned note's current content
    hash against what the index has on file for it."""
    monkeypatch.setenv("WICKED_BRAIN_VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("WICKED_BRAIN_SEARCH_SEMANTIC", "1")
    import importlib
    import json
    import semantic_search
    import vault_ops
    importlib.reload(vault_ops)

    (tmp_path / "concepts").mkdir(parents=True, exist_ok=True)
    note_path = tmp_path / "concepts" / "Edited Note.md"
    original_text = (
        "---\ndate: 2026-09-01\ntype: concept\ntags: [concept]\nai-first: true\n---\n\n"
        "## For future agent\nOriginal.\n\n## Notes\nOriginal content before the edit.\n"
    )
    note_path.write_text(original_text, encoding="utf-8")

    stale_hash = semantic_search._content_hash(original_text)
    fake_vec = [1.0, 0.0, 0.0]
    index = {"model": "bge-m3", "format": 2, "notes": {
        "concepts/Edited Note.md": {"hash": stale_hash, "title": "Edited Note", "vecs": [fake_vec]},
    }}
    (tmp_path / ".memory-semantic-index.json").write_text(json.dumps(index), encoding="utf-8")

    # Edited in place after indexing - same path, new content.
    note_path.write_text(original_text + "\nA brand new fact added after indexing.\n", encoding="utf-8")
    vault_ops._embed_query = lambda text, model=None: fake_vec

    vault_ops.search("original content", limit=10, semantic=True)
    stderr = capsys.readouterr().err
    assert "1 edited since indexing" in stderr, stderr


def test_embed_note_chunks_always_includes_the_ending(monkeypatch):
    """Regression (found 2026-09-10 via Codex Astra's report): chunking a
    long note used to keep only the FIRST _MAX_CHUNKS chunks - everything
    past that, often exactly where a note's conclusion lives, was silently
    never embedded at all. Fixed to always keep the last chunk too."""
    import semantic_search

    seen_chunks = []
    monkeypatch.setattr(semantic_search, "embed",
                         lambda text, model=None, retries=None: seen_chunks.append(text) or [1.0, 0.0])

    body_room = semantic_search._CHUNK_CHARS
    long_text = ("filler " * 2000) + "UNIQUE-ENDING-MARKER-XYZ"
    assert len(long_text) > body_room * semantic_search._MAX_CHUNKS  # actually exercises the cap

    semantic_search.embed_note_chunks(long_text, header="")
    assert len(seen_chunks) == semantic_search._MAX_CHUNKS
    assert any("UNIQUE-ENDING-MARKER-XYZ" in c for c in seen_chunks), "the note's ending was dropped"


def test_concurrent_update_note_calls_do_not_lose_an_edit(tmp_path, monkeypatch):
    """Regression (found 2026-09-10 via Codex Astra's report, reproduced with
    two racing threads before the fix): update_note was an unguarded
    read-modify-write. Two concurrent calls both read the same pre-edit text,
    both reported success, and only the second writer's change survived - the
    first was silently gone with no error anywhere. _write_lock in
    vault_ops.py now serializes the critical section across processes (a
    real file lock, not an in-process one - two separate MCP server
    instances, one per agent, is the real-world shape of this race)."""
    monkeypatch.setenv("WICKED_BRAIN_VAULT_PATH", str(tmp_path))
    import importlib
    import threading
    import vault_ops
    importlib.reload(vault_ops)

    _write(
        tmp_path, "concepts/Shared.md",
        "---\ndate: 2026-09-10\ntype: concept\ntags: [concept]\nai-first: true\n---\n\n"
        "## For future agent\nShared.\n\n## Notes\nInitial content.\n",
    )

    results: dict[str, dict] = {}

    def agent(name: str, text: str) -> None:
        results[name] = vault_ops.update_note("concepts/Shared.md", append=text)

    tA = threading.Thread(target=agent, args=("A", "Claude Code's addition."))
    tB = threading.Thread(target=agent, args=("B", "Codex CLI's addition."))
    tA.start(); tB.start()
    tA.join(timeout=30); tB.join(timeout=30)

    assert "error" not in results["A"] and "error" not in results["B"], results
    final = (tmp_path / "concepts" / "Shared.md").read_text(encoding="utf-8")
    assert "Claude Code's addition." in final, "first writer's edit was lost"
    assert "Codex CLI's addition." in final, "second writer's edit was lost"


def test_move_note_holds_the_write_lock_too(tmp_path, monkeypatch):
    """Found during a follow-up self-review (2026-09-10): move_note calls
    _bookkeep (appends to today's session log, and would rewrite index.md
    for any caller that passes a summary) without holding _write_lock, even
    though save_note/update_note/replace_text all do for exactly this
    reason - a concurrent writer's own bookkeeping could interleave with or
    clobber this one's. Not proven to lose data in practice (a single short
    session-log append tends to land atomically even unlocked, and
    move_note never currently passes a summary so never touches index.md at
    all), but there's no reason for it to be the one write path without the
    same protection everything else has. This just checks it does not
    deadlock or drop bookkeeping under real concurrency, now that it holds
    the same lock."""
    monkeypatch.setenv("WICKED_BRAIN_VAULT_PATH", str(tmp_path))
    import importlib
    import threading
    import vault_ops
    importlib.reload(vault_ops)

    for i in range(1, 9):
        _write(
            tmp_path, f"concepts/Note {i}.md",
            f"---\ndate: 2026-09-10\ntype: concept\ntags: [concept]\nai-first: true\n---\n\n"
            f"## For future agent\nNote {i}.\n",
        )

    results: dict[int, dict] = {}

    def mover(i: int) -> None:
        results[i] = vault_ops.move_note(f"concepts/Note {i}.md", f"concepts/Renamed {i}.md")

    threads = [threading.Thread(target=mover, args=(i,)) for i in range(1, 9)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert all("error" not in r for r in results.values()), results
    for i in range(1, 9):
        assert (tmp_path / "concepts" / f"Renamed {i}.md").is_file()

    import datetime
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    log_text = (tmp_path / "sessions" / f"{today}.md").read_text(encoding="utf-8")
    move_lines = [line for line in log_text.splitlines() if " - move | " in line]
    assert len(move_lines) == 8, f"expected 8 session-log lines, found {len(move_lines)}"


def test_update_note_refuses_invalid_utf8_instead_of_corrupting_it(tmp_path, monkeypatch):
    """Regression (found 2026-09-10 via Codex Astra's report): _read_safe
    (used for read-only browsing elsewhere) decodes with errors="replace" -
    fine for search/read_note, but update_note/replace_text used it too,
    which meant an invalid byte got silently replaced with a permanent
    U+FFFD on write-back, with update_note reporting full success. Fixed by
    giving update_note/replace_text a strict reader (_read_strict) that
    refuses instead, matching scripts/note_io.py's philosophy."""
    monkeypatch.setenv("WICKED_BRAIN_VAULT_PATH", str(tmp_path))
    import importlib
    import vault_ops
    importlib.reload(vault_ops)

    raw = (
        b"---\ndate: 2026-09-10\ntype: concept\ntags: [concept]\nai-first: true\n---\n\n"
        b"## For future agent\nEncoding test.\n\n## Notes\n"
        b"A stray invalid byte: [\xff] right here.\n"
    )
    path = tmp_path / "concepts" / "Encoding Test.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)

    result = vault_ops.update_note("concepts/Encoding Test.md", append="more text")
    assert "error" in result
    assert path.read_bytes() == raw, "the invalid byte must survive untouched, not become U+FFFD"


def test_update_note_does_not_truncate_a_note_past_the_internal_read_cap(tmp_path, monkeypatch):
    """Regression (found 2026-09-10 via Codex Astra's report): _read_safe
    silently sliced at 4,000,000 chars with no truncation flag on the
    write-back path (unlike read_note, which flags it explicitly) - editing
    a note past that cap permanently lost its entire tail, with update_note
    reporting full success. Fixed the same way as the encoding regression
    above: update_note/replace_text now use _read_strict, which never
    truncates."""
    monkeypatch.setenv("WICKED_BRAIN_VAULT_PATH", str(tmp_path))
    import importlib
    import vault_ops
    importlib.reload(vault_ops)

    filler = "Line of note content padding for size.\n" * 110_000  # ~4.29M chars
    text = (
        "---\ndate: 2026-09-10\ntype: concept\ntags: [concept]\nai-first: true\n---\n\n"
        "## For future agent\nLarge note test.\n\n## Notes\n"
        + filler + "\n### THE-VERY-END-MARKER\n"
    )
    path = tmp_path / "concepts" / "Large Note.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")

    result = vault_ops.update_note("concepts/Large Note.md", append="one more line")
    assert "error" not in result
    final = path.read_text(encoding="utf-8")
    assert "THE-VERY-END-MARKER" in final, "the note's tail was silently truncated"
    assert "one more line" in final


# --------------------------------------------------------------------------- #
# vault_git.py - Phase 2, version history
# --------------------------------------------------------------------------- #

def _git_init(vault: Path) -> None:
    """git init + a local identity, so commits work even without a global
    user.name/user.email configured (portable across CI and machines)."""
    vault.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=vault, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=vault, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=vault, check=True)


def test_maybe_commit_noop_on_non_git_vault(tmp_path):
    import vault_git
    vault = tmp_path / "vault"
    _write(vault, "concepts/A.md", "content\n")
    result = vault_git.maybe_commit(vault, "concepts/A.md", "test commit")
    assert result["committed"] is False
    assert result["reason"] == "not a git vault"


def test_maybe_commit_creates_a_real_commit(tmp_path):
    import vault_git
    vault = tmp_path / "vault"
    _git_init(vault)
    _write(vault, "concepts/A.md", "content\n")

    result = vault_git.maybe_commit(vault, "concepts/A.md", "add A")
    assert result["committed"] is True
    assert result["hash"]

    log = subprocess.run(["git", "log", "--oneline"], cwd=vault, capture_output=True, text=True)
    assert "add A" in log.stdout

    # A second commit with no actual changes is a safe no-op, not an error.
    again = vault_git.maybe_commit(vault, "concepts/A.md", "add A again")
    assert again["committed"] is False
    assert again["reason"] == "no changes to commit"


def test_maybe_commit_retries_on_index_lock_contention(tmp_path, monkeypatch):
    """bg-agent.sh's headless run fires several Write/Edit calls back to back,
    each triggering its own validate-ai-first.sh -> vault_git.py --commit
    subprocess - two can race for .git/index.lock. This was a real,
    previously-silent bug: the loser's commit failed and the shell hook
    swallowed it with `|| true`, leaving that file's edit uncommitted in the
    working tree indefinitely. Simulates two lock failures before success."""
    import vault_git
    vault = tmp_path / "vault"
    _git_init(vault)
    _write(vault, "concepts/A.md", "content\n")

    real_run = subprocess.run
    lock_failures = {"n": 0}

    def flaky_run(cmd, **kwargs):
        if "add" in cmd and lock_failures["n"] < 2:
            lock_failures["n"] += 1
            return subprocess.CompletedProcess(
                cmd, 128, "",
                "fatal: Unable to create '.../.git/index.lock': File exists.",
            )
        return real_run(cmd, **kwargs)

    monkeypatch.setattr(vault_git.subprocess, "run", flaky_run)
    monkeypatch.setattr(vault_git.time, "sleep", lambda *_a: None)  # keep the test fast

    result = vault_git.maybe_commit(vault, "concepts/A.md", "add A")
    assert result["committed"] is True
    assert lock_failures["n"] == 2  # confirms it actually hit the retry path, not a fluke pass


def test_maybe_commit_gives_up_after_sustained_lock_contention(tmp_path, monkeypatch):
    """Contention that never clears (a genuinely stuck lock, not a brief race)
    still fails cleanly - reported in the return value, not raised - after
    exhausting the retry budget, rather than retrying forever."""
    import vault_git
    vault = tmp_path / "vault"
    _git_init(vault)
    _write(vault, "concepts/A.md", "content\n")

    def always_locked(cmd, **kwargs):
        return subprocess.CompletedProcess(
            cmd, 128, "",
            "fatal: Unable to create '.../.git/index.lock': File exists.",
        )

    monkeypatch.setattr(vault_git.subprocess, "run", always_locked)
    monkeypatch.setattr(vault_git.time, "sleep", lambda *_a: None)

    result = vault_git.maybe_commit(vault, "concepts/A.md", "add A")
    assert result["committed"] is False
    assert "index.lock" in result["reason"]


def test_git_log_and_git_diff_after_a_few_commits(tmp_path):
    import vault_git
    vault = tmp_path / "vault"
    _git_init(vault)
    _write(vault, "concepts/A.md", "version one\n")
    vault_git.maybe_commit(vault, "concepts/A.md", "v1")
    _write(vault, "concepts/A.md", "version two\n")
    vault_git.maybe_commit(vault, "concepts/A.md", "v2")

    log = vault_git.git_log(vault, "concepts/A.md")
    assert [c["message"] for c in log] == ["v2", "v1"]  # newest first

    diff = vault_git.git_diff(vault, "concepts/A.md", log[0]["hash"])
    assert "-version one" in diff
    assert "+version two" in diff


def test_git_status_summary(tmp_path):
    import vault_git
    vault = tmp_path / "vault"
    assert vault_git.git_status_summary(tmp_path / "not-a-vault")["is_git_vault"] is False
    _git_init(vault)
    _write(vault, "concepts/A.md", "content\n")
    vault_git.maybe_commit(vault, "concepts/A.md", "add A")
    status = vault_git.git_status_summary(vault)
    assert status["is_git_vault"] is True
    assert status["commit_count"] == 1
    assert status["dirty_files"] == 0


def test_activity_by_day_empty_on_non_git_vault(tmp_path):
    import vault_git
    assert vault_git.activity_by_day(tmp_path / "not-a-vault") == []


def test_activity_by_day_counts_commits_and_lines(tmp_path):
    import vault_git
    vault = tmp_path / "vault"
    _git_init(vault)
    _write(vault, "concepts/A.md", "one\ntwo\n")
    vault_git.maybe_commit(vault, "concepts/A.md", "add A")
    _write(vault, "concepts/B.md", "three\n")
    vault_git.maybe_commit(vault, "concepts/B.md", "add B")

    by_day = vault_git.activity_by_day(vault, days=30)
    assert len(by_day) == 1  # both commits happened today, in this test run
    today = by_day[0]
    assert today["commits"] == 2
    assert today["notes_touched"] == 2
    assert today["insertions"] == 3  # 2 lines in A + 1 line in B
    assert today["deletions"] == 0


def test_init_vault_repo_makes_one_initial_commit(tmp_path):
    import vault_git
    vault = tmp_path / "vault"
    _write(vault, "concepts/A.md", "content\n")

    result = vault_git.init_vault_repo(vault)
    assert result["initialized"] is True
    assert (vault / ".git").is_dir()
    assert (vault / ".gitignore").is_file()

    # Idempotent: calling it again on an already-git vault is a safe no-op.
    again = vault_git.init_vault_repo(vault)
    assert again["initialized"] is False


def test_merge_apply_on_a_git_vault_is_one_commit(tmp_path):
    """merge_notes.apply_merge should produce exactly one commit covering
    both the canonical and retired files, not two."""
    import merge_notes
    vault = tmp_path / "vault"
    _git_init(vault)
    body = (
        "---\ndate: 2026-01-01\ntype: concept\ntags: [concept]\nai-first: true\n---\n\n"
        "## For future agent\nOriginal content.\n"
    )
    _write(vault, "concepts/Canonical.md", body)
    _write(vault, "concepts/Retired.md", body)
    subprocess.run(["git", "add", "-A"], cwd=vault, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "seed"], cwd=vault, check=True, capture_output=True)

    result = merge_notes.compute_merge(vault, "concepts/Canonical.md", "concepts/Retired.md", "Merged body.\n")
    merge_notes.apply_merge(vault, result)

    log = subprocess.run(["git", "log", "--oneline"], cwd=vault, capture_output=True, text=True)
    lines = [ln for ln in log.stdout.splitlines() if ln.strip()]
    assert len(lines) == 2  # seed + one merge commit (not two)
    assert "merge:" in lines[0]


# --------------------------------------------------------------------------- #
# Phase 3: vault_crypto.py - client-side encryption
# --------------------------------------------------------------------------- #

def test_vault_crypto_roundtrip_and_wrong_passphrase():
    import vault_crypto
    salt = vault_crypto.new_salt()
    key = vault_crypto.derive_key("correct horse battery staple", salt)
    ciphertext = vault_crypto.encrypt(b"hello vault", key)
    assert vault_crypto.decrypt(ciphertext, key) == b"hello vault"

    wrong_key = vault_crypto.derive_key("wrong passphrase", salt)
    with pytest.raises(vault_crypto.WrongPassphrase):
        vault_crypto.decrypt(ciphertext, wrong_key)


def test_vault_crypto_content_hash_is_stable_and_content_dependent():
    import vault_crypto
    h1 = vault_crypto.content_hash(b"same content")
    h2 = vault_crypto.content_hash(b"same content")
    h3 = vault_crypto.content_hash(b"different content")
    assert h1 == h2
    assert h1 != h3


# --------------------------------------------------------------------------- #
# integrations/mcp-server/server.py - resources and prompts, added alongside
# the existing tools. Imported by explicit file path (see _import_by_path
# below) for the same reason as sync_server: "server.py" exists in three
# directories, and a plain `import server` would grab whichever one a sys.path
# insert or an earlier test happened to cache in sys.modules first.
# --------------------------------------------------------------------------- #

def test_mcp_server_resources_and_prompts(monkeypatch):
    monkeypatch.setenv("WICKED_BRAIN_VAULT_PATH", str(SAMPLE_VAULT))
    mcp_server = _import_by_path(
        "mcp_server_under_test", REPO_ROOT / "integrations" / "mcp-server" / "server.py"
    )

    async def _check():
        resources = await mcp_server.mcp.list_resources()
        uris = {str(r.uri) for r in resources}
        assert "wicked-brain://critical-facts" in uris or "wicked-brain://index" in uris, (
            "at least one static resource should register against a real vault"
        )

        templates = await mcp_server.mcp.list_resource_templates()
        assert any(t.uriTemplate == "wicked-brain://note/{path}" for t in templates)

        # Read a real note through the templated resource - percent-encoded,
        # since FastMCP's URI-template matching here is single-segment only
        # (tested directly, see note_resource's own docstring).
        content = await mcp_server.mcp.read_resource("wicked-brain://note/concepts%2FBi-temporal%20facts.md")
        assert "bi-temporal" in content[0].content.lower()

        prompts = await mcp_server.mcp.list_prompts()
        names = {p.name for p in prompts}
        assert "brain-find" in names  # one real skill, spot-checked by name

        result = await mcp_server.mcp.get_prompt("brain-find")
        text = result.messages[0].content.text
        assert len(text) > 20  # got real instructions, not an empty/error stub

    import asyncio
    asyncio.run(_check())


# --------------------------------------------------------------------------- #
# dashboard/server.py - the revert endpoint (its first write path; every
# other route is read-only). Imported by explicit file path for the same
# "server.py" name-collision reason as the mcp-server test above.
# --------------------------------------------------------------------------- #

def test_dashboard_revert_writes_a_new_commit_not_a_hard_reset(tmp_path, monkeypatch):
    """Revert must add a new commit restoring the old content, never
    `git checkout <hash>` or a hard reset - the version being reverted away
    from has to stay fully recoverable in history too (see
    dashboard/server.py's api_revert docstring)."""
    monkeypatch.setenv("WICKED_BRAIN_VAULT_PATH", str(tmp_path))
    dash = _import_by_path("dashboard_server_under_test", REPO_ROOT / "dashboard" / "server.py")

    _git_init(tmp_path)
    import vault_git
    _write(tmp_path, "concepts/A.md", "version one\n")
    vault_git.maybe_commit(tmp_path, "concepts/A.md", "v1")
    _write(tmp_path, "concepts/A.md", "version two\n")
    v2 = vault_git.maybe_commit(tmp_path, "concepts/A.md", "v2")
    assert v2["committed"] is True

    log_v1 = vault_git.git_log(tmp_path, "concepts/A.md")[-1]  # oldest = v1
    assert log_v1["message"] == "v1"

    from starlette.testclient import TestClient
    client = TestClient(dash.app)
    r = client.post(f"/api/history/concepts/A.md?commit={log_v1['hash']}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["commit"]["committed"] is True

    # Working tree now has the OLD content back...
    assert (tmp_path / "concepts" / "A.md").read_text(encoding="utf-8") == "version one\n"
    # ...but as a NEW third commit, not a reset - v1 and v2 both still there.
    log_after = vault_git.git_log(tmp_path, "concepts/A.md")
    assert len(log_after) == 3
    assert log_after[0]["message"].startswith("revert:")

    # A bogus/unknown commit hash must 404, not 500.
    r2 = client.post("/api/history/concepts/A.md?commit=0000000")
    assert r2.status_code == 404


# --------------------------------------------------------------------------- #
# Phase 3: sync_server/ - imported by explicit file path, not sys.path, since
# "server.py" also exists in integrations/mcp-server/ and dashboard/ and a
# sys.path-order import would silently grab the wrong one.
# --------------------------------------------------------------------------- #

def _import_by_path(name: str, path: Path):
    """Regression (found 2026-09-10 while adding a required Optional[int]
    field to sync_server's request models): this helper never registered the
    module in sys.modules before exec_module - the standard importlib.util
    recipe does (see the docs for spec_from_file_location), because pydantic
    v2's forward-ref resolution for a REQUIRED nullable field looks the
    defining module up via sys.modules[cls.__module__] to build its
    validator eagerly. A field with a default happened not to need that
    lookup, so this stayed invisible until expected_revision (no default, by
    design - see NoteIn's docstring) exposed it as a real
    PydanticUserError."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _fresh_sync_server(tmp_path, monkeypatch, token: str = "test-token"):
    """A sync_server.server module bound to a fresh temp SQLite DB, imported
    fresh each call so its module-level engine cache never leaks between tests."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'sync.db'}")
    monkeypatch.setenv("SYNC_TOKEN", token)
    return _import_by_path("sync_server_under_test", REPO_ROOT / "sync_server" / "server.py")


def test_sync_server_endpoints(tmp_path, monkeypatch):
    from starlette.testclient import TestClient
    server = _fresh_sync_server(tmp_path, monkeypatch)
    client = TestClient(server.app)
    H = {"Authorization": "Bearer test-token"}

    assert client.get("/health").json() == {"ok": True}
    assert client.get("/salt").status_code == 401  # no auth
    assert client.get("/salt", headers=H).status_code == 404  # none set yet

    r = client.post("/salt", json={"value": "c2FsdA=="}, headers=H)
    assert r.status_code == 200 and r.json()["created"] is True
    assert client.post("/salt", json={"value": "b3RoZXI="}, headers=H).status_code == 409
    assert client.get("/salt", headers=H).json()["value"] == "c2FsdA=="

    import base64
    ct = base64.b64encode(b"fake-ciphertext").decode()
    # expected_revision=0: this device believes concepts/Foo.md is new.
    put = client.put("/notes/concepts/Foo.md", headers=H, json={
        "ciphertext": ct, "content_hash": "abc123",
        "mtime": "2026-09-08T00:00:00+00:00", "device_id": "dev1", "expected_revision": 0,
    })
    assert put.status_code == 200
    rev1 = put.json()["revision"]

    got = client.get("/notes/concepts/Foo.md", headers=H).json()
    assert got["content_hash"] == "abc123" and got["deleted"] is False

    manifest = client.get("/manifest", headers=H).json()["notes"]
    assert manifest == [{"path": "concepts/Foo.md", "content_hash": "abc123",
                          "mtime": "2026-09-08T00:00:00+00:00", "revision": rev1, "deleted": False}]

    # Regression (found 2026-09-10 via Codex Astra's report): a PUT/DELETE
    # whose expected_revision no longer matches the server's actual current
    # revision must be rejected with a 409 carrying the current state, not
    # silently accepted - this is the whole fix for "overlapping syncs lose
    # edits without a conflict". A stale expected_revision (0, as if the note
    # were still new) against a path that already has real content at rev1:
    stale_put = client.put("/notes/concepts/Foo.md", headers=H, json={
        "ciphertext": ct, "content_hash": "should-not-land",
        "mtime": "2026-09-08T00:01:00+00:00", "device_id": "dev2", "expected_revision": 0,
    })
    assert stale_put.status_code == 409
    conflict_body = stale_put.json()["detail"]
    assert conflict_body["conflict"] is True
    assert conflict_body["current"]["content_hash"] == "abc123"  # dev1's write, untouched
    assert conflict_body["current"]["revision"] == rev1
    # The rejected write must not have landed:
    assert client.get("/notes/concepts/Foo.md", headers=H).json()["content_hash"] == "abc123"

    # A force write (expected_revision=None) bypasses the check on purpose -
    # for a caller that has already resolved a conflict some other way.
    forced = client.put("/notes/concepts/Foo.md", headers=H, json={
        "ciphertext": ct, "content_hash": "forced-value",
        "mtime": "2026-09-08T00:02:00+00:00", "device_id": "dev2", "expected_revision": None,
    })
    assert forced.status_code == 200
    rev_forced = forced.json()["revision"]
    assert client.get("/notes/concepts/Foo.md", headers=H).json()["content_hash"] == "forced-value"

    # A DELETE with a stale expected_revision is rejected the same way.
    stale_delete = client.request("DELETE", "/notes/concepts/Foo.md", headers=H,
                                   json={"device_id": "dev1", "expected_revision": rev1})
    assert stale_delete.status_code == 409

    dele = client.request("DELETE", "/notes/concepts/Foo.md", headers=H,
                           json={"device_id": "dev1", "expected_revision": rev_forced})
    assert dele.status_code == 200
    assert dele.json()["revision"] > rev_forced

    manifest_after = client.get("/manifest", headers=H).json()["notes"]
    assert manifest_after[0]["deleted"] is True

    # revision is time.time_ns() - a fixed large literal isn't reliably "in the
    # future" against that, so use the last real revision seen instead.
    latest_revision = manifest_after[0]["revision"]
    assert client.get(f"/manifest?since={latest_revision}", headers=H).json()["notes"] == []


# --------------------------------------------------------------------------- #
# Phase 3: vault_sync.py end to end - two real devices against a live,
# backgrounded instance of the real server (not a mock), talking over real
# HTTP (127.0.0.1), the same way two real machines would.
# --------------------------------------------------------------------------- #

def _launch_sync_server(tmp_path_factory, monkeypatch, token, module_name):
    """Start a real, backgrounded instance of the sync server on a free port
    with its own empty database. Returns (url, stop). Used by the fixture and
    by tests that need a SECOND server (a replacement for a lost one)."""
    import socket
    import threading
    import time as time_mod
    import uvicorn

    db_dir = tmp_path_factory.mktemp("syncdb")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_dir / 'sync.db'}")
    monkeypatch.setenv("SYNC_TOKEN", token)
    server = _import_by_path(module_name, REPO_ROOT / "sync_server" / "server.py")

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    config = uvicorn.Config(server.app, host="127.0.0.1", port=port, log_level="warning")
    srv = uvicorn.Server(config)
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    for _ in range(100):
        if srv.started:
            break
        time_mod.sleep(0.05)
    else:
        pytest.fail("sync server did not start in time")

    def stop():
        srv.should_exit = True
        thread.join(timeout=5)

    return f"http://127.0.0.1:{port}", stop


@pytest.fixture
def live_sync_server(tmp_path_factory, monkeypatch):
    url, stop = _launch_sync_server(tmp_path_factory, monkeypatch, "e2e-token", "sync_server_e2e")
    yield url, "e2e-token"
    stop()


def _seed_vault(vault: Path, notes: dict[str, str]) -> None:
    for rel, body in notes.items():
        p = vault / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")


def test_bootstrap_preserves_preexisting_local_content(tmp_path, live_sync_server):
    """Regression (found 2026-09-10 via Codex Astra's report, reproduced
    against a real local server before this fix): bootstrap wrote every
    remote note over any matching local path with zero diffing. Realistic
    trap: every device's own /brain-init creates its own local index.md/
    _CLAUDE.md/CRITICAL_FACTS.md before that device ever syncs, so
    bootstrapping a SECOND real device silently destroyed its own genuinely-
    local, never-synced content at those exact paths - no warning, no
    backup. Fixed: a local file that exists and differs from what's about
    to be pulled is now preserved as a conflict copy first."""
    import vault_sync
    url, token = live_sync_server

    device_y = tmp_path / "device-y"
    _seed_vault(device_y, {"index.md": "# Index\n\nfrom device Y\n"})
    vault_sync.sync(device_y, url, token, "correct horse battery staple", "device-y")

    # device-x already has its OWN real, never-synced content at the same path.
    device_x = tmp_path / "device-x"
    _seed_vault(device_x, {"index.md": "# Index\n\nmy real local work, never synced\n"})

    result = vault_sync.bootstrap(device_x, url, token, "correct horse battery staple",
                                   device_id="device-x")
    assert "index.md" in result["written"]
    assert len(result["preserved"]) == 1
    preserved = result["preserved"][0]
    assert preserved["path"] == "index.md"

    # Remote content becomes canonical (this device is joining an existing
    # synced vault, per bootstrap's whole purpose) - but device-x's original
    # content must survive SOMEWHERE, not vanish.
    assert (device_x / "index.md").read_text(encoding="utf-8") == "# Index\n\nfrom device Y\n"
    conflict_copy = device_x / preserved["conflict_copy"]
    assert conflict_copy.is_file()
    assert conflict_copy.read_text(encoding="utf-8") == "# Index\n\nmy real local work, never synced\n"


def test_bootstrap_does_not_flag_identical_local_content_as_a_conflict(tmp_path, live_sync_server):
    """The flip side of the fix above: a local file that already matches
    what's about to be pulled (e.g. two devices' /brain-init produced the
    same boilerplate) must not spuriously get a conflict copy - nothing
    would actually be lost by the overwrite."""
    import vault_sync
    url, token = live_sync_server

    device_y = tmp_path / "device-y"
    _seed_vault(device_y, {"CRITICAL_FACTS.md": "same content on both devices\n"})
    vault_sync.sync(device_y, url, token, "correct horse battery staple", "device-y")

    device_x = tmp_path / "device-x"
    _seed_vault(device_x, {"CRITICAL_FACTS.md": "same content on both devices\n"})

    result = vault_sync.bootstrap(device_x, url, token, "correct horse battery staple",
                                   device_id="device-x")
    assert result["preserved"] == []
    assert not list(device_x.glob("*sync-conflict*"))


def test_bootstrap_creates_vault_dir_if_missing(tmp_path, live_sync_server):
    """Regression: a brand-new device's vault directory may not exist yet -
    bootstrap must create it rather than crash on the salt file write."""
    import vault_sync
    url, token = live_sync_server
    vault = tmp_path / "brand-new-device"  # deliberately not created
    assert not vault.exists()
    result = vault_sync.bootstrap(vault, url, token, "correct horse battery staple")
    assert result == {"written": [], "preserved": []}  # nothing pushed to this server yet in this test
    assert vault.is_dir()


def test_bootstrap_with_wrong_passphrase_fails_loudly(tmp_path, live_sync_server):
    """A wrong passphrase must raise, never silently write garbage or succeed."""
    import vault_crypto
    import vault_sync
    url, token = live_sync_server
    device_a = tmp_path / "device-a"
    _seed_vault(device_a, {"concepts/Secret.md": "sensitive content\n"})
    vault_sync.sync(device_a, url, token, "the right passphrase", "device-a")

    device_wrong = tmp_path / "device-wrong"
    with pytest.raises(vault_crypto.WrongPassphrase):
        vault_sync.bootstrap(device_wrong, url, token, "a completely different passphrase")


def test_sync_with_wrong_passphrase_does_not_corrupt_remote_content(tmp_path, live_sync_server):
    """Regression (found 2026-09-10 via Codex Astra's report, reproduced
    against a real local server before this fix): unlike bootstrap (which
    always decrypts something up front and so already failed loudly),
    sync()'s _push_one never verified the derived key against anything - a
    device that mistyped its passphrase would happily re-encrypt its local
    notes under the wrong key and overwrite good remote content, reporting
    full success. Every device with the CORRECT passphrase would then fail
    trying to read that note - the corruption happened silently on one
    device and only surfaced, confusingly, on a different one later.

    Fixed with _verify_passphrase: sync() now decrypts one existing remote
    note before allowing any push, so a typo fails loudly right here."""
    import vault_crypto
    import vault_sync
    url, token = live_sync_server
    right_passphrase = "correct horse battery staple"
    typo_passphrase = "correct horse battery staplle"  # one letter off
    device_a = tmp_path / "device-a"

    _seed_vault(device_a, {"concepts/Important.md": "original content\n"})
    vault_sync.sync(device_a, url, token, right_passphrase, "device-a")

    # Same device, same local edit, but a mistyped passphrase this time.
    (device_a / "concepts/Important.md").write_text("edited content\n", encoding="utf-8")
    with pytest.raises(vault_crypto.WrongPassphrase):
        vault_sync.sync(device_a, url, token, typo_passphrase, "device-a")

    # The remote content must be untouched and still readable with the
    # RIGHT passphrase - not silently overwritten with garbage.
    device_b = tmp_path / "device-b"
    boot = vault_sync.bootstrap(device_b, url, token, right_passphrase)
    assert "concepts/Important.md" in boot["written"]
    assert (device_b / "concepts/Important.md").read_text(encoding="utf-8") == "original content\n"


def test_vault_sync_two_devices_converge(tmp_path, live_sync_server):
    import vault_sync
    url, token = live_sync_server
    passphrase = "correct horse battery staple"
    device_a, device_b = tmp_path / "device-a", tmp_path / "device-b"

    _seed_vault(device_a, {"concepts/Shared idea.md": "content from device A\n"})
    push_result = vault_sync.sync(device_a, url, token, passphrase, "device-a")
    assert "concepts/Shared idea.md" in push_result["pushed"]

    device_b.mkdir()
    boot = vault_sync.bootstrap(device_b, url, token, passphrase)
    assert "concepts/Shared idea.md" in boot["written"]
    assert (device_b / "concepts/Shared idea.md").read_text(encoding="utf-8") == "content from device A\n"

    # Device B edits a different note and syncs; device A should pick it up.
    _seed_vault(device_b, {"concepts/B-only.md": "written on device B\n"})
    vault_sync.sync(device_b, url, token, passphrase, "device-b")
    pull_result = vault_sync.sync(device_a, url, token, passphrase, "device-a")
    assert "concepts/B-only.md" in pull_result["pulled"]
    assert (device_a / "concepts/B-only.md").read_text(encoding="utf-8") == "written on device B\n"

    # Device A deletes the shared note; device B should see it trashed, not vanished.
    (device_a / "concepts/Shared idea.md").unlink()
    del_result = vault_sync.sync(device_a, url, token, passphrase, "device-a")
    assert "concepts/Shared idea.md" in del_result["deleted_remote"]
    trash_result = vault_sync.sync(device_b, url, token, passphrase, "device-b")
    assert "concepts/Shared idea.md" in trash_result["trashed_local"]
    assert not (device_b / "concepts/Shared idea.md").exists()
    assert list((device_b / "_trash").glob("Shared idea*.md"))  # moved, not gone


def test_vault_sync_conflict_never_loses_data(tmp_path, live_sync_server):
    import time as time_mod
    import vault_sync
    url, token = live_sync_server
    passphrase = "correct horse battery staple"
    device_a, device_b = tmp_path / "device-a", tmp_path / "device-b"

    _seed_vault(device_a, {"concepts/Contested.md": "original content\n"})
    vault_sync.sync(device_a, url, token, passphrase, "device-a")
    device_b.mkdir()
    vault_sync.bootstrap(device_b, url, token, passphrase)

    # Both devices independently change the SAME note before either re-syncs.
    (device_a / "concepts/Contested.md").write_text("edited on device A\n", encoding="utf-8")
    time_mod.sleep(0.05)  # ensure a real mtime ordering between the two edits
    (device_b / "concepts/Contested.md").write_text("edited on device B\n", encoding="utf-8")

    vault_sync.sync(device_a, url, token, passphrase, "device-a")
    result_b = vault_sync.sync(device_b, url, token, passphrase, "device-b")

    assert len(result_b["conflicts"]) == 1
    conflict = result_b["conflicts"][0]
    assert conflict["path"] == "concepts/Contested.md"
    assert conflict["conflict_copy"] is not None

    # Device B's edit is newer, so it should be canonical after sync...
    assert (device_b / "concepts/Contested.md").read_text(encoding="utf-8") == "edited on device B\n"
    # ...and device A's edit must still exist somewhere, not be silently dropped.
    conflict_file = device_b / conflict["conflict_copy"]
    assert conflict_file.is_file()
    assert conflict_file.read_text(encoding="utf-8") == "edited on device A\n"

    # A third sync on device A converges it to the same canonical content.
    vault_sync.sync(device_a, url, token, passphrase, "device-a")
    assert (device_a / "concepts/Contested.md").read_text(encoding="utf-8") == "edited on device B\n"


def test_overlapping_syncs_do_not_silently_drop_an_edit(tmp_path, live_sync_server):
    """Regression (found 2026-09-10 via Codex Astra's report, reproduced
    against a real local server before the fix): the three-way diff detects
    a conflict by comparing against a manifest fetched once at the START of
    sync(). Two devices whose syncs genuinely OVERLAP - not just "both edited
    since last sync", but device B's manifest fetch happens BEFORE device A's
    push lands - each see the OTHER's edit as absent, both think theirs is a
    clean "local changed only" push, and the second push silently clobbered
    the first with zero conflict detected anywhere and no conflict-copy file.

    Fixed with server-side optimistic concurrency (expected_revision + a 409
    on mismatch - see sync_server/db.py's upsert_note). This test forces the
    exact overlap by freezing device B's manifest to a snapshot taken before
    device A's push, the same way two real devices racing in the wild would
    each start from what they last saw."""
    import vault_sync
    url, token = live_sync_server
    passphrase = "correct horse battery staple"
    device_a, device_b = tmp_path / "device-a", tmp_path / "device-b"

    _seed_vault(device_a, {"concepts/Shared.md": "original content\n"})
    vault_sync.sync(device_a, url, token, passphrase, "device-a")
    device_b.mkdir()
    vault_sync.bootstrap(device_b, url, token, passphrase)

    # Freeze the manifest device B would see BEFORE device A's next push -
    # the real-world shape of "syncs overlap".
    frozen_manifest = vault_sync._request("GET", f"{url}/manifest?since=0", token)

    (device_a / "concepts/Shared.md").write_text("device A's important edit\n", encoding="utf-8")
    result_a = vault_sync.sync(device_a, url, token, passphrase, "device-a")
    assert "concepts/Shared.md" in result_a["pushed"]

    (device_b / "concepts/Shared.md").write_text("device B's different edit\n", encoding="utf-8")
    orig_request = vault_sync._request

    def frozen_get_manifest(method, u, tok, body=None):
        if method == "GET" and u.startswith(f"{url}/manifest"):
            return frozen_manifest
        return orig_request(method, u, tok, body)

    vault_sync._request = frozen_get_manifest
    try:
        result_b = vault_sync.sync(device_b, url, token, passphrase, "device-b")
    finally:
        vault_sync._request = orig_request

    # The overlap must surface as a detected conflict, not a silent push.
    assert result_b["pushed"] == []
    assert len(result_b["conflicts"]) == 1
    conflict = result_b["conflicts"][0]
    assert conflict["conflict_copy"] is not None

    # Device A's edit must survive SOMEWHERE - either it won (newer mtime) or
    # its content is preserved in a conflict copy. Either way, never gone.
    final_content = (device_b / "concepts/Shared.md").read_text(encoding="utf-8")
    conflict_content = (device_b / conflict["conflict_copy"]).read_text(encoding="utf-8")
    assert "device A's important edit" in (final_content + conflict_content)
    assert "device B's different edit" in (final_content + conflict_content)


def test_sync_reseeds_a_replacement_server_that_lost_everything(tmp_path, tmp_path_factory, monkeypatch):
    """Regression (2026-10-14): the sync server was lost and replaced by an
    empty one. A device with an existing cursor used to fail with HTTP 404
    (it tried to PULL notes the new server never had), and a device with a
    local salt never registered it, so a brand-new device would derive a
    different key. The client must re-push, register its salt, and a fresh
    device must then bootstrap the same content."""
    import vault_sync
    passphrase = "correct horse battery staple"
    device_a, device_b = tmp_path / "device-a", tmp_path / "device-b"
    _seed_vault(device_a, {"concepts/One.md": "first note\n", "projects/Two.md": "second note\n"})

    url1, stop1 = _launch_sync_server(tmp_path_factory, monkeypatch, "token-one", "sync_server_lost")
    try:
        first = vault_sync.sync(device_a, url1, "token-one", passphrase, "device-a")
        assert sorted(first["pushed"]) == ["concepts/One.md", "projects/Two.md"]
    finally:
        stop1()

    url2, stop2 = _launch_sync_server(tmp_path_factory, monkeypatch, "token-two", "sync_server_replacement")
    try:
        again = vault_sync.sync(device_a, url2, "token-two", passphrase, "device-a")
        assert sorted(again["pushed"]) == ["concepts/One.md", "projects/Two.md"]
        assert sorted(again["repushed"]) == ["concepts/One.md", "projects/Two.md"]
        assert again["conflicts"] == [] and again["trashed_local"] == []
        assert (device_a / "concepts/One.md").read_text(encoding="utf-8") == "first note\n"

        # the existing salt was registered, so a fresh device derives the same key
        local_salt = (device_a / ".sync-salt").read_text(encoding="utf-8").strip()
        assert vault_sync._request("GET", f"{url2}/salt", "token-two")["value"] == local_salt
        device_b.mkdir()
        boot = vault_sync.bootstrap(device_b, url2, "token-two", passphrase)
        assert sorted(boot["written"]) == ["concepts/One.md", "projects/Two.md"]
        assert (device_b / "projects/Two.md").read_text(encoding="utf-8") == "second note\n"

        # and a third sync is a clean no-op
        third = vault_sync.sync(device_a, url2, "token-two", passphrase, "device-a")
        assert third["pushed"] == [] and third["repushed"] == [] and third["skipped"] == 2
    finally:
        stop2()


def test_pull_only_never_acts_on_notes_a_lost_server_forgot(tmp_path, tmp_path_factory, monkeypatch):
    """Pull-only mode must not push, trash or crash when the server lost its
    data; it reports what the server is missing and leaves local notes alone."""
    import vault_sync
    passphrase = "correct horse battery staple"
    device_a = tmp_path / "device-a"
    _seed_vault(device_a, {"concepts/Keep me.md": "local only now\n"})
    url1, stop1 = _launch_sync_server(tmp_path_factory, monkeypatch, "token-one", "sync_server_lost2")
    try:
        vault_sync.sync(device_a, url1, "token-one", passphrase, "device-a")
    finally:
        stop1()
    url2, stop2 = _launch_sync_server(tmp_path_factory, monkeypatch, "token-two", "sync_server_replacement2")
    try:
        out = vault_sync.sync(device_a, url2, "token-two", passphrase, "device-a", mode="pull")
        assert out["missing_on_server"] == ["concepts/Keep me.md"]
        assert out["pushed"] == [] and out["trashed_local"] == [] and out["repushed"] == []
        assert (device_a / "concepts/Keep me.md").read_text(encoding="utf-8") == "local only now\n"
    finally:
        stop2()


def test_a_salt_mismatch_fails_with_a_clear_error(tmp_path, tmp_path_factory, monkeypatch):
    """A device whose local salt differs from the server's must stop with an
    explicit explanation rather than a confusing decrypt failure."""
    import vault_sync
    url, stop = _launch_sync_server(tmp_path_factory, monkeypatch, "token-one", "sync_server_salt")
    try:
        other = tmp_path / "other-device"
        _seed_vault(other, {"concepts/X.md": "x\n"})
        vault_sync.sync(other, url, "token-one", "pass phrase here", "other")
        mine = tmp_path / "mine"
        _seed_vault(mine, {"concepts/Y.md": "y\n"})
        (mine / ".sync-salt").write_text("QUJDREVGR0hJSktMTU5PUA==\n", encoding="utf-8")
        with pytest.raises(vault_sync.SaltMismatch):
            vault_sync.sync(mine, url, "token-one", "pass phrase here", "mine")
    finally:
        stop()
