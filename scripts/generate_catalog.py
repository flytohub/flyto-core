#!/usr/bin/env python3
"""
Generate docs/TOOL_CATALOG.md from the module registry.

Usage:
    python scripts/generate_catalog.py
"""

import argparse
import os
import sys
from pathlib import Path

# Setup path
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root / "src"))

os.environ["FLYTO_VALIDATION_MODE"] = "dev"


# Categories whose *registration* is gated on an optional dependency being
# importable, so whether they appear depends on which extras the machine
# running this script happens to have installed.
#
# `core.modules.atomic._OPTIONAL_CATEGORIES` lists categories imported inside a
# try/except, but most of those still register unconditionally because their
# third-party imports are lazy (ssh defers asyncssh into the call). Only these
# gate registration itself — huggingface/__init__.py checks
# `find_spec("transformers")` before importing any module.
#
# They are excluded so the catalog is a property of the source tree rather than
# of the developer's virtualenv. Without this, running the generator on a
# machine with the `vector` extra installed (which pulls transformers in
# transitively) silently rewrites the catalog to advertise 7 modules and a
# category that a default `pip install flyto-core` does not expose — and every
# cross-referencing count in README/STATE/ARCHITECTURE with it.
#
# tests/core/test_catalog_determinism.py enforces that the generated file is
# byte-identical with and without the gating dependency present.
_ENV_GATED_CATEGORIES = {"huggingface"}


def format_params(params_schema: dict) -> str:
    """Format params_schema into a readable string."""
    if not params_schema:
        return "—"

    parts = []
    for name, defn in params_schema.items():
        if not isinstance(defn, dict):
            parts.append(f"`{name}`")
            continue
        ptype = defn.get("type", "any")
        required = defn.get("required", False)
        default = defn.get("default")

        suffix = ""
        if required:
            suffix = " *(required)*"
        elif default is not None:
            default_str = str(default).replace("\n", "\\n").replace("|", "\\|")
            if len(default_str) > 30:
                default_str = default_str[:27] + "..."
            suffix = f" (default: `{default_str}`)"

        parts.append(f"`{name}` {ptype}{suffix}")

    return ", ".join(parts)


def format_output(output_schema: dict) -> str:
    """Format output_schema into a readable string."""
    if not output_schema:
        return "—"

    parts = []
    for name, defn in output_schema.items():
        ptype = defn.get("type", "any") if isinstance(defn, dict) else str(defn)
        parts.append(f"`{name}` ({ptype})")

    return ", ".join(parts)


def escape_md(text: str) -> str:
    """Escape pipe characters for markdown tables."""
    return text.replace("|", "\\|").replace("\n", " ").strip()


def _optional_note() -> str:
    """One stable sentence naming the categories excluded from the counts.

    Written from the constant rather than from the runtime registry, so the
    sentence is identical whether or not the gating dependency is installed.
    """
    ordered = sorted(_ENV_GATED_CATEGORIES)
    names = ", ".join(f"`{c}`" for c in ordered)
    subject, verb = (names, "registers") if len(ordered) == 1 else (names, "register")
    return (
        f"{subject} {verb} only when the matching optional dependency is "
        "installed (see the extras in `pyproject.toml`), and is excluded here "
        "so this file does not vary by developer environment."
        if len(ordered) == 1
        else f"{subject} {verb} only when their matching optional dependencies "
        "are installed (see the extras in `pyproject.toml`), and are excluded "
        "here so this file does not vary by developer environment."
    )


def render_catalog() -> tuple[str, int, int]:
    """Render the runtime-discovered module catalog deterministically."""
    from core.modules.registry import ModuleRegistry

    registry = ModuleRegistry()
    registry.discover_plugins()

    all_metadata = registry.get_all_metadata(
        lang="en", filter_by_stability=False
    )

    # Group by module_id prefix (first segment before the first dot)
    # This ensures file.read, file.copy, file.write all appear under "file"
    categories: dict[str, list] = {}
    for module_id, meta in sorted(all_metadata.items()):
        cat = module_id.split(".")[0]
        # Skip categories whose registration depends on an optional dependency
        # being installed locally — see _ENV_GATED_CATEGORIES.
        if cat in _ENV_GATED_CATEGORIES:
            continue
        if cat not in categories:
            categories[cat] = []
        categories[cat].append((module_id, meta))

    # Count what is actually rendered, not what the registry happened to hold:
    # all_metadata still contains the env-gated categories filtered out above.
    total = sum(len(modules) for modules in categories.values())
    cat_count = len(categories)
    lines = [
        "# Tool Catalog",
        "",
        f"> Auto-generated from flyto-core module registry. **{total} modules** across **{cat_count} categories**.",
        ">",
        "> Generated from the active `ModuleRegistry`; do not edit manually.",
        ">",
        "> Counts cover what a default `pip install flyto-core` exposes. "
        + _optional_note(),
        "",
        "## Categories",
        "",
    ]

    # TOC
    for cat in sorted(categories.keys()):
        count = len(categories[cat])
        anchor = cat.replace(".", "").replace(" ", "-").lower()
        lines.append(f"- [{cat}](#{anchor}) ({count})")

    lines.append("")
    lines.append("---")
    lines.append("")

    # Details per category
    for cat in sorted(categories.keys()):
        modules = categories[cat]
        lines.append(f"## {cat}")
        lines.append("")
        lines.append("| Module | Description | Parameters | Output |")
        lines.append("|--------|-------------|------------|--------|")

        for module_id, meta in modules:
            desc = meta.get("ui_description") or meta.get("description", "")
            desc = escape_md(desc)
            params = format_params(meta.get("params_schema", {}))
            output = format_output(meta.get("output_schema", {}))
            lines.append(f"| `{module_id}` | {desc} | {params} | {output} |")

        lines.append("")

    return "\n".join(lines).rstrip() + "\n", total, cat_count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail when the catalog is stale")
    args = parser.parse_args()
    output_path = project_root / "docs" / "TOOL_CATALOG.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    content, total, cat_count = render_catalog()
    if args.check:
        if not output_path.exists() or output_path.read_text(encoding="utf-8") != content:
            print(f"Stale catalog: {output_path}", file=sys.stderr)
            return 1
        print(f"Catalog check passed: {output_path}")
    else:
        output_path.write_text(content, encoding="utf-8")
        print(f"Generated {output_path}")
    print(f"  {total} modules across {cat_count} categories")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
