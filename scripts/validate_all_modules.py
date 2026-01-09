#!/usr/bin/env python3
"""
validate_all_modules.py - Release-Gate Quality Validator

Validates all registered modules against 30+ rules across 6 categories:
- Identity (CORE-ID): module_id, stability, version
- Execution (CORE-EX): timeout_ms, retryable, max_retries
- Schema (CORE-SCH): params_schema, output_schema validation
- Capability (CORE-CAP): permissions whitelist, capability detection
- Security (CORE-SEC): secrets, sensitive data, credentials
- AST (CORE-AST): syntax, async, print statements

Usage:
    python scripts/validate_all_modules.py [options]

Strict Levels:
    --strict=default   Only BLOCKER/FATAL fail (default)
    --strict=timeout   timeout_ms required for all modules
    --strict=stable    Stable modules must pass all ERROR rules
    --strict=release   Release gate - all modules, all rules
    --strict=all       WARN → ERROR (strictest, for CI)

Examples:
    # Basic validation
    python scripts/validate_all_modules.py

    # CI gate for release
    python scripts/validate_all_modules.py --strict=release --json

    # Check specific category
    python scripts/validate_all_modules.py --category=security
"""

import argparse
import json
import sys
import os
from pathlib import Path
from typing import Dict, List, Any, Optional, Set

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))


def run_mypy_check(paths: List[str] = None) -> Dict[str, Any]:
    """
    Run mypy type checking on the codebase.

    Returns:
        Dict with 'success', 'error_count', 'errors' fields
    """
    import subprocess

    if paths is None:
        # Only check the quality validation subsystem (strict types)
        paths = ["src/core/modules/quality"]

    try:
        result = subprocess.run(
            [
                sys.executable, "-m", "mypy",
                *paths,
                "--ignore-missing-imports",
                "--no-error-summary",
                "--no-color",
                "--exclude", "test",  # Exclude test files
                "--exclude", "__pycache__",
            ],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(PROJECT_ROOT),
        )

        # Parse mypy output - only count errors in the target paths
        errors = []
        for line in result.stdout.strip().split("\n"):
            if line and ": error:" in line:
                # Only include errors from our target paths
                is_target_error = any(
                    p.replace("/", os.sep) in line or p in line
                    for p in paths
                )
                if is_target_error:
                    errors.append(line)

        return {
            "success": len(errors) == 0,  # Success if no target errors
            "error_count": len(errors),
            "errors": errors[:20],  # Limit to first 20 errors
            "raw_output": result.stdout[:2000] if result.stdout else "",
        }

    except FileNotFoundError:
        return {
            "success": True,  # Skip if mypy not installed
            "error_count": 0,
            "errors": [],
            "warning": "mypy not installed - skipping type check",
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error_count": 1,
            "errors": ["mypy check timed out after 300 seconds"],
        }
    except Exception as e:
        return {
            "success": False,
            "error_count": 1,
            "errors": [f"mypy check failed: {str(e)}"],
        }


def load_all_modules() -> Dict[str, Dict[str, Any]]:
    """
    Load all modules by importing the module packages.
    Returns metadata dict from ModuleRegistry.
    """
    # Import module packages to trigger registration
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

    # Import third-party modules
    try:
        from src.core.modules import third_party
    except ImportError:
        try:
            from core.modules import third_party
        except ImportError:
            pass

    # Get registry
    try:
        from src.core.modules.registry import ModuleRegistry
    except ImportError:
        from core.modules.registry import ModuleRegistry

    return ModuleRegistry.get_all_metadata()


def get_module_source_paths() -> Dict[str, str]:
    """Get file paths for all module source files."""
    paths = {}

    atomic_base = PROJECT_ROOT / "src" / "core" / "modules" / "atomic"
    if atomic_base.exists():
        for py_file in atomic_base.rglob("*.py"):
            if py_file.name.startswith("_"):
                continue
            # Read file to find module_id from @register_module decorator
            try:
                content = py_file.read_text()
                import re
                match = re.search(r'@register_module\(["\']([^"\']+)["\']', content)
                if match:
                    module_id = match.group(1)
                    paths[module_id] = str(py_file)
            except Exception:
                pass

    return paths


def get_module_source_codes(paths: Dict[str, str]) -> Dict[str, str]:
    """Read source code for all modules."""
    codes = {}
    for module_id, path in paths.items():
        try:
            codes[module_id] = Path(path).read_text(encoding="utf-8")
        except Exception:
            pass
    return codes


def format_text_report(report, verbose: bool = False) -> str:
    """Format aggregate report as text."""
    lines = [
        "═" * 70,
        "Flyto-Core Module Validation Report",
        "═" * 70,
        "",
        f"Total Modules:     {report.total_modules}",
        f"Passed:            {report.passed_modules} ({report.passed_modules * 100 // report.total_modules if report.total_modules else 0}%)",
        f"Failed:            {report.failed_modules} ({report.failed_modules * 100 // report.total_modules if report.total_modules else 0}%)",
        f"Total Issues:      {report.total_issues}",
        "",
    ]

    # Issues by severity
    if report.issues_by_severity:
        lines.append("─" * 70)
        lines.append("Issues by Severity:")
        lines.append("─" * 70)
        for severity in ["FATAL", "BLOCKER", "ERROR", "WARN", "INFO"]:
            count = report.issues_by_severity.get(severity, 0)
            if count > 0:
                lines.append(f"  {severity:10s}: {count}")
        lines.append("")

    # Issues by category
    if report.issues_by_category:
        lines.append("─" * 70)
        lines.append("Issues by Category:")
        lines.append("─" * 70)
        for category, count in sorted(report.issues_by_category.items()):
            lines.append(f"  {category:15s}: {count}")
        lines.append("")

    # Failed modules
    failed_reports = [r for r in report.reports if not r.passed]
    if failed_reports:
        lines.append("─" * 70)
        lines.append("Failed Modules:")
        lines.append("─" * 70)

        for module_report in sorted(failed_reports, key=lambda x: x.module_id):
            lines.append(f"\n  • {module_report.module_id}")

            # Show blocking issues
            blocking = [i for i in module_report.issues
                       if i.severity.value in ("FATAL", "BLOCKER", "ERROR")]
            for issue in blocking[:5]:  # Limit to 5 per module
                severity_icon = {
                    "FATAL": "💀",
                    "BLOCKER": "🚫",
                    "ERROR": "❌",
                }.get(issue.severity.value, "⚠")
                lines.append(f"    {severity_icon} [{issue.rule_id}] {issue.message}")
                if issue.suggestion:
                    lines.append(f"       └─ {issue.suggestion}")

            if len(blocking) > 5:
                lines.append(f"    ... and {len(blocking) - 5} more issues")

    # Passed modules with warnings (verbose only)
    if verbose:
        warned_reports = [r for r in report.reports
                        if r.passed and r.warn_count > 0]
        if warned_reports:
            lines.append("")
            lines.append("─" * 70)
            lines.append("Modules with Warnings:")
            lines.append("─" * 70)

            for module_report in sorted(warned_reports, key=lambda x: x.module_id)[:20]:
                lines.append(f"  • {module_report.module_id}: {module_report.warn_count} warnings")

    lines.extend([
        "",
        "═" * 70,
    ])

    return "\n".join(lines)


def format_json_report(report) -> str:
    """Format aggregate report as JSON."""
    return json.dumps({
        "summary": {
            "total_modules": report.total_modules,
            "passed_modules": report.passed_modules,
            "failed_modules": report.failed_modules,
            "total_issues": report.total_issues,
            "issues_by_severity": report.issues_by_severity,
            "issues_by_category": report.issues_by_category,
        },
        "modules": [
            {
                "module_id": r.module_id,
                "passed": r.passed,
                "error_count": r.error_count,
                "warn_count": r.warn_count,
                "issues": [
                    {
                        "rule_id": i.rule_id,
                        "severity": i.severity.value,
                        "message": i.message,
                        "line": i.line,
                        "suggestion": i.suggestion,
                    }
                    for i in r.issues
                ]
            }
            for r in report.reports
        ]
    }, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description="Validate all registered modules against quality rules",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Strict Levels:
  default   Only BLOCKER/FATAL cause failure
  timeout   timeout_ms required for all
  stable    Strict for stable modules
  release   All modules must pass all rules
  all       WARN → ERROR (strictest)

Output Formats:
  text      Human-readable text (default)
  json      Machine-readable JSON
  markdown  Markdown report
        """
    )
    parser.add_argument(
        "--strict",
        choices=["default", "timeout", "stable", "release", "all"],
        default="default",
        help="Strictness level (default: default)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON (shortcut for --format=json)"
    )
    parser.add_argument(
        "--format",
        choices=["text", "json", "markdown"],
        default="text",
        help="Output format (default: text)"
    )
    parser.add_argument(
        "--output", "-o",
        help="Output file path (default: stdout)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show all modules including warnings"
    )
    parser.add_argument(
        "--category",
        help="Only validate specific category (identity, execution, schema, capability, security, ast)"
    )
    parser.add_argument(
        "--disable-rule",
        action="append",
        dest="disabled_rules",
        default=[],
        help="Disable specific rule (can be repeated)"
    )
    parser.add_argument(
        "--list-rules",
        action="store_true",
        help="List all available rules and exit"
    )
    parser.add_argument(
        "--include-mypy",
        action="store_true",
        help="Include mypy type checking (requires mypy installed)"
    )
    parser.add_argument(
        "--baseline",
        help="Path to baseline JSON file for exemptions"
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Show fixes that would be applied (dry-run)"
    )
    parser.add_argument(
        "--fix-apply",
        action="store_true",
        help="Actually apply fixes to files"
    )

    args = parser.parse_args()

    # Handle --json shortcut
    if args.json:
        args.format = "json"

    # Import validation system (quality module)
    try:
        from src.core.modules.quality import (
            ValidationEngine,
            StrictLevel,
            Severity,
            Baseline,
            generate_report,
        )
        from src.core.modules.quality.rules import get_all_rules
    except ImportError:
        try:
            from core.modules.quality import (
                ValidationEngine,
                StrictLevel,
                Severity,
                Baseline,
                generate_report,
            )
            from core.modules.quality.rules import get_all_rules
        except ImportError as e:
            print(f"Error importing validation system: {e}", file=sys.stderr)
            print("Make sure you're running from the project root.", file=sys.stderr)
            sys.exit(2)

    # List rules mode
    if args.list_rules:
        rules = get_all_rules()
        print("Available Validation Rules:")
        print("=" * 60)

        by_category: Dict[str, List] = {}
        for rule in rules:
            cat = rule.category
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(rule)

        for category in sorted(by_category.keys()):
            print(f"\n{category.upper()}:")
            for rule in sorted(by_category[category], key=lambda r: r.rule_id):
                stability_note = " [stability-aware]" if rule.stability_aware else ""
                print(f"  {rule.rule_id:15s} {rule.default_severity.value:8s} {rule.description}{stability_note}")

        sys.exit(0)

    # Map strict level string to enum
    strict_map = {
        "default": StrictLevel.DEFAULT,
        "timeout": StrictLevel.TIMEOUT,
        "stable": StrictLevel.STABLE,
        "release": StrictLevel.RELEASE,
        "all": StrictLevel.ALL,
    }
    strict_level = strict_map[args.strict]

    # Categories filter
    enabled_categories: Optional[Set[str]] = None
    if args.category:
        enabled_categories = {args.category}

    # Disabled rules
    disabled_rules = set(args.disabled_rules)

    # Load modules
    try:
        metadata = load_all_modules()
    except Exception as e:
        print(f"Error loading modules: {e}", file=sys.stderr)
        sys.exit(2)

    if not metadata:
        print("No modules found.", file=sys.stderr)
        sys.exit(0)

    # Get source code for AST analysis
    file_paths = get_module_source_paths()
    source_codes = get_module_source_codes(file_paths)

    # Load baseline if specified
    baseline = None
    if args.baseline:
        baseline = Baseline.from_file(Path(args.baseline))

    # Create engine and run validation
    engine = ValidationEngine(
        strict_level=strict_level,
        enabled_categories=enabled_categories,
        disabled_rules=disabled_rules,
        baseline=baseline,
    )

    report = engine.validate_all(
        modules=metadata,
        source_codes=source_codes,
        file_paths=file_paths,
    )

    # Generate output
    if args.format == "json":
        output = generate_report(report, format="json")
    elif args.format == "markdown":
        output = generate_report(report, format="markdown")
    else:
        output = format_text_report(report, verbose=args.verbose)

    # Write output
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"Report written to: {args.output}")
    else:
        print(output)

    # Run mypy check if requested
    mypy_failed = False
    if args.include_mypy:
        print("\n" + "=" * 70)
        print("MYPY TYPE CHECK")
        print("=" * 70)

        mypy_result = run_mypy_check()

        if mypy_result.get("warning"):
            print(f"⚠️  {mypy_result['warning']}")
        elif mypy_result["success"]:
            print("✅ mypy: All checks passed")
        else:
            print(f"❌ mypy: {mypy_result['error_count']} type error(s) found")
            for err in mypy_result["errors"]:
                print(f"   {err}")
            mypy_failed = True

        print("=" * 70)

    # Exit code
    if report.failed_modules > 0 or mypy_failed:
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
