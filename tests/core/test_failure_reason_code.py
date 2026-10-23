"""A step that did not succeed hands its host a typed reason, never only a sentence.

A module failure reached hosts as ``"Module returned failure [SSRF_BLOCKED]: ..."``
-- the code existed, but only inside an English sentence, so a host that wanted
to say why on the step had to parse message text (Cloud gap G-12). The code
now travels as data: ``StepExecutionError.error_code`` and, for hooks,
``HookContext.metadata['error_code']``, found through the same deliberate
wrapping links as the outcome envelope. A raise that carries no code carries
none; nothing is inferred from an exception's type or text.
"""

import pytest

from core.engine.exceptions import StepExecutionError, error_code_from_exception
from core.engine.outcome import ClaimBy, Outcome, OutcomeError
from core.engine.step_executor.context_builder import create_step_context


def _context(error=None, result=None):
    return create_step_context(
        workflow_id="wf", workflow_name="wf", total_steps=1,
        step_config={"id": "call", "module": "http.request", "params": {}},
        step_index=0, context={}, result=result, error=error,
    )


def test_a_step_execution_error_carries_the_module_code():
    error = StepExecutionError("call", "Module returned failure [SSRF_BLOCKED]: refused", error_code="SSRF_BLOCKED")
    assert error.error_code == "SSRF_BLOCKED"


def test_the_code_is_found_through_the_wrapping_chain():
    inner = StepExecutionError("call", "Module returned failure [SSRF_BLOCKED]: refused", error_code="SSRF_BLOCKED")
    outer = StepExecutionError("call", f"Step failed: {inner}", inner)
    assert error_code_from_exception(outer) == "SSRF_BLOCKED"


def test_a_plain_raise_carries_no_code_and_none_is_guessed_from_its_text():
    assert error_code_from_exception(RuntimeError("[SSRF_BLOCKED] looks like a code")) is None


def test_hooks_read_the_code_from_metadata():
    error = StepExecutionError("call", "Step failed", StepExecutionError("call", "x", error_code="SSRF_BLOCKED"))
    assert _context(error=error).metadata["error_code"] == "SSRF_BLOCKED"


def test_a_raise_without_a_code_leaves_the_key_absent():
    assert "error_code" not in _context(error=RuntimeError("Browser not launched")).metadata


def test_an_outcome_error_names_its_reason_beside_its_rung():
    timeout = OutcomeError("Timeout 30000ms exceeded", rung=Outcome.INDETERMINATE, claim_by=ClaimBy.NONE, code="TIMEOUT")
    meta = _context(error=StepExecutionError("wait", f"Step failed: {timeout}", timeout)).metadata
    assert meta["outcome"]["rung"] == "indeterminate"
    assert meta["error_code"] == "TIMEOUT"


@pytest.mark.asyncio
async def test_a_module_failure_raises_with_its_code_as_data():
    from core.engine.step_executor.executor import StepExecutor

    class Failing:
        params = {}

        async def run(self):
            return {"ok": False, "error": "outbound address refused", "error_code": "SSRF_BLOCKED"}

    executor = StepExecutor.__new__(StepExecutor)
    with pytest.raises(StepExecutionError) as raised:
        await executor._execute_single_mode("call", Failing())
    assert raised.value.error_code == "SSRF_BLOCKED"
