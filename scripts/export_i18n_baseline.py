#!/usr/bin/env python3
"""
export_i18n_baseline.py - Export module metadata to i18n baseline format

Generates English locale files from the module registry for translation.
Output format is compatible with flyto-i18n locales structure.

Usage:
    python scripts/export_i18n_baseline.py [--output-dir OUTPUT_DIR]

Output:
    locales/en/modules.{category}.json for each category
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))


def load_all_modules() -> Dict[str, Dict[str, Any]]:
    """Load all modules by importing the module packages."""
    try:
        from src.core.modules import atomic
    except ImportError:
        from core.modules import atomic

    try:
        from src.core.modules import composite
    except ImportError:
        try:
            from core.modules import composite
        except ImportError:
            pass

    try:
        from src.core.modules import third_party
    except ImportError:
        try:
            from core.modules import third_party
        except ImportError:
            pass

    try:
        from src.core.modules.registry import ModuleRegistry
    except ImportError:
        from core.modules.registry import ModuleRegistry

    return ModuleRegistry.get_all_metadata()


def export_en_baseline(metadata: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Export module metadata to i18n baseline format.

    Args:
        metadata: Dict of module_id -> module metadata

    Returns:
        Dict of category -> {module_id -> i18n data}
    """
    by_category: Dict[str, Dict[str, Any]] = {}

    for module_id, meta in metadata.items():
        # Extract category from module_id (e.g., "browser" from "browser.click")
        parts = module_id.split(".")
        if len(parts) >= 2:
            category = parts[0]
        else:
            category = "misc"

        if category not in by_category:
            by_category[category] = {}

        # Build i18n structure for this module
        module_i18n = {
            "label": meta.get("module_name", module_id),
            "description": meta.get("module_description", ""),
        }

        # Add params if available
        params_schema = meta.get("params_schema", {})
        if params_schema and "properties" in params_schema:
            module_i18n["params"] = {}
            for param, spec in params_schema["properties"].items():
                if isinstance(spec, dict):
                    module_i18n["params"][param] = {
                        "label": param.replace("_", " ").title(),
                        "description": spec.get("description", ""),
                    }

        # Add outputs if available
        output_schema = meta.get("output_schema", {})
        if output_schema and "properties" in output_schema:
            module_i18n["outputs"] = {}
            for output, spec in output_schema["properties"].items():
                if isinstance(spec, dict):
                    module_i18n["outputs"][output] = {
                        "label": output.replace("_", " ").title(),
                        "description": spec.get("description", ""),
                    }

        by_category[category][module_id] = module_i18n

    return by_category


def main():
    parser = argparse.ArgumentParser(
        description="Export module metadata to i18n baseline format"
    )
    parser.add_argument(
        "--output-dir",
        default="../flyto-i18n/locales/en",
        help="Output directory for locale files (default: ../flyto-i18n/locales/en)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be written without writing files",
    )
    args = parser.parse_args()

    # Load modules
    print("Loading modules from registry...")
    try:
        metadata = load_all_modules()
    except Exception as e:
        print(f"Error loading modules: {e}", file=sys.stderr)
        sys.exit(1)

    if not metadata:
        print("No modules found.", file=sys.stderr)
        sys.exit(0)

    print(f"Found {len(metadata)} modules")

    # Export to i18n format
    baseline = export_en_baseline(metadata)

    # Write output files
    output_dir = Path(args.output_dir)

    if not args.dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)

    total_modules = 0
    for category, modules in sorted(baseline.items()):
        output_file = output_dir / f"modules.{category}.json"
        total_modules += len(modules)

        if args.dry_run:
            print(f"Would write {len(modules)} modules to {output_file}")
        else:
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(modules, f, indent=2, ensure_ascii=False)
            print(f"Wrote {len(modules)} modules to {output_file}")

    print(f"\nTotal: {total_modules} modules in {len(baseline)} categories")

    if args.dry_run:
        print("\n(Dry run - no files written)")


if __name__ == "__main__":
    main()
