"""
Base Rule Class

Abstract base class for all validation rules.
"""
import ast
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from ..types import Severity, ValidationIssue
from ..constants import SEVERITY_BY_STABILITY


class BaseRule(ABC):
    """Abstract base class for validation rules."""

    # Rule identification
    rule_id: str = ""           # e.g., "CORE-ID-001"
    description: str = ""       # Human-readable description
    category: str = ""          # e.g., "identity", "execution", "schema"

    # Default severity (can be overridden by stability)
    default_severity: Severity = Severity.ERROR

    # Whether severity should vary by stability
    stability_aware: bool = True

    @classmethod
    def get_severity(cls, stability: str = "stable") -> Severity:
        """Get severity based on module stability."""
        if not cls.stability_aware:
            return cls.default_severity

        severity_str = SEVERITY_BY_STABILITY.get(stability, "ERROR")

        # Map to Severity enum
        if severity_str == "INFO":
            return Severity.INFO
        elif severity_str == "WARN":
            return Severity.WARN
        elif severity_str == "ERROR":
            return Severity.ERROR
        else:
            return cls.default_severity

    @classmethod
    @abstractmethod
    def validate(
        cls,
        module_id: str,
        metadata: Dict[str, Any],
        source_code: Optional[str] = None,
        ast_tree: Optional[ast.AST] = None,
    ) -> List[ValidationIssue]:
        """
        Validate a module against this rule.

        Args:
            module_id: The module identifier
            metadata: Module metadata dict
            source_code: Optional source code for AST rules
            ast_tree: Optional pre-parsed AST

        Returns:
            List of validation issues (empty if passed)
        """
        pass

    @classmethod
    def create_issue(
        cls,
        message: str,
        module_id: str = "",
        severity: Optional[Severity] = None,
        file: str = "",
        line: int = 0,
        col: int = 0,
        suggestion: Optional[str] = None,
    ) -> ValidationIssue:
        """Helper to create a ValidationIssue."""
        return ValidationIssue(
            rule_id=cls.rule_id,
            severity=severity or cls.default_severity,
            message=message,
            module_id=module_id,
            file=file,
            line=line,
            col=col,
            suggestion=suggestion,
        )


class MetadataRule(BaseRule):
    """Base class for rules that only check metadata (no AST)."""

    @classmethod
    @abstractmethod
    def validate(
        cls,
        module_id: str,
        metadata: Dict[str, Any],
        source_code: Optional[str] = None,
        ast_tree: Optional[ast.AST] = None,
    ) -> List[ValidationIssue]:
        pass


class ASTRule(BaseRule):
    """Base class for rules that require AST analysis."""

    @classmethod
    @abstractmethod
    def validate(
        cls,
        module_id: str,
        metadata: Dict[str, Any],
        source_code: Optional[str] = None,
        ast_tree: Optional[ast.AST] = None,
    ) -> List[ValidationIssue]:
        pass

    @classmethod
    def parse_source(cls, source_code: str) -> Optional[ast.AST]:
        """Parse source code to AST."""
        try:
            return ast.parse(source_code)
        except SyntaxError:
            return None
