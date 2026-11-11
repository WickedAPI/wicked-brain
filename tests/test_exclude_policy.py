"""One exclude policy, pinned across every tool that walks the vault.

Ported from obsidian-second-brain-src/tests/ (Phase 1 dropped it by accident -
the code comments in vault_ops.py and semantic_search.py already referenced
this file by name as the thing pinning them together, but it never actually
made the trim). Six tools each carried a hardcoded set upstream. Only five
entries were common to all six, and the gaps caused real bugs: heal_links
rewrote notes inside folders the health check had excluded, and `Templates`
versus `templates` meant the same folder was skipped or scanned depending on
which tool ran.

scripts/vault_scan.py is the base. Two tools add to it deliberately, and those
additions are asserted here so a future merge cannot quietly erase the intent
behind them.

vault_ops.py keeps its own literal, because the MCP server ships standalone and
must not import from scripts/. That literal is pinned to the base below, which
is the only thing stopping the original drift from happening again.

semantic_search.py used to import _SKIP_DIRS from vault_ops.py instead of from
vault_scan.py like every other scripts/ tool - integrations/mcp-server/ is
never copied into dist/claude-code or dist/codex-cli, so every shipped build's
/brain-reindex crashed with ModuleNotFoundError (found 2026-09-10, fixed by
importing BASE_EXCLUDE_DIRS from vault_scan.py instead). Pinned here too so
scripts/ cannot grow a new cross-package dependency the same way again.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "integrations" / "mcp-server"))


def _lower(s) -> set[str]:
    return {str(x).lower() for x in s}


def test_the_base_covers_every_machine_owned_directory():
    from vault_scan import BASE_EXCLUDE_DIRS

    for d in (".git", ".obsidian", ".trash", "_trash", "_export", "__pycache__",
              "node_modules", ".claude", ".agents", ".codex", ".gemini",
              ".opencode", "templates"):
        assert d in _lower(BASE_EXCLUDE_DIRS), f"{d} dropped out of the base policy"


def test_every_scanning_tool_uses_the_base():
    """The regression this file exists for.

    Upstream's vault_stats.py did not make the Phase 1 trim (this fork folds
    note-count stats into dashboard/server.py's /api/stats instead), so it is
    not part of this coverage list - there is nothing here to pin it to.
    """
    import export_okf
    import freshness_lint
    import link_graph
    import semantic_search
    import vault_health
    from vault_scan import BASE_EXCLUDE_DIRS

    base = _lower(BASE_EXCLUDE_DIRS)
    for name, actual in (
        ("vault_health", vault_health.EXCLUDE_DIRS),
        ("link_graph", link_graph.SKIP_DIRS),
        ("export_okf", export_okf.SKIP_DIRS),
        ("freshness_lint", freshness_lint.SKIP_DIRS),
        ("semantic_search", semantic_search.SKIP_DIRS),
    ):
        missing = base - _lower(actual)
        assert not missing, f"{name} no longer skips {sorted(missing)}"


def test_the_mcp_server_literal_matches_the_base():
    """vault_ops cannot import from scripts/, so it is pinned instead."""
    import vault_ops
    from vault_scan import BASE_EXCLUDE_DIRS

    missing = _lower(BASE_EXCLUDE_DIRS) - _lower(vault_ops._SKIP_DIRS)
    assert not missing, (
        f"vault_ops._SKIP_DIRS has drifted from scripts/vault_scan.py: missing "
        f"{sorted(missing)}. Update the literal, it ships standalone in the MCP server."
    )


def test_deliberate_per_tool_additions_survive():
    """These encode intent, not oversight, and must not be merged away."""
    import export_okf

    assert "excalidraw" in _lower(export_okf.SKIP_DIRS), (
        "export_okf stopped skipping excalidraw; drawings are not exportable prose"
    )


def test_other_tools_do_not_inherit_those_additions():
    """The flip side: a per-tool skip must stay per-tool."""
    import link_graph
    import vault_health

    for name, actual in (("vault_health", vault_health.EXCLUDE_DIRS),
                         ("link_graph", link_graph.SKIP_DIRS)):
        assert "excalidraw" not in _lower(actual), (
            f"{name} picked up 'excalidraw', which belongs to export_okf only"
        )


def test_matching_is_case_insensitive():
    """`Templates` and `templates` must resolve identically.

    The bootstrapper writes capital-T; three tools spelled it lowercase, so the
    same folder was skipped or scanned depending on which tool ran.
    """
    from vault_scan import excluded_dirs, is_excluded

    ex = excluded_dirs()
    assert is_excluded(["Templates", "Daily.md"], ex)
    assert is_excluded(["templates", "Daily.md"], ex)
    assert is_excluded(["TEMPLATES", "Daily.md"], ex)
    assert not is_excluded(["Projects", "Real Note.md"], ex)


def test_is_excluded_expects_relative_parts():
    """Absolute parts let an ancestor outside the vault disable the scan.

    That is B29: vault_health's empty-folder check passed absolute parts, so a
    vault living under any directory named Templates reported zero findings.
    """
    from vault_scan import excluded_dirs, is_excluded

    ex = excluded_dirs()
    assert is_excluded(("Users", "someone", "Templates", "myvault"), ex), (
        "sanity: absolute parts DO match, which is exactly why callers must "
        "pass vault-relative parts"
    )
    assert not is_excluded(("Projects", "note.md"), ex)
