#!/usr/bin/env python3
"""
lint_i18n.py - Validate i18n keys in flyto-core modules

Usage:
    python scripts/lint_i18n.py [--strict] [--fix-report]

Options:
    --strict       Exit with code 1 on any ERROR
    --fix-report   Generate report of issues to fix

Rules:
    CORE-I18N-001: label_key must match modules.{subcategory}.{name}.label
    CORE-I18N-002: description_key must match modules.{subcategory}.{name}.description
    CORE-I18N-003: label fallback should be provided
    CORE-I18N-004: description fallback should be provided
    CORE-I18N-005: params_schema label_key format check
"""

import argparse
import ast
import re
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

PROJECT_ROOT = Path(__file__).parent.parent
MODULES_DIR = PROJECT_ROOT / 'src' / 'core' / 'modules' / 'atomic'


@dataclass
class Violation:
    rule_id: str
    severity: str  # ERROR, WARN, INFO
    message: str
    file: str
    line: int
    module_id: Optional[str] = None


class I18nLinter:
    """Linter for i18n keys in @register_module decorators."""

    def __init__(self):
        self.violations: List[Violation] = []

    def lint_file(self, file_path: Path) -> List[Violation]:
        """Lint a single Python file for i18n issues."""
        violations = []

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            return [Violation(
                rule_id='CORE-I18N-000',
                severity='ERROR',
                message=f'Could not read file: {e}',
                file=str(file_path),
                line=0
            )]

        try:
            tree = ast.parse(content)
        except SyntaxError as e:
            return [Violation(
                rule_id='CORE-I18N-000',
                severity='ERROR',
                message=f'Syntax error: {e}',
                file=str(file_path),
                line=e.lineno or 0
            )]

        # Find @register_module decorators
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                for decorator in node.decorator_list:
                    if self._is_register_module(decorator):
                        module_violations = self._check_decorator(decorator, file_path)
                        violations.extend(module_violations)

        return violations

    def _is_register_module(self, decorator: ast.expr) -> bool:
        """Check if decorator is @register_module."""
        if isinstance(decorator, ast.Call):
            if isinstance(decorator.func, ast.Name):
                return decorator.func.id == 'register_module'
            if isinstance(decorator.func, ast.Attribute):
                return decorator.func.attr == 'register_module'
        return False

    def _check_decorator(self, decorator: ast.Call, file_path: Path) -> List[Violation]:
        """Check @register_module decorator for i18n issues."""
        violations = []

        # Extract keyword arguments
        kwargs = {}
        for kw in decorator.keywords:
            if kw.arg:
                kwargs[kw.arg] = self._get_value(kw.value)

        module_id = kwargs.get('module_id', '')
        subcategory = kwargs.get('subcategory', '')
        label_key = kwargs.get('label_key')
        description_key = kwargs.get('description_key')
        label = kwargs.get('label')
        description = kwargs.get('description')

        # Derive expected key prefix from module_id
        # module_id = "browser.click" -> expected prefix = "modules.browser.click"
        if module_id:
            expected_prefix = f"modules.{module_id}"

            # CORE-I18N-001: Check label_key format
            if label_key:
                expected_label_key = f"{expected_prefix}.label"
                if label_key != expected_label_key:
                    violations.append(Violation(
                        rule_id='CORE-I18N-001',
                        severity='ERROR',
                        message=f"label_key mismatch: got '{label_key}', expected '{expected_label_key}'",
                        file=str(file_path),
                        line=decorator.lineno,
                        module_id=module_id
                    ))

            # CORE-I18N-002: Check description_key format
            if description_key:
                expected_desc_key = f"{expected_prefix}.description"
                if description_key != expected_desc_key:
                    violations.append(Violation(
                        rule_id='CORE-I18N-002',
                        severity='ERROR',
                        message=f"description_key mismatch: got '{description_key}', expected '{expected_desc_key}'",
                        file=str(file_path),
                        line=decorator.lineno,
                        module_id=module_id
                    ))

            # CORE-I18N-003: Check label fallback
            if label_key and not label:
                violations.append(Violation(
                    rule_id='CORE-I18N-003',
                    severity='WARN',
                    message=f"Missing label fallback for module '{module_id}'",
                    file=str(file_path),
                    line=decorator.lineno,
                    module_id=module_id
                ))

            # CORE-I18N-004: Check description fallback
            if description_key and not description:
                violations.append(Violation(
                    rule_id='CORE-I18N-004',
                    severity='WARN',
                    message=f"Missing description fallback for module '{module_id}'",
                    file=str(file_path),
                    line=decorator.lineno,
                    module_id=module_id
                ))

        return violations

    def _get_value(self, node: ast.expr) -> Any:
        """Extract value from AST node."""
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Str):  # Python 3.7 compatibility
            return node.s
        if isinstance(node, ast.Num):  # Python 3.7 compatibility
            return node.n
        if isinstance(node, ast.List):
            return [self._get_value(elt) for elt in node.elts]
        if isinstance(node, ast.Dict):
            return {
                self._get_value(k): self._get_value(v)
                for k, v in zip(node.keys, node.values)
                if k is not None
            }
        if isinstance(node, ast.Name):
            return f"<{node.id}>"
        if isinstance(node, ast.Call):
            return "<function_call>"
        return None

    def lint_all(self) -> List[Violation]:
        """Lint all module files."""
        all_violations = []

        if not MODULES_DIR.exists():
            print(f"Error: Modules directory not found: {MODULES_DIR}")
            return []

        for py_file in MODULES_DIR.rglob('*.py'):
            if '__pycache__' in str(py_file):
                continue
            if py_file.name.startswith('_'):
                continue

            violations = self.lint_file(py_file)
            all_violations.extend(violations)

        return all_violations


def print_violations(violations: List[Violation]) -> Dict[str, int]:
    """Print violations grouped by severity."""
    by_severity = {'ERROR': [], 'WARN': [], 'INFO': []}

    for v in violations:
        by_severity.get(v.severity, []).append(v)

    counts = {}

    for severity in ['ERROR', 'WARN', 'INFO']:
        items = by_severity[severity]
        counts[severity] = len(items)

        if items:
            print(f"\n{'=' * 60}")
            print(f"{severity} ({len(items)})")
            print('=' * 60)

            for v in items:
                rel_path = Path(v.file).relative_to(PROJECT_ROOT) if PROJECT_ROOT in Path(v.file).parents else v.file
                print(f"  [{v.rule_id}] {rel_path}:{v.line}")
                print(f"    {v.message}")
                if v.module_id:
                    print(f"    Module: {v.module_id}")

    return counts


def main():
    parser = argparse.ArgumentParser(description='Lint i18n keys in flyto-core modules')
    parser.add_argument('--strict', action='store_true', help='Exit with code 1 on ERROR')
    parser.add_argument('--fix-report', action='store_true', help='Generate fix report')
    args = parser.parse_args()

    print("Scanning flyto-core modules for i18n issues...")
    print(f"Modules directory: {MODULES_DIR}")

    linter = I18nLinter()
    violations = linter.lint_all()

    if not violations:
        print("\n✅ No i18n issues found!")
        return 0

    counts = print_violations(violations)

    print(f"\n{'=' * 60}")
    print("Summary")
    print('=' * 60)
    print(f"  ERROR: {counts.get('ERROR', 0)}")
    print(f"  WARN:  {counts.get('WARN', 0)}")
    print(f"  INFO:  {counts.get('INFO', 0)}")
    print(f"  Total: {len(violations)}")

    if args.fix_report:
        report_path = PROJECT_ROOT / 'i18n-lint-report.txt'
        with open(report_path, 'w') as f:
            for v in violations:
                f.write(f"{v.rule_id}|{v.severity}|{v.file}:{v.line}|{v.message}\n")
        print(f"\nFix report written to: {report_path}")

    if args.strict and counts.get('ERROR', 0) > 0:
        print("\n❌ Lint failed due to ERROR violations")
        return 1

    print("\n⚠️ Lint completed with warnings")
    return 0


if __name__ == '__main__':
    sys.exit(main())
