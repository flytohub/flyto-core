#!/usr/bin/env python3
"""
validate_schemas.py - Module Schema Completeness Validator

Validates that all registered modules have complete params_schema and output_schema.
This is critical for VarCatalog to properly introspect module interfaces for UI.

Usage:
    python scripts/validate_schemas.py [--strict] [--json] [--category CATEGORY] [--fix-report]

Options:
    --strict        Exit with code 1 if any module has ERROR-level issues
    --json          Output results as JSON
    --category      Filter by category (e.g., browser, data, flow)
    --fix-report    Generate a report file with modules that need fixing
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from collections import defaultdict

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def load_all_modules() -> Dict[str, Dict[str, Any]]:
    """
    Load all modules by importing the module packages.
    Returns metadata dict from ModuleRegistry.
    """
    # Import module packages to trigger registration
    from src.core.modules import atomic
    from src.core.modules import composite

    # Import third-party modules
    try:
        from src.core.modules import third_party
    except ImportError:
        pass

    # Get registry
    from src.core.modules.registry import ModuleRegistry

    return ModuleRegistry.get_all_metadata(filter_by_stability=False)


def validate_schemas(
    metadata: Dict[str, Dict[str, Any]],
    category_filter: Optional[str] = None
) -> Dict[str, Any]:
    """
    Validate all module schemas.

    Returns:
        {
            'summary': {...},
            'by_category': {...},
            'issues': [...],
            'modules_needing_fix': [...]
        }
    """
    from src.core.modules.schema_validator import SchemaValidator, ValidationSeverity

    validator = SchemaValidator(
        require_params_schema=True,
        require_output_schema=True,
        require_output_type=True,
        require_output_description=True,
    )

    # Filter by category if specified
    if category_filter:
        metadata = {
            k: v for k, v in metadata.items()
            if v.get('category') == category_filter or k.startswith(f"{category_filter}.")
        }

    result = validator.validate_all(metadata)

    # Group issues by module
    issues_by_module: Dict[str, List] = defaultdict(list)
    for issue in result.issues:
        issues_by_module[issue.module_id].append(issue.to_dict())

    # Group by category
    by_category: Dict[str, Dict] = defaultdict(lambda: {
        'total': 0,
        'valid': 0,
        'with_output_schema': 0,
        'with_params_schema': 0,
    })

    modules_needing_fix: List[Dict] = []

    for module_id, meta in metadata.items():
        category = meta.get('category', module_id.split('.')[0])
        by_category[category]['total'] += 1

        has_output = meta.get('output_schema') is not None
        has_params = meta.get('params_schema') is not None

        if has_output:
            by_category[category]['with_output_schema'] += 1
        if has_params:
            by_category[category]['with_params_schema'] += 1

        module_issues = issues_by_module.get(module_id, [])
        has_errors = any(i['severity'] == 'error' for i in module_issues)

        if not has_errors:
            by_category[category]['valid'] += 1
        else:
            modules_needing_fix.append({
                'module_id': module_id,
                'category': category,
                'has_output_schema': has_output,
                'has_params_schema': has_params,
                'issues': [i for i in module_issues if i['severity'] == 'error'],
            })

    return {
        'summary': {
            'total_modules': result.total_modules,
            'valid_modules': result.valid_modules,
            'error_count': result.error_count,
            'warning_count': result.warning_count,
            'is_valid': result.is_valid,
        },
        'by_category': dict(by_category),
        'issues': [i.to_dict() for i in result.issues],
        'modules_needing_fix': sorted(modules_needing_fix, key=lambda x: x['module_id']),
    }


def generate_text_report(data: Dict[str, Any]) -> str:
    """Generate human-readable text report."""
    summary = data['summary']
    by_category = data['by_category']
    modules_needing_fix = data['modules_needing_fix']

    lines = [
        "=" * 70,
        "Flyto-Core Module Schema Validation Report",
        "=" * 70,
        "",
        f"Total Modules:    {summary['total_modules']}",
        f"Valid Modules:    {summary['valid_modules']} ({summary['valid_modules']*100//summary['total_modules'] if summary['total_modules'] > 0 else 0}%)",
        f"Errors:           {summary['error_count']}",
        f"Warnings:         {summary['warning_count']}",
        f"Status:           {'PASS' if summary['is_valid'] else 'FAIL'}",
        "",
        "-" * 70,
        "Coverage by Category:",
        "-" * 70,
        f"{'Category':<20} {'Total':>8} {'Valid':>8} {'output_schema':>15} {'params_schema':>15}",
        "-" * 70,
    ]

    for cat in sorted(by_category.keys()):
        stats = by_category[cat]
        lines.append(
            f"{cat:<20} {stats['total']:>8} {stats['valid']:>8} "
            f"{stats['with_output_schema']:>15} {stats['with_params_schema']:>15}"
        )

    if modules_needing_fix:
        lines.extend([
            "",
            "-" * 70,
            f"Modules Needing Fix ({len(modules_needing_fix)}):",
            "-" * 70,
        ])

        # Group by missing type
        missing_output = [m for m in modules_needing_fix if not m['has_output_schema']]
        missing_params = [m for m in modules_needing_fix if not m['has_params_schema']]

        if missing_output:
            lines.append(f"\nMissing output_schema ({len(missing_output)}):")
            for m in missing_output[:20]:  # Show first 20
                lines.append(f"  - {m['module_id']}")
            if len(missing_output) > 20:
                lines.append(f"  ... and {len(missing_output) - 20} more")

        if missing_params:
            lines.append(f"\nMissing params_schema ({len(missing_params)}):")
            for m in missing_params[:20]:
                lines.append(f"  - {m['module_id']}")
            if len(missing_params) > 20:
                lines.append(f"  ... and {len(missing_params) - 20} more")

    lines.extend([
        "",
        "=" * 70,
    ])

    return '\n'.join(lines)


def generate_fix_report(modules_needing_fix: List[Dict], output_path: Path) -> None:
    """Generate a detailed fix report file."""
    lines = [
        "# Modules Needing Schema Fix",
        "",
        f"Total: {len(modules_needing_fix)} modules",
        "",
        "## Priority Order (by category usage frequency)",
        "",
    ]

    # Group by category
    by_cat: Dict[str, List] = defaultdict(list)
    for m in modules_needing_fix:
        by_cat[m['category']].append(m)

    # Priority order
    priority_order = ['browser', 'http', 'data', 'flow', 'array', 'file', 'llm']

    for cat in priority_order:
        if cat in by_cat:
            modules = by_cat.pop(cat)
            lines.append(f"### {cat} ({len(modules)} modules)")
            lines.append("")
            for m in modules:
                lines.append(f"- [ ] `{m['module_id']}`")
                if not m['has_output_schema']:
                    lines.append(f"      - Missing: `output_schema`")
                if not m['has_params_schema']:
                    lines.append(f"      - Missing: `params_schema`")
            lines.append("")

    # Remaining categories
    for cat in sorted(by_cat.keys()):
        modules = by_cat[cat]
        lines.append(f"### {cat} ({len(modules)} modules)")
        lines.append("")
        for m in modules:
            lines.append(f"- [ ] `{m['module_id']}`")
            if not m['has_output_schema']:
                lines.append(f"      - Missing: `output_schema`")
            if not m['has_params_schema']:
                lines.append(f"      - Missing: `params_schema`")
        lines.append("")

    output_path.write_text('\n'.join(lines))
    print(f"\nFix report written to: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Validate module schema completeness'
    )
    parser.add_argument('--strict', action='store_true',
                        help='Exit with code 1 if any ERROR-level issues exist')
    parser.add_argument('--json', action='store_true',
                        help='Output results as JSON')
    parser.add_argument('--category', '-c', type=str,
                        help='Filter by category (e.g., browser, data)')
    parser.add_argument('--fix-report', action='store_true',
                        help='Generate a markdown report of modules to fix')

    args = parser.parse_args()

    # Load modules
    try:
        metadata = load_all_modules()
    except Exception as e:
        print(f"Error loading modules: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(2)

    # Validate
    data = validate_schemas(metadata, category_filter=args.category)

    # Output
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print(generate_text_report(data))

    # Generate fix report
    if args.fix_report and data['modules_needing_fix']:
        report_path = PROJECT_ROOT / 'SCHEMA_FIX_TODO.md'
        generate_fix_report(data['modules_needing_fix'], report_path)

    # Exit code
    if args.strict and not data['summary']['is_valid']:
        sys.exit(1)

    sys.exit(0)


if __name__ == '__main__':
    main()
