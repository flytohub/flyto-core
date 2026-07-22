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
        if cat not in categories:
            categories[cat] = []
        categories[cat].append((module_id, meta))

    total = len(all_metadata)
    cat_count = len(categories)
    lines = [
        "# Tool Catalog",
        "",
        f"> Auto-generated from flyto-core module registry. **{total} modules** across **{cat_count} categories**.",
        ">",
        "> Generated from the active `ModuleRegistry`; do not edit manually.",
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
