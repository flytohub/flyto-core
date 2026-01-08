"""
Identity Rules (CORE-ID-*)

Rules for module identification and metadata.
"""
import re
from typing import Any, Dict, List, Optional
import ast

from ..types import Severity, ValidationIssue
from ..constants import STABILITY_LEVELS
from . import register_rule
from .base import MetadataRule


@register_rule
class ModuleIdFormat(MetadataRule):
    """CORE-ID-001: module_id must be in format 'category.action' or 'category.subcategory.action'."""

    rule_id = "CORE-ID-001"
    description = "module_id must be in format 'category.action'"
    category = "identity"
    default_severity = Severity.ERROR
    stability_aware = False

    # Valid module_id pattern
    MODULE_ID_PATTERN = re.compile(r'^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){1,3}$')

    @classmethod
    def validate(
        cls,
        module_id: str,
        metadata: Dict[str, Any],
        source_code: Optional[str] = None,
        ast_tree: Optional[ast.AST] = None,
    ) -> List[ValidationIssue]:
        issues = []

        if not module_id:
            issues.append(cls.create_issue(
                message="module_id is required",
                module_id=module_id,
            ))
            return issues

        if not cls.MODULE_ID_PATTERN.match(module_id):
            issues.append(cls.create_issue(
                message=f"Invalid module_id format: '{module_id}'. Expected 'category.action' or 'category.subcategory.action'",
                module_id=module_id,
                suggestion="Use lowercase letters, numbers, and underscores separated by dots",
            ))

        return issues


@register_rule
class StabilityRequired(MetadataRule):
    """CORE-ID-002: stability field must be a valid enum value."""

    rule_id = "CORE-ID-002"
    description = "stability must be a valid level"
    category = "identity"
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

        stability = metadata.get("stability")

        if stability is None:
            issues.append(cls.create_issue(
                message="stability field is required",
                module_id=module_id,
                suggestion=f"Add stability field with one of: {', '.join(sorted(STABILITY_LEVELS))}",
            ))
        elif stability.lower() not in STABILITY_LEVELS:
            issues.append(cls.create_issue(
                message=f"Invalid stability value: '{stability}'",
                module_id=module_id,
                suggestion=f"Use one of: {', '.join(sorted(STABILITY_LEVELS))}",
            ))

        return issues


@register_rule
class VersionSemver(MetadataRule):
    """CORE-ID-003: version should follow semver format."""

    rule_id = "CORE-ID-003"
    description = "version should follow semantic versioning"
    category = "identity"
    default_severity = Severity.WARN
    stability_aware = False

    # Semver pattern (simplified)
    SEMVER_PATTERN = re.compile(r'^\d+\.\d+\.\d+(-[a-zA-Z0-9.]+)?(\+[a-zA-Z0-9.]+)?$')

    @classmethod
    def validate(
        cls,
        module_id: str,
        metadata: Dict[str, Any],
        source_code: Optional[str] = None,
        ast_tree: Optional[ast.AST] = None,
    ) -> List[ValidationIssue]:
        issues = []

        version = metadata.get("version")

        if version is None:
            issues.append(cls.create_issue(
                message="version field is recommended",
                module_id=module_id,
                severity=Severity.INFO,
                suggestion="Add version='1.0.0'",
            ))
        elif not cls.SEMVER_PATTERN.match(str(version)):
            issues.append(cls.create_issue(
                message=f"Version '{version}' does not follow semver format",
                module_id=module_id,
                suggestion="Use format: major.minor.patch (e.g., 1.0.0)",
            ))

        return issues
