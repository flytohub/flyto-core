"""
Invoke Tests

Tests for plugin invocation and result handling.
Task: 1.16
"""

import json
import logging
from unittest.mock import MagicMock

import pytest

from core.runtime.invoke import RuntimeInvoker, parse_module_id
from core.runtime.protocol import ProtocolEncoder
from core.runtime.routing import ModuleRouter
from core.runtime.types import (
    InvokeError,
    InvokeMetrics,
    InvokeRequest,
    InvokeResponse,
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

        message = json.loads(message_json)

        assert message["jsonrpc"] == "2.0"
        assert message["method"] == "invoke"
        assert message["params"]["step"] == "query"
        assert message["params"]["input"]["query"] == "SELECT 1"

    @pytest.mark.asyncio
    async def test_invoker_with_real_module(self):
        """Test RuntimeInvoker with actual string.uppercase module."""
        from core.runtime.invoke import reset_invoker
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


class TestPluginManagerWiring:
    """`set_plugin_manager` must survive the manager it is documented to take.

    `PluginManager.list_plugins()` returns *status records* — dicts shaped
    `{"pluginId": ..., "status": ...}` — so `set(manager.list_plugins())` raised
    `TypeError: unhashable type: 'dict'` and took down the only call that wires
    subprocess plugins into routing at all.
    """

    @staticmethod
    def _status(plugin_id, status="running"):
        """One record in `PluginManager.list_plugins()` shape.

        Ids are spelled with hyphens because that is what `validate_plugin_id`
        accepts; a dotted reverse-DNS id could never have reached a real manager
        in the first place, so pinning routing against one pins nothing.
        """
        return {
            "pluginId": plugin_id,
            "version": "1.0.0",
            "status": status,
            "steps": ["query"],
        }

    def _invoker(self):
        # An owned router, so this does not read or mutate the process global.
        return RuntimeInvoker(router=ModuleRouter())

    def test_status_dicts_do_not_raise_and_are_reduced_to_ids(self):
        """The exact regression: dict records in, hashable id strings out."""
        manager = MagicMock()
        manager.list_plugins.return_value = [
            self._status("com-example-database"),
            self._status("com-example-thermal", status="starting"),
        ]
        # A manager that only reports loaded plugins.
        del manager.list_available_plugins

        invoker = self._invoker()
        invoker.set_plugin_manager(manager)

        assert invoker._router.config.available_plugins == {
            "com-example-database",
            "com-example-thermal",
        }

    def test_available_plugins_are_preferred_and_loaded_ones_kept(self):
        """Discovered plugins are already ids; loaded ones must not be dropped."""
        manager = MagicMock()
        manager.list_available_plugins.return_value = [
            "com-example-database",
            "com-example-unloaded",
        ]
        manager.list_plugins.return_value = [self._status("com-example-database")]

        invoker = self._invoker()
        invoker.set_plugin_manager(manager)

        available = invoker._router.config.available_plugins
        assert isinstance(available, set)
        assert available == {"com-example-database", "com-example-unloaded"}

    def test_a_broken_lister_does_not_break_wiring(self):
        """One unusable source must not cost the manager its other plugins."""
        manager = MagicMock()
        manager.list_available_plugins.side_effect = RuntimeError("registry down")
        manager.list_plugins.return_value = [self._status("com-example-database")]

        invoker = self._invoker()
        invoker.set_plugin_manager(manager)

        assert invoker._plugin_manager is manager
        assert invoker._router.config.available_plugins == {"com-example-database"}

    def test_empty_and_unnameable_entries_are_dropped(self, caplog):
        """Nothing unhashable, empty, or nameless reaches the router.

        Including the entry that cannot be reduced to an id at all. A listing is
        plugin-supplied data, so a value whose ``str()`` throws is a listing the
        manager can really hand over, not a programming error — and it used to
        escape ``_routable_plugin_ids`` and abort ``set_plugin_manager``, leaving
        the invoker holding a manager whose plugins the router never learned.
        One unreadable entry costs that entry its routing slot and nothing else.
        """
        unrenderable = MagicMock()
        unrenderable.__str__.side_effect = RuntimeError("id is not renderable")

        manager = MagicMock()
        manager.list_available_plugins.return_value = [
            "  spaced  ",
            "",
            None,
            {"pluginId": unrenderable},
            # After the bad entry, so a listing that stops at the first
            # unreadable id fails here rather than in production.
            "com-example-database",
        ]
        manager.list_plugins.return_value = [None, {"status": "running"}]

        invoker = self._invoker()
        with caplog.at_level(logging.WARNING, logger="core.runtime.invoke"):
            invoker.set_plugin_manager(manager)

        assert invoker._plugin_manager is manager
        assert invoker._router.config.available_plugins == {
            "spaced",
            "com-example-database",
        }
        # Skipped, not silently swallowed: an operator missing a plugin needs to
        # be able to find out why from the log.
        assert "unreadable" in caplog.text

    @pytest.mark.asyncio
    async def test_legacy_routing_survives_a_wired_manager(self):
        """Wiring plugins in must not steal modules the registry still owns."""
        manager = MagicMock()
        manager.list_available_plugins.return_value = ["com-example-thermal"]
        manager.list_plugins.return_value = []
        manager.get_manifest.return_value = None

        invoker = self._invoker()
        invoker.set_plugin_manager(manager)

        result = await invoker.invoke(
            module_id="string.uppercase",
            step_id="",
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
