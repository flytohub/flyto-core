"""
Unified Validation Types

Shared types for all validation components to ensure consistency.
"""

from enum import Enum
from dataclasses import dataclass
from typing import Any, Dict, Optional


class ValidationMode(Enum):
    """
    Validation mode determines strictness level.

    Usage:
        - Set via environment: FLYTO_VALIDATION_MODE=ci|release
        - Or pass directly to validators
    """
    DEV = "dev"          # Lenient: logs only, never blocks
    CI = "ci"            # Standard: ERROR blocks, WARNING logs
    RELEASE = "release"  # Strict: ERROR blocks, WARNING blocks for stable modules


class Severity(Enum):
    """Issue severity level."""
    ERROR = "error"      # Must fix - blocks in CI/RELEASE
    WARNING = "warning"  # Should fix - blocks in RELEASE for stable
    INFO = "info"        # Nice to have - never blocks


@dataclass
class ValidationIssue:
    """
    A single validation issue.

    Attributes:
        rule_id: Unique rule identifier (e.g., Q001, M002, SEC003)
        severity: ERROR/WARNING/INFO
        message: Human-readable description
        field: Affected field/location (optional)
        hint: How to fix (optional)
        line: Line number if applicable (optional)
        fixable: Whether this can be auto-fixed (optional)
    """
    rule_id: str
    severity: Severity
    message: str
    field: Optional[str] = None
    hint: Optional[str] = None
    line: Optional[int] = None
    fixable: bool = False

    def __str__(self) -> str:
        parts = [f"[{self.rule_id}] {self.message}"]
        if self.field:
            parts[0] += f" [{self.field}]"
        if self.line:
            parts[0] += f" (line {self.line})"
        if self.hint:
            parts.append(f"  Hint: {self.hint}")
        return "\n".join(parts)

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "message": self.message,
        }
        if self.field:
            result["field"] = self.field
        if self.hint:
            result["hint"] = self.hint
        if self.line:
            result["line"] = self.line
        if self.fixable:
            result["fixable"] = self.fixable
        return result


def get_validation_mode() -> ValidationMode:
    """
    Get validation mode from environment.

    Environment variable: FLYTO_VALIDATION_MODE
    Values: dev, ci, release (default: ci)
    """
    import os
    mode_str = os.environ.get("FLYTO_VALIDATION_MODE", "ci").lower()
    try:
        return ValidationMode(mode_str)
    except ValueError:
        return ValidationMode.CI


def should_block(
    severity: Severity,
    mode: ValidationMode,
    stability: str = "stable"
) -> bool:
    """
    Determine if an issue should block based on severity, mode, and stability.

    Args:
        severity: Issue severity
        mode: Validation mode
        stability: Module stability level (stable/beta/alpha/deprecated)

    Returns:
        True if this issue should block/fail
    """
    if severity == Severity.ERROR:
        # ERROR always blocks in CI and RELEASE
        return mode in (ValidationMode.CI, ValidationMode.RELEASE)

    if severity == Severity.WARNING:
        # WARNING only blocks in RELEASE for stable modules
        return mode == ValidationMode.RELEASE and stability == "stable"

    # INFO never blocks
    return False
