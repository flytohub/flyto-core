#!/usr/bin/env python3
"""
lint_modules.py - Unified Module Linter

Comprehensive validation for all registered modules using ModuleValidator.

Usage:
    python scripts/lint_modules.py [options]

Options:
    --strict          Warnings also fail (exit 1)
    --mode            Validation mode: dev|ci|release (default: ci)
    --json            Output results as JSON
    --category        Filter by category (e.g., --category browser)
    --module          Validate specific module (e.g., --module browser.launch)
    --verbose         Show all modules including passed ones
    --baseline FILE   Compare against baseline; only fail on NEW violations
    --baseline-create FILE  Create baseline from current violations
    --baseline-update FILE  Update baseline, removing fixed violations
    --trend-record DIR      Record results for trend tracking
    --trend-report DIR      Show quality trend report from recorded data

Exit codes:
    0 - All modules passed (or no new violations in baseline mode)
    1 - One or more modules failed validation (or new violations in baseline mode)
    2 - Error loading modules

Examples:
    # Standard CI check
    python scripts/lint_modules.py

    # Strict mode for release
    python scripts/lint_modules.py --strict --mode release

    # JSON output for automated processing
    python scripts/lint_modules.py --json > validation.json

    # Check only browser modules
    python scripts/lint_modules.py --category browser

    # Create baseline from current state
    python scripts/lint_modules.py --baseline-create baseline.json

    # CI with baseline (only fail on NEW violations)
    python scripts/lint_modules.py --baseline baseline.json

    # Update baseline after fixing issues
    python scripts/lint_modules.py --baseline-update baseline.json

    # Record results for trend tracking
    python scripts/lint_modules.py --trend-record .lint-history

    # Show quality trend report
    python scripts/lint_modules.py --trend-report .lint-history
"""

import argparse
import hashlib
import json
import pkgutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Set

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))


# =============================================================================
# Baseline Functions
# =============================================================================

def compute_violation_fingerprint(module_id: str, error: str) -> str:
    """
    Compute a stable fingerprint for a violation.

    The fingerprint is based on module_id and the error rule code (e.g., S001, SEC004).
    This allows tracking violations even if the error message wording changes slightly.
    """
    # Extract rule code from error if present (e.g., "[S001]" or "S001:")
    import re
    rule_match = re.search(r'\[([A-Z]+\d+)\]|^([A-Z]+\d+):', error)
    if rule_match:
        rule_code = rule_match.group(1) or rule_match.group(2)
        key = f"{module_id}:{rule_code}"
    else:
        # Fallback: use first 50 chars of error
        error_prefix = error[:50].strip()
        key = f"{module_id}:{error_prefix}"

    return hashlib.sha256(key.encode()).hexdigest()[:16]


def load_baseline(baseline_path: Path) -> Dict[str, Any]:
    """Load baseline file."""
    if not baseline_path.exists():
        return {"violations": {}, "created_at": None, "updated_at": None}

    with open(baseline_path, "r") as f:
        return json.load(f)


def save_baseline(baseline_path: Path, data: Dict[str, Any]) -> None:
    """Save baseline file."""
    with open(baseline_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Baseline saved to: {baseline_path}")


def create_baseline_from_results(results: Dict[str, Any]) -> Dict[str, Any]:
    """Create baseline data from validation results."""
    violations = {}

    for module in results["modules"]:
        if module["status"] == "failed":
            for error in module["errors"]:
                fingerprint = compute_violation_fingerprint(module["module_id"], error)
                violations[fingerprint] = {
                    "module_id": module["module_id"],
                    "error": error,
                    "first_seen": datetime.now().isoformat(),
                }

    # Also include import failures
    for failure in results.get("import_failures", []):
        # Extract module name from failure string
        module_name = failure.split(":")[0] if ":" in failure else failure
        fingerprint = compute_violation_fingerprint(module_name, "IMPORT_FAILURE")
        violations[fingerprint] = {
            "module_id": module_name,
            "error": f"IMPORT_FAILURE: {failure}",
            "first_seen": datetime.now().isoformat(),
        }

    return {
        "violations": violations,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "total_count": len(violations),
    }


def compare_with_baseline(
    results: Dict[str, Any],
    baseline: Dict[str, Any]
) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    """
    Compare current results with baseline.

    Returns:
        (new_violations, existing_violations, fixed_violations)
    """
    baseline_fingerprints = set(baseline.get("violations", {}).keys())
    current_fingerprints: Set[str] = set()

    new_violations = []
    existing_violations = []

    # Check module errors
    for module in results["modules"]:
        if module["status"] == "failed":
            for error in module["errors"]:
                fingerprint = compute_violation_fingerprint(module["module_id"], error)
                current_fingerprints.add(fingerprint)

                violation_info = {
                    "module_id": module["module_id"],
                    "error": error,
                    "fingerprint": fingerprint,
                }

                if fingerprint in baseline_fingerprints:
                    existing_violations.append(violation_info)
                else:
                    new_violations.append(violation_info)

    # Check import failures
    for failure in results.get("import_failures", []):
        module_name = failure.split(":")[0] if ":" in failure else failure
        fingerprint = compute_violation_fingerprint(module_name, "IMPORT_FAILURE")
        current_fingerprints.add(fingerprint)

        violation_info = {
            "module_id": module_name,
            "error": f"IMPORT_FAILURE: {failure}",
            "fingerprint": fingerprint,
        }

        if fingerprint in baseline_fingerprints:
            existing_violations.append(violation_info)
        else:
            new_violations.append(violation_info)

    # Find fixed violations (in baseline but not in current)
    fixed_violations = []
    for fingerprint, info in baseline.get("violations", {}).items():
        if fingerprint not in current_fingerprints:
            fixed_violations.append({
                "module_id": info["module_id"],
                "error": info["error"],
                "fingerprint": fingerprint,
                "first_seen": info.get("first_seen"),
            })

    return new_violations, existing_violations, fixed_violations


def update_baseline(
    baseline_path: Path,
    baseline: Dict[str, Any],
    results: Dict[str, Any]
) -> Dict[str, Any]:
    """Update baseline by removing fixed violations and adding new ones."""
    new_violations, existing_violations, fixed_violations = compare_with_baseline(results, baseline)

    # Start with existing violations that still exist
    updated_violations = {}
    for v in existing_violations:
        old_info = baseline["violations"].get(v["fingerprint"], {})
        updated_violations[v["fingerprint"]] = {
            "module_id": v["module_id"],
            "error": v["error"],
            "first_seen": old_info.get("first_seen", datetime.now().isoformat()),
        }

    # Add new violations (they become part of baseline now)
    for v in new_violations:
        updated_violations[v["fingerprint"]] = {
            "module_id": v["module_id"],
            "error": v["error"],
            "first_seen": datetime.now().isoformat(),
        }

    return {
        "violations": updated_violations,
        "created_at": baseline.get("created_at", datetime.now().isoformat()),
        "updated_at": datetime.now().isoformat(),
        "total_count": len(updated_violations),
        "fixed_count": len(fixed_violations),
    }


# =============================================================================
# Trend Tracking Functions
# =============================================================================

def record_trend_data(trend_dir: Path, results: Dict[str, Any]) -> None:
    """Record validation results for trend tracking."""
    trend_dir.mkdir(parents=True, exist_ok=True)

    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = trend_dir / f"lint_{timestamp}.json"

    # Extract summary metrics
    summary = results["summary"]
    trend_data = {
        "timestamp": datetime.now().isoformat(),
        "total": summary["total"],
        "passed": summary["passed"],
        "warned": summary["warned"],
        "failed": summary["failed"],
        "import_failures": summary.get("import_failures", 0),
        "pass_rate": round(summary["passed"] / summary["total"] * 100, 2) if summary["total"] > 0 else 0,
        "mode": summary["mode"],
        # Group errors by rule code
        "errors_by_rule": _group_errors_by_rule(results["modules"]),
        "warnings_by_rule": _group_warnings_by_rule(results["modules"]),
    }

    with open(filename, "w") as f:
        json.dump(trend_data, f, indent=2)

    print(f"Trend data recorded to: {filename}")


def _group_errors_by_rule(modules: List[Dict]) -> Dict[str, int]:
    """Group error counts by rule code."""
    counts: Dict[str, int] = {}
    import re
    for module in modules:
        for error in module.get("errors", []):
            match = re.search(r'\[([A-Z]+\d+)\]', error)
            if match:
                rule = match.group(1)
                counts[rule] = counts.get(rule, 0) + 1
    return counts


def _group_warnings_by_rule(modules: List[Dict]) -> Dict[str, int]:
    """Group warning counts by rule code."""
    counts: Dict[str, int] = {}
    import re
    for module in modules:
        for warning in module.get("warnings", []):
            match = re.search(r'\[([A-Z]+\d+)\]', warning)
            if match:
                rule = match.group(1)
                counts[rule] = counts.get(rule, 0) + 1
    return counts


def load_trend_history(trend_dir: Path, limit: int = 30) -> List[Dict[str, Any]]:
    """Load trend history from directory."""
    if not trend_dir.exists():
        return []

    files = sorted(trend_dir.glob("lint_*.json"), reverse=True)[:limit]
    history = []

    for f in reversed(files):  # Oldest first for chronological order
        try:
            with open(f, "r") as fp:
                history.append(json.load(fp))
        except Exception:
            continue

    return history


def print_trend_report(trend_dir: Path) -> None:
    """Print quality trend report."""
    history = load_trend_history(trend_dir)

    if not history:
        print(f"No trend data found in {trend_dir}")
        return

    print()
    print("=" * 70)
    print("Quality Trend Report")
    print("=" * 70)
    print(f"Data source: {trend_dir}")
    print(f"Records:     {len(history)}")
    print()

    # Show recent trend
    print("-" * 70)
    print("Recent History (last 10 runs)")
    print("-" * 70)
    print(f"{'Date':<20} {'Total':>8} {'Pass':>8} {'Fail':>8} {'Rate':>8}")
    print("-" * 70)

    recent = history[-10:]
    for entry in recent:
        ts = entry.get("timestamp", "")[:19].replace("T", " ")
        total = entry.get("total", 0)
        passed = entry.get("passed", 0)
        failed = entry.get("failed", 0)
        rate = entry.get("pass_rate", 0)
        print(f"{ts:<20} {total:>8} {passed:>8} {failed:>8} {rate:>7.1f}%")

    print()

    # Compare first and last
    if len(history) >= 2:
        first = history[0]
        last = history[-1]

        print("-" * 70)
        print("Trend Summary")
        print("-" * 70)

        rate_change = last.get("pass_rate", 0) - first.get("pass_rate", 0)
        fail_change = last.get("failed", 0) - first.get("failed", 0)
        total_change = last.get("total", 0) - first.get("total", 0)

        trend_icon = "+" if rate_change >= 0 else ""
        print(f"Pass rate change:  {trend_icon}{rate_change:.1f}%")

        trend_icon = "+" if total_change >= 0 else ""
        print(f"Module count:      {trend_icon}{total_change}")

        trend_icon = "+" if fail_change >= 0 else ""
        print(f"Failure count:     {trend_icon}{fail_change}")

        # Show rule trends
        print()
        print("Top Issues (by frequency):")

        # Aggregate rule counts
        all_errors: Dict[str, int] = {}
        for entry in history[-10:]:  # Last 10 entries
            for rule, count in entry.get("errors_by_rule", {}).items():
                all_errors[rule] = all_errors.get(rule, 0) + count

        all_warnings: Dict[str, int] = {}
        for entry in history[-10:]:
            for rule, count in entry.get("warnings_by_rule", {}).items():
                all_warnings[rule] = all_warnings.get(rule, 0) + count

        if all_errors:
            print("  Errors:")
            for rule, count in sorted(all_errors.items(), key=lambda x: -x[1])[:5]:
                print(f"    {rule}: {count}")

        if all_warnings:
            print("  Warnings:")
            for rule, count in sorted(all_warnings.items(), key=lambda x: -x[1])[:5]:
                print(f"    {rule}: {count}")

    print()
    print("=" * 70)


# =============================================================================
# Module Discovery
# =============================================================================

def discover_and_import_modules() -> List[str]:
    """
    Auto-discover and import ALL modules under src/core/modules.

    This ensures no modules are missed due to incomplete __init__.py imports.

    Returns:
        List of import failures (module_name: error_message)
    """
    import importlib

    import_failures: List[str] = []
    modules_path = PROJECT_ROOT / "src" / "core" / "modules"

    # Packages to scan
    packages_to_scan = [
        "core.modules.atomic",
        "core.modules.composite",
        "core.modules.third_party",
        "core.modules.integrations",
    ]

    for package_name in packages_to_scan:
        try:
            package = importlib.import_module(package_name)
            package_path = Path(package.__file__).parent

            # Walk all submodules
            for finder, name, is_pkg in pkgutil.walk_packages(
                [str(package_path)],
                prefix=package_name + "."
            ):
                try:
                    importlib.import_module(name)
                except Exception as e:
                    # Record import failures instead of silently skipping
                    import_failures.append(f"{name}: {type(e).__name__}: {e}")
        except ImportError as e:
            # Package doesn't exist - this is OK
            pass
        except Exception as e:
            import_failures.append(f"{package_name}: {type(e).__name__}: {e}")

    return import_failures


def load_all_modules() -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    """
    Load all modules via auto-discovery.

    Returns:
        Tuple of (metadata dict, import_failures list)
    """
    # Auto-discover all modules and capture failures
    import_failures = discover_and_import_modules()

    # Get registry
    from core.modules.registry import ModuleRegistry

    return ModuleRegistry.get_all_metadata(), import_failures


def validate_modules(
    metadata: Dict[str, Dict[str, Any]],
    import_failures: List[str],
    mode: str = "ci",
    category_filter: Optional[str] = None,
    module_filter: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Validate modules using ModuleValidator.

    Returns:
        {
            'summary': {...},
            'modules': [...],
            'import_failures': [...]
        }
    """
    from core.modules.validator import ModuleValidator
    from core.modules.registry.validation_types import ValidationMode
    from core.modules.registry import ModuleRegistry

    validator = ModuleValidator(mode=ValidationMode(mode))

    # Filter metadata if requested
    if module_filter:
        metadata = {k: v for k, v in metadata.items() if k == module_filter}
    elif category_filter:
        metadata = {
            k: v for k, v in metadata.items()
            if v.get("category") == category_filter or k.startswith(f"{category_filter}.")
        }

    results = []
    total = len(metadata)
    passed = 0
    warned = 0
    failed = 0

    for module_id, meta in sorted(metadata.items()):
        # Get module class for behavior inference
        module_class = ModuleRegistry.get(module_id)
        is_valid = validator.validate(meta, module_class)

        result = {
            "module_id": module_id,
            "category": meta.get("category", "unknown"),
            "stability": meta.get("stability", "unknown"),
            "status": "passed" if is_valid and not validator.warnings else (
                "warned" if is_valid else "failed"
            ),
            "errors": list(validator.errors),
            "warnings": list(validator.warnings),
        }
        results.append(result)

        if not is_valid:
            failed += 1
        elif validator.warnings:
            passed += 1
            warned += 1
        else:
            passed += 1

    # In CI/RELEASE mode, import failures count as failures
    import_failure_count = len(import_failures) if mode in ("ci", "release") else 0

    return {
        "summary": {
            "total": total,
            "passed": passed,
            "warned": warned,
            "failed": failed + import_failure_count,
            "import_failures": len(import_failures),
            "is_valid": failed == 0 and import_failure_count == 0,
            "mode": mode,
        },
        "modules": results,
        "import_failures": import_failures,
    }


def print_text_report(data: Dict[str, Any], verbose: bool = False) -> None:
    """Print human-readable report."""
    summary = data["summary"]
    modules = data["modules"]
    import_failures = data.get("import_failures", [])

    print()
    print("=" * 70)
    print("Flyto-Core Module Validation Report")
    print("=" * 70)
    print()
    print(f"Mode:           {summary['mode']}")
    print(f"Total:          {summary['total']}")
    print(f"Passed:         {summary['passed']}")
    print(f"With Warnings:  {summary['warned']}")
    print(f"Failed:         {summary['failed']}")
    if summary.get('import_failures', 0) > 0:
        print(f"Import Failures:{summary['import_failures']}")
    print(f"Status:         {'PASS' if summary['is_valid'] else 'FAIL'}")
    print()

    # Show import failures first (critical)
    if import_failures:
        print("-" * 70)
        print(f"IMPORT FAILURES ({len(import_failures)}) - These modules could not be loaded!")
        print("-" * 70)
        for failure in import_failures[:20]:  # Limit to 20
            print(f"  ✗ {failure}")
        if len(import_failures) > 20:
            print(f"  ... and {len(import_failures) - 20} more")
        print()

    # Group by status
    failed_modules = [m for m in modules if m["status"] == "failed"]
    warned_modules = [m for m in modules if m["status"] == "warned"]
    passed_modules = [m for m in modules if m["status"] == "passed"]

    # Show failed modules
    if failed_modules:
        print("-" * 70)
        print(f"FAILED ({len(failed_modules)})")
        print("-" * 70)
        for m in failed_modules:
            print(f"  ✗ {m['module_id']}")
            for error in m["errors"]:
                print(f"      ERROR: {error}")
        print()

    # Show warned modules
    if warned_modules:
        print("-" * 70)
        print(f"WARNINGS ({len(warned_modules)})")
        print("-" * 70)
        for m in warned_modules:
            print(f"  ⚠ {m['module_id']}")
            for warning in m["warnings"]:
                print(f"      WARN: {warning}")
        print()

    # Show passed modules (only in verbose mode)
    if verbose and passed_modules:
        print("-" * 70)
        print(f"PASSED ({len(passed_modules)})")
        print("-" * 70)
        for m in passed_modules:
            print(f"  ✓ {m['module_id']}")
        print()

    print("=" * 70)


def print_baseline_report(
    new_violations: List[Dict],
    existing_violations: List[Dict],
    fixed_violations: List[Dict],
    baseline_path: Path
) -> None:
    """Print baseline comparison report."""
    print()
    print("=" * 70)
    print("Baseline Comparison Report")
    print("=" * 70)
    print(f"Baseline file:    {baseline_path}")
    print(f"New violations:   {len(new_violations)}")
    print(f"Existing (known): {len(existing_violations)}")
    print(f"Fixed:            {len(fixed_violations)}")
    print()

    if new_violations:
        print("-" * 70)
        print(f"NEW VIOLATIONS ({len(new_violations)}) - These will cause CI to fail!")
        print("-" * 70)
        for v in new_violations:
            print(f"  ✗ {v['module_id']}")
            print(f"      {v['error']}")
        print()

    if fixed_violations:
        print("-" * 70)
        print(f"FIXED ({len(fixed_violations)}) - Great job!")
        print("-" * 70)
        for v in fixed_violations:
            print(f"  ✓ {v['module_id']}: {v['error'][:60]}...")
        print()

    if existing_violations and not new_violations:
        print("-" * 70)
        print(f"KNOWN VIOLATIONS ({len(existing_violations)}) - Tracked in baseline")
        print("-" * 70)
        for v in existing_violations[:10]:
            print(f"  ⚠ {v['module_id']}: {v['error'][:50]}...")
        if len(existing_violations) > 10:
            print(f"  ... and {len(existing_violations) - 10} more")
        print()

    # Final status
    if new_violations:
        print("STATUS: FAIL (new violations detected)")
    else:
        print("STATUS: PASS (no new violations)")

    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="Unified module linter for flyto-core",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        "--mode",
        choices=["dev", "ci", "release"],
        default="ci",
        help="Validation mode (default: ci)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON"
    )
    parser.add_argument(
        "--category", "-c",
        type=str,
        help="Filter by category"
    )
    parser.add_argument(
        "--module", "-m",
        type=str,
        help="Validate specific module"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show all modules including passed"
    )
    parser.add_argument(
        "--baseline",
        type=str,
        metavar="FILE",
        help="Compare against baseline file; only fail on NEW violations"
    )
    parser.add_argument(
        "--baseline-create",
        type=str,
        metavar="FILE",
        help="Create baseline from current violations"
    )
    parser.add_argument(
        "--baseline-update",
        type=str,
        metavar="FILE",
        help="Update baseline, removing fixed violations"
    )
    parser.add_argument(
        "--trend-record",
        type=str,
        metavar="DIR",
        help="Record results to directory for trend tracking"
    )
    parser.add_argument(
        "--trend-report",
        type=str,
        metavar="DIR",
        help="Show quality trend report from recorded data"
    )

    args = parser.parse_args()

    # Handle trend report (doesn't need module loading)
    if args.trend_report:
        print_trend_report(Path(args.trend_report))
        sys.exit(0)

    # Load modules - suppress import-time warnings/logging for JSON output
    import os
    import warnings
    import logging

    if args.json:
        # Suppress all import-time output for clean JSON
        os.environ["FLYTO_VALIDATION_MODE"] = "dev"
        warnings.filterwarnings("ignore")
        logging.disable(logging.CRITICAL)

    try:
        metadata, import_failures = load_all_modules()
    except Exception as e:
        print(f"Error loading modules: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(2)

    # Restore logging for validation phase
    if args.json:
        logging.disable(logging.NOTSET)

    if not metadata and not import_failures:
        print("Warning: No modules registered", file=sys.stderr)
        sys.exit(0)

    # Validate
    data = validate_modules(
        metadata,
        import_failures=import_failures,
        mode=args.mode,
        category_filter=args.category,
        module_filter=args.module,
    )

    # Handle baseline operations
    if args.baseline_create:
        # Create baseline from current violations
        baseline_path = Path(args.baseline_create)
        baseline_data = create_baseline_from_results(data)
        save_baseline(baseline_path, baseline_data)

        print(f"\nBaseline created with {baseline_data['total_count']} violations")
        print("Future runs with --baseline will only fail on NEW violations.")
        sys.exit(0)

    elif args.baseline_update:
        # Update existing baseline
        baseline_path = Path(args.baseline_update)
        baseline = load_baseline(baseline_path)

        if not baseline.get("violations"):
            print(f"No existing baseline at {baseline_path}, creating new one...")
            baseline_data = create_baseline_from_results(data)
        else:
            baseline_data = update_baseline(baseline_path, baseline, data)

        save_baseline(baseline_path, baseline_data)
        print(f"\nBaseline updated: {baseline_data['total_count']} violations tracked")
        if baseline_data.get('fixed_count', 0) > 0:
            print(f"Removed {baseline_data['fixed_count']} fixed violations")
        sys.exit(0)

    elif args.baseline:
        # Compare against baseline
        baseline_path = Path(args.baseline)
        baseline = load_baseline(baseline_path)

        if not baseline.get("violations") and baseline.get("created_at") is None:
            print(f"Warning: Baseline file not found: {baseline_path}")
            print("Run with --baseline-create first to create a baseline.")
            # Fall through to normal validation
            if args.json:
                print(json.dumps(data, indent=2))
            else:
                print_text_report(data, verbose=args.verbose)
            sys.exit(0 if data["summary"]["is_valid"] else 1)

        new_violations, existing_violations, fixed_violations = compare_with_baseline(data, baseline)

        if args.json:
            output = {
                **data,
                "baseline": {
                    "file": str(baseline_path),
                    "new_violations": new_violations,
                    "existing_violations": len(existing_violations),
                    "fixed_violations": fixed_violations,
                    "is_valid": len(new_violations) == 0,
                }
            }
            print(json.dumps(output, indent=2))
        else:
            print_baseline_report(new_violations, existing_violations, fixed_violations, baseline_path)

        # Exit code: only fail on NEW violations
        sys.exit(0 if len(new_violations) == 0 else 1)

    else:
        # Normal validation (no baseline)
        if args.json:
            print(json.dumps(data, indent=2))
        else:
            print_text_report(data, verbose=args.verbose)

        # Record trend data if requested
        if args.trend_record:
            record_trend_data(Path(args.trend_record), data)

        # Exit code
        sys.exit(0 if data["summary"]["is_valid"] else 1)


if __name__ == "__main__":
    main()
