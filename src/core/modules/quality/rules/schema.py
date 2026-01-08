"""
Schema Rules (CORE-SCH-*)

Rules for params_schema and output_schema validation.
"""
from typing import Any, Dict, List, Optional
import ast

from ..types import Severity, ValidationIssue
from . import register_rule
from .base import MetadataRule


@register_rule
class ParamsSchemaRequired(MetadataRule):
    """CORE-SCH-001: params_schema is required for stable modules."""

    rule_id = "CORE-SCH-001"
    description = "params_schema is required"
    category = "schema"
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

        params_schema = metadata.get("params_schema")
        stability = metadata.get("stability", "stable")

        severity = cls.get_severity(stability)

        if params_schema is None:
            issues.append(cls.create_issue(
                message="params_schema is required",
                module_id=module_id,
                severity=severity,
                suggestion="Add params_schema with type and properties",
            ))
        elif not isinstance(params_schema, dict):
            issues.append(cls.create_issue(
                message=f"params_schema must be a dict, got {type(params_schema).__name__}",
                module_id=module_id,
            ))

        return issues


@register_rule
class OutputSchemaRequired(MetadataRule):
    """CORE-SCH-002: output_schema is required."""

    rule_id = "CORE-SCH-002"
    description = "output_schema is required"
    category = "schema"
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

        output_schema = metadata.get("output_schema")
        stability = metadata.get("stability", "stable")

        severity = cls.get_severity(stability)

        if output_schema is None:
            issues.append(cls.create_issue(
                message="output_schema is required",
                module_id=module_id,
                severity=severity,
                suggestion="Add output_schema with type and properties",
            ))
        elif not isinstance(output_schema, dict):
            issues.append(cls.create_issue(
                message=f"output_schema must be a dict, got {type(output_schema).__name__}",
                module_id=module_id,
            ))

        return issues


@register_rule
class PropertyHasType(MetadataRule):
    """CORE-SCH-003: Every property in schema should have a type."""

    rule_id = "CORE-SCH-003"
    description = "Schema properties must have type"
    category = "schema"
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

        for schema_name in ["params_schema", "output_schema"]:
            schema = metadata.get(schema_name, {})
            if not isinstance(schema, dict):
                continue

            properties = schema.get("properties", {})
            if not isinstance(properties, dict):
                continue

            for prop_name, prop_def in properties.items():
                if isinstance(prop_def, dict) and "type" not in prop_def:
                    issues.append(cls.create_issue(
                        message=f"{schema_name}.properties.{prop_name} is missing 'type'",
                        module_id=module_id,
                        suggestion=f"Add type to {prop_name} (e.g., 'string', 'integer', 'boolean')",
                    ))

        return issues


@register_rule
class RequiredDefaultConflict(MetadataRule):
    """CORE-SCH-004: Required fields should not have defaults."""

    rule_id = "CORE-SCH-004"
    description = "Required field with default is contradictory"
    category = "schema"
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

        params_schema = metadata.get("params_schema", {})
        if not isinstance(params_schema, dict):
            return issues

        required = set(params_schema.get("required", []))
        properties = params_schema.get("properties", {})

        if not isinstance(properties, dict):
            return issues

        for prop_name, prop_def in properties.items():
            if prop_name in required and isinstance(prop_def, dict):
                if "default" in prop_def:
                    issues.append(cls.create_issue(
                        message=f"'{prop_name}' is required but has a default value. This is contradictory.",
                        module_id=module_id,
                        suggestion=f"Either remove '{prop_name}' from required or remove the default",
                    ))

        return issues


@register_rule
class PropertyDescription(MetadataRule):
    """CORE-SCH-005: Properties should have descriptions."""

    rule_id = "CORE-SCH-005"
    description = "Properties should have descriptions"
    category = "schema"
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

        params_schema = metadata.get("params_schema", {})
        if not isinstance(params_schema, dict):
            return issues

        properties = params_schema.get("properties", {})
        if not isinstance(properties, dict):
            return issues

        missing_desc = []
        for prop_name, prop_def in properties.items():
            if isinstance(prop_def, dict) and "description" not in prop_def:
                missing_desc.append(prop_name)

        if missing_desc:
            issues.append(cls.create_issue(
                message=f"Properties missing descriptions: {', '.join(missing_desc[:5])}{'...' if len(missing_desc) > 5 else ''}",
                module_id=module_id,
                suggestion="Add description field to help users understand each parameter",
            ))

        return issues


@register_rule
class ValidJsonSchemaType(MetadataRule):
    """CORE-SCH-006: Schema types must be valid JSON Schema types."""

    rule_id = "CORE-SCH-006"
    description = "Schema types must be valid"
    category = "schema"
    default_severity = Severity.ERROR
    stability_aware = False

    VALID_TYPES = {"string", "number", "integer", "boolean", "array", "object", "null"}

    @classmethod
    def validate(
        cls,
        module_id: str,
        metadata: Dict[str, Any],
        source_code: Optional[str] = None,
        ast_tree: Optional[ast.AST] = None,
    ) -> List[ValidationIssue]:
        issues = []

        for schema_name in ["params_schema", "output_schema"]:
            schema = metadata.get(schema_name, {})
            if not isinstance(schema, dict):
                continue

            properties = schema.get("properties", {})
            if not isinstance(properties, dict):
                continue

            for prop_name, prop_def in properties.items():
                if isinstance(prop_def, dict):
                    prop_type = prop_def.get("type")
                    if prop_type and prop_type not in cls.VALID_TYPES:
                        issues.append(cls.create_issue(
                            message=f"{schema_name}.{prop_name} has invalid type: '{prop_type}'",
                            module_id=module_id,
                            suggestion=f"Use one of: {', '.join(sorted(cls.VALID_TYPES))}",
                        ))

        return issues
