"""
Module Validation Utilities

Provides standardized validation functions and error types for module execution.
All modules should use these utilities for consistent error handling.
"""
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Type, Union

from ..constants import ErrorCode


@dataclass
class ModuleError:
    """
    Standardized error structure for module execution.

    Usage:
        error = ModuleError(
            code=ErrorCode.MISSING_PARAM,
            message="Missing required parameter: url",
            field="url",
            hint="Please provide a valid URL"
        )
        return error.to_result()

    Attributes:
        code: Error code from ErrorCode class
        message: Human-readable error message
        field: The field/parameter that caused the error (optional)
        hint: Suggestion for fixing the error (optional)
        node_id: Workflow node ID for debugging (optional)
    """

    code: str
    message: str
    field: Optional[str] = None
    hint: Optional[str] = None
    node_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, excluding None values."""
        result = {"code": self.code, "message": self.message}
        if self.field:
            result["field"] = self.field
        if self.hint:
            result["hint"] = self.hint
        if self.node_id:
            result["node_id"] = self.node_id
        return result

    def to_result(self) -> Dict[str, Any]:
        """Convert to standard module result format."""
        return {
            "ok": False,
            "error": self.to_dict()
        }


def validate_required(
    params: Dict[str, Any],
    field: str,
    label: Optional[str] = None
) -> Optional[ModuleError]:
    """
    Validate that a required parameter is present and not None.

    Args:
        params: Parameter dictionary
        field: Field name to validate
        label: Human-readable label for error messages

    Returns:
        ModuleError if validation fails, None if valid
    """
    if field not in params or params[field] is None:
        display_name = label or field
        return ModuleError(
            code=ErrorCode.MISSING_PARAM,
            message=f"Missing required parameter: {display_name}",
            field=field,
            hint=f"Please provide the '{display_name}' parameter"
        )
    return None


def validate_type(
    params: Dict[str, Any],
    field: str,
    expected_type: Union[Type, tuple],
    label: Optional[str] = None
) -> Optional[ModuleError]:
    """
    Validate that a parameter has the expected type.

    Args:
        params: Parameter dictionary
        field: Field name to validate
        expected_type: Expected type or tuple of types
        label: Human-readable label for error messages

    Returns:
        ModuleError if validation fails, None if valid
    """
    if field not in params:
        return None  # Not present is not a type error

    value = params[field]
    if value is None:
        return None  # None values are handled by validate_required

    if not isinstance(value, expected_type):
        display_name = label or field
        type_name = expected_type.__name__ if hasattr(expected_type, '__name__') else str(expected_type)
        actual_type = type(value).__name__
        return ModuleError(
            code=ErrorCode.INVALID_PARAM_TYPE,
            message=f"Invalid type for '{display_name}': expected {type_name}, got {actual_type}",
            field=field,
            hint=f"Please provide a {type_name} value for '{display_name}'"
        )
    return None


def validate_not_empty(
    params: Dict[str, Any],
    field: str,
    label: Optional[str] = None
) -> Optional[ModuleError]:
    """
    Validate that a string/list parameter is not empty.

    Args:
        params: Parameter dictionary
        field: Field name to validate
        label: Human-readable label for error messages

    Returns:
        ModuleError if validation fails, None if valid
    """
    if field not in params:
        return None

    value = params[field]
    if value is None:
        return None

    display_name = label or field

    if isinstance(value, str) and not value.strip():
        return ModuleError(
            code=ErrorCode.INVALID_PARAM_VALUE,
            message=f"Parameter '{display_name}' cannot be empty",
            field=field,
            hint=f"Please provide a non-empty value for '{display_name}'"
        )

    if isinstance(value, (list, dict)) and len(value) == 0:
        return ModuleError(
            code=ErrorCode.INVALID_PARAM_VALUE,
            message=f"Parameter '{display_name}' cannot be empty",
            field=field,
            hint=f"Please provide at least one item for '{display_name}'"
        )

    return None


def validate_range(
    params: Dict[str, Any],
    field: str,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
    label: Optional[str] = None
) -> Optional[ModuleError]:
    """
    Validate that a numeric parameter is within range.

    Args:
        params: Parameter dictionary
        field: Field name to validate
        min_value: Minimum allowed value (inclusive)
        max_value: Maximum allowed value (inclusive)
        label: Human-readable label for error messages

    Returns:
        ModuleError if validation fails, None if valid
    """
    if field not in params or params[field] is None:
        return None

    value = params[field]
    display_name = label or field

    if not isinstance(value, (int, float)):
        return None  # Type validation handled separately

    if min_value is not None and value < min_value:
        return ModuleError(
            code=ErrorCode.PARAM_OUT_OF_RANGE,
            message=f"Parameter '{display_name}' must be at least {min_value}, got {value}",
            field=field,
            hint=f"Please provide a value >= {min_value}"
        )

    if max_value is not None and value > max_value:
        return ModuleError(
            code=ErrorCode.PARAM_OUT_OF_RANGE,
            message=f"Parameter '{display_name}' must be at most {max_value}, got {value}",
            field=field,
            hint=f"Please provide a value <= {max_value}"
        )

    return None


def validate_enum(
    params: Dict[str, Any],
    field: str,
    allowed_values: List[Any],
    label: Optional[str] = None
) -> Optional[ModuleError]:
    """
    Validate that a parameter value is in allowed list.

    Args:
        params: Parameter dictionary
        field: Field name to validate
        allowed_values: List of allowed values
        label: Human-readable label for error messages

    Returns:
        ModuleError if validation fails, None if valid
    """
    if field not in params or params[field] is None:
        return None

    value = params[field]
    display_name = label or field

    if value not in allowed_values:
        allowed_str = ", ".join(str(v) for v in allowed_values)
        return ModuleError(
            code=ErrorCode.INVALID_PARAM_VALUE,
            message=f"Invalid value for '{display_name}': '{value}'. Allowed: {allowed_str}",
            field=field,
            hint=f"Choose one of: {allowed_str}"
        )

    return None


def validate_url(
    params: Dict[str, Any],
    field: str,
    label: Optional[str] = None
) -> Optional[ModuleError]:
    """
    Validate that a parameter is a valid URL.

    Args:
        params: Parameter dictionary
        field: Field name to validate
        label: Human-readable label for error messages

    Returns:
        ModuleError if validation fails, None if valid
    """
    if field not in params or params[field] is None:
        return None

    value = params[field]
    display_name = label or field

    if not isinstance(value, str):
        return None  # Type validation handled separately

    # Basic URL validation
    if not (value.startswith("http://") or value.startswith("https://")):
        return ModuleError(
            code=ErrorCode.INVALID_PARAM_VALUE,
            message=f"Invalid URL for '{display_name}': must start with http:// or https://",
            field=field,
            hint="Please provide a valid URL starting with http:// or https://"
        )

    return None


def validate_all(*errors: Optional[ModuleError]) -> Optional[ModuleError]:
    """
    Run multiple validations and return the first error found.

    Usage:
        error = validate_all(
            validate_required(params, 'url'),
            validate_url(params, 'url'),
            validate_type(params, 'timeout', int)
        )
        if error:
            return error.to_result()

    Args:
        *errors: Variable number of validation results

    Returns:
        First ModuleError found, or None if all valid
    """
    for error in errors:
        if error is not None:
            return error
    return None


def collect_errors(*errors: Optional[ModuleError]) -> List[ModuleError]:
    """
    Collect all validation errors (non-None values).

    Usage:
        errors = collect_errors(
            validate_required(params, 'url'),
            validate_required(params, 'method'),
            validate_type(params, 'timeout', int)
        )
        if errors:
            return {"ok": False, "errors": [e.to_dict() for e in errors]}

    Args:
        *errors: Variable number of validation results

    Returns:
        List of all ModuleError objects found
    """
    return [e for e in errors if e is not None]


def success(data: Any = None, message: Optional[str] = None) -> Dict[str, Any]:
    """
    Create a standard success result.

    Args:
        data: Result data
        message: Optional success message

    Returns:
        Standard success result dict
    """
    result = {"ok": True}
    if data is not None:
        result["data"] = data
    if message:
        result["message"] = message
    return result


def failure(
    code: str,
    message: str,
    field: Optional[str] = None,
    hint: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a standard failure result.

    Args:
        code: Error code from ErrorCode class
        message: Human-readable error message
        field: Field that caused the error
        hint: Suggestion for fixing the error

    Returns:
        Standard failure result dict
    """
    return ModuleError(
        code=code,
        message=message,
        field=field,
        hint=hint
    ).to_result()


# =============================================================================
# Field-Level Validation (ITEM_PIPELINE_SPEC.md Section 7)
# =============================================================================


@dataclass
class ValidationError:
    """
    Single validation error with field path.

    The path follows dot notation: "params.url", "params.headers[0].value"
    This allows frontend to map errors directly to form fields.
    """
    path: str              # Field path, e.g. "params.url" or "params.headers[0].value"
    message: str           # Human-readable error message
    code: str              # Error code for programmatic handling

    # Optional details
    expected: Optional[Any] = None
    actual: Optional[Any] = None
    suggestion: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "path": self.path,
            "message": self.message,
            "code": self.code,
        }
        if self.expected is not None:
            result["expected"] = self.expected
        if self.actual is not None:
            result["actual"] = self.actual
        if self.suggestion:
            result["suggestion"] = self.suggestion
        return result


@dataclass
class ValidationWarning:
    """
    Validation warning (non-blocking).

    Warnings don't prevent execution but should be shown to user.
    """
    path: str
    message: str
    code: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "path": self.path,
            "message": self.message,
            "code": self.code,
        }


@dataclass
class ValidationResult:
    """
    Complete validation result with field-level errors.

    This structure supports:
    - Multiple errors per validation
    - Field path mapping for UI
    - Warnings for non-blocking issues
    - Easy serialization for API responses

    Example:
        result = ValidationResult(
            valid=False,
            errors=[
                ValidationError(
                    path="params.url",
                    message="URL is required",
                    code="REQUIRED"
                ),
                ValidationError(
                    path="params.timeout",
                    message="Timeout must be positive",
                    code="RANGE",
                    expected="> 0",
                    actual=-1
                )
            ]
        )
    """
    valid: bool
    errors: List[ValidationError] = None
    warnings: List[ValidationWarning] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []

    def add_error(
        self,
        path: str,
        message: str,
        code: str,
        expected: Optional[Any] = None,
        actual: Optional[Any] = None,
        suggestion: Optional[str] = None
    ) -> "ValidationResult":
        """Add an error and mark as invalid."""
        self.errors.append(ValidationError(
            path=path,
            message=message,
            code=code,
            expected=expected,
            actual=actual,
            suggestion=suggestion
        ))
        self.valid = False
        return self

    def add_warning(
        self,
        path: str,
        message: str,
        code: str
    ) -> "ValidationResult":
        """Add a warning (doesn't affect validity)."""
        self.warnings.append(ValidationWarning(
            path=path,
            message=message,
            code=code
        ))
        return self

    def get_errors_for_field(self, field_path: str) -> List[ValidationError]:
        """Get all errors for a specific field path."""
        return [e for e in self.errors if e.path == field_path]

    def has_error_for_field(self, field_path: str) -> bool:
        """Check if a field has any errors."""
        return any(e.path == field_path for e in self.errors)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        result = {
            "valid": self.valid,
            "errors": [e.to_dict() for e in self.errors],
        }
        if self.warnings:
            result["warnings"] = [w.to_dict() for w in self.warnings]
        return result

    @classmethod
    def success(cls) -> "ValidationResult":
        """Create a successful validation result."""
        return cls(valid=True)

    @classmethod
    def from_errors(cls, errors: List[ValidationError]) -> "ValidationResult":
        """Create result from list of errors."""
        return cls(valid=len(errors) == 0, errors=errors)


class SchemaValidator:
    """
    Validate parameters against a schema with field-level error reporting.

    Supports:
    - Required field validation
    - Type checking
    - Range validation
    - Enum validation
    - showIf/hideIf conditional fields

    Example:
        validator = SchemaValidator()
        result = validator.validate(params, schema)
        if not result.valid:
            # Send errors to frontend
            return {"ok": False, "validation": result.to_dict()}
    """

    def validate(
        self,
        params: Dict[str, Any],
        schema: Dict[str, Dict[str, Any]],
        path_prefix: str = "params"
    ) -> ValidationResult:
        """
        Validate parameters against schema.

        Args:
            params: Parameter values to validate
            schema: Schema definition with field configs
            path_prefix: Prefix for error paths (default: "params")

        Returns:
            ValidationResult with all errors found
        """
        result = ValidationResult(valid=True)

        for field_key, field_schema in schema.items():
            field_errors = self._validate_field(
                path=f"{path_prefix}.{field_key}",
                value=params.get(field_key),
                schema=field_schema,
                params=params
            )
            result.errors.extend(field_errors)

        result.valid = len(result.errors) == 0
        return result

    def _validate_field(
        self,
        path: str,
        value: Any,
        schema: Dict[str, Any],
        params: Dict[str, Any]
    ) -> List[ValidationError]:
        """Validate a single field against its schema."""
        errors = []

        # Check conditional visibility
        if not self._should_validate(schema, params):
            return []  # Field not shown, skip validation

        # Required check
        if schema.get('required') and value in (None, '', []):
            errors.append(ValidationError(
                path=path,
                message=f"{schema.get('label', path)} is required",
                code="REQUIRED"
            ))
            return errors  # Don't continue if required field is missing

        # Skip other validations if value is None/empty
        if value in (None, '', []):
            return errors

        # Type check
        expected_type = schema.get('type')
        if expected_type:
            type_error = self._validate_type(path, value, expected_type, schema)
            if type_error:
                errors.append(type_error)
                return errors  # Don't continue if type is wrong

        # Range check for numbers
        if expected_type == 'number' and isinstance(value, (int, float)):
            range_errors = self._validate_range(path, value, schema)
            errors.extend(range_errors)

        # Enum check
        options = schema.get('options')
        if options:
            enum_error = self._validate_enum(path, value, options, schema)
            if enum_error:
                errors.append(enum_error)

        # Custom validation rules
        validation_rules = schema.get('validation')
        if validation_rules:
            rule_errors = self._validate_rules(path, value, validation_rules)
            errors.extend(rule_errors)

        return errors

    def _should_validate(
        self,
        schema: Dict[str, Any],
        params: Dict[str, Any]
    ) -> bool:
        """Check if field should be validated based on showIf/hideIf."""
        if 'showIf' in schema:
            if not self._evaluate_condition(schema['showIf'], params):
                return False
        if 'hideIf' in schema:
            if self._evaluate_condition(schema['hideIf'], params):
                return False
        return True

    def _evaluate_condition(
        self,
        condition: Dict[str, Any],
        params: Dict[str, Any]
    ) -> bool:
        """
        Evaluate a condition expression.

        Supports:
        - {"field": "value"} - equality
        - {"field": {"$ne": "value"}} - not equal
        - {"field": {"$in": ["a", "b"]}} - in list
        - {"field": {"$exists": True}} - field exists and not empty
        - {"$and": [...]} - all conditions true
        - {"$or": [...]} - any condition true
        """
        if '$and' in condition:
            return all(self._evaluate_condition(c, params) for c in condition['$and'])

        if '$or' in condition:
            return any(self._evaluate_condition(c, params) for c in condition['$or'])

        for field, expected in condition.items():
            if field.startswith('$'):
                continue  # Skip operators

            value = params.get(field)

            if isinstance(expected, dict):
                if '$ne' in expected:
                    if value == expected['$ne']:
                        return False
                elif '$in' in expected:
                    if value not in expected['$in']:
                        return False
                elif '$exists' in expected:
                    exists = value is not None and value != ''
                    if expected['$exists'] != exists:
                        return False
            else:
                if value != expected:
                    return False

        return True

    def _validate_type(
        self,
        path: str,
        value: Any,
        expected_type: str,
        schema: Dict[str, Any]
    ) -> Optional[ValidationError]:
        """Validate field type."""
        type_map = {
            'string': str,
            'number': (int, float),
            'integer': int,
            'boolean': bool,
            'array': list,
            'object': dict,
        }

        python_type = type_map.get(expected_type)
        if python_type and not isinstance(value, python_type):
            return ValidationError(
                path=path,
                message=f"Expected {expected_type}, got {type(value).__name__}",
                code="TYPE",
                expected=expected_type,
                actual=type(value).__name__
            )
        return None

    def _validate_range(
        self,
        path: str,
        value: Union[int, float],
        schema: Dict[str, Any]
    ) -> List[ValidationError]:
        """Validate numeric range."""
        errors = []
        min_val = schema.get('min')
        max_val = schema.get('max')

        if min_val is not None and value < min_val:
            errors.append(ValidationError(
                path=path,
                message=f"Value must be at least {min_val}",
                code="MIN",
                expected=f">= {min_val}",
                actual=value
            ))

        if max_val is not None and value > max_val:
            errors.append(ValidationError(
                path=path,
                message=f"Value must be at most {max_val}",
                code="MAX",
                expected=f"<= {max_val}",
                actual=value
            ))

        return errors

    def _validate_enum(
        self,
        path: str,
        value: Any,
        options: List[Dict[str, Any]],
        schema: Dict[str, Any]
    ) -> Optional[ValidationError]:
        """Validate value is in allowed options."""
        allowed_values = [opt.get('value') for opt in options if 'value' in opt]
        if value not in allowed_values:
            return ValidationError(
                path=path,
                message=f"Invalid value: {value}",
                code="ENUM",
                expected=allowed_values,
                actual=value
            )
        return None

    def _validate_rules(
        self,
        path: str,
        value: Any,
        rules: Dict[str, Any]
    ) -> List[ValidationError]:
        """Validate against custom rules."""
        errors = []

        # Pattern validation
        pattern = rules.get('pattern')
        if pattern and isinstance(value, str):
            import re
            if not re.match(pattern, value):
                errors.append(ValidationError(
                    path=path,
                    message=rules.get('patternMessage', f"Value doesn't match pattern"),
                    code="PATTERN",
                    expected=pattern,
                    actual=value
                ))

        # Length validation
        min_length = rules.get('minLength')
        max_length = rules.get('maxLength')
        if isinstance(value, (str, list)):
            if min_length is not None and len(value) < min_length:
                errors.append(ValidationError(
                    path=path,
                    message=f"Minimum length is {min_length}",
                    code="MIN_LENGTH",
                    expected=f">= {min_length} characters",
                    actual=len(value)
                ))
            if max_length is not None and len(value) > max_length:
                errors.append(ValidationError(
                    path=path,
                    message=f"Maximum length is {max_length}",
                    code="MAX_LENGTH",
                    expected=f"<= {max_length} characters",
                    actual=len(value)
                ))

        return errors
