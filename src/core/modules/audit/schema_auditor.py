"""
Schema Auditor - Main audit logic for module schemas

Scans all registered modules and identifies quality issues in their
params_schema and output_schema definitions.
"""
from __future__ import annotations
from dataclasses import dataclass, field as dataclass_field
from typing import Any, Dict, List, Optional, Set
from collections import defaultdict

from .standards import (
    QualityLevel,
    REQUIRED_PARAM_FIELDS,
    RECOMMENDED_PARAM_FIELDS,
    STRING_PARAM_FIELDS,
    REQUIRED_OUTPUT_FIELDS,
    TYPES_REQUIRING_PLACEHOLDER,
    DEFAULT_PLACEHOLDERS,
    DEFAULT_DESCRIPTIONS,
    DEFAULT_DESCRIPTIONS_BY_KEY,
    DEFAULT_PLACEHOLDERS_BY_KEY,
    FLOW_CONTROL_MODULES,
)


@dataclass
class FieldIssue:
    """Represents a single schema field issue."""
    module_id: str
    field_name: str
    issue_type: str  # 'missing_description', 'missing_placeholder', 'missing_label', etc.
    level: QualityLevel
    message: str
    suggested_fix: Optional[str] = None
    current_value: Optional[Any] = None


@dataclass
class ModuleAuditResult:
    """Audit result for a single module."""
    module_id: str
    category: str
    issues: List[FieldIssue] = dataclass_field(default_factory=list)
    params_schema: Dict[str, Any] = dataclass_field(default_factory=dict)
    output_schema: Dict[str, Any] = dataclass_field(default_factory=dict)
    input_types: List[str] = dataclass_field(default_factory=list)
    output_types: List[str] = dataclass_field(default_factory=list)
    uses_compose: bool = False

    @property
    def critical_count(self) -> int:
        return sum(1 for i in self.issues if i.level == QualityLevel.CRITICAL)

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.level == QualityLevel.WARNING)

    @property
    def info_count(self) -> int:
        return sum(1 for i in self.issues if i.level == QualityLevel.INFO)

    @property
    def has_issues(self) -> bool:
        return len(self.issues) > 0


@dataclass
class AuditResult:
    """Complete audit result across all modules."""
    modules: List[ModuleAuditResult] = dataclass_field(default_factory=list)
    total_modules: int = 0
    modules_with_issues: int = 0
    total_issues: int = 0
    critical_issues: int = 0
    warning_issues: int = 0
    info_issues: int = 0
    by_category: Dict[str, List[ModuleAuditResult]] = dataclass_field(default_factory=dict)
    by_issue_type: Dict[str, List[FieldIssue]] = dataclass_field(default_factory=dict)

    def add_module_result(self, result: ModuleAuditResult) -> None:
        """Add a module audit result."""
        self.modules.append(result)
        self.total_modules += 1

        if result.has_issues:
            self.modules_with_issues += 1
            self.total_issues += len(result.issues)
            self.critical_issues += result.critical_count
            self.warning_issues += result.warning_count
            self.info_issues += result.info_count

        # Index by category
        if result.category not in self.by_category:
            self.by_category[result.category] = []
        self.by_category[result.category].append(result)

        # Index by issue type
        for issue in result.issues:
            if issue.issue_type not in self.by_issue_type:
                self.by_issue_type[issue.issue_type] = []
            self.by_issue_type[issue.issue_type].append(issue)


class SchemaAuditor:
    """
    Audits module schemas for quality issues.

    Usage:
        auditor = SchemaAuditor()
        result = auditor.audit_all()

        # Or audit a single module
        module_result = auditor.audit_module(module_id, metadata)
    """

    def __init__(self, strict: bool = False):
        """
        Initialize the auditor.

        Args:
            strict: If True, treat warnings as critical issues
        """
        self.strict = strict

    def audit_all(self) -> AuditResult:
        """
        Audit all registered modules.

        Returns:
            AuditResult with all findings
        """
        from ..registry.core import ModuleRegistry

        result = AuditResult()

        # Get all module metadata
        all_metadata = ModuleRegistry.get_all_metadata(filter_by_stability=False)

        for module_id, metadata in all_metadata.items():
            module_result = self.audit_module(module_id, metadata)
            result.add_module_result(module_result)

        return result

    def audit_module(self, module_id: str, metadata: Dict[str, Any]) -> ModuleAuditResult:
        """
        Audit a single module's schema.

        Args:
            module_id: Module identifier
            metadata: Module metadata from registry

        Returns:
            ModuleAuditResult with findings
        """
        result = ModuleAuditResult(
            module_id=module_id,
            category=metadata.get('category', module_id.split('.')[0]),
            params_schema=metadata.get('params_schema', {}),
            output_schema=metadata.get('output_schema', {}),
            input_types=metadata.get('input_types', []),
            output_types=metadata.get('output_types', []),
        )

        # Audit params_schema
        self._audit_params_schema(result)

        # Audit output_schema
        self._audit_output_schema(result)

        # Audit input/output types
        self._audit_types(result)

        return result

    def _audit_params_schema(self, result: ModuleAuditResult) -> None:
        """Audit params_schema for quality issues."""
        params_schema = result.params_schema

        for field_name, field_def in params_schema.items():
            # Skip special fields
            if field_name.startswith('__'):
                continue

            if not isinstance(field_def, dict):
                result.issues.append(FieldIssue(
                    module_id=result.module_id,
                    field_name=field_name,
                    issue_type='invalid_field_def',
                    level=QualityLevel.CRITICAL,
                    message=f"Field definition is not a dict: {type(field_def)}",
                ))
                continue

            field_type = field_def.get('type', 'string')
            # Handle case where type might be a list
            if isinstance(field_type, list):
                field_type = field_type[0] if field_type else 'string'

            # Check for missing description
            if 'description' not in field_def:
                suggested = self._suggest_description(field_name, field_type)
                result.issues.append(FieldIssue(
                    module_id=result.module_id,
                    field_name=field_name,
                    issue_type='missing_description',
                    level=QualityLevel.WARNING,
                    message=f"Missing description for param '{field_name}'",
                    suggested_fix=suggested,
                ))

            # Check for missing label
            if 'label' not in field_def:
                suggested = self._suggest_label(field_name)
                result.issues.append(FieldIssue(
                    module_id=result.module_id,
                    field_name=field_name,
                    issue_type='missing_label',
                    level=QualityLevel.WARNING,
                    message=f"Missing label for param '{field_name}'",
                    suggested_fix=suggested,
                ))

            # Check for missing placeholder (string types)
            if field_type in TYPES_REQUIRING_PLACEHOLDER or field_type == 'string':
                if 'placeholder' not in field_def:
                    suggested = self._suggest_placeholder(field_name, field_type)
                    result.issues.append(FieldIssue(
                        module_id=result.module_id,
                        field_name=field_name,
                        issue_type='missing_placeholder',
                        level=QualityLevel.WARNING,
                        message=f"Missing placeholder for string param '{field_name}'",
                        suggested_fix=suggested,
                    ))

    def _audit_output_schema(self, result: ModuleAuditResult) -> None:
        """Audit output_schema for quality issues."""
        output_schema = result.output_schema

        for field_name, field_def in output_schema.items():
            # Skip special fields
            if field_name.startswith('__'):
                continue

            if not isinstance(field_def, dict):
                continue

            # Check for missing description in output
            if 'description' not in field_def:
                result.issues.append(FieldIssue(
                    module_id=result.module_id,
                    field_name=f"output.{field_name}",
                    issue_type='output_missing_description',
                    level=QualityLevel.INFO,
                    message=f"Missing description for output field '{field_name}'",
                    suggested_fix=self._suggest_description(field_name, field_def.get('type', 'any')),
                ))

    def _audit_types(self, result: ModuleAuditResult) -> None:
        """Audit input/output types."""
        # Check for missing input_types
        if not result.input_types:
            # Flow control modules are expected to have special handling
            if result.module_id in FLOW_CONTROL_MODULES:
                level = QualityLevel.WARNING
            else:
                level = QualityLevel.INFO

            result.issues.append(FieldIssue(
                module_id=result.module_id,
                field_name='input_types',
                issue_type='missing_input_types',
                level=level,
                message=f"Missing input_types for module",
                suggested_fix=self._suggest_input_types(result.module_id, result.category),
            ))

        # Check for missing output_types
        if not result.output_types:
            if result.module_id in FLOW_CONTROL_MODULES:
                level = QualityLevel.WARNING
            else:
                level = QualityLevel.INFO

            result.issues.append(FieldIssue(
                module_id=result.module_id,
                field_name='output_types',
                issue_type='missing_output_types',
                level=level,
                message=f"Missing output_types for module",
                suggested_fix=self._suggest_output_types(result.module_id, result.category),
            ))

    def _suggest_description(self, field_name: str, field_type: str) -> str:
        """Suggest a description for a field."""
        # First check by field name
        if field_name in DEFAULT_DESCRIPTIONS_BY_KEY:
            return DEFAULT_DESCRIPTIONS_BY_KEY[field_name]

        # Then check by type
        if field_type in DEFAULT_DESCRIPTIONS:
            return DEFAULT_DESCRIPTIONS[field_type]

        # Generate from field name
        return f"{field_name.replace('_', ' ').title()} value"

    def _suggest_label(self, field_name: str) -> str:
        """Suggest a label for a field."""
        return field_name.replace('_', ' ').title()

    def _suggest_placeholder(self, field_name: str, field_type: str) -> str:
        """Suggest a placeholder for a field."""
        # First check by field name
        if field_name in DEFAULT_PLACEHOLDERS_BY_KEY:
            return DEFAULT_PLACEHOLDERS_BY_KEY[field_name]

        # Then check by type
        if field_type in DEFAULT_PLACEHOLDERS:
            return DEFAULT_PLACEHOLDERS[field_type]

        return 'Enter value...'

    def _suggest_input_types(self, module_id: str, category: str) -> str:
        """Suggest input types based on module/category."""
        suggestions = {
            'string': "['string']",
            'array': "['array']",
            'object': "['object']",
            'math': "['number']",
            'browser': "['browser']",
            'file': "['string']",  # file path
            'http': "['string']",  # url
            'data': "['any']",
            'flow': "['control']",
            'error': "['any']",
        }
        return suggestions.get(category, "['any']")

    def _suggest_output_types(self, module_id: str, category: str) -> str:
        """Suggest output types based on module/category."""
        suggestions = {
            'string': "['string']",
            'array': "['array']",
            'object': "['object']",
            'math': "['number']",
            'browser': "['browser']",
            'file': "['string']",
            'http': "['object']",
            'data': "['any']",
            'flow': "['control']",
            'error': "['any']",
        }
        return suggestions.get(category, "['any']")


def run_audit(strict: bool = False) -> AuditResult:
    """
    Convenience function to run a full audit.

    Args:
        strict: If True, treat warnings as critical

    Returns:
        AuditResult with all findings
    """
    auditor = SchemaAuditor(strict=strict)
    return auditor.audit_all()
