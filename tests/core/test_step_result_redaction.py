"""A module names the leaves of its RESULT that the step log must not show.

``sensitive_paths`` covers what a step is given. A provider's response can
hold sensitive values too -- the assets behind a finding, a person's address
-- that the workflow needs and the step log and trace must not keep.
``BaseModule.sensitive_result_paths`` names them as paths into the result;
the hooks and the trace get a redacted copy, and the workflow the original.
"""

import json

import pytest

from core.engine.hooks import ExecutorHooks, HookResult
from core.engine.step_executor.executor import StepExecutor
from core.engine.trace import TraceCollector
from core.engine.variable_resolver import VariableResolver
from core.modules.base import BaseModule
from core.modules.registry import ModuleRegistry, register_module

MODULE_ID = "test.result.sensitive"
SECRET_ADDRESS = "221B Example Street"


class _Hooks(ExecutorHooks):
    def __init__(self):
        self.post = []

    def on_post_execute(self, context):
        self.post.append(context)
        return HookResult.continue_execution()


class _Lookup(BaseModule):
    def validate_params(self):
        return None

    @classmethod
    def sensitive_result_paths(cls, result):
        people = (result.get("data") or {}).get("people") or []
        return frozenset(("data", "people", index, "address") for index in range(len(people)))

    async def execute(self):
        return {"ok": True, "data": {"people": [{"name": "A", "address": SECRET_ADDRESS}]}}


@pytest.fixture
def module_id():
    register_module(
        module_id=MODULE_ID, version="1.0.0", category="testing", tags=["test"], label=MODULE_ID,
        description="test", icon="Box", color="#000000", input_types=["any"], output_types=["any"],
        can_receive_from=["*"], can_connect_to=["*"], params_schema={},
    )(_Lookup)
    yield MODULE_ID
    ModuleRegistry.unregister(MODULE_ID)


async def test_the_step_log_and_trace_get_the_redacted_copy(module_id):
    hooks = _Hooks()
    collector = TraceCollector("wf", "wf")
    collector.start()
    context = {}
    result = await StepExecutor(hooks=hooks, workflow_id="wf", workflow_name="wf", total_steps=1).execute_step(
        step_config={"id": "lookup", "module": module_id}, step_index=0, context=context,
        resolver=VariableResolver({}, context), trace_collector=collector,
    )
    assert result["data"]["people"][0]["address"] == SECRET_ADDRESS
    assert context["lookup"]["data"]["people"][0]["address"] == SECRET_ADDRESS
    assert hooks.post[-1].result["data"]["people"][0] == {"name": "A", "address": "[REDACTED]"}
    assert SECRET_ADDRESS not in json.dumps(collector.get_trace().to_dict())


def test_redaction_never_mutates_the_result(module_id):
    from core.engine.redaction import redact_step_result

    result = {"ok": True, "data": {"people": [{"name": "A", "address": SECRET_ADDRESS}]}}
    redacted = redact_step_result(module_id, result)
    assert redacted["data"]["people"][0]["address"] == "[REDACTED]"
    assert result["data"]["people"][0]["address"] == SECRET_ADDRESS


def test_a_module_that_declares_nothing_is_unchanged():
    from core.engine.redaction import redact_step_result

    result = {"ok": True, "data": {"address": "x"}}
    assert redact_step_result("no.such.module", result) is result
