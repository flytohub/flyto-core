"""
Module Errors - Exception hierarchy for module execution.

This module provides exception classes that modules can raise.
The runtime will catch these and convert them to ModuleResult failures.

Design Principles:
- Single responsibility: Only handles exception definitions
- Atomic: Each error class represents one error category
- No hardcoding: Uses ErrorCode from constants

Usage:
    from core.modules.errors import ValidationError, TimeoutError

    # In module execution
    if not url:
        raise ValidationError("URL is required", field="url")

    # Runtime catches and converts to:
    # ModuleResult(ok=False, error="URL is required", error_code="VALIDATION_ERROR")
"""
from typing import Any, Dict, Optional

from ..constants import ErrorCode


class ModuleError(Exception):
    """
    Base exception for all module errors.

    Modules should raise subclasses of this exception for predictable errors.
    The runtime will catch these and convert them to ModuleResult failures.

    Attributes:
        code: Error code from ErrorCode class
        message: Human-readable error message
        details: Additional error context
        field: Parameter/field that caused the error
        hint: Suggestion for fixing the error
    """

    code: str = ErrorCode.EXECUTION_ERROR

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        field: Optional[str] = None,
        hint: Optional[str] = None
    ):
        """
        Initialize ModuleError.

        Args:
            message: Human-readable error message
            code: Override default error code
            details: Additional error context
            field: Parameter/field that caused the error
            hint: Suggestion for fixing the error
        """
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        self.details = details or {}
        self.field = field
        self.hint = hint

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary format.

        Returns:
            Dictionary with code, message, and optional details
        """
        result: Dict[str, Any] = {
            "code": self.code,
            "message": self.message
        }
        if self.field:
            result["field"] = self.field
        if self.hint:
            result["hint"] = self.hint
        if self.details:
            result["details"] = self.details
        return result

    def __str__(self) -> str:
        """String representation."""
        parts = [f"[{self.code}] {self.message}"]
        if self.field:
            parts.append(f"(field: {self.field})")
        return " ".join(parts)

    def __repr__(self) -> str:
        """Debug representation."""
        return f"{self.__class__.__name__}({self.code!r}, {self.message!r})"


# =============================================================================
# Parameter Validation Errors
# =============================================================================

class ValidationError(ModuleError):
    """
    Parameter validation failed.

    Raised when module parameters don't meet requirements.

    Examples:
        raise ValidationError("URL is required", field="url")
        raise ValidationError("Timeout must be positive", field="timeout_ms")
    """

    code = ErrorCode.MISSING_PARAM

    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        hint: Optional[str] = None,
        **kwargs
    ):
        super().__init__(message, field=field, hint=hint, **kwargs)


class InvalidTypeError(ModuleError):
    """
    Parameter has invalid type.

    Raised when a parameter value doesn't match expected type.
    """

    code = ErrorCode.INVALID_PARAM_TYPE

    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        expected_type: Optional[str] = None,
        actual_type: Optional[str] = None,
        **kwargs
    ):
        details = kwargs.pop("details", {})
        if expected_type:
            details["expected_type"] = expected_type
        if actual_type:
            details["actual_type"] = actual_type
        super().__init__(message, field=field, details=details, **kwargs)


class InvalidValueError(ModuleError):
    """
    Parameter has invalid value.

    Raised when a parameter value is out of range or not in allowed set.
    """

    code = ErrorCode.INVALID_PARAM_VALUE


class ParamOutOfRangeError(ModuleError):
    """
    Numeric parameter out of allowed range.
    """

    code = ErrorCode.PARAM_OUT_OF_RANGE


# =============================================================================
# Configuration Errors
# =============================================================================

class ConfigMissingError(ModuleError):
    """
    Required configuration is missing.

    Raised when environment variables or config values are not set.

    Examples:
        raise ConfigMissingError("OPENAI_API_KEY not set")
    """

    code = ErrorCode.MISSING_CREDENTIAL


class InvalidConfigError(ModuleError):
    """
    Configuration value is invalid.
    """

    code = ErrorCode.INVALID_CONFIG


# =============================================================================
# Execution Errors
# =============================================================================

class ExecutionTimeoutError(ModuleError):
    """
    Module execution timed out.

    Note: Named ExecutionTimeoutError to avoid conflict with built-in TimeoutError.
    """

    code = ErrorCode.TIMEOUT

    def __init__(
        self,
        message: str,
        timeout_ms: Optional[int] = None,
        **kwargs
    ):
        details = kwargs.pop("details", {})
        if timeout_ms:
            details["timeout_ms"] = timeout_ms
        super().__init__(message, details=details, **kwargs)


class RetryExhaustedError(ModuleError):
    """
    All retry attempts failed.
    """

    code = ErrorCode.RETRY_EXHAUSTED

    def __init__(
        self,
        message: str,
        attempts: Optional[int] = None,
        last_error: Optional[str] = None,
        **kwargs
    ):
        details = kwargs.pop("details", {})
        if attempts:
            details["attempts"] = attempts
        if last_error:
            details["last_error"] = last_error
        super().__init__(message, details=details, **kwargs)


class CancelledError(ModuleError):
    """
    Module execution was cancelled.
    """

    code = ErrorCode.CANCELLED


# =============================================================================
# Network/API Errors
# =============================================================================

class NetworkError(ModuleError):
    """
    Network connection failed.

    Raised for connection errors, DNS failures, etc.
    """

    code = ErrorCode.NETWORK_ERROR

    def __init__(
        self,
        message: str,
        url: Optional[str] = None,
        status_code: Optional[int] = None,
        **kwargs
    ):
        details = kwargs.pop("details", {})
        if url:
            details["url"] = url
        if status_code:
            details["status_code"] = status_code
        super().__init__(message, details=details, **kwargs)


class APIError(ModuleError):
    """
    External API returned an error.
    """

    code = ErrorCode.API_ERROR

    def __init__(
        self,
        message: str,
        api_name: Optional[str] = None,
        status_code: Optional[int] = None,
        response_body: Optional[str] = None,
        **kwargs
    ):
        details = kwargs.pop("details", {})
        if api_name:
            details["api_name"] = api_name
        if status_code:
            details["status_code"] = status_code
        if response_body:
            details["response_body"] = response_body[:500]  # Truncate long responses
        super().__init__(message, details=details, **kwargs)


class RateLimitedError(ModuleError):
    """
    Rate limit exceeded.
    """

    code = ErrorCode.RATE_LIMITED

    def __init__(
        self,
        message: str,
        retry_after: Optional[int] = None,
        **kwargs
    ):
        details = kwargs.pop("details", {})
        if retry_after:
            details["retry_after_seconds"] = retry_after
        hint = kwargs.pop("hint", None) or f"Wait {retry_after}s before retrying" if retry_after else None
        super().__init__(message, details=details, hint=hint, **kwargs)


class AuthenticationError(ModuleError):
    """
    Authentication failed (401).
    """

    code = ErrorCode.UNAUTHORIZED


class ForbiddenError(ModuleError):
    """
    Access forbidden (403).
    """

    code = ErrorCode.FORBIDDEN


class NotFoundError(ModuleError):
    """
    Resource not found (404).
    """

    code = ErrorCode.NOT_FOUND


# =============================================================================
# Browser/Element Errors
# =============================================================================

class ElementNotFoundError(ModuleError):
    """
    DOM element not found.
    """

    code = ErrorCode.ELEMENT_NOT_FOUND

    def __init__(
        self,
        message: str,
        selector: Optional[str] = None,
        **kwargs
    ):
        details = kwargs.pop("details", {})
        if selector:
            details["selector"] = selector
        super().__init__(message, details=details, **kwargs)


class ElementNotVisibleError(ModuleError):
    """
    Element exists but not visible.
    """

    code = ErrorCode.ELEMENT_NOT_VISIBLE


class NavigationError(ModuleError):
    """
    Page navigation failed.
    """

    code = ErrorCode.NAVIGATION_ERROR


class BrowserError(ModuleError):
    """
    Browser operation failed.
    """

    code = ErrorCode.BROWSER_ERROR


# =============================================================================
# File Errors
# =============================================================================

class FileNotFoundError(ModuleError):
    """
    File does not exist.

    Note: Named to match common pattern, shadows built-in but more specific.
    """

    code = ErrorCode.FILE_NOT_FOUND

    def __init__(
        self,
        message: str,
        path: Optional[str] = None,
        **kwargs
    ):
        details = kwargs.pop("details", {})
        if path:
            details["path"] = path
        super().__init__(message, details=details, **kwargs)


class FileAccessDeniedError(ModuleError):
    """
    File access denied (permissions).
    """

    code = ErrorCode.FILE_ACCESS_DENIED


class FileReadError(ModuleError):
    """
    Failed to read file.
    """

    code = ErrorCode.FILE_READ_ERROR


class FileWriteError(ModuleError):
    """
    Failed to write file.
    """

    code = ErrorCode.FILE_WRITE_ERROR


# =============================================================================
# Type/Connection Errors
# =============================================================================

class TypeMismatchError(ModuleError):
    """
    Type mismatch in workflow connection.
    """

    code = ErrorCode.TYPE_MISMATCH


class InvalidConnectionError(ModuleError):
    """
    Invalid workflow connection.
    """

    code = ErrorCode.INVALID_CONNECTION


class DependencyError(ModuleError):
    """
    Module dependency not met.
    """

    code = ErrorCode.DEPENDENCY_ERROR


class ModuleNotFoundError(ModuleError):
    """
    Module not registered.
    """

    code = ErrorCode.MODULE_NOT_FOUND


# =============================================================================
# AI/LLM Errors
# =============================================================================

class AIResponseError(ModuleError):
    """
    AI model returned invalid response.
    """

    code = ErrorCode.AI_RESPONSE_ERROR


class AIContextTooLongError(ModuleError):
    """
    Input exceeds model context limit.
    """

    code = ErrorCode.AI_CONTEXT_TOO_LONG

    def __init__(
        self,
        message: str,
        token_count: Optional[int] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ):
        details = kwargs.pop("details", {})
        if token_count:
            details["token_count"] = token_count
        if max_tokens:
            details["max_tokens"] = max_tokens
        super().__init__(message, details=details, **kwargs)


class ModelNotAvailableError(ModuleError):
    """
    AI model not available.
    """

    code = ErrorCode.MODEL_NOT_AVAILABLE


# =============================================================================
# Unsupported Operation
# =============================================================================

class UnsupportedError(ModuleError):
    """
    Operation not supported.
    """

    code = ErrorCode.EXECUTION_ERROR

    def __init__(self, message: str, **kwargs):
        super().__init__(message, code="UNSUPPORTED", **kwargs)


# =============================================================================
# Error Factory
# =============================================================================

def error_from_code(code: str, message: str, **kwargs) -> ModuleError:
    """
    Create error from error code.

    Args:
        code: Error code from ErrorCode class
        message: Error message
        **kwargs: Additional error attributes

    Returns:
        Appropriate ModuleError subclass
    """
    error_map = {
        ErrorCode.MISSING_PARAM: ValidationError,
        ErrorCode.INVALID_PARAM_TYPE: InvalidTypeError,
        ErrorCode.INVALID_PARAM_VALUE: InvalidValueError,
        ErrorCode.PARAM_OUT_OF_RANGE: ParamOutOfRangeError,
        ErrorCode.TIMEOUT: ExecutionTimeoutError,
        ErrorCode.RETRY_EXHAUSTED: RetryExhaustedError,
        ErrorCode.CANCELLED: CancelledError,
        ErrorCode.NETWORK_ERROR: NetworkError,
        ErrorCode.API_ERROR: APIError,
        ErrorCode.RATE_LIMITED: RateLimitedError,
        ErrorCode.UNAUTHORIZED: AuthenticationError,
        ErrorCode.FORBIDDEN: ForbiddenError,
        ErrorCode.NOT_FOUND: NotFoundError,
        ErrorCode.ELEMENT_NOT_FOUND: ElementNotFoundError,
        ErrorCode.ELEMENT_NOT_VISIBLE: ElementNotVisibleError,
        ErrorCode.NAVIGATION_ERROR: NavigationError,
        ErrorCode.BROWSER_ERROR: BrowserError,
        ErrorCode.FILE_NOT_FOUND: FileNotFoundError,
        ErrorCode.FILE_ACCESS_DENIED: FileAccessDeniedError,
        ErrorCode.FILE_READ_ERROR: FileReadError,
        ErrorCode.FILE_WRITE_ERROR: FileWriteError,
        ErrorCode.TYPE_MISMATCH: TypeMismatchError,
        ErrorCode.INVALID_CONNECTION: InvalidConnectionError,
        ErrorCode.DEPENDENCY_ERROR: DependencyError,
        ErrorCode.MISSING_CREDENTIAL: ConfigMissingError,
        ErrorCode.INVALID_CONFIG: InvalidConfigError,
        ErrorCode.MODULE_NOT_FOUND: ModuleNotFoundError,
        ErrorCode.AI_RESPONSE_ERROR: AIResponseError,
        ErrorCode.AI_CONTEXT_TOO_LONG: AIContextTooLongError,
        ErrorCode.MODEL_NOT_AVAILABLE: ModelNotAvailableError,
    }

    error_class = error_map.get(code, ModuleError)
    return error_class(message, **kwargs)
