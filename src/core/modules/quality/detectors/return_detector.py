"""
Return Value Detector

AST-based detection of return statement keys:
- return {"key": value}
- return {"ok": True, "data": {...}}

Used to verify output_schema completeness.
"""

import ast
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from ..types import Severity, ValidationIssue


@dataclass
class ReturnAnalysis:
    """Result of return value analysis."""

    return_keys: Set[str] = field(default_factory=set)
    has_ok_field: bool = False
    return_count: int = 0


class ReturnValueDetector(ast.NodeVisitor):
    """Detect return statement dictionary keys."""

    def __init__(self):
        self.return_keys: Set[str] = set()
        self.has_ok_field: bool = False
        self.return_count: int = 0

    def visit_Return(self, node: ast.Return) -> None:
        """Detect return {...} dictionary keys."""
        self.return_count += 1

        if node.value and isinstance(node.value, ast.Dict):
            for key in node.value.keys:
                if key and isinstance(key, ast.Constant) and isinstance(key.value, str):
                    self.return_keys.add(key.value)
                    if key.value == "ok":
                        self.has_ok_field = True

        self.generic_visit(node)


def detect_return_keys(
    source_code: str,
    ast_tree: Optional[ast.AST] = None,
) -> ReturnAnalysis:
    """
    Detect return statement keys in source code.

    Args:
        source_code: Python source code
        ast_tree: Optional pre-parsed AST

    Returns:
        ReturnAnalysis with found keys
    """
    if ast_tree is None:
        try:
            ast_tree = ast.parse(source_code)
        except SyntaxError:
            return ReturnAnalysis()

    detector = ReturnValueDetector()
    detector.visit(ast_tree)

    return ReturnAnalysis(
        return_keys=detector.return_keys,
        has_ok_field=detector.has_ok_field,
        return_count=detector.return_count,
    )


def verify_return_schema(
    source_code: str,
    output_schema: Dict[str, Any],
    module_id: str = "",
    ast_tree: Optional[ast.AST] = None,
) -> List[ValidationIssue]:
    """
    Verify return structure matches output_schema.

    Checks:
    - CORE-SCH-012: return {"key": ...} → key in output_schema
    - Missing 'ok' field convention
    - Required output keys not found

    Args:
        source_code: Python source code
        output_schema: Declared output_schema
        module_id: Module identifier for issue reporting
        ast_tree: Optional pre-parsed AST

    Returns:
        List of validation issues
    """
    issues = []

    if not output_schema or not isinstance(output_schema, dict):
        return issues

    # Get declared properties and required fields
    properties = output_schema.get("properties", {})
    if not isinstance(properties, dict):
        return issues

    declared_keys = set(properties.keys())
    required_keys = set(output_schema.get("required", []))

    # Detect return keys in code
    analysis = detect_return_keys(source_code, ast_tree)

    # No return statements found - skip validation
    if analysis.return_count == 0:
        return issues

    # Check if 'ok' field is in schema but not returned
    if "ok" in declared_keys and not analysis.has_ok_field:
        issues.append(ValidationIssue(
            rule_id="CORE-SCH-012",
            severity=Severity.WARN,
            message="output_schema declares 'ok' field but not all return statements include it",
            module_id=module_id,
            suggestion="Ensure all return {...} include 'ok' field for consistency",
        ))

    # Check for undeclared return keys
    undeclared = analysis.return_keys - declared_keys
    for key in sorted(undeclared):
        issues.append(ValidationIssue(
            rule_id="CORE-SCH-012",
            severity=Severity.WARN,
            message=f"Return key '{key}' not declared in output_schema",
            module_id=module_id,
            suggestion=f"Add '{key}' to output_schema.properties",
        ))

    # Check required fields are returned
    missing_required = required_keys - analysis.return_keys
    for key in sorted(missing_required):
        if key != "ok":  # 'ok' is checked separately
            issues.append(ValidationIssue(
                rule_id="CORE-SCH-012",
                severity=Severity.INFO,
                message=f"Required output '{key}' not found in return statements",
                module_id=module_id,
                suggestion="Ensure all return paths include required fields",
            ))

    return issues
