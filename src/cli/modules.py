"""
CLI Module Listing Command

Provides `flyto modules` command to list registered modules
with environment-aware filtering.
"""
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .config import Colors


def get_modules_list(env: str = "production") -> Dict[str, Any]:
    """
    Get list of modules for specified environment.

    Args:
        env: Environment name (production, development, staging, local)

    Returns:
        Dict with modules list and metadata
    """
    # Set environment before importing registry
    os.environ["FLYTO_ENV"] = env

    # Import after setting env
    from core.modules.registry import ModuleRegistry
    from core.modules import atomic  # Trigger registration

    # Get package version
    try:
        from importlib.metadata import version
        pkg_version = version("flyto-core")
    except Exception:
        pkg_version = "unknown"

    # Get all metadata with stability filtering
    all_metadata = ModuleRegistry.get_all_metadata(
        filter_by_stability=True,
        env=env
    )

    # Build modules list
    modules = []
    categories: Dict[str, int] = {}

    for module_id, metadata in sorted(all_metadata.items()):
        module_info = {
            "id": module_id,
            "version": metadata.get("version", "1.0.0"),
            "category": metadata.get("category", "unknown"),
            "stability": metadata.get("stability", "stable"),
            "label": metadata.get("label", module_id),
        }
        modules.append(module_info)

        # Count by category
        cat = module_info["category"]
        categories[cat] = categories.get(cat, 0) + 1

    return {
        "version": pkg_version,
        "environment": env,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total": len(modules),
        "modules": modules,
        "categories": dict(sorted(categories.items())),
    }


def format_table(data: Dict[str, Any]) -> str:
    """Format modules as a table for terminal display."""
    lines = []

    # Header
    lines.append(f"{Colors.HEADER}Flyto Modules - {data['environment'].upper()}{Colors.ENDC}")
    lines.append(f"Version: {data['version']} | Total: {data['total']} modules")
    lines.append("")

    # Category summary
    lines.append(f"{Colors.OKBLUE}Categories:{Colors.ENDC}")
    for cat, count in data["categories"].items():
        lines.append(f"  {cat}: {count}")
    lines.append("")

    # Modules table
    lines.append(f"{Colors.OKGREEN}{'ID':<40} {'Category':<15} {'Stability':<10}{Colors.ENDC}")
    lines.append("-" * 70)

    for module in data["modules"]:
        stability_color = Colors.OKGREEN if module["stability"] == "stable" else Colors.WARNING
        lines.append(
            f"{module['id']:<40} {module['category']:<15} "
            f"{stability_color}{module['stability']:<10}{Colors.ENDC}"
        )

    return "\n".join(lines)


def run_modules_command(
    env: str = "production",
    format: str = "table",
    output_file: Optional[str] = None
) -> int:
    """
    Execute the modules command.

    Args:
        env: Environment (production, development, staging, local)
        format: Output format (table, json)
        output_file: Optional file path to write output

    Returns:
        Exit code (0 for success)
    """
    try:
        data = get_modules_list(env)

        if format == "json":
            output = json.dumps(data, indent=2, ensure_ascii=False)
        else:
            output = format_table(data)

        if output_file:
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(output)
            print(f"{Colors.OKGREEN}Written to {output_file}{Colors.ENDC}")
        else:
            print(output)

        return 0

    except Exception as e:
        print(f"{Colors.FAIL}Error: {e}{Colors.ENDC}", file=sys.stderr)
        return 1


def add_modules_parser(subparsers) -> None:
    """Add modules subcommand to argument parser."""
    modules_parser = subparsers.add_parser(
        "modules",
        help="List registered modules",
        description="List all registered modules with environment-aware filtering."
    )
    modules_parser.add_argument(
        "--env", "-e",
        default="production",
        choices=["production", "staging", "development", "local"],
        help="Environment for stability filtering (default: production)"
    )
    modules_parser.add_argument(
        "--format", "-f",
        default="table",
        choices=["table", "json"],
        help="Output format (default: table)"
    )
    modules_parser.add_argument(
        "--output", "-o",
        help="Output file path (default: stdout)"
    )
