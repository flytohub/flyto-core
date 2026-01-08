"""
Tests for ModuleError exception hierarchy.

Tests the standardized module error classes.
"""
import pytest
from src.core.modules.errors import (
    ModuleError,
    ValidationError,
    InvalidTypeError,
    InvalidValueError,
    ConfigMissingError,
    ExecutionTimeoutError,
    NetworkError,
    APIError,
    RateLimitedError,
    AuthenticationError,
    NotFoundError,
    ElementNotFoundError,
    FileNotFoundError,
    error_from_code,
)
from src.core.constants import ErrorCode


class TestModuleError:
    """Test base ModuleError class."""

    def test_basic_error(self):
        """Test basic error creation."""
        error = ModuleError("Something went wrong")

        assert str(error) == "[EXECUTION_ERROR] Something went wrong"
        assert error.code == ErrorCode.EXECUTION_ERROR
        assert error.message == "Something went wrong"

    def test_error_with_code(self):
        """Test error with custom code."""
        error = ModuleError("Custom error", code="CUSTOM_CODE")

        assert error.code == "CUSTOM_CODE"

    def test_error_with_field(self):
        """Test error with field."""
        error = ModuleError("Invalid field", field="username")

        assert error.field == "username"
        assert "(field: username)" in str(error)

    def test_error_with_hint(self):
        """Test error with hint."""
        error = ModuleError("Error", hint="Try doing X")

        assert error.hint == "Try doing X"

    def test_error_to_dict(self):
        """Test error to_dict method."""
        error = ModuleError(
            "Test error",
            code="TEST_CODE",
            field="test_field",
            hint="Test hint",
            details={"extra": "info"}
        )
        d = error.to_dict()

        assert d["code"] == "TEST_CODE"
        assert d["message"] == "Test error"
        assert d["field"] == "test_field"
        assert d["hint"] == "Test hint"
        assert d["details"] == {"extra": "info"}


class TestValidationError:
    """Test ValidationError class."""

    def test_validation_error_code(self):
        """Test ValidationError has correct code."""
        error = ValidationError("Missing required field")

        assert error.code == ErrorCode.MISSING_PARAM

    def test_validation_error_with_field(self):
        """Test ValidationError with field."""
        error = ValidationError("URL is required", field="url")

        assert error.field == "url"
        assert "url" in str(error)


class TestInvalidTypeError:
    """Test InvalidTypeError class."""

    def test_type_error_with_types(self):
        """Test InvalidTypeError with type info."""
        error = InvalidTypeError(
            "Expected string",
            field="name",
            expected_type="str",
            actual_type="int"
        )

        assert error.code == ErrorCode.INVALID_PARAM_TYPE
        assert error.details["expected_type"] == "str"
        assert error.details["actual_type"] == "int"


class TestNetworkError:
    """Test NetworkError class."""

    def test_network_error_with_url(self):
        """Test NetworkError with URL."""
        error = NetworkError(
            "Connection failed",
            url="https://example.com",
            status_code=500
        )

        assert error.code == ErrorCode.NETWORK_ERROR
        assert error.details["url"] == "https://example.com"
        assert error.details["status_code"] == 500


class TestAPIError:
    """Test APIError class."""

    def test_api_error_with_details(self):
        """Test APIError with API details."""
        error = APIError(
            "API returned error",
            api_name="OpenAI",
            status_code=429,
            response_body='{"error": "rate limited"}'
        )

        assert error.code == ErrorCode.API_ERROR
        assert error.details["api_name"] == "OpenAI"
        assert error.details["status_code"] == 429


class TestRateLimitedError:
    """Test RateLimitedError class."""

    def test_rate_limited_with_retry(self):
        """Test RateLimitedError with retry_after."""
        error = RateLimitedError(
            "Rate limited",
            retry_after=60
        )

        assert error.code == ErrorCode.RATE_LIMITED
        assert error.details["retry_after_seconds"] == 60
        assert "60" in error.hint


class TestExecutionTimeoutError:
    """Test ExecutionTimeoutError class."""

    def test_timeout_error_with_duration(self):
        """Test ExecutionTimeoutError with timeout_ms."""
        error = ExecutionTimeoutError(
            "Module timed out",
            timeout_ms=30000
        )

        assert error.code == ErrorCode.TIMEOUT
        assert error.details["timeout_ms"] == 30000


class TestElementNotFoundError:
    """Test ElementNotFoundError class."""

    def test_element_error_with_selector(self):
        """Test ElementNotFoundError with selector."""
        error = ElementNotFoundError(
            "Element not found",
            selector="#submit-button"
        )

        assert error.code == ErrorCode.ELEMENT_NOT_FOUND
        assert error.details["selector"] == "#submit-button"


class TestFileNotFoundError:
    """Test FileNotFoundError class."""

    def test_file_error_with_path(self):
        """Test FileNotFoundError with path."""
        error = FileNotFoundError(
            "File does not exist",
            path="/path/to/file.txt"
        )

        assert error.code == ErrorCode.FILE_NOT_FOUND
        assert error.details["path"] == "/path/to/file.txt"


class TestErrorFromCode:
    """Test error_from_code factory function."""

    def test_create_validation_error(self):
        """Test creating ValidationError from code."""
        error = error_from_code(
            ErrorCode.MISSING_PARAM,
            "Field is required",
            field="email"
        )

        assert isinstance(error, ValidationError)
        assert error.message == "Field is required"

    def test_create_network_error(self):
        """Test creating NetworkError from code."""
        error = error_from_code(
            ErrorCode.NETWORK_ERROR,
            "Connection refused"
        )

        assert isinstance(error, NetworkError)

    def test_create_timeout_error(self):
        """Test creating ExecutionTimeoutError from code."""
        error = error_from_code(
            ErrorCode.TIMEOUT,
            "Operation timed out",
            timeout_ms=5000
        )

        assert isinstance(error, ExecutionTimeoutError)

    def test_unknown_code_returns_base(self):
        """Test unknown code returns base ModuleError."""
        error = error_from_code(
            "UNKNOWN_CODE",
            "Unknown error"
        )

        assert isinstance(error, ModuleError)
        # Base ModuleError uses its default code (EXECUTION_ERROR)
        assert error.code == ErrorCode.EXECUTION_ERROR


class TestExceptionChaining:
    """Test that errors can be used as exceptions."""

    def test_raise_and_catch_validation_error(self):
        """Test raising and catching ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            raise ValidationError("URL is required", field="url")

        error = exc_info.value
        assert error.field == "url"

    def test_catch_as_module_error(self):
        """Test catching subclass as ModuleError."""
        with pytest.raises(ModuleError) as exc_info:
            raise NetworkError("Connection failed")

        assert exc_info.value.code == ErrorCode.NETWORK_ERROR
