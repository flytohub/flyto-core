"""
Module Quality Validator - Code quality checks integrated with @register_module

Validates actual code quality (not just metadata) at registration time.
This ensures "good decorator != bad code".

Validation Rules:
    Q001: AST syntax must be valid
    Q002: No print() statements allowed (use logging)
    Q003: No Chinese characters in identifiers (function/class/variable/param names)
    Q004: Class/function must have docstring
    Q005: execute() method must exist and be async
    Q006: validate_params() method must exist
    Q007: params_schema should be defined if module has parameters
    Q008: output_schema must be defined
    Q009: Methods should have return type hints
    Q010: Cyclomatic complexity should be reasonable
    Q011: No unused imports
    Q012: Function length should not exceed 50 lines
    Q013: params_schema fields should have description
    Q014: String params should have placeholder
    Q015: input_types/output_types should be defined
"""

import ast
import inspect
import re
import logging
from typing import List, Dict, Any, Optional, Type
from dataclasses import dataclass, field

from .validation_types import (
    ValidationMode,
    Severity,
    ValidationIssue,
    get_validation_mode,
    should_block,
)

logger = logging.getLogger(__name__)


# Chinese character pattern (CJK Unified Ideographs)
CHINESE_PATTERN = re.compile(r'[\u4e00-\u9fff]')


@dataclass
class QualityReport:
    """Complete quality validation report for a module."""
    module_id: str
    issues: List[ValidationIssue] = field(default_factory=list)
    source_file: Optional[str] = None

    @property
    def errors(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == Severity.ERROR]

    @property
    def warnings(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == Severity.WARNING]

    def has_blocking_issues(self, mode: ValidationMode, stability: str = "stable") -> bool:
        """Check if any issue should block based on mode and stability."""
        return any(should_block(i.severity, mode, stability) for i in self.issues)


class ModuleQualityValidator:
    """
    Validates module code quality at registration time.

    Usage:
        validator = ModuleQualityValidator()
        report = validator.validate(module_class, module_id, metadata)
    """

    def __init__(
        self,
        max_complexity: int = 15,
        skip_rules: Optional[List[str]] = None,
        disabled_rules: Optional[List[str]] = None,
    ):
        """
        Initialize validator.

        Args:
            max_complexity: Maximum allowed cyclomatic complexity
            skip_rules: List of rule IDs to skip (e.g., ['Q009', 'Q010'])
            disabled_rules: List of user-disabled rules (merged with skip_rules)
        """
        self.max_complexity = max_complexity

        # Merge skip_rules and disabled_rules
        all_skipped = set(skip_rules or []) | set(disabled_rules or [])

        # Never skip mandatory rules
        from .rule_config import get_mandatory_rules
        mandatory = get_mandatory_rules()
        self.skip_rules = all_skipped - mandatory

    def validate(
        self,
        module_class: Type,
        module_id: str,
        metadata: Dict[str, Any],
        original_func: Optional[Any] = None,
    ) -> QualityReport:
        """
        Validate a module class for quality issues.

        Args:
            module_class: The module class to validate
            module_id: Module identifier
            metadata: Module metadata from @register_module
            original_func: For function-based modules, the original function

        Returns:
            QualityReport with all issues found
        """
        issues: List[ValidationIssue] = []
        is_function_based = original_func is not None

        # Get source information
        target = original_func if is_function_based else module_class

        try:
            source_file = inspect.getfile(target)
            source_code = inspect.getsource(target)
        except (TypeError, OSError) as e:
            logger.debug(f"Cannot get source for {module_id}: {e}")
            source_file = None
            source_code = None

        # Run all validations
        if source_code:
            issues.extend(self._check_ast_syntax(source_code, module_id))
            issues.extend(self._check_no_print(source_code, module_id))
            issues.extend(self._check_no_chinese_identifiers(source_code, module_id))
            issues.extend(self._check_complexity(source_code, module_id))
            issues.extend(self._check_unused_imports(source_code, module_id))
            issues.extend(self._check_function_length(source_code, module_id))

        # Type-specific checks
        if is_function_based:
            issues.extend(self._check_function_docstring(original_func, module_id))
            issues.extend(self._check_function_is_async(original_func, module_id))
        else:
            issues.extend(self._check_class_docstring(module_class, module_id))
            issues.extend(self._check_execute_method(module_class, module_id))
            issues.extend(self._check_validate_params_method(module_class, module_id))
            issues.extend(self._check_type_hints(module_class, module_id))

        # Schema checks
        issues.extend(self._check_schemas(metadata, module_id))

        # Schema quality checks (Q013-Q015)
        issues.extend(self._check_params_schema_quality(metadata, module_id))
        issues.extend(self._check_types_defined(metadata, module_id))

        # Filter out skipped rules
        issues = [i for i in issues if i.rule_id not in self.skip_rules]

        return QualityReport(
            module_id=module_id,
            issues=issues,
            source_file=source_file,
        )

    # =========================================================================
    # Q001: AST Syntax
    # =========================================================================

    def _check_ast_syntax(self, source: str, module_id: str) -> List[ValidationIssue]:
        """Q001: Validate AST syntax."""
        try:
            ast.parse(source)
            return []
        except SyntaxError as e:
            return [ValidationIssue(
                rule_id="Q001",
                severity=Severity.ERROR,
                message=f"Syntax error: {e.msg}",
                line=e.lineno,
                hint="Fix the syntax error before registration",
            )]

    # =========================================================================
    # Q002: No print() statements
    # =========================================================================

    def _check_no_print(self, source: str, module_id: str) -> List[ValidationIssue]:
        """Q002: No print() statements allowed."""
        issues = []
        try:
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    func = node.func
                    if isinstance(func, ast.Name) and func.id == 'print':
                        issues.append(ValidationIssue(
                            rule_id="Q002",
                            severity=Severity.ERROR,
                            message="print() statement found",
                            line=node.lineno,
                            hint="Use logging.debug/info/warning/error instead",
                            fixable=True,
                        ))
        except SyntaxError:
            pass
        return issues

    # =========================================================================
    # Q003: No Chinese in identifiers (FIXED: comprehensive check)
    # =========================================================================

    def _check_no_chinese_identifiers(self, source: str, module_id: str) -> List[ValidationIssue]:
        """Q003: No Chinese characters in identifiers."""
        issues = []
        try:
            tree = ast.parse(source)
            for node in ast.walk(tree):
                # Function/method names
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if CHINESE_PATTERN.search(node.name):
                        issues.append(self._chinese_issue("function name", node.name, node.lineno))
                    # Function arguments
                    for arg in node.args.args + node.args.posonlyargs + node.args.kwonlyargs:
                        if CHINESE_PATTERN.search(arg.arg):
                            issues.append(self._chinese_issue("parameter", arg.arg, node.lineno))
                    if node.args.vararg and CHINESE_PATTERN.search(node.args.vararg.arg):
                        issues.append(self._chinese_issue("*args parameter", node.args.vararg.arg, node.lineno))
                    if node.args.kwarg and CHINESE_PATTERN.search(node.args.kwarg.arg):
                        issues.append(self._chinese_issue("**kwargs parameter", node.args.kwarg.arg, node.lineno))

                # Class names
                elif isinstance(node, ast.ClassDef):
                    if CHINESE_PATTERN.search(node.name):
                        issues.append(self._chinese_issue("class name", node.name, node.lineno))

                # Variable names (assignments)
                elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                    if CHINESE_PATTERN.search(node.id):
                        issues.append(self._chinese_issue("variable name", node.id, node.lineno))

                # Attribute access (obj.attr)
                elif isinstance(node, ast.Attribute):
                    if CHINESE_PATTERN.search(node.attr):
                        issues.append(self._chinese_issue("attribute name", node.attr, node.lineno))

                # Keyword arguments in calls (func(key=value))
                elif isinstance(node, ast.keyword) and node.arg:
                    if CHINESE_PATTERN.search(node.arg):
                        issues.append(self._chinese_issue("keyword argument", node.arg, node.lineno))

                # Global/Nonlocal declarations
                elif isinstance(node, (ast.Global, ast.Nonlocal)):
                    for name in node.names:
                        if CHINESE_PATTERN.search(name):
                            issues.append(self._chinese_issue("global/nonlocal name", name, node.lineno))

                # Import aliases
                elif isinstance(node, ast.alias):
                    if node.asname and CHINESE_PATTERN.search(node.asname):
                        issues.append(self._chinese_issue("import alias", node.asname, node.lineno))

        except SyntaxError:
            pass
        return issues

    def _chinese_issue(self, kind: str, name: str, line: int) -> ValidationIssue:
        return ValidationIssue(
            rule_id="Q003",
            severity=Severity.ERROR,
            message=f"Chinese characters in {kind}: {name}",
            line=line,
            hint="Use English for all identifiers",
        )

    # =========================================================================
    # Q004: Docstring required
    # =========================================================================

    def _check_class_docstring(self, module_class: Type, module_id: str) -> List[ValidationIssue]:
        """Q004: Class must have docstring."""
        if not module_class.__doc__ or not module_class.__doc__.strip():
            return [ValidationIssue(
                rule_id="Q004",
                severity=Severity.ERROR,
                message="Module class missing docstring",
                hint="Add a docstring describing what the module does",
            )]
        return []

    def _check_function_docstring(self, func: Any, module_id: str) -> List[ValidationIssue]:
        """Q004: Function must have docstring."""
        if not func.__doc__ or not func.__doc__.strip():
            return [ValidationIssue(
                rule_id="Q004",
                severity=Severity.ERROR,
                message="Module function missing docstring",
                hint="Add a docstring describing what the module does",
            )]
        return []

    # =========================================================================
    # Q005: execute() must be async
    # =========================================================================

    def _check_execute_method(self, module_class: Type, module_id: str) -> List[ValidationIssue]:
        """Q005: execute() method must exist and be async."""
        issues = []

        if not hasattr(module_class, 'execute'):
            issues.append(ValidationIssue(
                rule_id="Q005",
                severity=Severity.ERROR,
                message="Missing execute() method",
                hint="Add async def execute(self) -> Dict[str, Any]",
            ))
            return issues

        execute = getattr(module_class, 'execute')
        if not inspect.iscoroutinefunction(execute):
            issues.append(ValidationIssue(
                rule_id="Q005",
                severity=Severity.ERROR,
                message="execute() must be async (async def execute)",
                hint="Change 'def execute' to 'async def execute'",
            ))

        return issues

    def _check_function_is_async(self, func: Any, module_id: str) -> List[ValidationIssue]:
        """Q005: Function-based module must be async."""
        if not inspect.iscoroutinefunction(func):
            return [ValidationIssue(
                rule_id="Q005",
                severity=Severity.ERROR,
                message="Module function must be async (async def)",
                hint="Change 'def func_name(context)' to 'async def func_name(context)'",
            )]
        return []

    # =========================================================================
    # Q006: validate_params() must exist
    # =========================================================================

    def _check_validate_params_method(self, module_class: Type, module_id: str) -> List[ValidationIssue]:
        """Q006: validate_params() method must exist."""
        if not hasattr(module_class, 'validate_params'):
            return [ValidationIssue(
                rule_id="Q006",
                severity=Severity.ERROR,
                message="Missing validate_params() method",
                hint="Add def validate_params(self) -> None",
            )]
        return []

    # =========================================================================
    # Q007/Q008: Schema validation
    # =========================================================================

    def _check_schemas(self, metadata: Dict[str, Any], module_id: str) -> List[ValidationIssue]:
        """Q007/Q008: Schema completeness."""
        issues = []

        params_schema = metadata.get('params_schema')
        output_schema = metadata.get('output_schema')

        # Q007: params_schema - only warn if module likely has params
        # Check if there are required params or non-empty schema
        if not params_schema:
            # Only warn if category suggests params are expected
            category = metadata.get('category', '')
            # Most categories need params, except flow control
            if category not in ('flow', 'meta', 'utility'):
                issues.append(ValidationIssue(
                    rule_id="Q007",
                    severity=Severity.WARNING,
                    message="Missing params_schema",
                    hint="Define params_schema in @register_module if module accepts parameters",
                ))

        # Q008: output_schema is required
        if not output_schema:
            issues.append(ValidationIssue(
                rule_id="Q008",
                severity=Severity.ERROR,
                message="Missing output_schema",
                hint="Define output_schema in @register_module to describe return value",
            ))

        return issues

    # =========================================================================
    # Q009: Type hints
    # =========================================================================

    def _check_type_hints(self, module_class: Type, module_id: str) -> List[ValidationIssue]:
        """Q009: Methods should have return type hints."""
        issues = []

        for method_name in ['execute', 'validate_params']:
            method = getattr(module_class, method_name, None)
            if method:
                hints = getattr(method, '__annotations__', {})
                if 'return' not in hints:
                    issues.append(ValidationIssue(
                        rule_id="Q009",
                        severity=Severity.WARNING,
                        message=f"{method_name}() missing return type hint",
                        hint="Add -> Dict[str, Any] for execute(), -> None for validate_params()",
                    ))

        return issues

    # =========================================================================
    # Q010: Complexity (FIXED: BoolOp handling)
    # =========================================================================

    def _check_complexity(self, source: str, module_id: str) -> List[ValidationIssue]:
        """Q010: Cyclomatic complexity should be reasonable."""
        issues = []
        try:
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    complexity = self._calculate_complexity(node)
                    if complexity > self.max_complexity:
                        issues.append(ValidationIssue(
                            rule_id="Q010",
                            severity=Severity.WARNING,
                            message=f"{node.name}() has high complexity ({complexity} > {self.max_complexity})",
                            line=node.lineno,
                            hint="Consider breaking into smaller functions",
                        ))
        except SyntaxError:
            pass
        return issues

    def _calculate_complexity(self, node: ast.AST) -> int:
        """
        Calculate cyclomatic complexity of a function.

        Complexity starts at 1 and increases for each decision point.
        """
        complexity = 1
        for child in ast.walk(node):
            # Conditionals
            if isinstance(child, (ast.If, ast.IfExp)):
                complexity += 1
            # Loops
            elif isinstance(child, (ast.For, ast.While, ast.AsyncFor)):
                complexity += 1
            # Exception handlers
            elif isinstance(child, ast.ExceptHandler):
                complexity += 1
            # Boolean operators (FIXED: check BoolOp, not And/Or directly)
            elif isinstance(child, ast.BoolOp):
                # Each additional value in BoolOp adds complexity
                # e.g., a and b and c has 2 decision points
                complexity += len(child.values) - 1
            # Comprehensions
            elif isinstance(child, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                complexity += 1
            # Assert
            elif isinstance(child, ast.Assert):
                complexity += 1
            # With (context managers)
            elif isinstance(child, (ast.With, ast.AsyncWith)):
                complexity += 1
        return complexity

    # =========================================================================
    # Q011: Unused imports
    # =========================================================================

    def _check_unused_imports(self, source: str, module_id: str) -> List[ValidationIssue]:
        """Q011: Detect unused imports."""
        issues = []
        try:
            tree = ast.parse(source)

            # Collect all imported names
            imported_names = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imported_names.add(alias.asname or alias.name.split('.')[0])
                elif isinstance(node, ast.ImportFrom):
                    for alias in node.names:
                        if alias.name != '*':
                            imported_names.add(alias.asname or alias.name)

            # Collect all used names
            used_names = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                    used_names.add(node.id)
                elif isinstance(node, ast.Attribute):
                    # obj.attr - obj is used
                    if isinstance(node.value, ast.Name):
                        used_names.add(node.value.id)

            # Find unused imports
            unused = imported_names - used_names
            for name in unused:
                issues.append(ValidationIssue(
                    rule_id="Q011",
                    severity=Severity.WARNING,
                    message=f"Unused import: {name}",
                    hint=f"Remove 'import {name}' or use it",
                    fixable=True,
                ))
        except SyntaxError:
            pass
        return issues

    # =========================================================================
    # Q012: Function length limit
    # =========================================================================

    def _check_function_length(self, source: str, module_id: str) -> List[ValidationIssue]:
        """Q012: Function should not exceed 50 lines."""
        issues = []
        max_lines = 50
        try:
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    # Calculate function line count
                    if hasattr(node, 'end_lineno') and node.end_lineno:
                        length = node.end_lineno - node.lineno + 1
                        if length > max_lines:
                            issues.append(ValidationIssue(
                                rule_id="Q012",
                                severity=Severity.WARNING,
                                message=f"Function '{node.name}' is {length} lines (max {max_lines})",
                                line=node.lineno,
                                hint="Consider breaking into smaller functions",
                            ))
        except SyntaxError:
            pass
        return issues

    # =========================================================================
    # Q013/Q014: params_schema quality
    # =========================================================================

    def _check_params_schema_quality(self, metadata: Dict[str, Any], module_id: str) -> List[ValidationIssue]:
        """
        Q013: params_schema fields should have description
        Q014: String params should have placeholder
        """
        issues = []
        params_schema = metadata.get('params_schema')

        if not params_schema or not isinstance(params_schema, dict):
            return issues

        for field_key, field_def in params_schema.items():
            # Skip special fields
            if field_key.startswith('__'):
                continue

            if not isinstance(field_def, dict):
                continue

            field_type = field_def.get('type', 'string')

            # Q013: Check for description
            if 'description' not in field_def:
                issues.append(ValidationIssue(
                    rule_id="Q013",
                    severity=Severity.WARNING,
                    message=f"params_schema field '{field_key}' missing description",
                    field=field_key,
                    hint="Add 'description' to help users understand this parameter",
                ))

            # Q014: String/text params should have placeholder
            # Skip: select types, fields with options/enum (dropdown selects don't need placeholder)
            has_options = 'options' in field_def or 'enum' in field_def
            is_text_input = field_type in ('string', 'text') and not has_options
            if is_text_input and 'placeholder' not in field_def:
                issues.append(ValidationIssue(
                    rule_id="Q014",
                    severity=Severity.WARNING,
                    message=f"String param '{field_key}' missing placeholder",
                    field=field_key,
                    hint="Add 'placeholder' to show example value in UI",
                ))

        return issues

    # =========================================================================
    # Q015: input_types/output_types
    # =========================================================================

    def _check_types_defined(self, metadata: Dict[str, Any], module_id: str) -> List[ValidationIssue]:
        """Q015: input_types/output_types should be defined for connection validation."""
        issues = []

        input_types = metadata.get('input_types')
        output_types = metadata.get('output_types')
        category = metadata.get('category', '')

        # Skip flow/meta modules as they often have special type handling
        if category in ('flow', 'meta'):
            return issues

        if not input_types:
            issues.append(ValidationIssue(
                rule_id="Q015",
                severity=Severity.WARNING,
                message="Missing input_types",
                hint="Add input_types=['string'] (or appropriate types) for connection validation",
            ))

        if not output_types:
            issues.append(ValidationIssue(
                rule_id="Q015",
                severity=Severity.WARNING,
                message="Missing output_types",
                hint="Add output_types=['string'] (or appropriate types) for connection validation",
            ))

        return issues


# =============================================================================
# Main entry point for @register_module
# =============================================================================

def validate_module_quality(
    module_class: Type,
    module_id: str,
    metadata: Dict[str, Any],
    original_func: Optional[Any] = None,
) -> QualityReport:
    """
    Validate module quality - called by @register_module.

    Behavior is controlled by FLYTO_VALIDATION_MODE environment variable:
        - DEV: Logs issues, never blocks registration
        - CI: Blocks on ERROR, logs WARNING
        - RELEASE: Blocks on ERROR, blocks WARNING for stable modules

    Args:
        module_class: The module class to validate
        module_id: Module identifier
        metadata: Module metadata
        original_func: For function-based modules, the original function

    Returns:
        QualityReport with validation results

    Raises:
        ValueError: If validation fails in CI/RELEASE mode
    """
    mode = get_validation_mode()
    stability = metadata.get("stability", "stable")
    if hasattr(stability, 'value'):
        stability = stability.value

    validator = ModuleQualityValidator()
    report = validator.validate(module_class, module_id, metadata, original_func=original_func)

    if report.has_blocking_issues(mode, stability):
        # Build error message
        error_msg = f"\n{'='*60}\n"
        error_msg += f"Module Quality Validation FAILED: {module_id}\n"
        error_msg += f"Mode: {mode.value}, Stability: {stability}\n"
        error_msg += f"{'='*60}\n"

        for issue in report.errors:
            error_msg += f"  ERROR: {issue}\n"

        if report.warnings:
            error_msg += f"\nWarnings ({len(report.warnings)}):\n"
            for issue in report.warnings:
                error_msg += f"  WARN: {issue}\n"

        error_msg += f"{'='*60}\n"
        error_msg += "Fix the above issues before registration.\n"
        raise ValueError(error_msg)

    # Log non-blocking issues
    if mode != ValidationMode.DEV:
        for issue in report.issues:
            if issue.severity == Severity.ERROR:
                logger.error(f"[{module_id}] {issue}")
            elif issue.severity == Severity.WARNING:
                logger.warning(f"[{module_id}] {issue}")

    return report
