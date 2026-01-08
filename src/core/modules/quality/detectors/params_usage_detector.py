"""
Params Usage Detector

AST-based detection of how params are accessed in code:
- params["key"] (direct access)
- params.get("key") (optional access)
- self.params["key"] (class-based modules)

Used to verify params_schema completeness.
"""

import ast
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from ..types import Severity, ValidationIssue


@dataclass
class ParamsUsage:
    """Result of params usage analysis."""

    direct_keys: Set[str] = field(default_factory=set)  # params["key"]
    optional_keys: Set[str] = field(default_factory=set)  # params.get("key")
    all_keys: Set[str] = field(default_factory=set)  # combined


class ParamsUsageDetector(ast.NodeVisitor):
    """Detect params[...] and params.get(...) usage."""

    def __init__(self, params_name: str = "params"):
        self.params_name = params_name
        self.direct_keys: Set[str] = set()
        self.optional_keys: Set[str] = set()

    def visit_Subscript(self, node: ast.Subscript) -> None:
        """Detect params["key"] or params['key']."""
        # params["key"]
        if isinstance(node.value, ast.Name) and node.value.id == self.params_name:
            if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
                self.direct_keys.add(node.slice.value)

        # self.params["key"]
        if isinstance(node.value, ast.Attribute):
            if (isinstance(node.value.value, ast.Name) and
                node.value.value.id == "self" and
                node.value.attr == self.params_name):
                if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
                    self.direct_keys.add(node.slice.value)

        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Detect params.get("key") calls."""
        if isinstance(node.func, ast.Attribute) and node.func.attr == "get":
            # params.get("key")
            if isinstance(node.func.value, ast.Name) and node.func.value.id == self.params_name:
                if node.args and isinstance(node.args[0], ast.Constant):
                    if isinstance(node.args[0].value, str):
                        self.optional_keys.add(node.args[0].value)

            # self.params.get("key")
            if isinstance(node.func.value, ast.Attribute):
                if (isinstance(node.func.value.value, ast.Name) and
                    node.func.value.value.id == "self" and
                    node.func.value.attr == self.params_name):
                    if node.args and isinstance(node.args[0], ast.Constant):
                        if isinstance(node.args[0].value, str):
                            self.optional_keys.add(node.args[0].value)

        self.generic_visit(node)

    def get_all_keys(self) -> Set[str]:
        """Get all used keys (direct + optional)."""
        return self.direct_keys | self.optional_keys


def detect_params_usage(
    source_code: str,
    ast_tree: Optional[ast.AST] = None,
    params_name: str = "params",
) -> ParamsUsage:
    """
    Detect params usage in source code.

    Args:
        source_code: Python source code
        ast_tree: Optional pre-parsed AST
        params_name: Name of params variable (default: "params")

    Returns:
        ParamsUsage with found keys
    """
    if ast_tree is None:
        try:
            ast_tree = ast.parse(source_code)
        except SyntaxError:
            return ParamsUsage()

    detector = ParamsUsageDetector(params_name)
    detector.visit(ast_tree)

    return ParamsUsage(
        direct_keys=detector.direct_keys,
        optional_keys=detector.optional_keys,
        all_keys=detector.get_all_keys(),
    )


def verify_params_usage(
    source_code: str,
    params_schema: Dict[str, Any],
    module_id: str = "",
    ast_tree: Optional[ast.AST] = None,
) -> List[ValidationIssue]:
    """
    Verify params usage matches params_schema.

    Checks:
    - CORE-SCH-011: params["key"] in code → key in params_schema
    - Unused params (INFO level)
    - Required params accessed via .get() (WARN level)

    Args:
        source_code: Python source code
        params_schema: Declared params_schema
        module_id: Module identifier for issue reporting
        ast_tree: Optional pre-parsed AST

    Returns:
        List of validation issues
    """
    issues = []

    if not params_schema or not isinstance(params_schema, dict):
        return issues

    # Get declared properties and required fields
    properties = params_schema.get("properties", {})
    if not isinstance(properties, dict):
        return issues

    declared_keys = set(properties.keys())
    required_keys = set(params_schema.get("required", []))

    # Detect used keys in code
    usage = detect_params_usage(source_code, ast_tree)

    # Check for undeclared params usage
    undeclared = usage.all_keys - declared_keys
    for key in sorted(undeclared):
        issues.append(ValidationIssue(
            rule_id="CORE-SCH-011",
            severity=Severity.ERROR,
            message=f"params['{key}'] used in code but not declared in params_schema",
            module_id=module_id,
            suggestion=f"Add '{key}' to params_schema.properties",
        ))

    # Check required fields accessed with .get() instead of direct access
    for key in required_keys:
        if key in usage.optional_keys and key not in usage.direct_keys:
            issues.append(ValidationIssue(
                rule_id="CORE-SCH-011",
                severity=Severity.WARN,
                message=f"Required param '{key}' accessed via .get() instead of params['{key}']",
                module_id=module_id,
                suggestion=f"Use params['{key}'] for required fields",
            ))

    # Check for declared but unused params (INFO level)
    unused = declared_keys - usage.all_keys
    if unused:
        issues.append(ValidationIssue(
            rule_id="CORE-SCH-011",
            severity=Severity.INFO,
            message=f"Declared params not used in code: {', '.join(sorted(unused)[:5])}{'...' if len(unused) > 5 else ''}",
            module_id=module_id,
            suggestion="Remove from params_schema or use in code",
        ))

    return issues
