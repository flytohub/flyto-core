"""Regression tests for public package and MCP registry metadata."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DESCRIPTION = (
    "The open-source execution engine for AI agents. 452 modules, MCP-native, "
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
    assert "452 registry-backed modules" in readme
    assert "MCP registry pages" in readme

    for stale_copy in (
        "300+ atomic modules",
        "The open-source execution engine for AI agents. 300",
        "Flyto Core - MCP Server",
    ):
        assert stale_copy not in readme
