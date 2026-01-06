"""
E2E Smoke Tests

These tests verify the validation system and error handling.

Run with: pytest tests/e2e/test_smoke.py -v
"""
import os
import sys
from pathlib import Path

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

# Mark all tests in this module as e2e
pytestmark = pytest.mark.e2e


class TestValidationSystem:
    """Test the unified validation and error system."""

    def test_module_error_format(self):
        """Verify ModuleError produces correct format."""
        from core.modules.validation import ModuleError
        from core.constants import ErrorCode

        error = ModuleError(
            code=ErrorCode.MISSING_PARAM,
            message="Missing required parameter: url",
            field="url",
            hint="Please provide a valid URL"
        )

        result = error.to_result()

        assert result["ok"] is False
        assert "error" in result
        assert result["error"]["code"] == "MISSING_PARAM"
        assert result["error"]["field"] == "url"
        assert result["error"]["hint"] is not None

    def test_validate_required(self):
        """Test required parameter validation."""
        from core.modules.validation import validate_required

        # Valid case
        params = {"url": "https://example.com"}
        error = validate_required(params, "url")
        assert error is None

        # Invalid case - missing
        params = {}
        error = validate_required(params, "url")
        assert error is not None
        assert error.code == "MISSING_PARAM"
        assert error.field == "url"

        # Invalid case - None value
        params = {"url": None}
        error = validate_required(params, "url")
        assert error is not None

    def test_validate_type(self):
        """Test type validation."""
        from core.modules.validation import validate_type

        # Valid case
        params = {"timeout": 30}
        error = validate_type(params, "timeout", int)
        assert error is None

        # Invalid case
        params = {"timeout": "not a number"}
        error = validate_type(params, "timeout", int)
        assert error is not None
        assert error.code == "INVALID_PARAM_TYPE"

    def test_validate_url(self):
        """Test URL validation."""
        from core.modules.validation import validate_url

        # Valid cases
        assert validate_url({"url": "https://example.com"}, "url") is None
        assert validate_url({"url": "http://localhost:3000"}, "url") is None

        # Invalid case
        error = validate_url({"url": "not-a-url"}, "url")
        assert error is not None
        assert error.code == "INVALID_PARAM_VALUE"

    def test_validate_all(self):
        """Test combined validation."""
        from core.modules.validation import validate_all, validate_required, validate_url

        # All valid
        params = {"url": "https://example.com"}
        error = validate_all(
            validate_required(params, "url"),
            validate_url(params, "url")
        )
        assert error is None

        # First error returned
        params = {}
        error = validate_all(
            validate_required(params, "url"),
            validate_url(params, "url")
        )
        assert error is not None
        assert error.code == "MISSING_PARAM"


class TestErrorCodes:
    """Test the ErrorCode class coverage."""

    def test_error_codes_exist(self):
        """Verify all expected error codes are defined."""
        from core.constants import ErrorCode

        expected_codes = [
            "MISSING_PARAM",
            "INVALID_PARAM_TYPE",
            "INVALID_PARAM_VALUE",
            "TIMEOUT",
            "NETWORK_ERROR",
            "ELEMENT_NOT_FOUND",
            "FILE_NOT_FOUND",
            "MISSING_CREDENTIAL",
        ]

        for code in expected_codes:
            assert hasattr(ErrorCode, code), f"Missing error code: {code}"
            assert getattr(ErrorCode, code) == code

    def test_error_codes_are_strings(self):
        """Verify all error codes are string values."""
        from core.constants import ErrorCode

        for attr in dir(ErrorCode):
            if not attr.startswith("_"):
                value = getattr(ErrorCode, attr)
                assert isinstance(value, str), f"ErrorCode.{attr} should be string"


class TestBaseModuleHelpers:
    """Test BaseModule success/failure helpers."""

    def test_success_helper(self):
        """Test success result format."""
        from core.modules.validation import success

        # Basic success
        result = success()
        assert result["ok"] is True
        assert "data" not in result

        # Success with data
        result = success({"title": "Test"})
        assert result["ok"] is True
        assert result["data"]["title"] == "Test"

        # Success with message
        result = success(data=None, message="Done!")
        assert result["ok"] is True
        assert result["message"] == "Done!"

    def test_failure_helper(self):
        """Test failure result format."""
        from core.modules.validation import failure
        from core.constants import ErrorCode

        result = failure(
            code=ErrorCode.TIMEOUT,
            message="Operation timed out",
            field=None,
            hint="Try increasing the timeout"
        )

        assert result["ok"] is False
        assert result["error"]["code"] == "TIMEOUT"
        assert result["error"]["message"] == "Operation timed out"
        assert result["error"]["hint"] == "Try increasing the timeout"


class TestModuleRegistry:
    """Test module registry functionality."""

    def test_production_modules_load(self):
        """Test that production modules load correctly."""
        os.environ["FLYTO_ENV"] = "production"

        from core.modules.registry import ModuleRegistry
        from core.modules import atomic

        metadata = ModuleRegistry.get_all_metadata(
            filter_by_stability=True,
            env="production"
        )

        assert len(metadata) >= 170, "Should have at least 170 production modules"

    def test_browser_launch_module_exists(self):
        """Test browser.launch module is registered."""
        os.environ["FLYTO_ENV"] = "production"

        from core.modules.registry import ModuleRegistry
        from core.modules import atomic

        metadata = ModuleRegistry.get_metadata("browser.launch")
        assert metadata is not None
        assert metadata.get("stability") == "stable"
