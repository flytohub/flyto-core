"""
Tests for ModuleResult dataclass.

Tests the standardized module execution result format.
"""
import pytest
from src.core.modules.result import ModuleResult


class TestModuleResultSuccess:
    """Test ModuleResult.success() factory method."""

    def test_basic_success(self):
        """Test basic success result."""
        result = ModuleResult.success(data={"value": 42})

        assert result.ok is True
        assert result.data == {"value": 42}
        assert result.error is None
        assert result.error_code is None

    def test_success_with_meta(self):
        """Test success with metadata."""
        meta = {"duration_ms": 100, "module_id": "test.module"}
        result = ModuleResult.success(data="test", meta=meta)

        assert result.ok is True
        assert result.data == "test"
        assert result.meta == meta

    def test_success_with_none_data(self):
        """Test success with None data."""
        result = ModuleResult.success(data=None)

        assert result.ok is True
        assert result.data is None

    def test_success_with_list_data(self):
        """Test success with list data."""
        result = ModuleResult.success(data=[1, 2, 3])

        assert result.ok is True
        assert result.data == [1, 2, 3]


class TestModuleResultFailure:
    """Test ModuleResult.failure() factory method."""

    def test_basic_failure(self):
        """Test basic failure result."""
        result = ModuleResult.failure(
            error="Something went wrong",
            error_code="EXECUTION_ERROR"
        )

        assert result.ok is False
        assert result.error == "Something went wrong"
        assert result.error_code == "EXECUTION_ERROR"
        assert result.data is None

    def test_failure_with_details(self):
        """Test failure with details."""
        result = ModuleResult.failure(
            error="Validation failed",
            error_code="VALIDATION_ERROR",
            details={"field": "url", "hint": "Must be a valid URL"}
        )

        assert result.ok is False
        assert result.error == "Validation failed"
        assert result.meta["error_details"] == {"field": "url", "hint": "Must be a valid URL"}

    def test_failure_with_meta(self):
        """Test failure with metadata."""
        meta = {"duration_ms": 50}
        result = ModuleResult.failure(
            error="Timeout",
            error_code="TIMEOUT",
            meta=meta
        )

        assert result.ok is False
        assert result.meta == meta


class TestModuleResultToDict:
    """Test ModuleResult.to_dict() method."""

    def test_success_to_dict(self):
        """Test converting success result to dict."""
        result = ModuleResult.success(data={"key": "value"})
        d = result.to_dict()

        assert d["ok"] is True
        assert d["data"] == {"key": "value"}
        assert "error" not in d
        assert "error_code" not in d

    def test_failure_to_dict(self):
        """Test converting failure result to dict."""
        result = ModuleResult.failure(
            error="Error message",
            error_code="TEST_ERROR"
        )
        d = result.to_dict()

        assert d["ok"] is False
        assert d["error"] == "Error message"
        assert d["error_code"] == "TEST_ERROR"

    def test_to_dict_with_meta(self):
        """Test to_dict includes meta when present."""
        result = ModuleResult.success(
            data=None,
            meta={"module_id": "test"}
        )
        d = result.to_dict()

        assert d["meta"] == {"module_id": "test"}


class TestModuleResultUnwrap:
    """Test ModuleResult.unwrap() and unwrap_or() methods."""

    def test_unwrap_success(self):
        """Test unwrap on success."""
        result = ModuleResult.success(data="success_data")
        assert result.unwrap() == "success_data"

    def test_unwrap_failure_raises(self):
        """Test unwrap on failure raises ValueError."""
        result = ModuleResult.failure(error="fail", error_code="ERROR")

        with pytest.raises(ValueError) as exc_info:
            result.unwrap()

        assert "fail" in str(exc_info.value)

    def test_unwrap_or_success(self):
        """Test unwrap_or on success returns data."""
        result = ModuleResult.success(data="real_data")
        assert result.unwrap_or("default") == "real_data"

    def test_unwrap_or_failure(self):
        """Test unwrap_or on failure returns default."""
        result = ModuleResult.failure(error="fail", error_code="ERROR")
        assert result.unwrap_or("default") == "default"


class TestModuleResultProperties:
    """Test ModuleResult properties."""

    def test_is_success(self):
        """Test is_success property."""
        result = ModuleResult.success(data=None)
        assert result.is_success is True
        assert result.is_failure is False

    def test_is_failure(self):
        """Test is_failure property."""
        result = ModuleResult.failure(error="fail", error_code="ERROR")
        assert result.is_success is False
        assert result.is_failure is True


class TestModuleResultLegacyDict:
    """Test ModuleResult.to_legacy_dict() for backwards compatibility."""

    def test_success_legacy_dict(self):
        """Test legacy dict format for success."""
        result = ModuleResult.success(data={"result": "test"})
        d = result.to_legacy_dict()

        assert d["ok"] is True
        assert d["data"] == {"result": "test"}

    def test_failure_legacy_dict(self):
        """Test legacy dict format for failure."""
        result = ModuleResult.failure(
            error="Test error",
            error_code="TEST_CODE"
        )
        d = result.to_legacy_dict()

        assert d["ok"] is False
        # In legacy format, error is a nested object
        assert d["error"]["message"] == "Test error"
        assert d["error"]["code"] == "TEST_CODE"

    def test_failure_legacy_dict_with_details(self):
        """Test legacy dict with error details."""
        result = ModuleResult.failure(
            error="Validation error",
            error_code="VALIDATION_ERROR",
            details={"field": "email", "hint": "Must be valid"}
        )
        d = result.to_legacy_dict()

        assert d["error"]["field"] == "email"
        assert d["error"]["hint"] == "Must be valid"


class TestModuleResultMetaFiltering:
    """Test meta filtering for public/internal separation."""

    def test_to_dict_filters_internal_meta_by_default(self):
        """Test that to_dict() filters out internal meta keys by default."""
        result = ModuleResult.success(
            data={"value": 1},
            meta={
                "module_id": "test.module",       # public
                "duration_ms": 100,               # public
                "request_id": "req-123",          # public
                "traceback": "internal stack...", # internal - should be filtered
                "debug_info": {"x": 1},           # internal - should be filtered
            }
        )
        d = result.to_dict()

        assert "meta" in d
        assert d["meta"]["module_id"] == "test.module"
        assert d["meta"]["duration_ms"] == 100
        assert d["meta"]["request_id"] == "req-123"
        assert "traceback" not in d["meta"]
        assert "debug_info" not in d["meta"]

    def test_to_dict_include_internal_true(self):
        """Test that to_dict(include_internal=True) includes all meta keys."""
        result = ModuleResult.success(
            data={"value": 1},
            meta={
                "module_id": "test.module",
                "traceback": "internal stack...",
                "debug_info": {"x": 1},
            }
        )
        d = result.to_dict(include_internal=True)

        assert d["meta"]["module_id"] == "test.module"
        assert d["meta"]["traceback"] == "internal stack..."
        assert d["meta"]["debug_info"] == {"x": 1}

    def test_to_public_dict(self):
        """Test to_public_dict() filters internal meta."""
        result = ModuleResult.success(
            data=None,
            meta={
                "module_id": "test",
                "traceback": "should not appear",
            }
        )
        d = result.to_public_dict()

        assert d["meta"]["module_id"] == "test"
        assert "traceback" not in d["meta"]

    def test_to_internal_dict(self):
        """Test to_internal_dict() includes all meta."""
        result = ModuleResult.failure(
            error="Error",
            error_code="ERROR",
            meta={
                "module_id": "test",
                "traceback": "full stack trace here",
            }
        )
        d = result.to_internal_dict()

        assert d["meta"]["module_id"] == "test"
        assert d["meta"]["traceback"] == "full stack trace here"

    def test_empty_public_meta_omitted(self):
        """Test that empty public meta is not included in response."""
        result = ModuleResult.success(
            data={"value": 1},
            meta={
                "internal_only": "secret",  # Not in PUBLIC_META_KEYS
            }
        )
        d = result.to_dict()

        # meta should not be present if all keys are filtered out
        assert "meta" not in d

    def test_error_details_in_public_meta(self):
        """Test that error_details is included in public meta."""
        result = ModuleResult.failure(
            error="Validation failed",
            error_code="VALIDATION_ERROR",
            details={"field": "url", "hint": "Must be HTTPS"}
        )
        d = result.to_dict()

        assert "meta" in d
        assert d["meta"]["error_details"]["field"] == "url"
        assert d["meta"]["error_details"]["hint"] == "Must be HTTPS"
