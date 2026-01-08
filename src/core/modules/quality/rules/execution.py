"""
Execution Rules (CORE-EX-*)

Rules for execution settings: timeout, retry, concurrency.
"""
from typing import Any, Dict, List, Optional
import ast

from ..types import Severity, ValidationIssue
from . import register_rule
from .base import MetadataRule


@register_rule
class TimeoutRequired(MetadataRule):
    """CORE-EX-001: timeout_ms is required for stable modules."""

    rule_id = "CORE-EX-001"
    description = "timeout_ms is required"
    category = "execution"
    default_severity = Severity.ERROR
    stability_aware = True

    @classmethod
    def validate(
        cls,
        module_id: str,
        metadata: Dict[str, Any],
        source_code: Optional[str] = None,
        ast_tree: Optional[ast.AST] = None,
    ) -> List[ValidationIssue]:
        issues = []

        timeout_ms = metadata.get("timeout_ms")
        timeout = metadata.get("timeout")  # Legacy field
        stability = metadata.get("stability", "stable")

        severity = cls.get_severity(stability)

        if timeout_ms is None:
            if timeout is not None:
                # Legacy timeout field used
                issues.append(cls.create_issue(
                    message="Using deprecated 'timeout' (seconds). Use 'timeout_ms' (milliseconds) instead",
                    module_id=module_id,
                    severity=Severity.WARN,
                    suggestion=f"Replace timeout={timeout} with timeout_ms={timeout * 1000}",
                ))
            else:
                issues.append(cls.create_issue(
                    message="timeout_ms is required for production use",
                    module_id=module_id,
                    severity=severity,
                    suggestion="Add timeout_ms=60000 (60 seconds) or appropriate value",
                ))
        elif not isinstance(timeout_ms, int) or timeout_ms <= 0:
            issues.append(cls.create_issue(
                message=f"timeout_ms must be a positive integer, got: {timeout_ms}",
                module_id=module_id,
            ))

        return issues


@register_rule
class RetryableConsistency(MetadataRule):
    """CORE-EX-002: If retryable=True, max_retries must be >= 1."""

    rule_id = "CORE-EX-002"
    description = "retryable=True requires max_retries >= 1"
    category = "execution"
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

        retryable = metadata.get("retryable", False)
        max_retries = metadata.get("max_retries", 0)

        if retryable is True:
            if max_retries is None or max_retries < 1:
                issues.append(cls.create_issue(
                    message=f"retryable=True but max_retries={max_retries}. This is contradictory.",
                    module_id=module_id,
                    suggestion="Set max_retries >= 1 when retryable=True",
                ))

        return issues


@register_rule
class NotRetryableConsistency(MetadataRule):
    """CORE-EX-003: If retryable=False, max_retries should be 0 or absent."""

    rule_id = "CORE-EX-003"
    description = "retryable=False should have max_retries=0"
    category = "execution"
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

        retryable = metadata.get("retryable", False)
        max_retries = metadata.get("max_retries")

        if retryable is False and max_retries is not None and max_retries > 0:
            issues.append(cls.create_issue(
                message=f"retryable=False but max_retries={max_retries}. This is confusing.",
                module_id=module_id,
                suggestion="Remove max_retries or set to 0 when retryable=False",
            ))

        return issues


@register_rule
class MaxRetriesBounds(MetadataRule):
    """CORE-EX-004: max_retries should be between 1 and 10."""

    rule_id = "CORE-EX-004"
    description = "max_retries should be reasonable (1-10)"
    category = "execution"
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

        max_retries = metadata.get("max_retries")

        if max_retries is not None:
            if max_retries > 10:
                issues.append(cls.create_issue(
                    message=f"max_retries={max_retries} is too high. This may overwhelm the system.",
                    module_id=module_id,
                    suggestion="Keep max_retries <= 10",
                ))
            elif max_retries < 0:
                issues.append(cls.create_issue(
                    message=f"max_retries={max_retries} cannot be negative",
                    module_id=module_id,
                    severity=Severity.ERROR,
                ))

        return issues


@register_rule
class ConcurrentSafety(MetadataRule):
    """CORE-EX-005: Warn if concurrent_safe=True with shell/filesystem capabilities."""

    rule_id = "CORE-EX-005"
    description = "concurrent_safe=True with side effects needs caution"
    category = "execution"
    default_severity = Severity.WARN
    stability_aware = False

    # Only permissions that are truly unsafe for concurrent execution
    # filesystem.write is safe when writing to different files (user-specified paths)
    RISKY_PERMISSIONS = {
        "shell.execute",      # Commands can conflict, race conditions
        "database.write",     # Transaction conflicts possible
    }

    @classmethod
    def validate(
        cls,
        module_id: str,
        metadata: Dict[str, Any],
        source_code: Optional[str] = None,
        ast_tree: Optional[ast.AST] = None,
    ) -> List[ValidationIssue]:
        issues = []

        concurrent_safe = metadata.get("concurrent_safe", False)
        permissions = set(metadata.get("required_permissions", []))

        if concurrent_safe is True:
            risky = permissions & cls.RISKY_PERMISSIONS
            if risky:
                issues.append(cls.create_issue(
                    message=f"concurrent_safe=True but has risky permissions: {', '.join(risky)}",
                    module_id=module_id,
                    suggestion="Verify that concurrent execution is truly safe with these capabilities",
                ))

        return issues
