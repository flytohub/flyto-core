"""
Schema Validator for Atomic Modules

Validates that all modules have complete params_schema and output_schema.
This ensures VarCatalog can properly introspect module interfaces for UI.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
from enum import Enum


class ValidationSeverity(Enum):
    ERROR = "error"      # Must fix - blocks CI
    WARNING = "warning"  # Should fix - logged but passes
    INFO = "info"        # Nice to have


# Valid data types for schema
VALID_DATA_TYPES: Set[str] = {
    "any",
    "string",
    "number",
    "boolean",
    "object",
    "array",
    "json",
    "table",
    "file",
    "image",
    "binary",
    "html",
    "xml",
}


@dataclass
class SchemaIssue:
    """Single schema validation issue."""
    module_id: str
    severity: ValidationSeverity
    field: str
    message: str
    hint: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "module_id": self.module_id,
            "severity": self.severity.value,
            "field": self.field,
            "message": self.message,
        }
        if self.hint:
            result["hint"] = self.hint
        return result


@dataclass
class ValidationResult:
    """Result of validating all modules."""
    total_modules: int = 0
    valid_modules: int = 0
    issues: List[SchemaIssue] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == ValidationSeverity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == ValidationSeverity.WARNING)

    @property
    def is_valid(self) -> bool:
        return self.error_count == 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_modules": self.total_modules,
            "valid_modules": self.valid_modules,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "is_valid": self.is_valid,
            "issues": [i.to_dict() for i in self.issues],
        }

    def summary(self) -> str:
        lines = [
            f"Schema Validation Summary",
            f"=" * 40,
            f"Total modules:  {self.total_modules}",
            f"Valid modules:  {self.valid_modules}",
            f"Errors:         {self.error_count}",
            f"Warnings:       {self.warning_count}",
            f"Status:         {'PASS' if self.is_valid else 'FAIL'}",
        ]
        return "\n".join(lines)


class SchemaValidator:
    """
    Validates module schemas for completeness and correctness.

    Usage:
        from core.modules.registry import ModuleRegistry

        validator = SchemaValidator()
        result = validator.validate_all(ModuleRegistry._metadata)

        if not result.is_valid:
            for issue in result.issues:
                print(f"[{issue.severity.value}] {issue.module_id}: {issue.message}")
    """

    def __init__(
        self,
        require_params_schema: bool = True,
        require_output_schema: bool = True,
        require_output_type: bool = True,
        require_output_description: bool = True,
    ):
        self.require_params_schema = require_params_schema
        self.require_output_schema = require_output_schema
        self.require_output_type = require_output_type
        self.require_output_description = require_output_description

    def validate_all(self, metadata: Dict[str, Dict[str, Any]]) -> ValidationResult:
        """
        Validate all module metadata.

        Args:
            metadata: Dict of module_id -> metadata from ModuleRegistry

        Returns:
            ValidationResult with all issues found
        """
        result = ValidationResult(total_modules=len(metadata))

        for module_id, meta in metadata.items():
            issues = self.validate_module(module_id, meta)
            result.issues.extend(issues)

            if not any(i.severity == ValidationSeverity.ERROR for i in issues):
                result.valid_modules += 1

        return result

    def validate_module(
        self, module_id: str, metadata: Dict[str, Any]
    ) -> List[SchemaIssue]:
        """
        Validate a single module's schema.

        Args:
            module_id: Module identifier
            metadata: Module metadata

        Returns:
            List of SchemaIssue found
        """
        issues: List[SchemaIssue] = []

        # Check params_schema
        if self.require_params_schema:
            issues.extend(self._validate_params_schema(module_id, metadata))

        # Check output_schema
        if self.require_output_schema:
            issues.extend(self._validate_output_schema(module_id, metadata))

        # Check input/output types
        issues.extend(self._validate_io_types(module_id, metadata))

        return issues

    def _validate_params_schema(
        self, module_id: str, metadata: Dict[str, Any]
    ) -> List[SchemaIssue]:
        """Validate params_schema exists and is valid."""
        issues: List[SchemaIssue] = []
        params_schema = metadata.get("params_schema")

        if params_schema is None:
            issues.append(
                SchemaIssue(
                    module_id=module_id,
                    severity=ValidationSeverity.WARNING,
                    field="params_schema",
                    message="Missing params_schema",
                    hint="Add params_schema using compose() and presets",
                )
            )
            return issues

        if not isinstance(params_schema, dict):
            issues.append(
                SchemaIssue(
                    module_id=module_id,
                    severity=ValidationSeverity.ERROR,
                    field="params_schema",
                    message=f"params_schema must be dict, got {type(params_schema).__name__}",
                )
            )
            return issues

        # Validate each param field
        for param_name, param_def in params_schema.items():
            if not isinstance(param_def, dict):
                continue

            param_type = param_def.get("type")
            # param_type can be a string or list, skip validation for complex types
            if param_type and isinstance(param_type, str):
                if param_type not in VALID_DATA_TYPES and param_type != "select":
                    issues.append(
                        SchemaIssue(
                            module_id=module_id,
                            severity=ValidationSeverity.WARNING,
                            field=f"params_schema.{param_name}.type",
                            message=f"Unknown type '{param_type}'",
                            hint=f"Valid types: {', '.join(sorted(VALID_DATA_TYPES))}",
                        )
                    )

        return issues

    def _validate_output_schema(
        self, module_id: str, metadata: Dict[str, Any]
    ) -> List[SchemaIssue]:
        """Validate output_schema exists and is valid."""
        issues: List[SchemaIssue] = []
        output_schema = metadata.get("output_schema")

        if output_schema is None:
            issues.append(
                SchemaIssue(
                    module_id=module_id,
                    severity=ValidationSeverity.ERROR,
                    field="output_schema",
                    message="Missing output_schema - UI cannot connect to this module's output",
                    hint="Add output_schema with type and description for each output field",
                )
            )
            return issues

        if not isinstance(output_schema, dict):
            issues.append(
                SchemaIssue(
                    module_id=module_id,
                    severity=ValidationSeverity.ERROR,
                    field="output_schema",
                    message=f"output_schema must be dict, got {type(output_schema).__name__}",
                )
            )
            return issues

        if len(output_schema) == 0:
            issues.append(
                SchemaIssue(
                    module_id=module_id,
                    severity=ValidationSeverity.ERROR,
                    field="output_schema",
                    message="output_schema is empty",
                    hint="Define at least one output field",
                )
            )
            return issues

        # Validate each output field
        for field_name, field_def in output_schema.items():
            if not isinstance(field_def, dict):
                issues.append(
                    SchemaIssue(
                        module_id=module_id,
                        severity=ValidationSeverity.ERROR,
                        field=f"output_schema.{field_name}",
                        message=f"Field definition must be dict, got {type(field_def).__name__}",
                    )
                )
                continue

            # Check type
            if self.require_output_type:
                field_type = field_def.get("type")
                if not field_type:
                    issues.append(
                        SchemaIssue(
                            module_id=module_id,
                            severity=ValidationSeverity.ERROR,
                            field=f"output_schema.{field_name}.type",
                            message="Missing type in output field",
                            hint=f"Add type: one of {', '.join(sorted(VALID_DATA_TYPES))}",
                        )
                    )
                elif isinstance(field_type, str) and field_type not in VALID_DATA_TYPES:
                    issues.append(
                        SchemaIssue(
                            module_id=module_id,
                            severity=ValidationSeverity.WARNING,
                            field=f"output_schema.{field_name}.type",
                            message=f"Unknown type '{field_type}'",
                            hint=f"Valid types: {', '.join(sorted(VALID_DATA_TYPES))}",
                        )
                    )

            # Check description
            if self.require_output_description:
                if not field_def.get("description"):
                    issues.append(
                        SchemaIssue(
                            module_id=module_id,
                            severity=ValidationSeverity.WARNING,
                            field=f"output_schema.{field_name}.description",
                            message="Missing description in output field",
                            hint="Add description for better UI display",
                        )
                    )

        return issues

    def _validate_io_types(
        self, module_id: str, metadata: Dict[str, Any]
    ) -> List[SchemaIssue]:
        """Validate input_types and output_types for connection validation."""
        issues: List[SchemaIssue] = []

        # input_types is optional but recommended
        if not metadata.get("input_types"):
            issues.append(
                SchemaIssue(
                    module_id=module_id,
                    severity=ValidationSeverity.INFO,
                    field="input_types",
                    message="Missing input_types",
                    hint="Add input_types for connection type checking",
                )
            )

        # output_types is optional but recommended
        if not metadata.get("output_types"):
            issues.append(
                SchemaIssue(
                    module_id=module_id,
                    severity=ValidationSeverity.INFO,
                    field="output_types",
                    message="Missing output_types",
                    hint="Add output_types for connection type checking",
                )
            )

        return issues


def validate_registry() -> ValidationResult:
    """
    Convenience function to validate all registered modules.

    Usage:
        from core.modules.schema_validator import validate_registry

        result = validate_registry()
        print(result.summary())
    """
    from .registry import ModuleRegistry

    validator = SchemaValidator()
    return validator.validate_all(ModuleRegistry._metadata)
