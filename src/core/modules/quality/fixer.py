"""
Fix Runner

Auto-fix infrastructure for fixable lint rules.
"""
import difflib
from abc import abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Type

from .types import ValidationIssue


@dataclass
class FixResult:
    """Result of applying a fix."""
    rule_id: str
    module_id: str
    file_path: str
    applied: bool
    original: str
    fixed: str
    diff: str = ""
    error: Optional[str] = None


class FixableRule(Protocol):
    """Protocol for rules that can auto-fix issues."""

    rule_id: str

    @classmethod
    def can_fix(cls, issue: ValidationIssue) -> bool:
        """Check if this rule can fix the given issue."""
        ...

    @classmethod
    def fix(
        cls,
        source_code: str,
        issue: ValidationIssue,
        metadata: Dict[str, Any],
    ) -> Optional[str]:
        """
        Apply fix to source code.

        Args:
            source_code: Original source code
            issue: The issue to fix
            metadata: Module metadata

        Returns:
            Fixed source code, or None if fix failed
        """
        ...


class FixRunner:
    """
    Runs fixable rules to auto-fix issues.

    Supports dry-run mode and generates unified diffs.
    """

    def __init__(
        self,
        fixable_rules: Optional[List[Type[FixableRule]]] = None,
        dry_run: bool = True,
    ):
        """
        Initialize fix runner.

        Args:
            fixable_rules: List of fixable rule classes
            dry_run: If True, don't write files (default)
        """
        self.fixable_rules = fixable_rules or []
        self.dry_run = dry_run
        self._rule_map: Dict[str, Type[FixableRule]] = {}

        # Build rule map for quick lookup
        for rule in self.fixable_rules:
            self._rule_map[rule.rule_id] = rule

    def run(
        self,
        issues: List[ValidationIssue],
        source_codes: Dict[str, str],
        file_paths: Dict[str, str],
        metadata: Dict[str, Dict[str, Any]],
    ) -> List[FixResult]:
        """
        Run fixes for all fixable issues.

        Args:
            issues: List of validation issues
            source_codes: Dict of module_id -> source code
            file_paths: Dict of module_id -> file path
            metadata: Dict of module_id -> metadata

        Returns:
            List of FixResult for each attempted fix
        """
        results: List[FixResult] = []

        # Group issues by module
        issues_by_module: Dict[str, List[ValidationIssue]] = {}
        for issue in issues:
            module_id = issue.module_id
            if module_id not in issues_by_module:
                issues_by_module[module_id] = []
            issues_by_module[module_id].append(issue)

        # Process each module
        for module_id, module_issues in issues_by_module.items():
            source = source_codes.get(module_id)
            file_path = file_paths.get(module_id, "")
            meta = metadata.get(module_id, {})

            if not source:
                continue

            current_source = source

            for issue in module_issues:
                rule_class = self._rule_map.get(issue.rule_id)

                if not rule_class:
                    continue

                if not rule_class.can_fix(issue):
                    continue

                try:
                    fixed = rule_class.fix(current_source, issue, meta)

                    if fixed and fixed != current_source:
                        diff = self._generate_diff(
                            current_source,
                            fixed,
                            file_path,
                        )

                        result = FixResult(
                            rule_id=issue.rule_id,
                            module_id=module_id,
                            file_path=file_path,
                            applied=not self.dry_run,
                            original=current_source,
                            fixed=fixed,
                            diff=diff,
                        )

                        if not self.dry_run and file_path:
                            Path(file_path).write_text(fixed, encoding="utf-8")
                            current_source = fixed

                        results.append(result)

                except Exception as e:
                    results.append(FixResult(
                        rule_id=issue.rule_id,
                        module_id=module_id,
                        file_path=file_path,
                        applied=False,
                        original=current_source,
                        fixed=current_source,
                        error=str(e),
                    ))

        return results

    def _generate_diff(
        self,
        original: str,
        fixed: str,
        file_path: str = "",
    ) -> str:
        """Generate unified diff between original and fixed."""
        original_lines = original.splitlines(keepends=True)
        fixed_lines = fixed.splitlines(keepends=True)

        diff = difflib.unified_diff(
            original_lines,
            fixed_lines,
            fromfile=f"a/{file_path}" if file_path else "a/original",
            tofile=f"b/{file_path}" if file_path else "b/fixed",
        )

        return "".join(diff)

    def generate_diff_report(self, results: List[FixResult]) -> str:
        """
        Generate a combined diff report from all fix results.

        Args:
            results: List of FixResult

        Returns:
            Combined diff report string
        """
        lines = []
        lines.append("# Auto-Fix Report")
        lines.append("")
        lines.append(f"Total fixes: {len(results)}")
        lines.append(f"Applied: {sum(1 for r in results if r.applied)}")
        lines.append(f"Dry-run: {sum(1 for r in results if not r.applied and not r.error)}")
        lines.append(f"Errors: {sum(1 for r in results if r.error)}")
        lines.append("")

        for result in results:
            lines.append(f"## {result.module_id} - {result.rule_id}")
            lines.append("")

            if result.error:
                lines.append(f"ERROR: {result.error}")
            elif result.diff:
                lines.append("```diff")
                lines.append(result.diff)
                lines.append("```")
            else:
                lines.append("No changes.")

            lines.append("")

        return "\n".join(lines)


def register_fixable_rule(rule_class: Type[FixableRule]) -> Type[FixableRule]:
    """Decorator to register a fixable rule."""
    # This is a placeholder for a global registry if needed
    return rule_class
