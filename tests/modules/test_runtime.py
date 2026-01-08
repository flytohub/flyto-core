"""
Tests for module runtime execution wrapper.

Tests the unified execute_module function.
"""
import asyncio
import pytest
from src.core.modules.runtime import (
    execute_module,
    execute_module_with_retry,
    wrap_sync_module,
    _normalize_result,
)
from src.core.modules.result import ModuleResult
from src.core.modules.errors import (
    ModuleError,
    ValidationError,
    NetworkError,
)
from src.core.constants import ErrorCode


class TestExecuteModule:
    """Test execute_module function."""

    @pytest.mark.asyncio
    async def test_execute_success_raw_data(self):
        """Test executing module that returns raw data."""
        async def my_module(context):
            return {"value": context["params"]["x"] + context["params"]["y"]}

        result = await execute_module(
            module_fn=my_module,
            params={"x": 1, "y": 2},
            context={},
            module_id="test.add"
        )

        assert result.ok is True
        assert result.data == {"value": 3}
        assert "duration_ms" in result.meta

    @pytest.mark.asyncio
    async def test_execute_success_ok_pattern(self):
        """Test executing module that returns ok pattern."""
        async def my_module(context):
            return {"ok": True, "data": {"result": "success"}}

        result = await execute_module(
            module_fn=my_module,
            params={},
            context={},
            module_id="test.ok"
        )

        assert result.ok is True
        assert result.data == {"result": "success"}

    @pytest.mark.asyncio
    async def test_execute_failure_ok_pattern(self):
        """Test executing module that returns ok=False."""
        async def my_module(context):
            return {
                "ok": False,
                "error": "Validation failed",
                "error_code": "VALIDATION_ERROR"
            }

        result = await execute_module(
            module_fn=my_module,
            params={},
            context={},
            module_id="test.fail"
        )

        assert result.ok is False
        assert result.error == "Validation failed"
        assert result.error_code == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_execute_with_module_error(self):
        """Test executing module that raises ModuleError."""
        async def my_module(context):
            raise ValidationError("URL is required", field="url")

        result = await execute_module(
            module_fn=my_module,
            params={},
            context={},
            module_id="test.validation"
        )

        assert result.ok is False
        assert result.error == "URL is required"
        assert result.error_code == ErrorCode.MISSING_PARAM

    @pytest.mark.asyncio
    async def test_execute_with_unexpected_error(self):
        """Test executing module that raises unexpected exception."""
        async def my_module(context):
            raise ValueError("Unexpected error")

        result = await execute_module(
            module_fn=my_module,
            params={},
            context={},
            module_id="test.error"
        )

        assert result.ok is False
        assert "Unexpected error" in result.error
        assert result.error_code == ErrorCode.EXECUTION_ERROR

    @pytest.mark.asyncio
    async def test_execute_timeout(self):
        """Test module timeout."""
        async def slow_module(context):
            await asyncio.sleep(5)
            return {"done": True}

        result = await execute_module(
            module_fn=slow_module,
            params={},
            context={},
            module_id="test.slow",
            timeout_ms=100  # 100ms timeout
        )

        assert result.ok is False
        assert result.error_code == ErrorCode.TIMEOUT

    @pytest.mark.asyncio
    async def test_execute_returns_module_result(self):
        """Test module that returns ModuleResult directly."""
        async def my_module(context):
            return ModuleResult.success(data={"direct": True})

        result = await execute_module(
            module_fn=my_module,
            params={},
            context={},
            module_id="test.direct"
        )

        assert result.ok is True
        assert result.data == {"direct": True}


class TestNormalizeResult:
    """Test _normalize_result function."""

    def test_normalize_module_result(self):
        """Test normalizing ModuleResult."""
        raw = ModuleResult.success(data="test")
        result = _normalize_result(raw, {"module_id": "test"})

        assert result.ok is True
        assert result.data == "test"

    def test_normalize_ok_true(self):
        """Test normalizing ok=True dict."""
        raw = {"ok": True, "data": {"value": 1}}
        result = _normalize_result(raw, {})

        assert result.ok is True
        assert result.data == {"value": 1}

    def test_normalize_ok_false(self):
        """Test normalizing ok=False dict."""
        raw = {"ok": False, "error": "failed", "error_code": "TEST_ERROR"}
        result = _normalize_result(raw, {})

        assert result.ok is False
        assert result.error == "failed"

    def test_normalize_ok_false_nested_error(self):
        """Test normalizing ok=False with nested error object."""
        raw = {
            "ok": False,
            "error": {
                "code": "NESTED_ERROR",
                "message": "Nested error message",
                "field": "test_field"
            }
        }
        result = _normalize_result(raw, {})

        assert result.ok is False
        assert result.error == "Nested error message"
        assert result.error_code == "NESTED_ERROR"

    def test_normalize_status_error(self):
        """Test normalizing status=error dict."""
        raw = {"status": "error", "message": "Something failed"}
        result = _normalize_result(raw, {})

        assert result.ok is False
        assert result.error == "Something failed"

    def test_normalize_raw_dict(self):
        """Test normalizing raw dict without ok/status."""
        raw = {"result": "test", "count": 5}
        result = _normalize_result(raw, {})

        assert result.ok is True
        assert result.data == {"result": "test", "count": 5}

    def test_normalize_raw_value(self):
        """Test normalizing raw non-dict value."""
        result = _normalize_result(42, {})

        assert result.ok is True
        assert result.data == 42

    def test_normalize_ok_true_without_data_strips_protocol_keys(self):
        """Test normalizing ok=True without data field strips protocol keys."""
        # Legacy format: {ok: true, foo: 1} should become data={foo: 1}
        raw = {"ok": True, "foo": 1, "bar": "test"}
        result = _normalize_result(raw, {})

        assert result.ok is True
        assert result.data == {"foo": 1, "bar": "test"}
        # Protocol keys should NOT be in data
        assert "ok" not in result.data

    def test_normalize_ok_true_strips_all_protocol_keys(self):
        """Test that all protocol keys are stripped from legacy format."""
        raw = {
            "ok": True,
            "status": "success",  # Should be stripped
            "message": "Done",    # Should be stripped
            "meta": {"x": 1},     # Should be stripped
            "actual_data": "keep this",
        }
        result = _normalize_result(raw, {})

        assert result.ok is True
        assert result.data == {"actual_data": "keep this"}
        assert "ok" not in result.data
        assert "status" not in result.data
        assert "message" not in result.data
        assert "meta" not in result.data

    def test_normalize_ok_true_with_data_uses_data_directly(self):
        """Test that when data key exists, it's used directly."""
        raw = {
            "ok": True,
            "data": {"result": "from_data"},
            "extra": "should_not_appear"
        }
        result = _normalize_result(raw, {})

        assert result.ok is True
        assert result.data == {"result": "from_data"}
        # extra should NOT leak into data
        assert "extra" not in str(result.data)

    def test_normalize_ok_true_only_protocol_keys_returns_empty_data(self):
        """Test that if only protocol keys exist, data is empty dict."""
        raw = {"ok": True}  # Only protocol key
        result = _normalize_result(raw, {})

        assert result.ok is True
        assert result.data == {}


class TestExecuteModuleWithRetry:
    """Test execute_module_with_retry function."""

    @pytest.mark.asyncio
    async def test_retry_on_network_error(self):
        """Test retry on network error."""
        call_count = 0

        async def flaky_module(context):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise NetworkError("Connection failed")
            return {"success": True}

        result = await execute_module_with_retry(
            module_fn=flaky_module,
            params={},
            context={},
            module_id="test.flaky",
            max_retries=3,
            retry_delay_ms=10  # Fast for testing
        )

        assert result.ok is True
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_no_retry_on_validation_error(self):
        """Test no retry on validation error."""
        call_count = 0

        async def bad_module(context):
            nonlocal call_count
            call_count += 1
            raise ValidationError("Invalid input")

        result = await execute_module_with_retry(
            module_fn=bad_module,
            params={},
            context={},
            module_id="test.bad",
            max_retries=3
        )

        assert result.ok is False
        assert call_count == 1  # No retries

    @pytest.mark.asyncio
    async def test_retry_exhausted(self):
        """Test all retries exhausted."""
        call_count = 0

        async def always_fail(context):
            nonlocal call_count
            call_count += 1
            raise NetworkError("Always fails")

        result = await execute_module_with_retry(
            module_fn=always_fail,
            params={},
            context={},
            module_id="test.fail",
            max_retries=2,
            retry_delay_ms=10
        )

        assert result.ok is False
        assert result.error_code == ErrorCode.RETRY_EXHAUSTED
        assert call_count == 3  # Initial + 2 retries


class TestWrapSyncModule:
    """Test wrap_sync_module function."""

    @pytest.mark.asyncio
    async def test_wrap_sync_function(self):
        """Test wrapping a sync function."""
        def sync_module(context):
            return {"result": context["params"]["x"] * 2}

        async_fn = wrap_sync_module(sync_module)
        result = await async_fn({"params": {"x": 5}})

        assert result == {"result": 10}
