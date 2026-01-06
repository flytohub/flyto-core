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
