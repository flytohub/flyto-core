from __future__ import annotations

from copy import deepcopy

import pytest

from core.engine.capability_dispatch import (
    CAPABILITY_REQUEST_VERSION,
    RUNTIME_DISPATCHER_KEY,
    CapabilityDispatchError,
    consume_capability_request,
)
from core.engine.step_executor import StepExecutor
from core.engine.exceptions import StepExecutionError
from core.modules.base import BaseModule
from core.modules.registry import ModuleRegistry


REQUEST = {
    "contract_version": CAPABILITY_REQUEST_VERSION,
    "resource_id": "robot-1",
    "capability_id": "motion.advance",
    "arguments": {"distance_m": 0.25},
    "goal": "move forward 0.25 m",
}


class OpaqueDispatcher:
    _flyto_runtime_opaque = True

    def __init__(self, outcome="completed"):
        self.outcome = outcome
        self.calls = []

    async def invoke(self, request):
        self.calls.append(deepcopy(request))
        return {
            "call_id": "call-1",
            "outcome": self.outcome,
            "detail": "" if self.outcome == "completed" else "resource refused",
            "evidence": {"source": "fixture"},
        }


@pytest.mark.asyncio
async def test_declaration_stays_non_actuating_without_runtime_dispatcher():
    result = {"dispatched": False, "capability_request": deepcopy(REQUEST)}

    consumed = await consume_capability_request(result, {})

    assert consumed == result
    assert consumed["dispatched"] is False
    assert "execution" not in consumed


@pytest.mark.asyncio
async def test_runtime_owned_dispatcher_executes_exact_canonical_request_once():
    dispatcher = OpaqueDispatcher()
    result = {"dispatched": False, "capability_request": deepcopy(REQUEST)}

    consumed = await consume_capability_request(
        result, {RUNTIME_DISPATCHER_KEY: dispatcher}
    )

    assert dispatcher.calls == [REQUEST]
    assert consumed["dispatched"] is True
    assert consumed["execution"]["outcome"] == "completed"
    assert result["dispatched"] is False, "consumer must not mutate module output"


@pytest.mark.asyncio
async def test_workflow_data_cannot_self_authorize_a_callable_dispatcher():
    class UserCallable:
        async def invoke(self, request):
            return {"outcome": "completed"}

    with pytest.raises(CapabilityDispatchError, match="runtime-owned opaque"):
        await consume_capability_request(
            {"capability_request": deepcopy(REQUEST)},
            {RUNTIME_DISPATCHER_KEY: UserCallable()},
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change, message",
    [
        ({"contract_version": "flyto.capability-request.v0"}, "unsupported"),
        ({"resource_id": ""}, "commanded resource"),
        ({"arguments": []}, "arguments"),
    ],
)
async def test_runtime_dispatch_fails_closed_on_malformed_requests(change, message):
    dispatcher = OpaqueDispatcher()
    request = {**REQUEST, **change}

    with pytest.raises(CapabilityDispatchError, match=message):
        await consume_capability_request(
            {"capability_request": request},
            {RUNTIME_DISPATCHER_KEY: dispatcher},
        )
    assert dispatcher.calls == []


@pytest.mark.asyncio
async def test_non_completed_adapter_outcome_is_a_failure():
    dispatcher = OpaqueDispatcher(outcome="refused")

    with pytest.raises(CapabilityDispatchError, match="resource refused"):
        await consume_capability_request(
            {"capability_request": deepcopy(REQUEST)},
            {RUNTIME_DISPATCHER_KEY: dispatcher},
        )


class DeclaringModule(BaseModule):
    module_id = "test.capability.declaration"

    def validate_params(self):
        return None

    def enforce_policy(self, metadata=None):
        return None

    async def execute(self):
        return {
            "dispatched": False,
            "capability_request": deepcopy(REQUEST),
        }


@pytest.fixture
def registered(monkeypatch):
    monkeypatch.setattr(
        ModuleRegistry,
        "get",
        staticmethod(
            lambda module_id: DeclaringModule
            if module_id == DeclaringModule.module_id
            else None
        ),
    )


async def _run(context):
    return await StepExecutor()._execute_module(
        step_id="capability-step",
        module_id=DeclaringModule.module_id,
        params={},
        context=context,
        input_items=None,
        step_trace=None,
    )


@pytest.mark.asyncio
async def test_step_executor_consumes_request_only_at_runtime_boundary(registered):
    preview = await _run({})
    assert preview["dispatched"] is False

    dispatcher = OpaqueDispatcher()
    executed = await _run({RUNTIME_DISPATCHER_KEY: dispatcher})
    assert executed["dispatched"] is True
    assert dispatcher.calls == [REQUEST]


@pytest.mark.asyncio
async def test_step_executor_turns_adapter_refusal_into_step_failure(registered):
    dispatcher = OpaqueDispatcher(outcome="refused")

    with pytest.raises(StepExecutionError) as caught:
        await _run({RUNTIME_DISPATCHER_KEY: dispatcher})

    assert "resource refused" in str(caught.value)
