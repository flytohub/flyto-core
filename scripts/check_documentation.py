#!/usr/bin/env python3
"""Validate Flyto2 Core generated docs, ownership, and local links."""

from __future__ import annotations

import fnmatch
import json
import re
import runpy
import subprocess
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs" / "documentation-manifest.json"
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\]]+\]\((?:<([^>]+)>|([^)]+))\)")
RECIPE_COMMAND = re.compile(r"\bflyto recipe ([a-z0-9][a-z0-9_-]*)\b")
INVALID_CLI = re.compile(r"\bflyto-core (?:lint|create-module)\b")
PYTHON_SCRIPT = re.compile(
    r"\b(?:\.venv/bin/)?python(?:3(?:\.\d+)?)?\s+(scripts/[A-Za-z0-9_./-]+\.py)\b"
)
BASH_SCRIPT = re.compile(r"\bbash\s+(scripts/[A-Za-z0-9_./-]+\.sh)\b")
PACKAGE_EXTRA = re.compile(r"flyto-core\[([^\]]+)\]")
SOURCE_EXTENSIONS = {
    ".css",
    ".html",
    ".js",
    ".json",
    ".lock",
    ".py",
    ".sh",
    ".tape",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
ROOT_SOURCE = {
    ".flyto-rules.yaml",
    "Dockerfile",
    "Dockerfile.verification",
    "MANIFEST.in",
    "demo.py",
    "demo.tape",
    "package-lock.json",
    "package.json",
    "pyproject.toml",
    "registry.json",
    "requirements-integrations.txt",
    "requirements.lock",
    "requirements.txt",
    "run.py",
    "run_demo.sh",
    "server.json",
    "setup.py",
}


def command(*args: str) -> None:
    subprocess.run(args, cwd=ROOT, check=True)


def repository_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return sorted(item for item in result.stdout.splitlines() if (ROOT / item).is_file())


def documentation_paths(manifest: dict) -> list[str]:
    paths = []
    scope_keys = {"source_reference_exclude", "module_roots", "configuration_not_applicable"}
    for key, value in manifest["documentation"].items():
        if key in scope_keys:
            continue
        if isinstance(value, str):
            paths.append(value)
        elif isinstance(value, list):
            paths.extend(item for item in value if isinstance(item, str))
    for area in manifest["source_areas"]:
        paths.extend(area["documentation"])
    return paths


def owned_source_files(files: list[str]) -> list[str]:
    roots = (
        ".github/",
        "audit_report/",
        "demo/",
        "examples/",
        "plugin-template/",
        "scripts/",
        "src/",
        "tests/",
        "workflows/",
    )
    return [
        relative
        for relative in files
        if relative in ROOT_SOURCE
        or (
            relative.startswith(roots)
            and Path(relative).suffix.lower() in SOURCE_EXTENSIONS
        )
    ]


def local_target(source: Path, raw_target: str) -> Optional[Path]:
    target = raw_target.strip().split(maxsplit=1)[0].strip("<>")
    if target.startswith(("#", "http://", "https://", "mailto:")):
        return None
    path = target.split("#", 1)[0]
    return (source.parent / path).resolve() if path else None


def check_current_inventory() -> list[str]:
    """Require active public inventory copy to match authoritative sources exactly."""
    facts = runpy.run_path(str(ROOT / "src" / "core" / "catalog_facts.py"))
    modules = facts["CORE_MODULE_COUNT"]
    categories = facts["CORE_CATALOG_CATEGORY_COUNT"]
    recipes = facts["BUILT_IN_RECIPE_COUNT"]

    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    version_match = re.search(r'^version = "([^"]+)"$', pyproject, re.MULTILINE)

    registered = (ROOT / "docs" / "reference" / "registered-modules.md").read_text(
        encoding="utf-8"
    )
    registered_match = re.search(r"\*\*(\d+) explicit, literal", registered)
    python_reference = (ROOT / "docs" / "reference" / "python-api.md").read_text(
        encoding="utf-8"
    )
    python_match = re.search(
        r"\*\*(\d[\d,]*) declarations across (\d[\d,]*) files\*\*",
        python_reference,
    )
    source_reference = (ROOT / "docs" / "reference" / "source-modules.md").read_text(
        encoding="utf-8"
    )
    source_match = re.search(
        r"Inventory: \*\*(\d[\d,]*) Python files\*\*, \*\*(\d[\d,]*) lines\*\*, "
        r"and \*\*(\d[\d,]*) class/function/method declarations\*\*",
        source_reference,
    )
    configuration = (ROOT / "docs" / "reference" / "configuration.md").read_text(
        encoding="utf-8"
    )
    environment_match = re.search(
        r"Implementation sources read \*\*(\d+) environment-variable names\*\*",
        configuration,
    )
    if not all(
        (version_match, registered_match, python_match, source_match, environment_match)
    ):
        return ["generated source references do not expose inventory facts"]
    version = version_match.group(1)
    registrations = int(registered_match.group(1))
    declarations = int(python_match.group(1).replace(",", ""))
    declaration_files = int(python_match.group(2).replace(",", ""))
    source_files = int(source_match.group(1).replace(",", ""))
    source_lines = int(source_match.group(2).replace(",", ""))
    source_declarations = int(source_match.group(3).replace(",", ""))
    environments = int(environment_match.group(1))
    if source_declarations != declarations:
        return ["generated source references disagree on declaration count"]

    expected = {
        "README.md": [
            f"## {modules} Modules, {categories} Catalog Categories",
            f"The current public inventory is **{modules} registry-backed modules** across **{categories}\ncatalog categories**",
        ],
        "SECURITY.md": [f"The current release is **{version}**."],
        "PROJECT.md": [
            f"The current registry inventory is {modules} modules across {categories} generated catalog\ncategories, with {recipes} maintained built-in recipes exposed through the CLI."
        ],
        "ARCHITECTURE.md": [
            f"source of truth for the current {modules}-module, {categories}-category public inventory.",
            f"{source_files} maintained Python files, {declarations:,} declarations, {registrations} literal module\n  registrations, 28 HTTP operations, {environments} environment names",
        ],
        "STATE.md": [
            f"Source-backed documentation now covers {source_files} maintained Python files, {declarations:,}\n  declarations, {registrations} literal module registrations",
            f"surfaces (28 static HTTP operations, {environments} environment names)",
        ],
        "docs/README.md": [
            f"[Tool Catalog](TOOL_CATALOG.md): all {modules} active runtime modules",
            f"- {modules} active runtime modules across {categories} catalog categories.",
            f"- {source_files} maintained Python files and {declarations:,} declarations.",
            f"- {registrations} literal module registrations linked to source.",
            f"- {environments} environment-variable readers.",
        ],
        "docs/MIGRATION_STATUS.md": [
            f"{modules} modules, {categories} categories",
            f"| Literal module registrations | {registrations} |",
            f"| Packaged recipes | {recipes} |",
            f"| Maintained Python source | {source_files} files, {source_lines:,} lines |",
            f"{declarations:,} across {declaration_files} files",
            f"| Environment-variable names | {environments} |",
        ],
        "docs/WHITEPAPER.md": [
            f"{modules} modules across {categories} categories",
            f"{recipes} packaged recipes",
            f"Source traceability covers {source_files} maintained Python files,\n{source_lines:,} lines",
            f"{declarations:,} class/function/method declarations",
            f"{registrations} literal registrations",
        ],
        "docs/FEATURES.md": [
            f"{modules} modules are active",
            f"{categories} categories",
            f"{registrations} literal decorator registrations",
            f"[All {modules} active module schemas](TOOL_CATALOG.md)",
            f"[All {registrations} literal module implementations](reference/registered-modules.md)",
            f"[All {declarations:,} maintained Python declarations](reference/python-api.md)",
        ],
        "docs/OPERATIONS.md": [
            f"generated {modules}-module/{categories}-category\nsnapshot"
        ],
        "docs/RECIPES.md": [
            f"[{modules} registry-backed modules](TOOL_CATALOG.md)"
        ],
        "demo.py": [
            f'"""30-second demo: Give your AI {modules} tools with one command."""',
            f"flyto-core demo — {modules} tools for AI agents",
            f"flyto-core: {modules} tools, zero config",
        ],
    }
    errors: list[str] = []
    for relative, tokens in expected.items():
        content = (ROOT / relative).read_text(encoding="utf-8")
        for token in tokens:
            if token not in content:
                errors.append(f"{relative}: missing current inventory token {token!r}")

    stale_patterns = (
        r"\b(?:468|476)\s+(?:registry-backed\s+)?modules\b",
        r"\b(?:85|86)\s+(?:generated\s+)?catalog categories\b",
        r"\b(?:468|476)[- ]module/(?:85|86)[- ]category\b",
        r"\b107 environment(?:-variable)? names\b",
        r"\b2\.30\.0\b",
    )
    for relative in expected:
        content = (ROOT / relative).read_text(encoding="utf-8")
        if relative == "STATE.md":
            content = content.split("## Last Verification", 1)[0]
        for pattern in stale_patterns:
            match = re.search(pattern, content)
            if match:
                errors.append(
                    f"{relative}: stale active inventory text {match.group(0)!r}"
                )
    return errors


def main() -> int:
    command(sys.executable, "scripts/generate_reference.py", "--check")
    command(sys.executable, "scripts/generate_catalog.py", "--check")
    command(sys.executable, "scripts/generate_security_status.py", "--check")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    files = repository_files()
    missing = check_current_inventory()
    for raw_path in documentation_paths(manifest):
        path = raw_path.split("#", 1)[0]
        if path and not (ROOT / path).exists():
            missing.append(f"manifest: {raw_path}")

    patterns = [
        pattern
        for area in manifest["source_areas"]
        for pattern in area["paths"]
    ]
    owned = owned_source_files(files)
    unowned = [
        relative
        for relative in owned
        if not any(fnmatch.fnmatch(relative, pattern) for pattern in patterns)
    ]

    markdown_files = [ROOT / relative for relative in files if relative.endswith(".md")]
    recipe_names = {path.stem for path in (ROOT / "src" / "recipes").glob("*.yaml")}
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    extras_section = pyproject.split("[project.optional-dependencies]", 1)[1].split(
        "[project.urls]", 1
    )[0]
    package_extras = set(re.findall(r"^([a-z][a-z0-9_-]*)\s*=", extras_section, re.MULTILINE))
    checked_links = 0
    for source in markdown_files:
        content = source.read_text(encoding="utf-8")
        for recipe_name in RECIPE_COMMAND.findall(content):
            if recipe_name not in recipe_names:
                missing.append(
                    f"{source.relative_to(ROOT)}: unknown packaged recipe {recipe_name}"
                )
        if INVALID_CLI.search(content):
            missing.append(
                f"{source.relative_to(ROOT)}: unsupported flyto-core CLI command"
            )
        for script in PYTHON_SCRIPT.findall(content) + BASH_SCRIPT.findall(content):
            if not (ROOT / script).is_file():
                missing.append(
                    f"{source.relative_to(ROOT)}: missing documented script {script}"
                )
        for extra_list in PACKAGE_EXTRA.findall(content):
            for extra in (item.strip() for item in extra_list.split(",")):
                if extra and extra not in package_extras:
                    missing.append(
                        f"{source.relative_to(ROOT)}: unknown package extra {extra}"
                    )
        for match in MARKDOWN_LINK.finditer(content):
            raw_target = match.group(1) or match.group(2) or ""
            target = local_target(source, raw_target)
            if target is None:
                continue
            checked_links += 1
            if not target.exists():
                missing.append(f"{source.relative_to(ROOT)}: {raw_target}")

    if missing or unowned:
        errors = []
        if missing:
            errors.append("missing documentation targets:\n" + "\n".join(missing))
        if unowned:
            errors.append("unowned source/configuration:\n" + "\n".join(unowned))
        raise RuntimeError("\n\n".join(errors))

    print(
        "documentation contract passed: "
        f"{len(markdown_files)} Markdown files, "
        f"{len(owned)} owned source/config files, "
        f"{checked_links} local links"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
