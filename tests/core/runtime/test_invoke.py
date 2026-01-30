"""
Invoke Tests

Tests for plugin invocation and result handling.
Task: 1.16
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.runtime.invoke import (
    RuntimeInvoker,
    get_invoker,
    parse_module_id,
)
from src.core.runtime.types import (
    InvokeRequest,
    InvokeResponse,
    InvokeError,
    InvokeMetrics,
    InvokeStatus,
)
from src.core.runtime.protocol import (
    ProtocolEncoder,
    ProtocolDecoder,
)


class TestInvokeQueryReturnsResults:
    """Test 1.16: Invoke query returns results."""

    def test_parse_module_id_legacy_format(self):
        """Test parsing legacy module ID format."""
        # parse_module_id converts legacy format to plugin format
        plugin_id, step_id = parse_module_id("database.query")

        assert plugin_id == "flyto-official/database"
        assert step_id == "query"

    def test_parse_module_id_simple(self):
        """Test parsing simple module ID."""
        plugin_id, step_id = parse_module_id("string.uppercase")

        assert plugin_id == "flyto-official/string"
        assert step_id == "uppercase"

    def test_invoke_request_creation(self):
        """Test InvokeRequest creation."""
        request = InvokeRequest(
            module_id="flyto-official/database",
            step_id="query",
            input_data={"query": "SELECT * FROM users"},
            config={},
            context={"tenant_id": "tenant-123"},
        )

        assert request.module_id == "flyto-official/database"
        assert request.step_id == "query"
        assert request.input_data["query"] == "SELECT * FROM users"

    def test_invoke_response_success(self):
        """Test successful InvokeResponse."""
        response = InvokeResponse(
            ok=True,
            data={
                "rows": [{"id": 1, "name": "Alice"}],
                "rowCount": 1,
                "columns": ["id", "name"],
            },
        )

        assert response.ok is True
        assert response.data["rowCount"] == 1

    def test_invoke_response_to_dict(self):
        """Test InvokeResponse serialization."""
        response = InvokeResponse(
            ok=True,
            data={"result": "test"},
            metrics=InvokeMetrics(duration_ms=42),
        )

        data = response.to_dict()

        assert data["ok"] is True
        assert data["data"]["result"] == "test"
        assert data["metrics"]["durationMs"] == 42

    def test_protocol_encoder_invoke(self):
        """Test invoke message encoding."""
        # encode_invoke returns a JSON string, not a dict
        message_json = ProtocolEncoder.encode_invoke(
            step="query",
            input_data={"query": "SELECT 1"},
            config={},
            context={},
            request_id=1,
        )

        import json
        message = json.loads(message_json)

        assert message["jsonrpc"] == "2.0"
        assert message["method"] == "invoke"
        assert message["params"]["step"] == "query"
        assert message["params"]["input"]["query"] == "SELECT 1"

    @pytest.mark.asyncio
    async def test_invoker_with_real_module(self):
        """Test RuntimeInvoker with actual string.uppercase module."""
        from src.core.runtime.invoke import reset_invoker
        reset_invoker()

        invoker = RuntimeInvoker()

        # Test with real legacy module - for legacy modules, module_id contains
        # the full dotted path, step_id should be empty or extracted from it
        result = await invoker.invoke(
            module_id="string.uppercase",
            step_id="",  # Empty for legacy format
            input_data={"text": "hello"},
            config={},
            context={},
        )

        assert result["ok"] is True
        assert result["data"]["result"] == "HELLO"


class TestInvokeErrors:
    """Test invoke error handling."""

    def test_invoke_response_error(self):
        """Test error InvokeResponse."""
        response = InvokeResponse(
            ok=False,
            error=InvokeError(
                code="EXECUTION_ERROR",
                message="Database connection failed",
                retryable=True,
            ),
        )

        assert response.ok is False
        assert response.error.code == "EXECUTION_ERROR"
        assert response.error.retryable is True

    def test_invoke_response_from_dict(self):
        """Test InvokeResponse deserialization."""
        data = {
            "ok": True,
            "data": {"result": "test"},
        }

        response = InvokeResponse.from_dict(data)

        assert response.ok is True
        assert response.data["result"] == "test"

    def test_invoke_response_error_from_dict(self):
        """Test InvokeResponse error deserialization."""
        data = {
            "ok": False,
            "error": {
                "code": "TIMEOUT",
                "message": "Plugin timed out",
            },
        }

        response = InvokeResponse.from_dict(data)

        assert response.ok is False
        assert response.error.code == "TIMEOUT"
