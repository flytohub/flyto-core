"""
AST Rules (CORE-AST-*)

Rules that require AST analysis of source code.
Ported from quality_validator.py Q001-Q010.
"""
import ast
import re
from typing import Any, Dict, List, Optional

from ..types import Severity, ValidationIssue
from . import register_rule
from .base import ASTRule


# Chinese character pattern
CHINESE_PATTERN = re.compile(r'[\u4e00-\u9fff]')


@register_rule
class SyntaxValid(ASTRule):
    """CORE-AST-001: Source code must be syntactically valid Python."""

    rule_id = "CORE-AST-001"
    description = "Syntax must be valid"
    category = "ast"
    default_severity = Severity.FATAL
    stability_aware = False

    @classmethod
    def validate(
        cls,
        module_id: str,
        metadata: Dict[str, Any],
        source_code: Optional[str] = None,
        ast_tree: Optional[ast.AST] = None,
    ) -> List[ValidationIssue]:
        issues = []

        if source_code is None:
            return issues

        if ast_tree is None:
            try:
                ast.parse(source_code)
            except SyntaxError as e:
                issues.append(cls.create_issue(
                    message=f"Syntax error: {e.msg}",
                    module_id=module_id,
                    line=e.lineno or 0,
                    col=e.offset or 0,
                ))

        return issues


@register_rule
class ExecuteIsAsync(ASTRule):
    """CORE-AST-002: execute() method must be async."""

    rule_id = "CORE-AST-002"
    description = "execute() must be async"
    category = "ast"
    default_severity = Severity.ERROR
    stability_aware = False

    @classmethod
    def validate(
        cls,
        module_id: str,
        metadata: Dict[str, Any],
        source_code: Optional[str] = None,
        ast_tree: Optional[ast.AST] = None,
    ) -> List[ValidationIssue]:
        issues = []

        if source_code is None:
            return issues

        if ast_tree is None:
            try:
                ast_tree = ast.parse(source_code)
            except SyntaxError:
                return issues

        for node in ast.walk(ast_tree):
            # Look for class definitions
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    # Check if execute method exists and is async
                    if isinstance(item, ast.FunctionDef) and item.name == "execute":
                        issues.append(cls.create_issue(
                            message="execute() method is not async",
                            module_id=module_id,
                            line=item.lineno,
                            suggestion="Change 'def execute' to 'async def execute'",
                        ))
                    # AsyncFunctionDef is fine, no issue

            # Also check top-level functions (for function-based modules)
            if isinstance(node, ast.FunctionDef) and node.name == "execute":
                # Only flag if it's a top-level function that looks like a module entry
                if hasattr(node, 'col_offset') and node.col_offset == 0:
                    issues.append(cls.create_issue(
                        message="execute() function is not async",
                        module_id=module_id,
                        line=node.lineno,
                        suggestion="Change 'def execute' to 'async def execute'",
                    ))

        return issues


@register_rule
class NoPrintStatements(ASTRule):
    """CORE-AST-003: No print() statements - use logging."""

    rule_id = "CORE-AST-003"
    description = "No print() statements"
    category = "ast"
    default_severity = Severity.ERROR
    stability_aware = False

    @classmethod
    def validate(
        cls,
        module_id: str,
        metadata: Dict[str, Any],
        source_code: Optional[str] = None,
        ast_tree: Optional[ast.AST] = None,
    ) -> List[ValidationIssue]:
        issues = []

        if source_code is None:
            return issues

        if ast_tree is None:
            try:
                ast_tree = ast.parse(source_code)
            except SyntaxError:
                return issues

        for node in ast.walk(ast_tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == "print":
                    issues.append(cls.create_issue(
                        message="print() statement found",
                        module_id=module_id,
                        line=node.lineno,
                        suggestion="Use logging.info(), logging.debug(), etc. instead",
                    ))

        return issues


@register_rule
class NoChineseInIdentifiers(ASTRule):
    """CORE-AST-004: No Chinese characters in identifiers."""

    rule_id = "CORE-AST-004"
    description = "No Chinese in identifiers"
    category = "ast"
    default_severity = Severity.ERROR
    stability_aware = False

    @classmethod
    def validate(
        cls,
        module_id: str,
        metadata: Dict[str, Any],
        source_code: Optional[str] = None,
        ast_tree: Optional[ast.AST] = None,
    ) -> List[ValidationIssue]:
        issues = []

        if source_code is None:
            return issues

        if ast_tree is None:
            try:
                ast_tree = ast.parse(source_code)
            except SyntaxError:
                return issues

        found_chinese = set()

        for node in ast.walk(ast_tree):
            # Function names
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if CHINESE_PATTERN.search(node.name):
                    found_chinese.add(f"function '{node.name}'")

            # Class names
            if isinstance(node, ast.ClassDef):
                if CHINESE_PATTERN.search(node.name):
                    found_chinese.add(f"class '{node.name}'")

            # Variable names
            if isinstance(node, ast.Name):
                if CHINESE_PATTERN.search(node.id):
                    found_chinese.add(f"variable '{node.id}'")

        if found_chinese:
            issues.append(cls.create_issue(
                message=f"Chinese characters in identifiers: {', '.join(list(found_chinese)[:3])}",
                module_id=module_id,
                suggestion="Use English identifiers only",
            ))

        return issues


@register_rule
class ClassHasDocstring(ASTRule):
    """CORE-AST-005: Module class should have a docstring."""

    rule_id = "CORE-AST-005"
    description = "Class should have docstring"
    category = "ast"
    default_severity = Severity.WARN
    stability_aware = False

    @classmethod
    def validate(
        cls,
        module_id: str,
        metadata: Dict[str, Any],
        source_code: Optional[str] = None,
        ast_tree: Optional[ast.AST] = None,
    ) -> List[ValidationIssue]:
        issues = []

        if source_code is None:
            return issues

        if ast_tree is None:
            try:
                ast_tree = ast.parse(source_code)
            except SyntaxError:
                return issues

        for node in ast.walk(ast_tree):
            if isinstance(node, ast.ClassDef):
                # Check if first statement is a docstring
                if node.body:
                    first = node.body[0]
                    if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                        if isinstance(first.value.value, str):
                            continue  # Has docstring
                    # No docstring
                    issues.append(cls.create_issue(
                        message=f"Class '{node.name}' is missing a docstring",
                        module_id=module_id,
                        line=node.lineno,
                        suggestion="Add a docstring describing the class purpose",
                    ))

        return issues


@register_rule
class ValidateParamsExists(ASTRule):
    """CORE-AST-006: Class should have validate_params() method."""

    rule_id = "CORE-AST-006"
    description = "validate_params() method recommended"
    category = "ast"
    default_severity = Severity.INFO
    stability_aware = False

    @classmethod
    def validate(
        cls,
        module_id: str,
        metadata: Dict[str, Any],
        source_code: Optional[str] = None,
        ast_tree: Optional[ast.AST] = None,
    ) -> List[ValidationIssue]:
        issues = []

        if source_code is None:
            return issues

        if ast_tree is None:
            try:
                ast_tree = ast.parse(source_code)
            except SyntaxError:
                return issues

        for node in ast.walk(ast_tree):
            if isinstance(node, ast.ClassDef):
                has_validate = False
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if item.name == "validate_params":
                            has_validate = True
                            break

                if not has_validate:
                    # Only warn for classes that look like modules
                    method_names = [
                        item.name for item in node.body
                        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                    ]
                    if "execute" in method_names:
                        issues.append(cls.create_issue(
                            message=f"Class '{node.name}' is missing validate_params() method",
                            module_id=module_id,
                            line=node.lineno,
                            suggestion="Add validate_params() for input validation",
                        ))

        return issues


# Dangerous functions that allow arbitrary code execution
DANGEROUS_FUNCTIONS = {
    "eval": "Executes arbitrary Python expressions",
    "exec": "Executes arbitrary Python code",
    "compile": "Compiles code dynamically",
    "__import__": "Dynamic module imports can be exploited",
}


@register_rule
class NoDangerousFunctions(ASTRule):
    """CORE-AST-007: Dangerous functions (eval, exec, compile, __import__) are forbidden."""

    rule_id = "CORE-AST-007"
    description = "No dangerous functions (eval/exec/compile)"
    category = "ast"
    default_severity = Severity.BLOCKER
    stability_aware = False

    @classmethod
    def validate(
        cls,
        module_id: str,
        metadata: Dict[str, Any],
        source_code: Optional[str] = None,
        ast_tree: Optional[ast.AST] = None,
    ) -> List[ValidationIssue]:
        issues = []

        if source_code is None:
            return issues

        if ast_tree is None:
            try:
                ast_tree = ast.parse(source_code)
            except SyntaxError:
                return issues

        for node in ast.walk(ast_tree):
            if isinstance(node, ast.Call):
                func_name = None

                # Direct call: eval(), exec(), compile()
                if isinstance(node.func, ast.Name):
                    func_name = node.func.id

                # builtins.eval(), builtins.exec() etc.
                elif isinstance(node.func, ast.Attribute):
                    if (isinstance(node.func.value, ast.Name) and
                        node.func.value.id == "builtins"):
                        func_name = node.func.attr

                if func_name and func_name in DANGEROUS_FUNCTIONS:
                    issues.append(cls.create_issue(
                        message=f"Dangerous function '{func_name}()' is forbidden: {DANGEROUS_FUNCTIONS[func_name]}",
                        module_id=module_id,
                        line=node.lineno,
                        suggestion="Use safe alternatives or refactor code to avoid dynamic execution",
                        severity=Severity.BLOCKER,
                    ))

        return issues
