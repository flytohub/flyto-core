#!/usr/bin/env python3
"""Validate Flyto2 Core generated docs, ownership, and local links."""

from __future__ import annotations

import fnmatch
import json
import re
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
    paths = list(manifest["documentation"].values())
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


def main() -> int:
    command(sys.executable, "scripts/generate_reference.py", "--check")
    command(sys.executable, "scripts/generate_catalog.py", "--check")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    files = repository_files()
    missing = []
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
