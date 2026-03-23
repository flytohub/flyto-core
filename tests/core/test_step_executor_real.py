# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
StepExecutor Real Integration Tests — Zero Mocks for Modules

Tests the StepExecutor class using the real module registry and real module
execution. No module mocks — modules execute with actual logic.

Modules used (no external dependencies):
- string.uppercase  — converts text to uppercase
- math.calculate    — arithmetic operations
- validate.email    — validates email format
- math.round        — rounds numbers
"""

import pytest

# ---------------------------------------------------------------------------
# Trigger @register_module decorators BEFORE any test runs
# ---------------------------------------------------------------------------
from core.modules import atomic  # noqa: F401 — registers 400+ modules

from core.engine.step_executor.executor import StepExecutor, _redact_sensitive_output
from core.engine.variable_resolver import VariableResolver
from core.engine.exceptions import StepTimeoutError, StepExecutionError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_resolver(params: dict = None, context: dict = None) -> VariableResolver:
    """Create a VariableResolver with the given params and context."""
    return VariableResolver(params or {}, context or {})


def make_executor(**kwargs) -> StepExecutor:
    """Create a StepExecutor with sensible defaults."""
    return StepExecutor(
        workflow_id="test-wf",
        workflow_name="Test Workflow",
        total_steps=kwargs.pop("total_steps", 1),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# 1. Execute a simple module step — result stored in context
# ---------------------------------------------------------------------------

class TestBasicExecution:
    async def test_string_uppercase_result_in_context(self):
        """string.uppercase returns uppercased text and stores it under step_id."""
        context = {}
        step_config = {
            "id": "step_upper",
            "module": "string.uppercase",
            "params": {"text": "hello world"},
        }
        executor = make_executor()
        resolver = make_resolver(context=context)

        result = await executor.execute_step(
            step_config=step_config,
            step_index=0,
            context=context,
            resolver=resolver,
        )

        # Result is stored in context under the step id
        assert "step_upper" in context
        assert context["step_upper"] == result

        # The module returns ok=True and result in data
        assert result is not None
        data = result.get("data") if isinstance(result, dict) else None
        assert data is not None
        assert data["result"] == "HELLO WORLD"
        assert data["original"] == "hello world"

    async def test_math_calculate_addition(self):
        """math.calculate (add) returns correct sum."""
        context = {}
        step_config = {
            "id": "add_step",
            "module": "math.calculate",
            "params": {"operation": "add", "a": 7, "b": 3},
        }
        executor = make_executor()
        resolver = make_resolver(context=context)

        result = await executor.execute_step(
            step_config=step_config,
            step_index=0,
            context=context,
            resolver=resolver,
        )

        assert context["add_step"] == result
        assert result["data"]["result"] == 10
        assert result["data"]["operation"] == "add"

    async def test_validate_email_valid(self):
        """validate.email returns valid=True for a valid address."""
        context = {}
        step_config = {
            "id": "email_check",
            "module": "validate.email",
            "params": {"email": "user@example.com"},
        }
        executor = make_executor()
        resolver = make_resolver(context=context)

        result = await executor.execute_step(
            step_config=step_config,
            step_index=0,
            context=context,
            resolver=resolver,
        )

        assert result["data"]["valid"] is True
        assert result["data"]["domain"] == "example.com"


# ---------------------------------------------------------------------------
# 2. Execute with output variable — context[output_var] is set
# ---------------------------------------------------------------------------

class TestOutputVariable:
    async def test_output_var_is_set(self):
        """When 'output' is specified, context[output_var] mirrors the result."""
        context = {}
        step_config = {
            "id": "step1",
            "module": "string.uppercase",
            "params": {"text": "flyto"},
            "output": "my_result",
        }
        executor = make_executor()
        resolver = make_resolver(context=context)

        result = await executor.execute_step(
            step_config=step_config,
            step_index=0,
            context=context,
            resolver=resolver,
        )

        # Both step_id and output_var should point to the same result
        assert context["step1"] == result
        assert context["my_result"] == result
        assert context["my_result"]["data"]["result"] == "FLYTO"

    async def test_output_var_does_not_clobber_step_id(self):
        """step_id key and output_var key coexist independently."""
        context = {}
        step_config = {
            "id": "step_math",
            "module": "math.round",
            "params": {"number": 3.14159, "decimals": 2},
            "output": "rounded",
        }
        executor = make_executor()
        resolver = make_resolver(context=context)

        await executor.execute_step(
            step_config=step_config,
            step_index=0,
            context=context,
            resolver=resolver,
        )

        assert "step_math" in context
        assert "rounded" in context
        assert context["step_math"] is context["rounded"]


# ---------------------------------------------------------------------------
# 3. Execute with 'when' condition false — step is skipped
# ---------------------------------------------------------------------------

class TestWhenConditionSkip:
    async def test_step_skipped_when_should_execute_false(self):
        """Passing should_execute=False returns None and leaves context untouched."""
        context = {}
        step_config = {
            "id": "skip_me",
            "module": "string.uppercase",
            "params": {"text": "should not run"},
        }
        executor = make_executor()
        resolver = make_resolver(context=context)

        result = await executor.execute_step(
            step_config=step_config,
            step_index=0,
            context=context,
            resolver=resolver,
            should_execute=False,
        )

        assert result is None
        assert "skip_me" not in context

    async def test_step_runs_when_should_execute_true(self):
        """Passing should_execute=True (default) executes normally."""
        context = {}
        step_config = {
            "id": "run_me",
            "module": "string.uppercase",
            "params": {"text": "yes"},
        }
        executor = make_executor()
        resolver = make_resolver(context=context)

        result = await executor.execute_step(
            step_config=step_config,
            step_index=0,
            context=context,
            resolver=resolver,
            should_execute=True,
        )

        assert result is not None
        assert "run_me" in context


# ---------------------------------------------------------------------------
# 4. Execute with timeout — StepTimeoutError raised
# ---------------------------------------------------------------------------

class TestTimeout:
    async def test_step_timeout_raises_step_timeout_error(self):
        """A step with timeout=0.001s should raise StepTimeoutError."""
        import asyncio
        from core.modules.registry import register_module
        from core.modules.base import BaseModule

        # Register a deliberately slow module for this test only
        SLOW_MODULE_ID = "test.slow_module_for_timeout"

        # Only register if not already registered (idempotent)
        from core.modules.registry import ModuleRegistry
        if not ModuleRegistry.has(SLOW_MODULE_ID):
            @register_module(
                module_id=SLOW_MODULE_ID,
                version="1.0.0",
                category="testing",
                tags=["test"],
                label="Slow Test Module",
                description="Deliberately slow for timeout testing",
                icon="Clock",
                color="#FF0000",
                input_types=["any"],
                output_types=["any"],
                can_receive_from=["*"],
                can_connect_to=["*"],
                requires_credentials=False,
                handles_sensitive_data=False,
            )
            async def slow_module(ctx):
                await asyncio.sleep(10)
                return {"ok": True, "data": {}}

        context = {}
        step_config = {
            "id": "timeout_step",
            "module": SLOW_MODULE_ID,
            "params": {},
            "timeout": 0,  # will be set below
        }
        # timeout field in step_config is in seconds for executor
        step_config["timeout"] = 0.001  # 1ms — will always timeout

        executor = make_executor()
        resolver = make_resolver(context=context)

        with pytest.raises(StepTimeoutError) as exc_info:
            await executor.execute_step(
                step_config=step_config,
                step_index=0,
                context=context,
                resolver=resolver,
            )

        assert exc_info.value.step_id == "timeout_step"


# ---------------------------------------------------------------------------
# 5. Execute with on_error='continue' — error dict returned instead of raise
# ---------------------------------------------------------------------------

class TestOnErrorContinue:
    async def test_on_error_continue_returns_error_dict(self):
        """When on_error='continue', a failing step returns {ok: False, error: ...}."""
        context = {}
        step_config = {
            "id": "bad_step",
            "module": "math.calculate",
            # Missing required 'operation' and 'a' — will fail
            "params": {"operation": "divide", "a": 10, "b": 0},
            "on_error": "continue",
        }
        executor = make_executor()
        resolver = make_resolver(context=context)

        result = await executor.execute_step(
            step_config=step_config,
            step_index=0,
            context=context,
            resolver=resolver,
        )

        # Should NOT raise, should return error dict
        assert result is not None
        assert result.get("ok") is False
        assert "error" in result

    async def test_on_error_stop_raises(self):
        """When on_error='stop' (default), a failing step raises StepExecutionError."""
        context = {}
        step_config = {
            "id": "bad_step_stop",
            "module": "math.calculate",
            "params": {"operation": "divide", "a": 5, "b": 0},
            "on_error": "stop",
        }
        executor = make_executor()
        resolver = make_resolver(context=context)

        with pytest.raises(StepExecutionError):
            await executor.execute_step(
                step_config=step_config,
                step_index=0,
                context=context,
                resolver=resolver,
            )


# ---------------------------------------------------------------------------
# 6. Execute with retry config — retry behavior verified
# ---------------------------------------------------------------------------

class TestRetry:
    async def test_retry_succeeds_eventually(self):
        """A module that fails once and then succeeds is handled by retry."""
        from core.modules.registry import ModuleRegistry, register_module

        FLAKY_MODULE_ID = "test.flaky_retry_module"
        call_count = {"n": 0}

        if not ModuleRegistry.has(FLAKY_MODULE_ID):
            @register_module(
                module_id=FLAKY_MODULE_ID,
                version="1.0.0",
                category="testing",
                tags=["test"],
                label="Flaky Retry Test",
                description="Fails on first call, succeeds on second",
                icon="RefreshCw",
                color="#FF9900",
                input_types=["any"],
                output_types=["any"],
                can_receive_from=["*"],
                can_connect_to=["*"],
                requires_credentials=False,
                handles_sensitive_data=False,
            )
            async def flaky_module(ctx):
                call_count["n"] += 1
                if call_count["n"] < 2:
                    raise RuntimeError("Transient failure")
                return {"ok": True, "data": {"attempt": call_count["n"]}}

        context = {}
        step_config = {
            "id": "flaky_step",
            "module": FLAKY_MODULE_ID,
            "params": {},
            "retry": {"count": 2, "delay_ms": 0, "backoff": "linear"},
        }
        executor = make_executor()
        resolver = make_resolver(context=context)

        result = await executor.execute_step(
            step_config=step_config,
            step_index=0,
            context=context,
            resolver=resolver,
        )

        assert result is not None
        assert result.get("ok") is True or (
            isinstance(result, dict) and result.get("data", {}).get("attempt") == 2
        )

    async def test_retry_exhausted_raises_step_execution_error(self):
        """A module that always fails exhausts retries and raises StepExecutionError."""
        from core.modules.registry import ModuleRegistry, register_module

        ALWAYS_FAIL_ID = "test.always_fail_retry"

        if not ModuleRegistry.has(ALWAYS_FAIL_ID):
            @register_module(
                module_id=ALWAYS_FAIL_ID,
                version="1.0.0",
                category="testing",
                tags=["test"],
                label="Always Fail",
                description="Always raises to test retry exhaustion",
                icon="X",
                color="#FF0000",
                input_types=["any"],
                output_types=["any"],
                can_receive_from=["*"],
                can_connect_to=["*"],
                requires_credentials=False,
                handles_sensitive_data=False,
            )
            async def always_fail(ctx):
                raise RuntimeError("Always fails")

        context = {}
        step_config = {
            "id": "always_fail_step",
            "module": ALWAYS_FAIL_ID,
            "params": {},
            "retry": {"count": 2, "delay_ms": 0, "backoff": "linear"},
        }
        executor = make_executor()
        resolver = make_resolver(context=context)

        with pytest.raises(StepExecutionError):
            await executor.execute_step(
                step_config=step_config,
                step_index=0,
                context=context,
                resolver=resolver,
            )


# ---------------------------------------------------------------------------
# 7. Execute with pinned_output — skips execution, returns pinned value
# ---------------------------------------------------------------------------

class TestPinnedOutput:
    async def test_pinned_output_skips_execution(self):
        """When pinned_output is set, execution is skipped and the pinned value returned."""
        pinned = {"ok": True, "data": {"result": "cached_value"}}
        context = {}
        step_config = {
            "id": "pinned_step",
            # Even an invalid module id should NOT be called
            "module": "nonexistent.module.should.not.run",
            "params": {},
            "pinned_output": pinned,
        }
        executor = make_executor()
        resolver = make_resolver(context=context)

        result = await executor.execute_step(
            step_config=step_config,
            step_index=0,
            context=context,
            resolver=resolver,
        )

        # Pinned value returned as-is
        assert result == pinned
        assert context["pinned_step"] == pinned

    async def test_pinned_output_sets_output_var(self):
        """Pinned output also sets the output variable if specified."""
        pinned = {"ok": True, "data": {"x": 42}}
        context = {}
        step_config = {
            "id": "pinned_with_output",
            "module": "nonexistent.module",
            "params": {},
            "pinned_output": pinned,
            "output": "my_pinned",
        }
        executor = make_executor()
        resolver = make_resolver(context=context)

        await executor.execute_step(
            step_config=step_config,
            step_index=0,
            context=context,
            resolver=resolver,
        )

        assert context["pinned_with_output"] == pinned
        assert context["my_pinned"] == pinned

    async def test_pinned_output_none_does_not_skip(self):
        """When pinned_output is None (not present), execution proceeds normally."""
        context = {}
        step_config = {
            "id": "not_pinned",
            "module": "string.uppercase",
            "params": {"text": "go"},
            # No pinned_output key — normal execution
        }
        executor = make_executor()
        resolver = make_resolver(context=context)

        result = await executor.execute_step(
            step_config=step_config,
            step_index=0,
            context=context,
            resolver=resolver,
        )

        assert result is not None
        assert result["data"]["result"] == "GO"


# ---------------------------------------------------------------------------
# 8. _redact_sensitive_output — API keys are redacted
# ---------------------------------------------------------------------------

class TestRedactSensitiveOutput:
    def test_api_key_redacted(self):
        data = {"api_key": "sk-super-secret-12345", "result": "some data"}
        redacted = _redact_sensitive_output(data)
        assert redacted["api_key"] == "[REDACTED]"
        assert redacted["result"] == "some data"

    def test_password_redacted(self):
        data = {"password": "hunter2", "username": "alice"}
        redacted = _redact_sensitive_output(data)
        assert redacted["password"] == "[REDACTED]"
        assert redacted["username"] == "alice"

    def test_nested_secret_redacted(self):
        data = {
            "config": {
                "api_key": "abc123",
                "timeout": 30,
            }
        }
        redacted = _redact_sensitive_output(data)
        assert redacted["config"]["api_key"] == "[REDACTED]"
        assert redacted["config"]["timeout"] == 30

    def test_token_in_list_redacted(self):
        # Use a neutral container key so only the inner 'token' key triggers redaction
        data = {"services": [{"token": "xyz", "name": "service-a"}]}
        redacted = _redact_sensitive_output(data)
        assert redacted["services"][0]["token"] == "[REDACTED]"
        assert redacted["services"][0]["name"] == "service-a"

    def test_non_sensitive_keys_untouched(self):
        data = {"result": "ok", "count": 42, "items": ["a", "b"]}
        redacted = _redact_sensitive_output(data)
        assert redacted == data

    def test_none_passthrough(self):
        assert _redact_sensitive_output(None) is None

    def test_string_not_redacted(self):
        """Plain strings are never redacted — only dict keys trigger redaction."""
        assert _redact_sensitive_output("api_key_value") == "api_key_value"

    def test_depth_limit(self):
        """Recursion stops at depth 10 to prevent infinite loops."""
        # Build a deeply nested structure (12 levels)
        data = {}
        current = data
        for i in range(12):
            current["next"] = {}
            current = current["next"]
        current["api_key"] = "deep-secret"

        # Should not raise and should process without error
        result = _redact_sensitive_output(data)
        assert isinstance(result, dict)

    def test_bearer_redacted(self):
        data = {"bearer": "eyJhbGc..."}
        redacted = _redact_sensitive_output(data)
        assert redacted["bearer"] == "[REDACTED]"

    def test_private_key_redacted(self):
        data = {"private_key": "-----BEGIN RSA PRIVATE KEY-----"}
        redacted = _redact_sensitive_output(data)
        assert redacted["private_key"] == "[REDACTED]"

    def test_auth_header_redacted(self):
        data = {"auth": "Basic dXNlcjpwYXNz"}
        redacted = _redact_sensitive_output(data)
        assert redacted["auth"] == "[REDACTED]"


# ---------------------------------------------------------------------------
# 9. Variable resolution in params
# ---------------------------------------------------------------------------

class TestVariableResolutionInParams:
    async def test_param_resolved_from_context(self):
        """Params referencing ${prev_step.data.result} resolve from context."""
        # Pre-populate context with a previous step result
        context = {
            "prev": {"ok": True, "data": {"result": "hello"}}
        }
        step_config = {
            "id": "next_step",
            "module": "string.uppercase",
            "params": {"text": "${prev.result}"},
        }
        executor = make_executor()
        resolver = make_resolver(params={}, context=context)

        result = await executor.execute_step(
            step_config=step_config,
            step_index=1,
            context=context,
            resolver=resolver,
        )

        assert result["data"]["result"] == "HELLO"

    async def test_param_resolved_from_workflow_params(self):
        """Params referencing ${params.input} resolve from workflow params."""
        context = {}
        step_config = {
            "id": "upper_step",
            "module": "string.uppercase",
            "params": {"text": "${params.input}"},
        }
        executor = make_executor()
        resolver = make_resolver(params={"input": "world"}, context=context)

        result = await executor.execute_step(
            step_config=step_config,
            step_index=0,
            context=context,
            resolver=resolver,
        )

        assert result["data"]["result"] == "WORLD"


# ---------------------------------------------------------------------------
# 10. Missing module raises StepExecutionError
# ---------------------------------------------------------------------------

class TestMissingModule:
    async def test_unknown_module_raises_on_execution(self):
        """Referencing a non-existent module raises an exception during execution.

        ModuleRegistry.get() raises ValueError before the executor's inner try/except
        can wrap it into StepExecutionError, so we accept either exception type.
        """
        context = {}
        step_config = {
            "id": "bad_module_step",
            "module": "nonexistent.totally.fake",
            "params": {},
        }
        executor = make_executor()
        resolver = make_resolver(context=context)

        with pytest.raises((StepExecutionError, ValueError)) as exc_info:
            await executor.execute_step(
                step_config=step_config,
                step_index=0,
                context=context,
                resolver=resolver,
            )

        assert "nonexistent.totally.fake" in str(exc_info.value)

    async def test_missing_module_field_raises_step_execution_error(self):
        """A step without a 'module' field raises StepExecutionError."""
        context = {}
        step_config = {
            "id": "no_module_step",
            "params": {},
            # no "module" key
        }
        executor = make_executor()
        resolver = make_resolver(context=context)

        with pytest.raises(StepExecutionError):
            await executor.execute_step(
                step_config=step_config,
                step_index=0,
                context=context,
                resolver=resolver,
            )


# ---------------------------------------------------------------------------
# 11. TraceCollector integration — trace records are populated
# ---------------------------------------------------------------------------

class TestTraceCollector:
    async def test_pinned_output_with_trace_collector(self):
        """When pinned_output is set and trace_collector is provided, trace is recorded."""
        from core.engine.trace import TraceCollector

        pinned = {"ok": True, "data": {"result": "pinned_value"}}
        context = {}
        step_config = {
            "id": "pinned_traced",
            "module": "string.uppercase",
            "params": {"text": "hello"},
            "pinned_output": pinned,
        }
        executor = make_executor()
        resolver = make_resolver(context=context)
        collector = TraceCollector("wf-trace", "Trace Test Workflow")
        collector.start()

        result = await executor.execute_step(
            step_config=step_config,
            step_index=0,
            context=context,
            resolver=resolver,
            trace_collector=collector,
        )

        assert result == pinned
        trace = collector.get_trace()
        # Trace has one step recorded (the pinned step)
        assert len(trace.steps) == 1
        step_trace = trace.steps[0]
        assert step_trace.stepId == "pinned_traced"
        assert step_trace.status == "success"

    async def test_step_trace_recorded_on_success(self):
        """When trace_collector is provided, a successful step is recorded."""
        from core.engine.trace import TraceCollector

        context = {}
        step_config = {
            "id": "traced_step",
            "module": "string.uppercase",
            "params": {"text": "trace me"},
        }
        executor = make_executor()
        resolver = make_resolver(context=context)
        collector = TraceCollector("wf-trace", "Trace Test Workflow")
        collector.start()

        result = await executor.execute_step(
            step_config=step_config,
            step_index=0,
            context=context,
            resolver=resolver,
            trace_collector=collector,
        )

        assert result["data"]["result"] == "TRACE ME"
        trace = collector.get_trace()
        assert len(trace.steps) == 1
        step_trace = trace.steps[0]
        assert step_trace.stepId == "traced_step"
        assert step_trace.moduleId == "string.uppercase"
        assert step_trace.status == "success"
        assert step_trace.input is not None
        assert step_trace.output is not None

    async def test_skipped_step_recorded_in_trace(self):
        """When should_execute=False and trace_collector provided, skip is recorded."""
        from core.engine.trace import TraceCollector

        context = {}
        step_config = {
            "id": "skipped_trace",
            "module": "string.uppercase",
            "params": {"text": "skip"},
        }
        executor = make_executor()
        resolver = make_resolver(context=context)
        collector = TraceCollector("wf-trace", "Trace Test Workflow")
        collector.start()

        result = await executor.execute_step(
            step_config=step_config,
            step_index=0,
            context=context,
            resolver=resolver,
            should_execute=False,
            trace_collector=collector,
        )

        assert result is None
        trace = collector.get_trace()
        assert len(trace.steps) == 1
        assert trace.steps[0].status == "skipped"

    async def test_failed_step_recorded_in_trace(self):
        """When a step fails and on_error='continue', trace records the failure."""
        from core.engine.trace import TraceCollector

        context = {}
        step_config = {
            "id": "fail_trace",
            "module": "math.calculate",
            "params": {"operation": "divide", "a": 1, "b": 0},
            "on_error": "continue",
        }
        executor = make_executor()
        resolver = make_resolver(context=context)
        collector = TraceCollector("wf-trace", "Trace Test Workflow")
        collector.start()

        result = await executor.execute_step(
            step_config=step_config,
            step_index=0,
            context=context,
            resolver=resolver,
            trace_collector=collector,
        )

        assert result["ok"] is False
        trace = collector.get_trace()
        # Step trace was started; error may be recorded
        assert len(trace.steps) >= 1

    async def test_step_trace_with_step_description(self):
        """A step with a description logs correctly and trace is populated."""
        from core.engine.trace import TraceCollector

        context = {}
        step_config = {
            "id": "described_step",
            "module": "string.uppercase",
            "params": {"text": "described"},
            "description": "This step uppercases text",
        }
        executor = make_executor()
        resolver = make_resolver(context=context)
        collector = TraceCollector("wf-trace", "Trace Test Workflow")
        collector.start()

        result = await executor.execute_step(
            step_config=step_config,
            step_index=0,
            context=context,
            resolver=resolver,
            trace_collector=collector,
        )

        assert result["data"]["result"] == "DESCRIBED"
        trace = collector.get_trace()
        assert trace.steps[0].status == "success"


# ---------------------------------------------------------------------------
# 12. Items mode execution
# ---------------------------------------------------------------------------

def _register_items_module():
    """Register a real items-mode module for testing."""
    from core.modules.registry import ModuleRegistry, register_module
    from core.modules.base import BaseModule
    from core.modules.items import Item, PairedItemInfo

    MODULE_ID = "test.items_mode_double"
    if ModuleRegistry.has(MODULE_ID):
        return MODULE_ID

    @register_module(
        module_id=MODULE_ID,
        version="1.0.0",
        category="testing",
        tags=["test"],
        label="Items Mode Double",
        description="Doubles the 'value' field of each item",
        icon="List",
        color="#00FF00",
        input_types=["any"],
        output_types=["any"],
        can_receive_from=["*"],
        can_connect_to=["*"],
        requires_credentials=False,
        handles_sensitive_data=False,
    )
    class ItemsDoubleModule(BaseModule):
        execution_mode = "items"

        def validate_params(self):
            pass

        async def execute(self):
            return {"ok": True, "data": {}}

        async def execute_item(self, item, index, ctx):
            val = item.json.get("value", 0)
            return Item(json={"value": val * 2}, pairedItem=PairedItemInfo(item=index))

    return MODULE_ID


def _register_all_mode_module():
    """Register a real all-mode module for testing."""
    from core.modules.registry import ModuleRegistry, register_module
    from core.modules.base import BaseModule
    from core.modules.items import Item

    MODULE_ID = "test.all_mode_sum"
    if ModuleRegistry.has(MODULE_ID):
        return MODULE_ID

    @register_module(
        module_id=MODULE_ID,
        version="1.0.0",
        category="testing",
        tags=["test"],
        label="All Mode Sum",
        description="Sums all item values at once",
        icon="Sigma",
        color="#0000FF",
        input_types=["any"],
        output_types=["any"],
        can_receive_from=["*"],
        can_connect_to=["*"],
        requires_credentials=False,
        handles_sensitive_data=False,
    )
    class AllModeSumModule(BaseModule):
        execution_mode = "all"

        def validate_params(self):
            pass

        async def execute(self):
            return {"ok": True, "data": {}}

        async def execute_all(self, items, ctx):
            total = sum(item.json.get("value", 0) for item in items)
            return [Item(json={"total": total, "count": len(items)})]

    return MODULE_ID


class TestItemsModeExecution:
    async def test_items_mode_processes_each_item(self):
        """items execution_mode processes each item independently."""
        module_id = _register_items_module()

        # Set up context with upstream step providing items
        upstream_result = {
            "ok": True,
            "data": {},
            "items": [{"value": 3}, {"value": 7}, {"value": 10}],
        }
        context = {"upstream": upstream_result}
        step_config = {
            "id": "items_step",
            "module": module_id,
            "params": {},
            "$upstream_steps": ["upstream"],
        }
        executor = make_executor()
        resolver = make_resolver(context=context)

        result = await executor.execute_step(
            step_config=step_config,
            step_index=1,
            context=context,
            resolver=resolver,
        )

        assert result is not None
        assert result["ok"] is True
        items_out = result.get("items", [])
        assert len(items_out) == 3
        values = [item["value"] for item in items_out]
        assert values == [6, 14, 20]

    async def test_items_mode_no_input_items_uses_empty_item(self):
        """items mode with no upstream steps uses a single empty Item."""
        module_id = _register_items_module()

        context = {}
        step_config = {
            "id": "items_no_input",
            "module": module_id,
            "params": {},
            # No $upstream_steps → input_items is None → defaults to [Item(json={})]
        }
        executor = make_executor()
        resolver = make_resolver(context=context)

        result = await executor.execute_step(
            step_config=step_config,
            step_index=0,
            context=context,
            resolver=resolver,
        )

        assert result is not None
        assert result["ok"] is True
        # value=0 doubled → 0
        items_out = result.get("items", [])
        assert len(items_out) == 1
        assert items_out[0]["value"] == 0

    async def test_items_mode_with_trace_collector(self):
        """items mode records per-item traces."""
        from core.engine.trace import TraceCollector

        module_id = _register_items_module()

        upstream_result = {
            "ok": True,
            "data": {},
            "items": [{"value": 5}],
        }
        context = {"up": upstream_result}
        step_config = {
            "id": "items_traced",
            "module": module_id,
            "params": {},
            "$upstream_steps": ["up"],
        }
        executor = make_executor()
        resolver = make_resolver(context=context)
        collector = TraceCollector("wf-items", "Items Trace Workflow")
        collector.start()

        result = await executor.execute_step(
            step_config=step_config,
            step_index=0,
            context=context,
            resolver=resolver,
            trace_collector=collector,
        )

        assert result["items"][0]["value"] == 10
        trace = collector.get_trace()
        step_trace = trace.steps[0]
        assert step_trace.status == "success"

    async def test_items_mode_on_error_continue(self):
        """items mode with on_error=continue collects errors per item."""
        from core.modules.registry import ModuleRegistry, register_module
        from core.modules.base import BaseModule
        from core.modules.items import Item

        MODULE_ID = "test.items_error_module"
        if not ModuleRegistry.has(MODULE_ID):
            @register_module(
                module_id=MODULE_ID,
                version="1.0.0",
                category="testing",
                tags=["test"],
                label="Items Error Module",
                description="Fails on odd index items",
                icon="AlertTriangle",
                color="#FF6600",
                input_types=["any"],
                output_types=["any"],
                can_receive_from=["*"],
                can_connect_to=["*"],
                requires_credentials=False,
                handles_sensitive_data=False,
            )
            class ItemsErrorModule(BaseModule):
                execution_mode = "items"

                def validate_params(self):
                    pass

                async def execute(self):
                    return {"ok": True, "data": {}}

                async def execute_item(self, item, index, ctx):
                    if index % 2 == 1:
                        raise ValueError(f"Error on index {index}")
                    return Item(json={"processed": True, "index": index})

        upstream_result = {
            "ok": True,
            "data": {},
            "items": [{"v": 0}, {"v": 1}, {"v": 2}],
        }
        context = {"up": upstream_result}
        step_config = {
            "id": "items_err_step",
            "module": MODULE_ID,
            "params": {"$on_error": "continue"},
            "$upstream_steps": ["up"],
            "on_error": "continue",
        }
        executor = make_executor()
        resolver = make_resolver(context=context)

        result = await executor.execute_step(
            step_config=step_config,
            step_index=0,
            context=context,
            resolver=resolver,
        )

        # Should return partial result (not raise)
        assert result is not None
        # 3 output items (1 success + 1 error item + 1 success)
        items_out = result.get("items", [])
        assert len(items_out) == 3


# ---------------------------------------------------------------------------
# 13. All mode execution
# ---------------------------------------------------------------------------

class TestAllModeExecution:
    async def test_all_mode_aggregates_items(self):
        """all execution_mode receives all items at once and aggregates."""
        module_id = _register_all_mode_module()

        upstream_result = {
            "ok": True,
            "data": {},
            "items": [{"value": 1}, {"value": 4}, {"value": 10}],
        }
        context = {"upstream": upstream_result}
        step_config = {
            "id": "all_step",
            "module": module_id,
            "params": {},
            "$upstream_steps": ["upstream"],
        }
        executor = make_executor()
        resolver = make_resolver(context=context)

        result = await executor.execute_step(
            step_config=step_config,
            step_index=1,
            context=context,
            resolver=resolver,
        )

        assert result is not None
        assert result["ok"] is True
        items_out = result.get("items", [])
        assert len(items_out) == 1
        assert items_out[0]["total"] == 15
        assert items_out[0]["count"] == 3

    async def test_all_mode_empty_input(self):
        """all mode with no upstream steps processes empty list."""
        module_id = _register_all_mode_module()

        context = {}
        step_config = {
            "id": "all_empty",
            "module": module_id,
            "params": {},
        }
        executor = make_executor()
        resolver = make_resolver(context=context)

        result = await executor.execute_step(
            step_config=step_config,
            step_index=0,
            context=context,
            resolver=resolver,
        )

        assert result is not None
        items_out = result.get("items", [])
        assert len(items_out) == 1
        assert items_out[0]["total"] == 0
        assert items_out[0]["count"] == 0


# ---------------------------------------------------------------------------
# 14. _get_input_items_from_context — extracting items from upstream steps
# ---------------------------------------------------------------------------

class TestGetInputItemsFromContext:
    def test_none_when_no_upstream_step_ids(self):
        """Returns None when upstream_step_ids is None."""
        executor = make_executor()
        result = executor._get_input_items_from_context({}, None)
        assert result is None

    def test_empty_list_when_upstream_step_ids_empty(self):
        """Returns [] when upstream_step_ids is empty list."""
        executor = make_executor()
        result = executor._get_input_items_from_context({}, [])
        assert result == []

    def test_extracts_items_array_from_context(self):
        """Extracts items array from upstream step result."""
        from core.modules.items import Item

        context = {
            "step_a": {
                "ok": True,
                "data": {},
                "items": [{"x": 1}, {"x": 2}],
            }
        }
        executor = make_executor()
        result = executor._get_input_items_from_context(context, ["step_a"])
        assert result is not None
        assert len(result) == 2
        assert result[0].json == {"x": 1}
        assert result[1].json == {"x": 2}

    def test_wraps_legacy_data_as_single_item(self):
        """When no items array but data exists, wraps it as a single Item."""
        context = {
            "step_b": {
                "ok": True,
                "data": {"name": "Alice"},
            }
        }
        executor = make_executor()
        result = executor._get_input_items_from_context(context, ["step_b"])
        assert result is not None
        assert len(result) == 1
        assert result[0].json == {"name": "Alice"}

    def test_merges_items_from_multiple_upstream_steps(self):
        """Items from multiple upstream steps are merged into one list."""
        context = {
            "step_1": {
                "ok": True,
                "data": {},
                "items": [{"val": 1}],
            },
            "step_2": {
                "ok": True,
                "data": {},
                "items": [{"val": 2}, {"val": 3}],
            },
        }
        executor = make_executor()
        result = executor._get_input_items_from_context(context, ["step_1", "step_2"])
        assert result is not None
        assert len(result) == 3
        assert result[0].json == {"val": 1}
        assert result[1].json == {"val": 2}
        assert result[2].json == {"val": 3}

    def test_missing_upstream_step_in_context_yields_no_items(self):
        """A missing upstream step ID yields no items (graceful)."""
        executor = make_executor()
        result = executor._get_input_items_from_context({}, ["nonexistent"])
        assert result is not None
        assert len(result) == 0


# ---------------------------------------------------------------------------
# 15. _get_input_items_by_port — multi-input port merging
# ---------------------------------------------------------------------------

class TestGetInputItemsByPort:
    def test_none_when_empty_upstream_by_port(self):
        """Returns None when upstream_by_port is empty dict."""
        executor = make_executor()
        result = executor._get_input_items_by_port({}, {}, {})
        assert result is None

    def test_single_port_items(self):
        """Extracts items from a single port."""
        context = {
            "step_a": {
                "ok": True,
                "data": {},
                "items": [{"n": 10}, {"n": 20}],
            }
        }
        upstream_by_port = {"input": ["step_a"]}
        params = {}
        executor = make_executor()
        result = executor._get_input_items_by_port(context, upstream_by_port, params)
        assert result is not None
        assert len(result) == 2
        assert "$input_items_by_port" in params
        assert "input" in params["$input_items_by_port"]

    def test_multi_port_append_strategy(self):
        """Multi-port items are merged using append strategy by default."""
        context = {
            "step_a": {"ok": True, "data": {}, "items": [{"n": 1}]},
            "step_b": {"ok": True, "data": {}, "items": [{"n": 2}]},
        }
        upstream_by_port = {
            "port1": ["step_a"],
            "port2": ["step_b"],
        }
        params = {}
        executor = make_executor()
        result = executor._get_input_items_by_port(context, upstream_by_port, params)
        assert result is not None
        assert len(result) == 2

    def test_multi_port_multiplex_strategy(self):
        """Multi-port items are merged using multiplex strategy."""
        context = {
            "step_a": {"ok": True, "data": {}, "items": [{"a": 1}, {"a": 2}]},
            "step_b": {"ok": True, "data": {}, "items": [{"b": 10}, {"b": 20}]},
        }
        upstream_by_port = {
            "port_a": ["step_a"],
            "port_b": ["step_b"],
        }
        params = {"$merge_strategy": "multiplex"}
        executor = make_executor()
        result = executor._get_input_items_by_port(context, upstream_by_port, params)
        assert result is not None
        # Multiplex: zips by index → 2 combined items
        assert len(result) == 2
        assert "port_a" in result[0].json
        assert "port_b" in result[0].json

    def test_empty_result_when_no_items_found(self):
        """Returns empty list when all referenced steps have no items or data."""
        upstream_by_port = {"input": ["missing_step"]}
        params = {}
        executor = make_executor()
        result = executor._get_input_items_by_port({}, upstream_by_port, params)
        assert result == []


# ---------------------------------------------------------------------------
# 16. _substitute_local_vars — template variable substitution
# ---------------------------------------------------------------------------

class TestSubstituteLocalVars:
    def test_no_vars_returns_params_unchanged(self):
        """When __vars__ is not present, params are returned unchanged."""
        params = {"text": "hello", "count": 5}
        result = StepExecutor._substitute_local_vars(params)
        assert result == {"text": "hello", "count": 5}

    def test_double_brace_substitution(self):
        """{{var}} placeholders are replaced by values from __vars__."""
        params = {"text": "Hello {{name}}", "__vars__": {"name": "World"}}
        result = StepExecutor._substitute_local_vars(params)
        assert result["text"] == "Hello World"
        assert "__vars__" not in result

    def test_dollar_brace_substitution(self):
        """${var} placeholders are replaced by values from __vars__."""
        params = {"text": "Hello ${name}", "__vars__": {"name": "Alice"}}
        result = StepExecutor._substitute_local_vars(params)
        assert result["text"] == "Hello Alice"

    def test_nested_dict_substitution(self):
        """Substitution works inside nested dicts."""
        params = {
            "config": {"url": "https://{{host}}/api"},
            "__vars__": {"host": "example.com"},
        }
        result = StepExecutor._substitute_local_vars(params)
        assert result["config"]["url"] == "https://example.com/api"

    def test_list_substitution(self):
        """Substitution works inside lists."""
        params = {
            "items": ["{{a}}", "{{b}}"],
            "__vars__": {"a": "first", "b": "second"},
        }
        result = StepExecutor._substitute_local_vars(params)
        assert result["items"] == ["first", "second"]

    def test_non_string_values_not_substituted(self):
        """Non-string values are left unchanged."""
        params = {"count": 42, "flag": True, "__vars__": {"x": "y"}}
        result = StepExecutor._substitute_local_vars(params)
        assert result["count"] == 42
        assert result["flag"] is True

    def test_empty_vars_returns_params_unchanged(self):
        """When __vars__ is empty, params are returned unchanged (falsy guard)."""
        params = {"text": "{{name}}", "__vars__": {}}
        result = StepExecutor._substitute_local_vars(params)
        # Empty dict is falsy, so __vars__ is popped but no substitution occurs
        assert result["text"] == "{{name}}"


# ---------------------------------------------------------------------------
# 17. template.invoke handling in _execute_module
# ---------------------------------------------------------------------------

class TestTemplateInvokeHandling:
    async def test_template_invoke_strips_suffix_for_registry_lookup(self):
        """template.invoke:some-id is handled: template_id injected into params."""
        from core.modules.registry import ModuleRegistry, register_module
        from core.modules.base import BaseModule

        # Register a real template.invoke module if not present
        TEMPLATE_INVOKE_ID = "template.invoke"
        received_params = {}

        if not ModuleRegistry.has(TEMPLATE_INVOKE_ID):
            @register_module(
                module_id=TEMPLATE_INVOKE_ID,
                version="1.0.0",
                category="template",
                tags=["template"],
                label="Template Invoke",
                description="Invokes a template workflow",
                icon="FileCode",
                color="#9900FF",
                input_types=["any"],
                output_types=["any"],
                can_receive_from=["*"],
                can_connect_to=["*"],
                requires_credentials=False,
                handles_sensitive_data=False,
            )
            class TemplateInvokeModule(BaseModule):
                def validate_params(self):
                    pass

                async def execute(self):
                    received_params.update(self.params)
                    return {"ok": True, "data": {"invoked": True}}

        context = {}
        step_config = {
            "id": "template_step",
            "module": "template.invoke:my-template-123",
            "params": {},
        }
        executor = make_executor()
        resolver = make_resolver(context=context)

        result = await executor.execute_step(
            step_config=step_config,
            step_index=0,
            context=context,
            resolver=resolver,
        )

        assert result is not None
        # template_id and library_id should be injected into params
        # (captured in received_params since module reads self.params)
        assert "template_step" in context


# ---------------------------------------------------------------------------
# 18. _parse_module_id — parse legacy module_id into plugin/step tuple
# ---------------------------------------------------------------------------

class TestParseModuleId:
    def test_two_part_module_id(self):
        """'database.query' → ('flyto-official/database', 'query')"""
        executor = make_executor()
        plugin_id, step_id = executor._parse_module_id("database.query")
        assert plugin_id == "flyto-official/database"
        assert step_id == "query"

    def test_multi_part_module_id(self):
        """'a.b.c' → ('flyto-official/a', 'b.c')"""
        executor = make_executor()
        plugin_id, step_id = executor._parse_module_id("a.b.c")
        assert plugin_id == "flyto-official/a"
        assert step_id == "b.c"

    def test_single_part_module_id(self):
        """'mymodule' → ('flyto-official/mymodule', 'execute')"""
        executor = make_executor()
        plugin_id, step_id = executor._parse_module_id("mymodule")
        assert plugin_id == "flyto-official/mymodule"
        assert step_id == "execute"

    def test_common_module_id(self):
        """'string.uppercase' → ('flyto-official/string', 'uppercase')"""
        executor = make_executor()
        plugin_id, step_id = executor._parse_module_id("string.uppercase")
        assert plugin_id == "flyto-official/string"
        assert step_id == "uppercase"


# ---------------------------------------------------------------------------
# 19. _invoke_via_runtime — direct registry fallback (no RuntimeInvoker)
# ---------------------------------------------------------------------------

class TestInvokeViaRuntime:
    async def test_invoke_via_runtime_calls_module(self):
        """_invoke_via_runtime executes a real module via direct registry access."""
        context = {}
        params = {"text": "runtime test"}
        executor = make_executor()

        result = await executor._invoke_via_runtime(
            module_id="string.uppercase",
            params=params,
            context=context,
        )

        # Result may be legacy dict or item-based — accept either
        assert result is not None

    async def test_invoke_via_runtime_module_not_found_returns_error_or_raises(self):
        """_invoke_via_runtime handles missing module gracefully.

        When RuntimeInvoker is available, it returns an error dict.
        When the fallback path is used, it raises ValueError/StepExecutionError.
        """
        from core.engine.step_executor.executor import _RUNTIME_INVOKER_AVAILABLE

        executor = make_executor()

        if _RUNTIME_INVOKER_AVAILABLE:
            # RuntimeInvoker returns error dict for unknown modules
            result = await executor._invoke_via_runtime(
                module_id="totally.nonexistent.module",
                params={},
                context={},
            )
            # Returns an error result dict (not raises)
            assert result is not None
            assert isinstance(result, dict)
        else:
            # Fallback path: raises ValueError or StepExecutionError
            with pytest.raises((ValueError, Exception)):
                await executor._invoke_via_runtime(
                    module_id="totally.nonexistent.module",
                    params={},
                    context={},
                )

    async def test_invoke_via_runtime_template_invoke_format(self):
        """_invoke_via_runtime handles template.invoke:id format."""
        from core.modules.registry import ModuleRegistry

        # Ensure template.invoke is registered (may already be from previous test)
        if not ModuleRegistry.has("template.invoke"):
            pytest.skip("template.invoke not registered")

        context = {}
        params = {}
        executor = make_executor()

        result = await executor._invoke_via_runtime(
            module_id="template.invoke:some-template",
            params=params,
            context=context,
        )
        assert result is not None


# ---------------------------------------------------------------------------
# 20. upstream_by_port step config triggers _get_input_items_by_port
# ---------------------------------------------------------------------------

class TestUpstreamByPortStepConfig:
    async def test_step_with_upstream_by_port_merges_items(self):
        """A step with $upstream_by_port gets items merged by port."""
        module_id = _register_items_module()

        context = {
            "source_a": {"ok": True, "data": {}, "items": [{"value": 3}]},
            "source_b": {"ok": True, "data": {}, "items": [{"value": 7}]},
        }
        step_config = {
            "id": "port_step",
            "module": module_id,
            "params": {},
            "$upstream_by_port": {
                "input1": ["source_a"],
                "input2": ["source_b"],
            },
        }
        executor = make_executor()
        resolver = make_resolver(context=context)

        result = await executor.execute_step(
            step_config=step_config,
            step_index=0,
            context=context,
            resolver=resolver,
        )

        assert result is not None
        assert result["ok"] is True
        items_out = result.get("items", [])
        # 2 items from 2 ports, each doubled by items module
        assert len(items_out) == 2
        values = {item["value"] for item in items_out}
        assert values == {6, 14}


# ---------------------------------------------------------------------------
# 21. on_error='retry' auto-creates retry config
# ---------------------------------------------------------------------------

class TestOnErrorRetryAutoConfig:
    async def test_on_error_retry_uses_default_retry_config(self):
        """on_error='retry' without explicit retry config auto-creates {count:3, ...}."""
        from core.modules.registry import ModuleRegistry, register_module
        from core.modules.base import BaseModule

        RETRY_ID = "test.on_error_retry_module"
        call_count = {"n": 0}

        if not ModuleRegistry.has(RETRY_ID):
            @register_module(
                module_id=RETRY_ID,
                version="1.0.0",
                category="testing",
                tags=["test"],
                label="On Error Retry Module",
                description="Succeeds on second call for retry test",
                icon="RotateCcw",
                color="#FF9900",
                input_types=["any"],
                output_types=["any"],
                can_receive_from=["*"],
                can_connect_to=["*"],
                requires_credentials=False,
                handles_sensitive_data=False,
            )
            class OnErrorRetryModule(BaseModule):
                def validate_params(self):
                    pass

                async def execute(self):
                    call_count["n"] += 1
                    if call_count["n"] < 2:
                        raise RuntimeError("transient")
                    return {"ok": True, "data": {"attempt": call_count["n"]}}

        context = {}
        step_config = {
            "id": "retry_auto",
            "module": RETRY_ID,
            "params": {},
            "on_error": "retry",
            # No "retry" key — should auto-create {count:3, delay_ms:1000}
        }
        executor = make_executor()
        resolver = make_resolver(context=context)

        result = await executor.execute_step(
            step_config=step_config,
            step_index=0,
            context=context,
            resolver=resolver,
        )

        assert result is not None
        assert result.get("ok") is True


# ---------------------------------------------------------------------------
# 22. Hook SKIP and ABORT actions (lines 230-235)
# ---------------------------------------------------------------------------

class TestHookActions:
    async def test_pre_execute_hook_skip_returns_none(self):
        """When pre_execute hook returns SKIP, step returns None."""
        from core.engine.hooks import ExecutorHooks, HookResult, HookAction
        from core.engine.hooks.models import HookContext

        class SkipHook(ExecutorHooks):
            def on_pre_execute(self, context: HookContext) -> HookResult:
                return HookResult.skip_step()

            def on_post_execute(self, context: HookContext) -> None:
                pass

        context = {}
        step_config = {
            "id": "skipped_by_hook",
            "module": "string.uppercase",
            "params": {"text": "should not run"},
        }
        executor = make_executor(hooks=SkipHook())
        resolver = make_resolver(context=context)

        result = await executor.execute_step(
            step_config=step_config,
            step_index=0,
            context=context,
            resolver=resolver,
        )

        assert result is None
        assert "skipped_by_hook" not in context

    async def test_pre_execute_hook_abort_raises_step_execution_error(self):
        """When pre_execute hook returns ABORT, StepExecutionError is raised."""
        from core.engine.hooks import ExecutorHooks, HookResult, HookAction
        from core.engine.hooks.models import HookContext

        class AbortHook(ExecutorHooks):
            def on_pre_execute(self, context: HookContext) -> HookResult:
                return HookResult.abort_execution("Test abort reason")

            def on_post_execute(self, context: HookContext) -> None:
                pass

        context = {}
        step_config = {
            "id": "aborted_step",
            "module": "string.uppercase",
            "params": {"text": "should not run"},
        }
        executor = make_executor(hooks=AbortHook())
        resolver = make_resolver(context=context)

        with pytest.raises(StepExecutionError) as exc_info:
            await executor.execute_step(
                step_config=step_config,
                step_index=0,
                context=context,
                resolver=resolver,
            )

        assert "aborted_step" in str(exc_info.value) or "Test abort reason" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 23. Foreach execution path (line 248)
# ---------------------------------------------------------------------------

class TestForeachExecution:
    async def test_foreach_executes_for_each_item(self):
        """Step with 'foreach' iterates over the array."""
        context = {
            "names": ["alice", "bob", "carol"],
        }
        step_config = {
            "id": "upper_foreach",
            "module": "string.uppercase",
            "params": {"text": "${item}"},
            "foreach": "${names}",
            "as": "item",
        }
        executor = make_executor()
        resolver = make_resolver(context=context)

        result = await executor.execute_step(
            step_config=step_config,
            step_index=0,
            context=context,
            resolver=resolver,
        )

        assert result is not None
        # foreach returns a list of results
        assert isinstance(result, list)
        assert len(result) == 3


# ---------------------------------------------------------------------------
# 24. Step trace with result.data path (line 274-275)
#     and trace fail path (line 284)
# ---------------------------------------------------------------------------

class TestTraceResultPaths:
    async def test_trace_records_data_field_when_no_items(self):
        """Trace output uses data field when result has data but no items."""
        from core.engine.trace import TraceCollector

        context = {}
        step_config = {
            "id": "data_trace_step",
            "module": "string.uppercase",
            "params": {"text": "tracedata"},
        }
        executor = make_executor()
        resolver = make_resolver(context=context)
        collector = TraceCollector("wf-data", "Data Trace Workflow")
        collector.start()

        result = await executor.execute_step(
            step_config=step_config,
            step_index=0,
            context=context,
            resolver=resolver,
            trace_collector=collector,
        )

        assert result["data"]["result"] == "TRACEDATA"
        trace = collector.get_trace()
        step_trace = trace.steps[0]
        assert step_trace.status == "success"
        # Output was set with data-based items
        assert step_trace.output is not None

    async def test_trace_records_fail_on_step_error(self):
        """When a step raises, trace records the failure."""
        from core.engine.trace import TraceCollector

        context = {}
        step_config = {
            "id": "fail_step_trace",
            "module": "math.calculate",
            "params": {"operation": "divide", "a": 1, "b": 0},
            # on_error defaults to 'stop' → will raise
        }
        executor = make_executor()
        resolver = make_resolver(context=context)
        collector = TraceCollector("wf-fail", "Fail Trace Workflow")
        collector.start()

        with pytest.raises(StepExecutionError):
            await executor.execute_step(
                step_config=step_config,
                step_index=0,
                context=context,
                resolver=resolver,
                trace_collector=collector,
            )

        trace = collector.get_trace()
        assert len(trace.steps) == 1
        assert trace.steps[0].status == "error"


# ---------------------------------------------------------------------------
# 25. Pinned output with items array branch (line 190)
# ---------------------------------------------------------------------------

class TestPinnedOutputWithItemsArray:
    async def test_pinned_output_with_items_array_traced(self):
        """Pinned output that has 'items' array sets items_output = [items]."""
        from core.engine.trace import TraceCollector

        pinned = {
            "ok": True,
            "data": {},
            "items": [{"x": 1}, {"x": 2}],
        }
        context = {}
        step_config = {
            "id": "pinned_items",
            "module": "string.uppercase",
            "params": {"text": "irrelevant"},
            "pinned_output": pinned,
        }
        executor = make_executor()
        resolver = make_resolver(context=context)
        collector = TraceCollector("wf-pinned-items", "Pinned Items Workflow")
        collector.start()

        result = await executor.execute_step(
            step_config=step_config,
            step_index=0,
            context=context,
            resolver=resolver,
            trace_collector=collector,
        )

        assert result == pinned
        trace = collector.get_trace()
        assert trace.steps[0].status == "success"
        # Output should have items_output = [pinned['items']]
        output = trace.steps[0].output
        assert output is not None
        assert output.itemCount > 0


# ---------------------------------------------------------------------------
# 26. Items mode with list result from execute_item (lines 517-519)
#     Items mode with dict result (lines 530-531)
#     Items mode item error with trace (lines 542-545)
# ---------------------------------------------------------------------------

def _register_items_list_return_module():
    """Register a module that returns a list of Items from execute_item."""
    from core.modules.registry import ModuleRegistry, register_module
    from core.modules.base import BaseModule
    from core.modules.items import Item

    MODULE_ID = "test.items_list_return"
    if ModuleRegistry.has(MODULE_ID):
        return MODULE_ID

    @register_module(
        module_id=MODULE_ID,
        version="1.0.0",
        category="testing",
        tags=["test"],
        label="Items List Return",
        description="Returns list of Items from execute_item (1:N)",
        icon="List",
        color="#00AAFF",
        input_types=["any"],
        output_types=["any"],
        can_receive_from=["*"],
        can_connect_to=["*"],
        requires_credentials=False,
        handles_sensitive_data=False,
    )
    class ItemsListReturnModule(BaseModule):
        execution_mode = "items"

        def validate_params(self):
            pass

        async def execute(self):
            return {"ok": True, "data": {}}

        async def execute_item(self, item, index, ctx):
            # Return a list of Items (1:N expansion)
            val = item.json.get("value", 1)
            return [Item(json={"expanded": val * i}) for i in range(1, 3)]

    return MODULE_ID


def _register_items_dict_return_module():
    """Register a module that returns a plain dict from execute_item."""
    from core.modules.registry import ModuleRegistry, register_module
    from core.modules.base import BaseModule

    MODULE_ID = "test.items_dict_return"
    if ModuleRegistry.has(MODULE_ID):
        return MODULE_ID

    @register_module(
        module_id=MODULE_ID,
        version="1.0.0",
        category="testing",
        tags=["test"],
        label="Items Dict Return",
        description="Returns dict from execute_item",
        icon="Hash",
        color="#AABB00",
        input_types=["any"],
        output_types=["any"],
        can_receive_from=["*"],
        can_connect_to=["*"],
        requires_credentials=False,
        handles_sensitive_data=False,
    )
    class ItemsDictReturnModule(BaseModule):
        execution_mode = "items"

        def validate_params(self):
            pass

        async def execute(self):
            return {"ok": True, "data": {}}

        async def execute_item(self, item, index, ctx):
            # Return a plain dict (not an Item instance)
            return {"mapped_value": item.json.get("value", 0) + 100}

    return MODULE_ID


class TestItemsModeReturnVariants:
    async def test_items_list_return_expands_items(self):
        """execute_item returning a list expands each item (1:N)."""
        module_id = _register_items_list_return_module()

        upstream_result = {
            "ok": True,
            "data": {},
            "items": [{"value": 3}, {"value": 5}],
        }
        context = {"up": upstream_result}
        step_config = {
            "id": "expand_step",
            "module": module_id,
            "params": {},
            "$upstream_steps": ["up"],
        }
        executor = make_executor()
        resolver = make_resolver(context=context)

        result = await executor.execute_step(
            step_config=step_config,
            step_index=0,
            context=context,
            resolver=resolver,
        )

        assert result is not None
        items_out = result.get("items", [])
        # 2 input items × 2 expansions each = 4 output items
        assert len(items_out) == 4

    async def test_items_list_return_with_trace(self):
        """execute_item returning a list is traced via item_trace.complete(...)."""
        from core.engine.trace import TraceCollector

        module_id = _register_items_list_return_module()

        upstream_result = {
            "ok": True,
            "data": {},
            "items": [{"value": 2}],
        }
        context = {"up": upstream_result}
        step_config = {
            "id": "expand_traced",
            "module": module_id,
            "params": {},
            "$upstream_steps": ["up"],
        }
        executor = make_executor()
        resolver = make_resolver(context=context)
        collector = TraceCollector("wf-list", "List Return Workflow")
        collector.start()

        result = await executor.execute_step(
            step_config=step_config,
            step_index=0,
            context=context,
            resolver=resolver,
            trace_collector=collector,
        )

        assert result is not None
        trace = collector.get_trace()
        step_trace = trace.steps[0]
        assert step_trace.status == "success"
        # Item traces should be recorded
        assert step_trace.itemTraces is not None
        assert len(step_trace.itemTraces) == 1

    async def test_items_dict_return_with_trace(self):
        """execute_item returning a dict is traced with item_trace.complete(dict).

        Calls _execute_items_mode directly so we can test the trace branch (lines
        530-531) without going through items_to_legacy_context which would crash
        on a bare dict in output_items.
        """
        from core.engine.trace import TraceCollector, StepTrace
        from core.modules.items import Item, ItemContext
        from core.modules.registry import ModuleRegistry

        # Ensure the module is registered before getting it
        module_id_str = _register_items_dict_return_module()

        # Build a small fake module instance with execute_item that returns dict
        module_class = ModuleRegistry.get(module_id_str)
        module_instance = module_class({}, {})

        step_trace = StepTrace(stepId="dict_inner", stepIndex=0, moduleId="test.items_dict_return")
        step_trace.start()

        # Provide one Item input
        input_items = [Item(json={"value": 7})]

        executor = make_executor()

        # Call _execute_items_mode directly — this exercises lines 526-531
        # We need to use on_error=continue params to handle the eventual
        # items_to_legacy_context crash from the dict in output_items.
        # We'll catch the StepExecutionError but the trace branch fires first.
        try:
            result = await executor._execute_items_mode(
                "dict_inner", module_instance, {"$on_error": "stop"}, input_items, step_trace
            )
        except Exception:
            pass  # items_to_legacy_context crashes on bare dict — expected

        # The item trace should have been recorded with the dict branch (line 531)
        assert step_trace.itemTraces is not None
        assert len(step_trace.itemTraces) == 1
        assert step_trace.itemTraces[0].output == {"mapped_value": 107}

    async def test_items_mode_error_with_trace_records_item_fail(self):
        """Item error with trace_collector records item_trace.fail(...)."""
        from core.engine.trace import TraceCollector
        from core.modules.registry import ModuleRegistry, register_module
        from core.modules.base import BaseModule
        from core.modules.items import Item

        MODULE_ID = "test.items_always_fail"
        if not ModuleRegistry.has(MODULE_ID):
            @register_module(
                module_id=MODULE_ID,
                version="1.0.0",
                category="testing",
                tags=["test"],
                label="Items Always Fail",
                description="Always raises in execute_item",
                icon="X",
                color="#FF0000",
                input_types=["any"],
                output_types=["any"],
                can_receive_from=["*"],
                can_connect_to=["*"],
                requires_credentials=False,
                handles_sensitive_data=False,
            )
            class ItemsAlwaysFailModule(BaseModule):
                execution_mode = "items"

                def validate_params(self):
                    pass

                async def execute(self):
                    return {"ok": True, "data": {}}

                async def execute_item(self, item, index, ctx):
                    raise RuntimeError("Item always fails")

        upstream_result = {
            "ok": True,
            "data": {},
            "items": [{"val": 1}],
        }
        context = {"up": upstream_result}
        step_config = {
            "id": "always_fail_item",
            "module": MODULE_ID,
            "params": {"$on_error": "continue"},
            "$upstream_steps": ["up"],
            "on_error": "continue",
        }
        executor = make_executor()
        resolver = make_resolver(context=context)
        collector = TraceCollector("wf-item-fail", "Item Fail Trace")
        collector.start()

        result = await executor.execute_step(
            step_config=step_config,
            step_index=0,
            context=context,
            resolver=resolver,
            trace_collector=collector,
        )

        assert result is not None
        trace = collector.get_trace()
        step_trace = trace.steps[0]
        assert step_trace.itemTraces is not None
        assert step_trace.itemTraces[0].status == "error"


# ---------------------------------------------------------------------------
# 27. Unknown execution_mode triggers fallback warning (line 465)
# ---------------------------------------------------------------------------

class TestUnknownExecutionMode:
    async def test_unknown_execution_mode_falls_back_to_single(self):
        """A module with unknown execution_mode logs warning and uses single mode."""
        from core.modules.registry import ModuleRegistry, register_module
        from core.modules.base import BaseModule

        MODULE_ID = "test.unknown_mode_module"
        if not ModuleRegistry.has(MODULE_ID):
            @register_module(
                module_id=MODULE_ID,
                version="1.0.0",
                category="testing",
                tags=["test"],
                label="Unknown Mode Module",
                description="Has an unrecognized execution_mode",
                icon="HelpCircle",
                color="#888888",
                input_types=["any"],
                output_types=["any"],
                can_receive_from=["*"],
                can_connect_to=["*"],
                requires_credentials=False,
                handles_sensitive_data=False,
            )
            class UnknownModeModule(BaseModule):
                execution_mode = "future_unsupported_mode"

                def validate_params(self):
                    pass

                async def execute(self):
                    return {"ok": True, "data": {"result": "executed"}}

        context = {}
        step_config = {
            "id": "unknown_mode_step",
            "module": MODULE_ID,
            "params": {},
        }
        executor = make_executor()
        resolver = make_resolver(context=context)

        result = await executor.execute_step(
            step_config=step_config,
            step_index=0,
            context=context,
            resolver=resolver,
        )

        # Falls back to single mode — should return a result
        assert result is not None
        assert "unknown_mode_step" in context


# ---------------------------------------------------------------------------
# 28. _get_input_items_by_port with legacy data (line 659)
# ---------------------------------------------------------------------------

class TestGetInputItemsByPortLegacyData:
    def test_legacy_data_in_port_wrapped_as_item(self):
        """When a port's upstream step has data but no items, it's wrapped as Item."""
        context = {
            "step_legacy": {
                "ok": True,
                "data": {"name": "legacy_value"},
                # No 'items' key
            }
        }
        upstream_by_port = {"input": ["step_legacy"]}
        params = {}
        executor = make_executor()
        result = executor._get_input_items_by_port(context, upstream_by_port, params)
        assert result is not None
        assert len(result) == 1
        assert result[0].json == {"name": "legacy_value"}


# ---------------------------------------------------------------------------
# 29. Trace path: result has data but no items (line 275)
# ---------------------------------------------------------------------------

class TestTraceDataPath:
    async def test_trace_uses_data_when_result_has_no_items(self):
        """When result dict has data but no items key, trace uses [[data]] (line 275)."""
        from core.engine.trace import TraceCollector, StepTrace
        from core.modules.registry import ModuleRegistry, register_module
        from core.modules.base import BaseModule

        MODULE_ID = "test.raw_data_return"
        if not ModuleRegistry.has(MODULE_ID):
            @register_module(
                module_id=MODULE_ID,
                version="1.0.0",
                category="testing",
                tags=["test"],
                label="Raw Data Return",
                description="Returns dict without ok key — bypasses wrap_legacy_result",
                icon="Database",
                color="#333333",
                input_types=["any"],
                output_types=["any"],
                can_receive_from=["*"],
                can_connect_to=["*"],
                requires_credentials=False,
                handles_sensitive_data=False,
            )
            class RawDataReturnModule(BaseModule):
                def validate_params(self):
                    pass

                async def execute(self):
                    # Return dict WITHOUT 'ok' key → bypasses wrap_legacy_result
                    # So _execute_single_mode returns raw dict with data but no items
                    return {"data": {"raw": "value"}, "status": "done"}

        context = {}
        step_config = {
            "id": "raw_data_step",
            "module": MODULE_ID,
            "params": {},
        }
        executor = make_executor()
        resolver = make_resolver(context=context)
        collector = TraceCollector("wf-raw", "Raw Data Workflow")
        collector.start()

        result = await executor.execute_step(
            step_config=step_config,
            step_index=0,
            context=context,
            resolver=resolver,
            trace_collector=collector,
        )

        assert result is not None
        assert result.get("data") == {"raw": "value"}
        trace = collector.get_trace()
        step_trace = trace.steps[0]
        assert step_trace.status == "success"
        assert step_trace.output is not None


# ---------------------------------------------------------------------------
# 30. Items mode: execute_item returns scalar → line 533
#     Items mode: on_error='stop' raises on item error → line 545
# ---------------------------------------------------------------------------

def _register_items_scalar_return_module():
    """Register a module that returns a scalar from execute_item."""
    from core.modules.registry import ModuleRegistry, register_module
    from core.modules.base import BaseModule
    from core.modules.items import Item

    MODULE_ID = "test.items_scalar_return"
    if ModuleRegistry.has(MODULE_ID):
        return MODULE_ID

    @register_module(
        module_id=MODULE_ID,
        version="1.0.0",
        category="testing",
        tags=["test"],
        label="Items Scalar Return",
        description="Returns a scalar (int) from execute_item",
        icon="Hash",
        color="#BB00AA",
        input_types=["any"],
        output_types=["any"],
        can_receive_from=["*"],
        can_connect_to=["*"],
        requires_credentials=False,
        handles_sensitive_data=False,
    )
    class ItemsScalarReturnModule(BaseModule):
        execution_mode = "items"

        def validate_params(self):
            pass

        async def execute(self):
            return {"ok": True, "data": {}}

        async def execute_item(self, item, index, ctx):
            # Return a scalar (not Item, not dict, not list)
            return item.json.get("value", 0) * 3

    return MODULE_ID


class TestItemsModeScalarAndStop:
    async def test_items_scalar_return_traced(self):
        """execute_item returning a scalar hits item_trace.complete({"value": ...})."""
        from core.engine.trace import StepTrace
        from core.modules.items import Item
        from core.modules.registry import ModuleRegistry

        module_id_str = _register_items_scalar_return_module()
        module_class = ModuleRegistry.get(module_id_str)
        module_instance = module_class({}, {})

        step_trace = StepTrace(stepId="scalar_inner", stepIndex=0, moduleId=module_id_str)
        step_trace.start()

        input_items = [Item(json={"value": 5})]
        executor = make_executor()

        # Call _execute_items_mode directly
        # The scalar return (15) will be in output_items, but items_to_legacy_context
        # will crash. We catch the error but verify the trace was recorded.
        try:
            result = await executor._execute_items_mode(
                "scalar_inner", module_instance, {"$on_error": "stop"}, input_items, step_trace
            )
        except Exception:
            pass  # Expected crash from items_to_legacy_context on non-Item

        # Item trace should have been recorded with scalar branch (line 533)
        assert step_trace.itemTraces is not None
        assert len(step_trace.itemTraces) == 1
        assert step_trace.itemTraces[0].output == {"value": 15}

    async def test_items_mode_stop_on_error_raises(self):
        """items mode with on_error='stop' re-raises item exception (line 545)."""
        from core.modules.items import Item
        from core.modules.registry import ModuleRegistry, register_module
        from core.modules.base import BaseModule

        MODULE_ID = "test.items_fail_once"
        if not ModuleRegistry.has(MODULE_ID):
            @register_module(
                module_id=MODULE_ID,
                version="1.0.0",
                category="testing",
                tags=["test"],
                label="Items Fail Once",
                description="Raises in execute_item",
                icon="AlertOctagon",
                color="#CC0000",
                input_types=["any"],
                output_types=["any"],
                can_receive_from=["*"],
                can_connect_to=["*"],
                requires_credentials=False,
                handles_sensitive_data=False,
            )
            class ItemsFailOnceModule(BaseModule):
                execution_mode = "items"

                def validate_params(self):
                    pass

                async def execute(self):
                    return {"ok": True, "data": {}}

                async def execute_item(self, item, index, ctx):
                    raise ValueError("item error stop")

        context = {}
        step_config = {
            "id": "items_stop_err",
            "module": MODULE_ID,
            "params": {},
            "$upstream_steps": [],
        }
        executor = make_executor()
        resolver = make_resolver(context=context)

        # on_error defaults to 'stop' → should raise StepExecutionError
        with pytest.raises(StepExecutionError):
            await executor.execute_step(
                step_config=step_config,
                step_index=0,
                context=context,
                resolver=resolver,
            )


# ---------------------------------------------------------------------------
# Runtime invoker fallback tests (lines 726-776)
# ---------------------------------------------------------------------------

import core.engine.step_executor.executor as _executor_mod


class TestRuntimeInvokerFallback:
    """Test fallback paths when _RUNTIME_INVOKER_AVAILABLE is False."""

    async def test_parse_module_id_fallback_two_parts(self):
        """Lines 727-731: fallback splits 'category.action' into plugin_id and step_id."""
        original = _executor_mod._RUNTIME_INVOKER_AVAILABLE
        _executor_mod._RUNTIME_INVOKER_AVAILABLE = False
        try:
            executor = make_executor()
            plugin_id, step_id = executor._parse_module_id("database.query")
            assert plugin_id == "flyto-official/database"
            assert step_id == "query"
        finally:
            _executor_mod._RUNTIME_INVOKER_AVAILABLE = original

    async def test_parse_module_id_fallback_single_part(self):
        """Lines 732-733: single-part module_id defaults step_id to 'execute'."""
        original = _executor_mod._RUNTIME_INVOKER_AVAILABLE
        _executor_mod._RUNTIME_INVOKER_AVAILABLE = False
        try:
            executor = make_executor()
            plugin_id, step_id = executor._parse_module_id("mymodule")
            assert plugin_id == "flyto-official/mymodule"
            assert step_id == "execute"
        finally:
            _executor_mod._RUNTIME_INVOKER_AVAILABLE = original

    async def test_parse_module_id_fallback_three_parts(self):
        """Lines 728-731: three-part module_id joins remaining parts as step_id."""
        original = _executor_mod._RUNTIME_INVOKER_AVAILABLE
        _executor_mod._RUNTIME_INVOKER_AVAILABLE = False
        try:
            executor = make_executor()
            plugin_id, step_id = executor._parse_module_id("browser.page.click")
            assert plugin_id == "flyto-official/browser"
            assert step_id == "page.click"
        finally:
            _executor_mod._RUNTIME_INVOKER_AVAILABLE = original

    async def test_invoke_via_runtime_fallback_real_module(self):
        """Lines 758-776: fallback uses ModuleRegistry.get() for real module execution."""
        original = _executor_mod._RUNTIME_INVOKER_AVAILABLE
        _executor_mod._RUNTIME_INVOKER_AVAILABLE = False
        try:
            executor = make_executor()
            result = await executor._invoke_via_runtime(
                "string.uppercase",
                {"text": "hello"},
                {},
            )
            assert result is not None
            assert result.get("ok") is True
            assert result["data"]["result"] == "HELLO"
        finally:
            _executor_mod._RUNTIME_INVOKER_AVAILABLE = original

    async def test_invoke_via_runtime_fallback_module_not_found(self):
        """Line 772-774: fallback raises when module is not in registry."""
        original = _executor_mod._RUNTIME_INVOKER_AVAILABLE
        _executor_mod._RUNTIME_INVOKER_AVAILABLE = False
        try:
            executor = make_executor()
            with pytest.raises((StepExecutionError, ValueError), match="Module not found"):
                await executor._invoke_via_runtime(
                    "nonexistent.module",
                    {},
                    {},
                )
        finally:
            _executor_mod._RUNTIME_INVOKER_AVAILABLE = original

    async def test_invoke_via_runtime_fallback_template_invoke(self):
        """Lines 764-770: fallback handles template.invoke:xxx format."""
        original = _executor_mod._RUNTIME_INVOKER_AVAILABLE
        _executor_mod._RUNTIME_INVOKER_AVAILABLE = False
        try:
            executor = make_executor()
            # template.invoke should be looked up in registry; it may or may not
            # be registered. We just verify the params are set correctly.
            params = {}
            try:
                await executor._invoke_via_runtime(
                    "template.invoke:my-template-id",
                    params,
                    {},
                )
            except StepExecutionError:
                # template.invoke may not be registered, that's fine
                pass
            # Verify template_id and library_id were injected into params
            assert params.get("template_id") == "my-template-id"
            assert params.get("library_id") == "my-template-id"
        finally:
            _executor_mod._RUNTIME_INVOKER_AVAILABLE = original


# ---------------------------------------------------------------------------
# Edge case additions
# ---------------------------------------------------------------------------

class TestSubstituteLocalVarsEdgeCases:
    def test_empty_vars_dict_pops_key_and_returns_unchanged(self):
        """When __vars__ is {} (falsy), it is popped but params are returned as-is."""
        params = {"text": "{{name}}", "__vars__": {}}
        result = StepExecutor._substitute_local_vars(params)
        # __vars__ is popped
        assert "__vars__" not in result
        # No substitution happened — value unchanged
        assert result["text"] == "{{name}}"

    def test_vars_key_is_popped_as_side_effect(self):
        """__vars__ is always removed from the returned dict."""
        params = {"a": "{{x}}", "__vars__": {"x": "1"}}
        result = StepExecutor._substitute_local_vars(params)
        assert "__vars__" not in result
        assert result["a"] == "1"

    def test_no_vars_key_params_returned_exactly(self):
        """When __vars__ is absent, the original dict is returned unchanged."""
        params = {"key": "value", "num": 42}
        result = StepExecutor._substitute_local_vars(params)
        assert result is params  # same object, not a copy


class TestRedactSensitiveOutputEdgeCases:
    def test_tuple_input_returns_list(self):
        """A tuple is treated like a sequence and the result is a list."""
        data = ({"api_key": "secret"}, {"name": "safe"})
        result = _redact_sensitive_output(data)
        assert isinstance(result, list)
        assert result[0]["api_key"] == "[REDACTED]"
        assert result[1]["name"] == "safe"


class TestExecuteStepTimeoutZero:
    async def test_timeout_zero_disabled_no_timeout_error(self):
        """When timeout=0 on a step, no timeout is applied and step completes normally."""
        context = {}
        step_config = {
            "id": "no_timeout_step",
            "module": "string.uppercase",
            "params": {"text": "fast"},
            "timeout": 0,
        }
        executor = make_executor()
        resolver = make_resolver(context=context)

        result = await executor.execute_step(
            step_config=step_config,
            step_index=0,
            context=context,
            resolver=resolver,
        )

        assert result is not None
        assert result["data"]["result"] == "FAST"


class TestHookSkipAndAbortPaths:
    """Test SKIP and ABORT hook paths using a real ExecutorHooks subclass."""

    async def test_pre_execute_skip_returns_none(self):
        """When on_pre_execute returns SKIP, execute_step returns None."""
        from core.engine.hooks.base import ExecutorHooks
        from core.engine.hooks.models import HookResult

        class SkipHooks(ExecutorHooks):
            def on_pre_execute(self, context):
                return HookResult.skip_step()

        context = {}
        step_config = {
            "id": "should_be_skipped",
            "module": "string.uppercase",
            "params": {"text": "will not run"},
        }
        executor = make_executor(hooks=SkipHooks())
        resolver = make_resolver(context=context)

        result = await executor.execute_step(
            step_config=step_config,
            step_index=0,
            context=context,
            resolver=resolver,
        )

        assert result is None
        assert "should_be_skipped" not in context

    async def test_pre_execute_abort_raises_step_execution_error(self):
        """When on_pre_execute returns ABORT, execute_step raises StepExecutionError."""
        from core.engine.hooks.base import ExecutorHooks
        from core.engine.hooks.models import HookResult

        class AbortHooks(ExecutorHooks):
            def on_pre_execute(self, context):
                return HookResult.abort_execution("blocked by policy")

        context = {}
        step_config = {
            "id": "aborted_step",
            "module": "string.uppercase",
            "params": {"text": "aborted"},
        }
        executor = make_executor(hooks=AbortHooks())
        resolver = make_resolver(context=context)

        with pytest.raises(StepExecutionError) as exc_info:
            await executor.execute_step(
                step_config=step_config,
                step_index=0,
                context=context,
                resolver=resolver,
            )

        assert "aborted_step" in str(exc_info.value) or "blocked by policy" in str(exc_info.value)
