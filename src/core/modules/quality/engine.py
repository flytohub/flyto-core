"""
Validation Engine

Orchestrates all validation rules and produces unified reports.
Implements 3-stage execution: Metadata -> AST -> Security
"""

import ast
import logging
import pkgutil
import importlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Type

from .types import (
    Severity,
    StrictLevel,
    RuleStage,
    ValidationIssue,
    ValidationReport,
    AggregateReport,
)
from .rules import get_all_rules, get_rules_by_category, get_rules_by_stage, BaseRule
from .detectors import verify_params_usage, verify_return_schema
from .policy import SeverityPolicy, get_policy, CI_POLICY
from .baseline import Baseline

logger = logging.getLogger(__name__)


class ValidationEngine:
    """
    Central validation engine that runs all rules against modules.

    Features:
    - 3-stage execution: Metadata -> AST -> Security
    - Baseline exemptions support
    - SeverityPolicy for gate-level control
    - Stability-aware severity adjustment
    - AST-based detectors for params/return verification
    """

    def __init__(
        self,
        strict_level: StrictLevel = StrictLevel.DEFAULT,
        enabled_categories: Optional[Set[str]] = None,
        disabled_rules: Optional[Set[str]] = None,
        policy: Optional[SeverityPolicy] = None,
        baseline: Optional[Baseline] = None,
    ):
        """
        Initialize validation engine.

        Args:
            strict_level: Strictness level for validation
            enabled_categories: Only run rules from these categories (None = all)
            disabled_rules: Skip these rule IDs
            policy: SeverityPolicy for gate-level blocking decisions
            baseline: Baseline for rule exemptions
        """
        self.strict_level = strict_level
        self.enabled_categories = enabled_categories
        self.disabled_rules = disabled_rules or set()
        self.policy = policy or CI_POLICY
        self.baseline = baseline or Baseline()

    def validate_module(
        self,
        module_id: str,
        metadata: Dict[str, Any],
        source_code: Optional[str] = None,
        file_path: Optional[str] = None,
    ) -> ValidationReport:
        """
        Validate a single module using 3-stage execution.

        Stage 1: METADATA - Fast checks on registry metadata only
        Stage 2: AST - Parse source code and run AST-based rules
        Stage 3: SECURITY - Deep security scans

        Early exit on FATAL errors in Stage 1.

        Args:
            module_id: Module identifier
            metadata: Module metadata dict
            source_code: Optional Python source code
            file_path: Optional file path for reporting

        Returns:
            ValidationReport with all issues
        """
        issues: List[ValidationIssue] = []
        ast_tree = None

        # Stage 1: METADATA rules (fast, no AST needed)
        stage1_issues = self._run_stage(
            stage=RuleStage.METADATA,
            module_id=module_id,
            metadata=metadata,
            source_code=None,  # Don't pass source to metadata rules
            ast_tree=None,
            file_path=file_path,
        )
        issues.extend(stage1_issues)

        # Early exit if FATAL error in Stage 1
        if self._has_fatal(stage1_issues):
            return self._create_report(module_id, issues, metadata)

        # Stage 2: AST rules (requires source code parsing)
        if source_code:
            try:
                ast_tree = ast.parse(source_code)
            except SyntaxError as e:
                issues.append(ValidationIssue(
                    rule_id="CORE-AST-000",
                    severity=Severity.FATAL,
                    message=f"Syntax error: {e}",
                    module_id=module_id,
                    file=file_path or "",
                    line=e.lineno or 0,
                    col=e.offset or 0,
                ))
                return self._create_report(module_id, issues, metadata)

            stage2_issues = self._run_stage(
                stage=RuleStage.AST,
                module_id=module_id,
                metadata=metadata,
                source_code=source_code,
                ast_tree=ast_tree,
                file_path=file_path,
            )
            issues.extend(stage2_issues)

            # Run AST detectors for schema verification
            params_schema = metadata.get("params_schema", {})
            output_schema = metadata.get("output_schema", {})

            if params_schema:
                issues.extend(verify_params_usage(
                    source_code=source_code,
                    params_schema=params_schema,
                    module_id=module_id,
                    ast_tree=ast_tree,
                ))

            if output_schema:
                issues.extend(verify_return_schema(
                    source_code=source_code,
                    output_schema=output_schema,
                    module_id=module_id,
                    ast_tree=ast_tree,
                ))

        # Stage 3: SECURITY rules (deep security scan)
        if source_code:
            stage3_issues = self._run_stage(
                stage=RuleStage.SECURITY,
                module_id=module_id,
                metadata=metadata,
                source_code=source_code,
                ast_tree=ast_tree,
                file_path=file_path,
            )
            issues.extend(stage3_issues)

        # Apply baseline exemptions
        issues = self._apply_baseline(issues, module_id)

        # Apply strict level adjustments
        issues = self._apply_strict_level(issues, metadata)

        return self._create_report(module_id, issues, metadata)

    def _run_stage(
        self,
        stage: RuleStage,
        module_id: str,
        metadata: Dict[str, Any],
        source_code: Optional[str],
        ast_tree: Optional[ast.AST],
        file_path: Optional[str],
    ) -> List[ValidationIssue]:
        """Run all rules for a specific stage."""
        issues: List[ValidationIssue] = []
        rules = get_rules_by_stage(stage)

        for rule in rules:
            # Skip disabled rules
            if rule.rule_id in self.disabled_rules:
                continue

            # Filter by category if specified
            if self.enabled_categories and rule.category not in self.enabled_categories:
                continue

            try:
                rule_issues = rule.validate(
                    module_id=module_id,
                    metadata=metadata,
                    source_code=source_code,
                    ast_tree=ast_tree,
                )

                # Add file path to issues
                for issue in rule_issues:
                    if file_path and not issue.file:
                        issue.file = file_path

                issues.extend(rule_issues)

            except Exception as e:
                logger.warning(f"Rule {rule.rule_id} failed on {module_id}: {e}")
                issues.append(ValidationIssue(
                    rule_id=rule.rule_id,
                    severity=Severity.WARN,
                    message=f"Rule execution failed: {str(e)}",
                    module_id=module_id,
                    file=file_path or "",
                ))

        return issues

    def _has_fatal(self, issues: List[ValidationIssue]) -> bool:
        """Check if any issue is FATAL severity."""
        return any(i.severity == Severity.FATAL for i in issues)

    def _apply_baseline(
        self,
        issues: List[ValidationIssue],
        module_id: str,
    ) -> List[ValidationIssue]:
        """Apply baseline exemptions to filter out exempt issues."""
        return [
            issue for issue in issues
            if not self.baseline.is_exempt(module_id, issue.rule_id)
        ]

    def _create_report(
        self,
        module_id: str,
        issues: List[ValidationIssue],
        metadata: Dict[str, Any],
    ) -> ValidationReport:
        """Create a ValidationReport from issues."""
        return ValidationReport(
            module_id=module_id,
            issues=issues,
            metadata=metadata,
        )

    def validate_all(
        self,
        modules: Dict[str, Dict[str, Any]],
        source_codes: Optional[Dict[str, str]] = None,
        file_paths: Optional[Dict[str, str]] = None,
    ) -> AggregateReport:
        """
        Validate multiple modules.

        Args:
            modules: Dict of module_id -> metadata
            source_codes: Optional dict of module_id -> source code
            file_paths: Optional dict of module_id -> file path

        Returns:
            AggregateReport with all results
        """
        source_codes = source_codes or {}
        file_paths = file_paths or {}

        reports = []
        for module_id, metadata in modules.items():
            report = self.validate_module(
                module_id=module_id,
                metadata=metadata,
                source_code=source_codes.get(module_id),
                file_path=file_paths.get(module_id),
            )
            reports.append(report)

        return AggregateReport(reports=reports, strict_level=self.strict_level)

    def _apply_strict_level(
        self,
        issues: List[ValidationIssue],
        metadata: Dict[str, Any],
    ) -> List[ValidationIssue]:
        """Apply strict level adjustments to issues."""
        stability = metadata.get("stability", "stable")

        adjusted = []
        for issue in issues:
            # Make a copy to avoid mutating original
            new_issue = ValidationIssue(
                rule_id=issue.rule_id,
                severity=issue.severity,
                message=issue.message,
                module_id=issue.module_id,
                file=issue.file,
                line=issue.line,
                col=issue.col,
                suggestion=issue.suggestion,
            )

            # Apply strict level upgrades
            if self.strict_level == StrictLevel.ALL:
                # Upgrade all WARN to ERROR
                if new_issue.severity == Severity.WARN:
                    new_issue.severity = Severity.ERROR

            elif self.strict_level == StrictLevel.STABLE:
                # Strict for stable modules only
                if stability == "stable" and new_issue.severity == Severity.WARN:
                    new_issue.severity = Severity.ERROR

            elif self.strict_level == StrictLevel.RELEASE:
                # Everything is strict
                if new_issue.severity == Severity.WARN:
                    new_issue.severity = Severity.ERROR
                if new_issue.severity == Severity.INFO:
                    new_issue.severity = Severity.WARN

            elif self.strict_level == StrictLevel.TIMEOUT:
                # Upgrade timeout-related issues
                if "timeout" in new_issue.rule_id.lower() or "timeout" in new_issue.message.lower():
                    if new_issue.severity == Severity.WARN:
                        new_issue.severity = Severity.ERROR

            adjusted.append(new_issue)

        return adjusted

    def _check_passed(self, issues: List[ValidationIssue]) -> bool:
        """Check if validation passed based on issue severities."""
        for issue in issues:
            if issue.severity in (Severity.ERROR, Severity.BLOCKER, Severity.FATAL):
                return False
        return True


def discover_modules(
    base_path: str = "src/core/modules/atomic",
    prefix: str = "core.modules.atomic",
) -> Dict[str, Dict[str, Any]]:
    """
    Auto-discover all modules using pkgutil.

    Args:
        base_path: Base path to search for modules
        prefix: Module prefix for imports

    Returns:
        Dict of module_id -> metadata
    """
    from core.modules.registry import ModuleRegistry

    discovered = {}

    # Walk through all packages
    path = Path(base_path)
    if not path.exists():
        logger.warning(f"Base path {base_path} does not exist")
        return discovered

    for importer, modname, ispkg in pkgutil.walk_packages(
        path=[str(path)],
        prefix=f"{prefix}.",
    ):
        try:
            # Import the module to trigger registration
            importlib.import_module(modname)
        except ImportError as e:
            logger.warning(f"Failed to import {modname}: {e}")
        except Exception as e:
            logger.warning(f"Error importing {modname}: {e}")

    # Get all registered modules
    discovered = ModuleRegistry.get_all_metadata()

    return discovered


def validate_single_file(
    file_path: str,
    strict_level: StrictLevel = StrictLevel.DEFAULT,
) -> ValidationReport:
    """
    Validate a single Python file.

    Args:
        file_path: Path to Python file
        strict_level: Strictness level

    Returns:
        ValidationReport for the file
    """
    path = Path(file_path)

    if not path.exists():
        return ValidationReport(
            module_id=path.stem,
            issues=[ValidationIssue(
                rule_id="CORE-FILE-001",
                severity=Severity.FATAL,
                message=f"File not found: {file_path}",
                module_id=path.stem,
                file=file_path,
            )],
        )

    source_code = path.read_text(encoding="utf-8")

    # Try to extract metadata from decorators
    metadata = _extract_metadata_from_source(source_code, path.stem)

    engine = ValidationEngine(strict_level=strict_level)
    return engine.validate_module(
        module_id=metadata.get("module_id", path.stem),
        metadata=metadata,
        source_code=source_code,
        file_path=file_path,
    )


def _extract_metadata_from_source(source_code: str, default_id: str) -> Dict[str, Any]:
    """
    Extract metadata from source code by parsing decorators.

    This is a simplified extraction - real metadata comes from registry.
    """
    metadata = {
        "module_id": default_id,
        "stability": "stable",
    }

    try:
        tree = ast.parse(source_code)

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                # Look for class attributes
                for item in node.body:
                    if isinstance(item, ast.Assign):
                        for target in item.targets:
                            if isinstance(target, ast.Name):
                                if target.id == "module_id" and isinstance(item.value, ast.Constant):
                                    metadata["module_id"] = item.value.value
                                elif target.id == "stability" and isinstance(item.value, ast.Constant):
                                    metadata["stability"] = item.value.value

    except SyntaxError:
        pass

    return metadata


# Convenience function for CLI
def run_validation(
    modules: Optional[Dict[str, Dict[str, Any]]] = None,
    source_codes: Optional[Dict[str, str]] = None,
    file_paths: Optional[Dict[str, str]] = None,
    strict_level: StrictLevel = StrictLevel.DEFAULT,
    auto_discover: bool = True,
) -> AggregateReport:
    """
    Run full validation.

    Args:
        modules: Module metadata dict (or None for auto-discovery)
        source_codes: Source code dict
        file_paths: File paths dict
        strict_level: Strictness level
        auto_discover: Whether to auto-discover modules

    Returns:
        AggregateReport with all results
    """
    if modules is None and auto_discover:
        modules = discover_modules()

    if not modules:
        return AggregateReport(
            total_modules=0,
            passed_modules=0,
            failed_modules=0,
            total_issues=0,
            issues_by_severity={},
            issues_by_category={},
            reports=[],
        )

    engine = ValidationEngine(strict_level=strict_level)
    return engine.validate_all(
        modules=modules,
        source_codes=source_codes,
        file_paths=file_paths,
    )
