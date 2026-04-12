# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Comprehensive tests for the module registry system.

Covers:
- resolve.py: tier resolution, timeout resolution, can_be_start, port enrichment, module config
- metadata.py: metadata building
- decorators.py: registration, validation, function wrapping
- core.py: registry operations, connection graph validation
- retry.py: structured logging in retry logic
"""

import asyncio
import logging
import os
import warnings
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from core.modules.registry.resolve import (
    resolve_tier,
    resolve_can_be_start,
    resolve_timeout_ms,
    resolve_module_config,
    enrich_port_handle_metadata,
)
from core.modules.registry.metadata import build_module_metadata
from core.modules.registry.decorators import (
    _validate_module_registration,
    _wrap_function_as_module,
    register_module,
)
from core.modules.registry.core import ModuleRegistry
from core.modules.types import (
    ModuleLevel,
    ModuleTier,
    UIVisibility,
    ExecutionEnvironment,
    NodeType,
    StabilityLevel,
)
from core.engine.step_executor.retry import execute_with_retry, _calculate_wait_time


# ============================================================================
# resolve_tier
# ============================================================================

class TestResolveTier:
    """Tests for tier auto-detection logic."""

    def test_explicit_tier_takes_priority(self):
        result = resolve_tier(
            tier=ModuleTier.FEATURED,
            level=ModuleLevel.ATOMIC,
            tags=None,
            category="string",  # would be TOOLKIT without explicit
        )
        assert result == ModuleTier.FEATURED

    def test_internal_categories(self):
        for cat in ('meta', 'testing', 'debug', 'training'):
            result = resolve_tier(
                tier=None, level=ModuleLevel.ATOMIC, tags=None, category=cat
            )
            assert result == ModuleTier.INTERNAL, f"Expected INTERNAL for category '{cat}'"

    def test_toolkit_categories(self):
        for cat in ('string', 'array', 'object', 'math', 'datetime', 'crypto', 'utility'):
            result = resolve_tier(
                tier=None, level=ModuleLevel.ATOMIC, tags=None, category=cat
            )
            assert result == ModuleTier.TOOLKIT, f"Expected TOOLKIT for category '{cat}'"

    def test_toolkit_from_subcategory(self):
        result = resolve_tier(
            tier=None, level=ModuleLevel.ATOMIC, tags=None,
            category="atomic", subcategory="string",
        )
        assert result == ModuleTier.TOOLKIT

    def test_toolkit_from_module_id_prefix(self):
        result = resolve_tier(
            tier=None, level=ModuleLevel.ATOMIC, tags=None,
            category="other", module_id="array.filter",
        )
        assert result == ModuleTier.TOOLKIT

    def test_advanced_tag_goes_to_toolkit(self):
        result = resolve_tier(
            tier=None, level=ModuleLevel.ATOMIC,
            tags=['advanced'], category="browser",
        )
        assert result == ModuleTier.TOOLKIT

    def test_template_level_is_featured(self):
        result = resolve_tier(
            tier=None, level=ModuleLevel.TEMPLATE, tags=None, category="browser",
        )
        assert result == ModuleTier.FEATURED

    def test_user_facing_defaults_to_standard(self):
        result = resolve_tier(
            tier=None, level=ModuleLevel.ATOMIC, tags=None, category="browser",
        )
        assert result == ModuleTier.STANDARD


# ============================================================================
# resolve_timeout_ms
# ============================================================================

class TestResolveTimeoutMs:
    """Tests for timeout resolution including edge cases."""

    def test_explicit_timeout_ms(self):
        assert resolve_timeout_ms(5000, None, "test.mod") == 5000

    def test_none_returns_none(self):
        assert resolve_timeout_ms(None, None, "test.mod") is None

    def test_zero_timeout_ms_returns_none(self):
        """timeout_ms=0 means 'no timeout' — normalized to None."""
        assert resolve_timeout_ms(0, None, "test.mod") is None

    def test_negative_timeout_ms_raises(self):
        with pytest.raises(ValueError, match="non-negative"):
            resolve_timeout_ms(-1, None, "test.mod")

    def test_deprecated_timeout_seconds(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = resolve_timeout_ms(None, 5, "test.mod")
            assert result == 5000
            assert len(w) == 1
            assert "deprecated" in str(w[0].message).lower()

    def test_deprecated_timeout_zero_returns_none(self):
        """timeout=0 (deprecated) also means 'no timeout'."""
        result = resolve_timeout_ms(None, 0, "test.mod")
        assert result is None

    def test_negative_deprecated_timeout_raises(self):
        with pytest.raises(ValueError, match="non-negative"):
            resolve_timeout_ms(None, -10, "test.mod")

    def test_timeout_ms_takes_precedence_over_timeout(self):
        """If both are specified, timeout_ms wins."""
        result = resolve_timeout_ms(3000, 10, "test.mod")
        assert result == 3000


# ============================================================================
# resolve_can_be_start
# ============================================================================

class TestResolveCanBeStart:
    """Tests for start-node resolution logic."""

    def test_explicit_true(self):
        assert resolve_can_be_start(True, NodeType.STANDARD, None, [], None) is True

    def test_explicit_false(self):
        assert resolve_can_be_start(False, NodeType.START, None, [], None) is False

    def test_start_node_type(self):
        assert resolve_can_be_start(None, NodeType.START, None, [], None) is True

    def test_trigger_node_type(self):
        assert resolve_can_be_start(None, NodeType.TRIGGER, None, [], None) is True

    def test_flow_control_cannot_start(self):
        for nt in (NodeType.SWITCH, NodeType.MERGE, NodeType.LOOP, NodeType.JOIN, NodeType.END):
            assert resolve_can_be_start(None, nt, None, [], None) is False

    def test_with_input_types_cannot_start(self):
        assert resolve_can_be_start(None, NodeType.STANDARD, ['string'], [], None) is False

    def test_wildcard_input_types_can_start(self):
        assert resolve_can_be_start(None, NodeType.STANDARD, ['*'], [], None) is True

    def test_requires_context_cannot_start(self):
        assert resolve_can_be_start(None, NodeType.STANDARD, None, ['browser'], None) is False

    def test_can_receive_from_start(self):
        assert resolve_can_be_start(None, NodeType.STANDARD, None, [], ['start']) is True
        assert resolve_can_be_start(None, NodeType.STANDARD, None, [], ['start.trigger']) is True

    def test_can_receive_from_non_start(self):
        assert resolve_can_be_start(None, NodeType.STANDARD, None, [], ['browser.*']) is False


# ============================================================================
# enrich_port_handle_metadata
# ============================================================================

class TestEnrichPortHandleMetadata:
    """Tests for port handle auto-filling."""

    def test_existing_handle_id_preserved(self):
        port = {'id': 'input', 'handle_id': 'custom'}
        result = enrich_port_handle_metadata(port, 'input', NodeType.STANDARD)
        assert result['handle_id'] == 'custom'

    def test_input_port_standard(self):
        port = {'id': 'input'}
        result = enrich_port_handle_metadata(port, 'input', NodeType.STANDARD)
        assert result['handle_id'] == 'target'
        assert result['position'] == 'left'

    def test_input_port_loop(self):
        port = {'id': 'input'}
        result = enrich_port_handle_metadata(port, 'input', NodeType.LOOP)
        assert result['handle_id'] == 'in'

    def test_input_port_custom_id(self):
        port = {'id': 'data'}
        result = enrich_port_handle_metadata(port, 'input', NodeType.STANDARD)
        assert result['handle_id'] == 'target-data'

    def test_output_port_success(self):
        port = {'id': 'success'}
        result = enrich_port_handle_metadata(port, 'output', NodeType.STANDARD)
        assert result['handle_id'] == 'output'
        assert result['position'] == 'right'

    def test_output_port_iterate(self):
        port = {'id': 'iterate'}
        result = enrich_port_handle_metadata(port, 'output', NodeType.LOOP)
        assert result['handle_id'] == 'body_out'

    def test_output_port_done(self):
        port = {'id': 'done'}
        result = enrich_port_handle_metadata(port, 'output', NodeType.LOOP)
        assert result['handle_id'] == 'done_out'

    def test_output_port_custom(self):
        port = {'id': 'error'}
        result = enrich_port_handle_metadata(port, 'output', NodeType.STANDARD)
        assert result['handle_id'] == 'source-error'

    def test_does_not_mutate_original(self):
        port = {'id': 'input'}
        result = enrich_port_handle_metadata(port, 'input', NodeType.STANDARD)
        assert 'handle_id' not in port
        assert 'handle_id' in result


# ============================================================================
# _validate_module_registration
# ============================================================================

class TestValidateModuleRegistration:
    """Tests for import-time validation checks."""

    def test_missing_connection_rules_raises(self):
        with pytest.raises(ValueError, match="can_receive_from"):
            _validate_module_registration(
                module_id="test.mod",
                category="test",
                node_type=NodeType.STANDARD,
                input_ports=None,
                output_ports=None,
                can_receive_from=None,
                can_connect_to=['*'],
            )

    def test_missing_can_connect_to_raises(self):
        with pytest.raises(ValueError, match="can_connect_to"):
            _validate_module_registration(
                module_id="test.mod",
                category="test",
                node_type=NodeType.STANDARD,
                input_ports=None,
                output_ports=None,
                can_receive_from=['*'],
                can_connect_to=None,
            )

    def test_flow_module_missing_ports_raises(self):
        with pytest.raises(ValueError, match="input_ports"):
            _validate_module_registration(
                module_id="flow.test",
                category="flow",
                node_type=NodeType.STANDARD,
                input_ports=None,
                output_ports=[{'id': 'success'}],
                can_receive_from=['*'],
                can_connect_to=['*'],
            )

    def test_flow_start_no_input_ports_ok(self):
        """START nodes don't need input ports."""
        _validate_module_registration(
            module_id="flow.start",
            category="flow",
            node_type=NodeType.START,
            input_ports=None,
            output_ports=[{'id': 'success'}],
            can_receive_from=['*'],
            can_connect_to=['*'],
        )

    def test_flow_end_no_output_ports_ok(self):
        """END nodes don't need output ports."""
        _validate_module_registration(
            module_id="flow.end",
            category="flow",
            node_type=NodeType.END,
            input_ports=[{'id': 'input'}],
            output_ports=None,
            can_receive_from=['*'],
            can_connect_to=['*'],
        )

    def test_reserved_event_keyword_in_params(self):
        with pytest.raises(ValueError, match="__event__"):
            _validate_module_registration(
                module_id="test.mod",
                category="test",
                node_type=NodeType.STANDARD,
                input_ports=None,
                output_ports=None,
                can_receive_from=['*'],
                can_connect_to=['*'],
                params_schema={'__event__': {'type': 'string'}},
            )

    def test_valid_registration_passes(self):
        """No exception for valid registration."""
        _validate_module_registration(
            module_id="test.mod",
            category="test",
            node_type=NodeType.STANDARD,
            input_ports=None,
            output_ports=None,
            can_receive_from=['*'],
            can_connect_to=['*'],
            params_schema={'url': {'type': 'string'}},
        )


# ============================================================================
# _wrap_function_as_module
# ============================================================================

class TestWrapFunctionAsModule:
    """Tests for function-to-class wrapping."""

    def test_wraps_async_function(self):
        async def my_func(context):
            """Test module"""
            return {'ok': True}

        wrapped, is_function = _wrap_function_as_module(my_func, "test.func")
        assert is_function is True
        assert wrapped.__doc__ == "Test module"
        assert wrapped.module_id == "test.func"
        assert "my_func" in wrapped.__name__

    def test_class_passes_through(self):
        from core.modules.base import BaseModule

        class MyModule(BaseModule):
            """Test"""
            def validate_params(self): pass
            async def execute(self): pass

        result, is_function = _wrap_function_as_module(MyModule, "test.cls")
        assert is_function is False
        assert result is MyModule
        assert result.module_id == "test.cls"

    @pytest.mark.asyncio
    async def test_wrapped_function_executes(self):
        async def my_func(context):
            """Test module"""
            return {'ok': True, 'data': {'result': context['params']['x'] * 2}}

        wrapped, _ = _wrap_function_as_module(my_func, "test.func")
        instance = wrapped({'x': 5}, {})
        result = await instance.execute()
        assert result == {'ok': True, 'data': {'result': 10}}


# ============================================================================
# build_module_metadata
# ============================================================================

class TestBuildModuleMetadata:
    """Tests for metadata construction."""

    def _make_resolved(self, **overrides):
        base = {
            "category": "test",
            "visibility": UIVisibility.DEFAULT,
            "requires_context": [],
            "provides_context": [],
            "execution_env": ExecutionEnvironment.ALL,
            "input_ports": [],
            "output_ports": [],
            "can_receive_from": ['*'],
            "can_connect_to": ['*'],
            "can_be_start": True,
            "tier": ModuleTier.STANDARD,
            "timeout_ms": None,
        }
        base.update(overrides)
        return base

    def _build(self, **overrides):
        defaults = dict(
            module_id="test.mod",
            version="1.0.0",
            stability=StabilityLevel.STABLE,
            level=ModuleLevel.ATOMIC,
            resolved=self._make_resolved(),
            subcategory=None,
            tags=None,
            ui_label="Test",
            ui_label_key=None,
            ui_description="A test module",
            ui_description_key=None,
            ui_group=None,
            ui_icon=None,
            ui_color=None,
            ui_help=None,
            ui_help_key=None,
            label=None,
            label_key=None,
            description=None,
            description_key=None,
            icon=None,
            color=None,
            input_types=None,
            output_types=None,
            input_type_labels=None,
            input_type_descriptions=None,
            output_type_labels=None,
            output_type_descriptions=None,
            suggested_predecessors=None,
            suggested_successors=None,
            connection_error_messages=None,
            params_schema=None,
            output_schema=None,
            retryable=False,
            max_retries=3,
            concurrent_safe=True,
            requires_credentials=False,
            handles_sensitive_data=False,
            required_permissions=None,
            credential_keys=None,
            required_secrets=None,
            env_vars=None,
            node_type=NodeType.STANDARD,
            dynamic_ports=None,
            container_config=None,
            start_requires_params=None,
            requires=None,
            permissions=None,
            examples=None,
            docs_url=None,
            author=None,
            license_str="MIT",
            required_tier=None,
            required_feature=None,
        )
        defaults.update(overrides)
        return build_module_metadata(**defaults)

    def test_basic_fields(self):
        meta = self._build()
        assert meta["module_id"] == "test.mod"
        assert meta["version"] == "1.0.0"
        assert meta["stability"] == "stable"
        assert meta["level"] == "atomic"
        assert meta["category"] == "test"

    def test_ui_label_fallback_to_legacy(self):
        meta = self._build(ui_label=None, label="Legacy Label")
        assert meta["ui_label"] == "Legacy Label"

    def test_ui_label_fallback_to_module_id(self):
        meta = self._build(ui_label=None, label=None)
        assert meta["ui_label"] == "test.mod"

    def test_retryable_false_zeros_max_retries(self):
        meta = self._build(retryable=False, max_retries=5)
        assert meta["max_retries"] == 0

    def test_retryable_true_keeps_max_retries(self):
        meta = self._build(retryable=True, max_retries=5)
        assert meta["max_retries"] == 5

    def test_enum_values_serialized(self):
        meta = self._build()
        assert isinstance(meta["stability"], str)
        assert isinstance(meta["level"], str)
        assert isinstance(meta["tier"], str)
        assert isinstance(meta["node_type"], str)
        assert isinstance(meta["execution_environment"], str)

    def test_none_lists_default_to_empty(self):
        meta = self._build(
            tags=None, required_permissions=None,
            credential_keys=None, examples=None,
        )
        assert meta["tags"] == []
        assert meta["required_permissions"] == []
        assert meta["credential_keys"] == []
        assert meta["examples"] == []


# ============================================================================
# ModuleRegistry
# ============================================================================

class TestModuleRegistry:
    """Tests for core registry operations."""

    def setup_method(self):
        """Save and restore registry state."""
        self._saved_modules = ModuleRegistry._modules.copy()
        self._saved_metadata = ModuleRegistry._metadata.copy()

    def teardown_method(self):
        ModuleRegistry._modules = self._saved_modules
        ModuleRegistry._metadata = self._saved_metadata

    def test_register_and_get(self):
        from core.modules.base import BaseModule

        class DummyModule(BaseModule):
            """Dummy"""
            def validate_params(self): pass
            async def execute(self): return {}

        ModuleRegistry.register("_test.dummy", DummyModule, {"module_id": "_test.dummy"})
        assert ModuleRegistry.has("_test.dummy")
        assert ModuleRegistry.get("_test.dummy") is DummyModule

    def test_get_nonexistent_raises(self):
        with pytest.raises(ValueError):
            ModuleRegistry.get("_nonexistent.module.xyz")

    def test_unregister(self):
        from core.modules.base import BaseModule

        class TempModule(BaseModule):
            """Temp"""
            def validate_params(self): pass
            async def execute(self): return {}

        ModuleRegistry.register("_test.temp", TempModule, {"module_id": "_test.temp"})
        assert ModuleRegistry.has("_test.temp")
        ModuleRegistry.unregister("_test.temp")
        assert not ModuleRegistry.has("_test.temp")

    def test_validate_connection_graph_returns_dict(self):
        result = ModuleRegistry.validate_connection_graph()
        assert 'orphaned_receive' in result
        assert 'orphaned_connect' in result
        assert isinstance(result['orphaned_receive'], list)
        assert isinstance(result['orphaned_connect'], list)

    def test_validate_connection_graph_detects_orphaned_patterns(self):
        """Register a module with a bogus can_receive_from pattern."""
        from core.modules.base import BaseModule

        class OrphanedModule(BaseModule):
            """Orphan test"""
            def validate_params(self): pass
            async def execute(self): return {}

        ModuleRegistry.register("_test.orphan", OrphanedModule, {
            "module_id": "_test.orphan",
            "can_receive_from": ["nonexistent_category_xyz.*"],
            "can_connect_to": ["also_nonexistent.*"],
        })

        result = ModuleRegistry.validate_connection_graph()
        assert any("_test.orphan" in e for e in result['orphaned_receive'])
        assert any("_test.orphan" in e for e in result['orphaned_connect'])

        # Cleanup
        ModuleRegistry.unregister("_test.orphan")

    def test_get_snapshot(self):
        snapshot = ModuleRegistry.get_snapshot()
        assert snapshot.registry_version is not None
        assert snapshot.module_count > 0
        assert len(snapshot.modules_hash) == 12


# ============================================================================
# retry.py — structured logging
# ============================================================================

class TestRetryStructuredLogging:
    """Tests for retry observability improvements."""

    @pytest.mark.asyncio
    async def test_retry_logs_structured_fields(self, caplog):
        attempt_count = 0

        async def flaky_fn():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise RuntimeError("transient error")
            return {"ok": True}

        with caplog.at_level(logging.WARNING):
            result = await execute_with_retry(
                step_id="test_step",
                execute_fn=flaky_fn,
                retry_config={"count": 3, "delay_ms": 10, "backoff": "linear"},
                workflow_id="wf-test",
            )

        assert result == {"ok": True}
        assert attempt_count == 3

        # Check structured fields in log records
        retry_records = [r for r in caplog.records if "Retrying" in r.message]
        assert len(retry_records) == 2

        for record in retry_records:
            assert record.step_id == "test_step"
            assert record.error_type == "RuntimeError"
            assert record.workflow_id == "wf-test"
            assert hasattr(record, "backoff_ms")
            assert hasattr(record, "retry_count")

    @pytest.mark.asyncio
    async def test_final_failure_logs_structured_fields(self, caplog):
        async def always_fail():
            raise ValueError("permanent error")

        with caplog.at_level(logging.ERROR):
            with pytest.raises(Exception):
                await execute_with_retry(
                    step_id="fail_step",
                    execute_fn=always_fail,
                    retry_config={"count": 1, "delay_ms": 10, "backoff": "linear"},
                    workflow_id="wf-fail",
                )

        error_records = [r for r in caplog.records if "failed after" in r.message]
        assert len(error_records) == 1
        record = error_records[0]
        assert record.step_id == "fail_step"
        assert record.final_error_type == "ValueError"
        assert record.workflow_id == "wf-fail"


class TestCalculateWaitTime:
    """Tests for backoff calculation."""

    def test_linear_backoff(self):
        assert _calculate_wait_time(1000, 0, 'linear') == 1.0
        assert _calculate_wait_time(1000, 1, 'linear') == 2.0
        assert _calculate_wait_time(1000, 2, 'linear') == 3.0

    def test_exponential_backoff(self):
        from core.constants import EXPONENTIAL_BACKOFF_BASE
        assert _calculate_wait_time(1000, 0, 'exponential') == 1.0 * (EXPONENTIAL_BACKOFF_BASE ** 0)
        assert _calculate_wait_time(1000, 1, 'exponential') == 1.0 * (EXPONENTIAL_BACKOFF_BASE ** 1)

    def test_fixed_backoff(self):
        assert _calculate_wait_time(500, 0, 'fixed') == 0.5
        assert _calculate_wait_time(500, 5, 'fixed') == 0.5
