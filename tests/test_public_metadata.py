"""Regression tests for public package and MCP registry metadata."""

from __future__ import annotations

import json
import re
import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DESCRIPTION = (
    "The open-source execution engine for AI agents. 480 modules, MCP-native, "
    "triggers, queue, versioning, metering."
)


def _project_value(name: str) -> str:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    project_section = pyproject.split("[project]", 1)[1].split("\n[", 1)[0]
    match = re.search(rf'^{re.escape(name)}\s*=\s*"([^"]+)"$', project_section, re.MULTILINE)
    assert match is not None, f"Missing [project].{name}"
    return match.group(1)


def test_mcp_registry_metadata_matches_package_metadata() -> None:
    server = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    package_version = _project_value("version")

    assert server["name"] == "io.github.flytohub/flyto-core"
    assert server["title"] == "Flyto2 Core"
    assert server["description"] == PUBLIC_DESCRIPTION
    assert _project_value("description") == PUBLIC_DESCRIPTION
    assert server["version"] == package_version
    assert server["packages"][0]["version"] == package_version


def test_readme_citation_contract_uses_current_public_positioning() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert PUBLIC_DESCRIPTION in readme
    assert "480 registry-backed modules" in readme

    for stale_copy in (
        "300+ atomic modules",
        "The open-source execution engine for AI agents. 300",
        "Flyto Core - MCP Server",
    ):
        assert stale_copy not in readme


@pytest.mark.parametrize(
    ("relative", "current", "stale"),
    [
        ("README.md", "## 480 Modules, 88 Catalog Categories", "## 476 Modules, 86 Catalog Categories"),
        ("docs/FEATURES.md", "[All 480 active module schemas]", "[All 476 active module schemas]"),
        ("SECURITY.md", "The current release is **2.31.0**.", "The current release is **2.30.0**."),
        ("demo.py", "flyto-core demo — 480 tools for AI agents", "flyto-core demo — 468 tools for AI agents"),
    ],
)
def test_current_inventory_rejects_stale_active_copy(
    monkeypatch: pytest.MonkeyPatch, relative: str, current: str, stale: str
) -> None:
    checker = runpy.run_path(str(ROOT / "scripts" / "check_documentation.py"))
    original_read_text = Path.read_text

    def substituted_read_text(path: Path, *args: object, **kwargs: object) -> str:
        content = original_read_text(path, *args, **kwargs)
        if path.resolve() == (ROOT / relative).resolve():
            assert current in content
            return content.replace(current, stale, 1)
        return content

    monkeypatch.setattr(Path, "read_text", substituted_read_text)
    errors = checker["check_current_inventory"]()

    assert any(relative in error for error in errors)


def test_current_inventory_permits_historical_state_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checker = runpy.run_path(str(ROOT / "scripts" / "check_documentation.py"))
    original_read_text = Path.read_text

    def historical_read_text(path: Path, *args: object, **kwargs: object) -> str:
        content = original_read_text(path, *args, **kwargs)
        if path.resolve() == (ROOT / "STATE.md").resolve():
            return content + "\nHistorical evidence: 468 modules across 85 categories.\n"
        return content

    monkeypatch.setattr(Path, "read_text", historical_read_text)

    assert checker["check_current_inventory"]() == []
