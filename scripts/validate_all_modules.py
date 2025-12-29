#!/usr/bin/env python3
"""
validate_all_modules.py - Phase 2 Compliance Validator

Scans all registered modules and validates Phase 2 compliance.

Usage:
    python scripts/validate_all_modules.py [--strict] [--json] [--verbose]

Options:
    --strict    Exit with code 1 if any module lacks timeout field
    --json      Output results as JSON
    --verbose   Show all modules, not just non-compliant
"""
import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Any, Tuple

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Phase 2 required fields and their expected types
PHASE2_FIELDS = {
    'timeout': (int, type(None)),           # Execution timeout (seconds)
    'retryable': (bool,),                   # Can be retried on failure
    'max_retries': (int,),                  # Maximum retry attempts
    'concurrent_safe': (bool,),             # Safe for parallel execution
    'requires_credentials': (bool,),        # Needs API keys/auth
    'handles_sensitive_data': (bool,),      # Processes sensitive data
    'required_permissions': (list,),        # List of required permissions
}

# Critical fields that SHOULD be explicitly set (not just defaulted)
CRITICAL_FIELDS = ['timeout', 'requires_credentials', 'handles_sensitive_data']


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

    return ModuleRegistry.get_all_metadata()


def check_phase2_compliance(module_id: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Check a single module's Phase 2 compliance.

    Returns:
        {
            'module_id': str,
            'compliant': bool,
            'score': float (0-1),
            'missing_fields': list,
            'warnings': list
        }
    """
    missing = []
    warnings = []

    for field, expected_types in PHASE2_FIELDS.items():
        value = metadata.get(field)

        # Check if field exists and has correct type
        if value is None and type(None) not in expected_types:
            missing.append(field)
        elif value is not None and not isinstance(value, expected_types):
            warnings.append(f"{field}: expected {expected_types}, got {type(value)}")

    # Check critical fields that should be explicitly set
    for field in CRITICAL_FIELDS:
        value = metadata.get(field)
        if field == 'timeout' and value is None:
            warnings.append(f"{field}: should be explicitly set for production use")

    # Calculate compliance score
    total_fields = len(PHASE2_FIELDS)
    present_fields = total_fields - len(missing)
    score = present_fields / total_fields if total_fields > 0 else 0

    return {
        'module_id': module_id,
        'category': metadata.get('category', 'unknown'),
        'compliant': len(missing) == 0,
        'score': score,
        'missing_fields': missing,
        'warnings': warnings,
        'has_timeout': metadata.get('timeout') is not None,
    }


def generate_report(results: List[Dict[str, Any]], verbose: bool = False) -> Tuple[str, Dict[str, Any]]:
    """
    Generate compliance report.

    Returns:
        (text_report, summary_dict)
    """
    total = len(results)
    compliant = sum(1 for r in results if r['compliant'])
    with_timeout = sum(1 for r in results if r['has_timeout'])

    # Group by compliance level
    fully_compliant = [r for r in results if r['compliant'] and not r['warnings']]
    partial = [r for r in results if r['compliant'] and r['warnings']]
    non_compliant = [r for r in results if not r['compliant']]

    # Group by category
    by_category: Dict[str, List] = {}
    for r in results:
        cat = r['category']
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(r)

    # Build text report
    lines = [
        "═" * 60,
        "Flyto-Core Module Phase 2 Compliance Report",
        "═" * 60,
        "",
        f"Total Modules:        {total}",
        f"Fully Compliant:      {len(fully_compliant)} ({len(fully_compliant)*100//total}%)" if total > 0 else "Fully Compliant: 0",
        f"Partial (warnings):   {len(partial)} ({len(partial)*100//total}%)" if total > 0 else "Partial: 0",
        f"Non-compliant:        {len(non_compliant)} ({len(non_compliant)*100//total}%)" if total > 0 else "Non-compliant: 0",
        f"With timeout set:     {with_timeout} ({with_timeout*100//total}%)" if total > 0 else "With timeout: 0",
        "",
        "─" * 60,
        "By Category:",
        "─" * 60,
    ]

    for cat in sorted(by_category.keys()):
        cat_modules = by_category[cat]
        cat_compliant = sum(1 for r in cat_modules if r['compliant'])
        lines.append(f"  {cat:20s}: {len(cat_modules):3d} modules, {cat_compliant:3d} compliant")

    if non_compliant:
        lines.extend([
            "",
            "─" * 60,
            "Non-compliant Modules:",
            "─" * 60,
        ])
        for r in sorted(non_compliant, key=lambda x: x['module_id']):
            missing = ', '.join(r['missing_fields'])
            lines.append(f"  • {r['module_id']}")
            lines.append(f"    Missing: {missing}")

    if verbose and partial:
        lines.extend([
            "",
            "─" * 60,
            "Modules with Warnings:",
            "─" * 60,
        ])
        for r in sorted(partial, key=lambda x: x['module_id']):
            lines.append(f"  • {r['module_id']}")
            for w in r['warnings']:
                lines.append(f"    ⚠ {w}")

    lines.extend([
        "",
        "═" * 60,
    ])

    summary = {
        'total_modules': total,
        'fully_compliant': len(fully_compliant),
        'partial_compliant': len(partial),
        'non_compliant': len(non_compliant),
        'with_timeout': with_timeout,
        'compliance_rate': compliant / total if total > 0 else 0,
        'by_category': {
            cat: {
                'total': len(modules),
                'compliant': sum(1 for r in modules if r['compliant'])
            }
            for cat, modules in by_category.items()
        }
    }

    return '\n'.join(lines), summary


def main():
    parser = argparse.ArgumentParser(
        description='Validate Phase 2 compliance for all registered modules'
    )
    parser.add_argument('--strict', action='store_true',
                        help='Exit with code 1 if any module lacks timeout')
    parser.add_argument('--json', action='store_true',
                        help='Output results as JSON')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Show all modules including warnings')

    args = parser.parse_args()

    # Load modules
    try:
        metadata = load_all_modules()
    except Exception as e:
        print(f"Error loading modules: {e}", file=sys.stderr)
        sys.exit(2)

    # Check compliance
    results = []
    for module_id, meta in metadata.items():
        result = check_phase2_compliance(module_id, meta)
        results.append(result)

    # Generate report
    text_report, summary = generate_report(results, verbose=args.verbose)

    if args.json:
        output = {
            'summary': summary,
            'modules': results
        }
        print(json.dumps(output, indent=2))
    else:
        print(text_report)

    # Exit code
    if args.strict:
        modules_without_timeout = [r for r in results if not r['has_timeout']]
        if modules_without_timeout:
            if not args.json:
                print(f"\n⚠ {len(modules_without_timeout)} modules without timeout (strict mode)")
            sys.exit(1)

    sys.exit(0)


if __name__ == '__main__':
    main()
