#!/usr/bin/env python3
"""
Module Return Pattern Analyzer

Scans all modules in flyto-core to identify return value patterns.
Generates a report showing which modules need standardization.

Usage:
    python scripts/analyze_module_returns.py [--category <category>] [--verbose]

Patterns detected:
- OK_PATTERN: Returns {"ok": True/False, ...}
- STATUS_PATTERN: Returns {"status": "success"/"error", ...}
- RAW_DATA: Returns raw data without wrapper
- MIXED: Uses multiple patterns

Design:
- Single responsibility: Only analyzes, doesn't modify
- No hardcoding: Patterns detected dynamically
"""
import argparse
import ast
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


@dataclass
class ReturnPattern:
    """Detected return pattern in a module."""
    pattern_type: str  # OK_PATTERN, STATUS_PATTERN, RAW_DATA, MIXED
    has_ok_true: bool = False
    has_ok_false: bool = False
    has_status_success: bool = False
    has_status_error: bool = False
    has_raw_return: bool = False
    return_statements: List[str] = field(default_factory=list)
    line_numbers: List[int] = field(default_factory=list)


@dataclass
class ModuleAnalysis:
    """Analysis result for a single module."""
    module_id: str
    file_path: str
    category: str
    pattern: ReturnPattern
    is_class_based: bool
    uses_base_success: bool = False
    uses_base_failure: bool = False
    needs_migration: bool = False
    migration_difficulty: str = "unknown"  # easy, medium, hard


class ReturnPatternVisitor(ast.NodeVisitor):
    """AST visitor to detect return patterns."""

    def __init__(self):
        self.patterns: List[Tuple[str, int, str]] = []  # (pattern_type, line, snippet)
        self.uses_base_success = False
        self.uses_base_failure = False

    def visit_Return(self, node):
        """Visit return statements."""
        if node.value is None:
            self.patterns.append(("NONE", node.lineno, "return"))
            return

        # Get source snippet
        snippet = ast.unparse(node.value) if hasattr(ast, 'unparse') else str(node.value)[:50]

        # Detect self.success() / self.failure()
        if isinstance(node.value, ast.Call):
            func = node.value.func
            if isinstance(func, ast.Attribute):
                if func.attr == 'success' and isinstance(func.value, ast.Name) and func.value.id == 'self':
                    self.uses_base_success = True
                    self.patterns.append(("BASE_SUCCESS", node.lineno, snippet))
                    return
                if func.attr == 'failure' and isinstance(func.value, ast.Name) and func.value.id == 'self':
                    self.uses_base_failure = True
                    self.patterns.append(("BASE_FAILURE", node.lineno, snippet))
                    return

        # Detect dict returns
        if isinstance(node.value, ast.Dict):
            keys = []
            for key in node.value.keys:
                if isinstance(key, ast.Constant):
                    keys.append(key.value)
                elif isinstance(key, ast.Str):
                    keys.append(key.s)

            if 'ok' in keys:
                # Check if ok is True or False
                for key, val in zip(node.value.keys, node.value.values):
                    key_name = key.value if isinstance(key, ast.Constant) else (key.s if isinstance(key, ast.Str) else None)
                    if key_name == 'ok':
                        if isinstance(val, ast.Constant) and val.value is True:
                            self.patterns.append(("OK_TRUE", node.lineno, snippet))
                        elif isinstance(val, ast.Constant) and val.value is False:
                            self.patterns.append(("OK_FALSE", node.lineno, snippet))
                        elif isinstance(val, ast.NameConstant):
                            if val.value is True:
                                self.patterns.append(("OK_TRUE", node.lineno, snippet))
                            elif val.value is False:
                                self.patterns.append(("OK_FALSE", node.lineno, snippet))
                        else:
                            self.patterns.append(("OK_DYNAMIC", node.lineno, snippet))
                        return

            if 'status' in keys:
                # Check status value
                for key, val in zip(node.value.keys, node.value.values):
                    key_name = key.value if isinstance(key, ast.Constant) else (key.s if isinstance(key, ast.Str) else None)
                    if key_name == 'status':
                        if isinstance(val, ast.Constant):
                            if val.value == 'success':
                                self.patterns.append(("STATUS_SUCCESS", node.lineno, snippet))
                            elif val.value == 'error':
                                self.patterns.append(("STATUS_ERROR", node.lineno, snippet))
                            else:
                                self.patterns.append(("STATUS_OTHER", node.lineno, snippet))
                        elif isinstance(val, ast.Str):
                            if val.s == 'success':
                                self.patterns.append(("STATUS_SUCCESS", node.lineno, snippet))
                            elif val.s == 'error':
                                self.patterns.append(("STATUS_ERROR", node.lineno, snippet))
                            else:
                                self.patterns.append(("STATUS_OTHER", node.lineno, snippet))
                        else:
                            self.patterns.append(("STATUS_DYNAMIC", node.lineno, snippet))
                        return

            # Raw dict without ok/status
            self.patterns.append(("RAW_DICT", node.lineno, snippet))
        else:
            # Non-dict return
            self.patterns.append(("RAW_OTHER", node.lineno, snippet))

        self.generic_visit(node)


def analyze_file(file_path: Path) -> Optional[ModuleAnalysis]:
    """Analyze a single module file."""
    try:
        source = file_path.read_text()
        tree = ast.parse(source)
    except (SyntaxError, UnicodeDecodeError) as e:
        print(f"  Warning: Could not parse {file_path}: {e}")
        return None

    # Find module_id from @register_module decorator
    module_id = None
    is_class_based = False

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Call):
                    func = decorator.func
                    if isinstance(func, ast.Name) and func.id == 'register_module':
                        is_class_based = True
                        # Extract module_id
                        if decorator.args:
                            arg = decorator.args[0]
                            if isinstance(arg, ast.Constant):
                                module_id = arg.value
                            elif isinstance(arg, ast.Str):
                                module_id = arg.s
                        for kw in decorator.keywords:
                            if kw.arg == 'module_id':
                                if isinstance(kw.value, ast.Constant):
                                    module_id = kw.value.value
                                elif isinstance(kw.value, ast.Str):
                                    module_id = kw.value.s

        elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Call):
                    func = decorator.func
                    if isinstance(func, ast.Name) and func.id == 'register_module':
                        # Extract module_id
                        if decorator.args:
                            arg = decorator.args[0]
                            if isinstance(arg, ast.Constant):
                                module_id = arg.value
                            elif isinstance(arg, ast.Str):
                                module_id = arg.s
                        for kw in decorator.keywords:
                            if kw.arg == 'module_id':
                                if isinstance(kw.value, ast.Constant):
                                    module_id = kw.value.value
                                elif isinstance(kw.value, ast.Str):
                                    module_id = kw.value.s

    if not module_id:
        return None

    # Find execute function/method and analyze returns
    visitor = ReturnPatternVisitor()

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Analyze execute method or decorated function
            if node.name == 'execute' or any(
                isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id == 'register_module'
                for d in node.decorator_list
            ):
                visitor.visit(node)

    # Determine overall pattern
    pattern_types = set(p[0] for p in visitor.patterns)

    pattern = ReturnPattern(
        pattern_type="UNKNOWN",
        has_ok_true="OK_TRUE" in pattern_types,
        has_ok_false="OK_FALSE" in pattern_types or "OK_DYNAMIC" in pattern_types,
        has_status_success="STATUS_SUCCESS" in pattern_types,
        has_status_error="STATUS_ERROR" in pattern_types or "STATUS_DYNAMIC" in pattern_types,
        has_raw_return="RAW_DICT" in pattern_types or "RAW_OTHER" in pattern_types,
        return_statements=[p[2][:80] for p in visitor.patterns],
        line_numbers=[p[1] for p in visitor.patterns]
    )

    # Classify pattern type
    ok_patterns = {"OK_TRUE", "OK_FALSE", "OK_DYNAMIC", "BASE_SUCCESS", "BASE_FAILURE"}
    status_patterns = {"STATUS_SUCCESS", "STATUS_ERROR", "STATUS_OTHER", "STATUS_DYNAMIC"}
    raw_patterns = {"RAW_DICT", "RAW_OTHER", "NONE"}
    base_patterns = {"BASE_SUCCESS", "BASE_FAILURE"}

    has_ok = bool(pattern_types & ok_patterns)
    has_status = bool(pattern_types & status_patterns)
    has_raw = bool(pattern_types & raw_patterns)
    has_base = bool(pattern_types & base_patterns)

    if has_base and not (has_ok or has_status or has_raw):
        pattern.pattern_type = "BASE_HELPERS"
    elif has_ok and not has_status and not has_raw:
        pattern.pattern_type = "OK_PATTERN"
    elif has_status and not has_ok and not has_raw:
        pattern.pattern_type = "STATUS_PATTERN"
    elif has_raw and not has_ok and not has_status:
        pattern.pattern_type = "RAW_DATA"
    elif has_ok or has_status:
        pattern.pattern_type = "MIXED"
    else:
        pattern.pattern_type = "UNKNOWN"

    # Determine migration difficulty
    if pattern.pattern_type in ("OK_PATTERN", "BASE_HELPERS"):
        difficulty = "none"  # Already standardized
        needs_migration = False
    elif pattern.pattern_type == "RAW_DATA" and len(visitor.patterns) <= 3:
        difficulty = "easy"
        needs_migration = True
    elif pattern.pattern_type == "STATUS_PATTERN":
        difficulty = "medium"
        needs_migration = True
    elif pattern.pattern_type == "MIXED":
        difficulty = "hard"
        needs_migration = True
    else:
        difficulty = "unknown"
        needs_migration = True

    # Extract category from module_id
    category = module_id.split('.')[0] if '.' in module_id else "unknown"

    return ModuleAnalysis(
        module_id=module_id,
        file_path=str(file_path),
        category=category,
        pattern=pattern,
        is_class_based=is_class_based,
        uses_base_success=visitor.uses_base_success,
        uses_base_failure=visitor.uses_base_failure,
        needs_migration=needs_migration,
        migration_difficulty=difficulty
    )


def analyze_directory(base_path: Path, category_filter: Optional[str] = None) -> List[ModuleAnalysis]:
    """Analyze all modules in a directory."""
    results = []

    atomic_path = base_path / "src" / "core" / "modules" / "atomic"
    if not atomic_path.exists():
        print(f"Error: {atomic_path} does not exist")
        return results

    for category_dir in sorted(atomic_path.iterdir()):
        if not category_dir.is_dir() or category_dir.name.startswith('_'):
            continue

        if category_filter and category_dir.name != category_filter:
            continue

        for py_file in sorted(category_dir.glob("*.py")):
            if py_file.name.startswith('_'):
                continue

            analysis = analyze_file(py_file)
            if analysis:
                results.append(analysis)

    return results


def print_report(results: List[ModuleAnalysis], verbose: bool = False):
    """Print analysis report."""
    print("\n" + "=" * 70)
    print("MODULE RETURN PATTERN ANALYSIS REPORT")
    print("=" * 70)

    # Summary by pattern type
    by_pattern: Dict[str, List[ModuleAnalysis]] = defaultdict(list)
    for r in results:
        by_pattern[r.pattern.pattern_type].append(r)

    print("\n## Summary by Pattern Type\n")
    for pattern_type in ["OK_PATTERN", "BASE_HELPERS", "RAW_DATA", "STATUS_PATTERN", "MIXED", "UNKNOWN"]:
        modules = by_pattern.get(pattern_type, [])
        status = "OK" if pattern_type in ("OK_PATTERN", "BASE_HELPERS") else "NEEDS MIGRATION"
        print(f"  {pattern_type:20s}: {len(modules):3d} modules [{status}]")

    # Summary by category
    by_category: Dict[str, List[ModuleAnalysis]] = defaultdict(list)
    for r in results:
        by_category[r.category].append(r)

    print("\n## Summary by Category\n")
    for category in sorted(by_category.keys()):
        modules = by_category[category]
        needs_migration = sum(1 for m in modules if m.needs_migration)
        total = len(modules)
        if needs_migration > 0:
            print(f"  {category:20s}: {needs_migration:3d}/{total:3d} need migration")

    # Migration difficulty summary
    print("\n## Migration Difficulty\n")
    by_difficulty: Dict[str, List[ModuleAnalysis]] = defaultdict(list)
    for r in results:
        if r.needs_migration:
            by_difficulty[r.migration_difficulty].append(r)

    for difficulty in ["easy", "medium", "hard", "unknown"]:
        modules = by_difficulty.get(difficulty, [])
        if modules:
            print(f"  {difficulty:10s}: {len(modules):3d} modules")

    # Detailed report
    if verbose:
        print("\n## Detailed Module List\n")
        for r in sorted(results, key=lambda x: (x.category, x.module_id)):
            if not r.needs_migration:
                continue
            print(f"\n### {r.module_id}")
            print(f"  File: {r.file_path}")
            print(f"  Pattern: {r.pattern.pattern_type}")
            print(f"  Difficulty: {r.migration_difficulty}")
            print(f"  Class-based: {r.is_class_based}")
            if r.pattern.return_statements:
                print(f"  Returns ({len(r.pattern.return_statements)}):")
                for stmt, line in zip(r.pattern.return_statements[:5], r.pattern.line_numbers[:5]):
                    print(f"    L{line}: {stmt}")

    # Priority migration list
    print("\n## Priority Migration List (Easy)\n")
    easy_modules = [r for r in results if r.migration_difficulty == "easy"]
    for category in sorted(set(r.category for r in easy_modules)):
        modules = [r for r in easy_modules if r.category == category]
        print(f"\n  {category}/ ({len(modules)} modules):")
        for m in modules:
            print(f"    - {m.module_id}")

    print("\n" + "=" * 70)
    print(f"Total: {len(results)} modules analyzed")
    print(f"Need migration: {sum(1 for r in results if r.needs_migration)}")
    print("=" * 70 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Analyze module return patterns")
    parser.add_argument("--category", "-c", help="Filter by category")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed report")
    parser.add_argument("--path", "-p", default=".", help="Path to flyto-core")
    args = parser.parse_args()

    base_path = Path(args.path)
    if not (base_path / "src" / "core").exists():
        # Try parent
        base_path = Path(__file__).parent.parent

    print(f"Analyzing modules in: {base_path}")
    results = analyze_directory(base_path, args.category)

    if not results:
        print("No modules found!")
        return 1

    print_report(results, args.verbose)
    return 0


if __name__ == "__main__":
    sys.exit(main())
