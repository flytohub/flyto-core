"""Failure propagation contracts for nested template execution."""

import pytest

from core.engine.exceptions import WorkflowExecutionError
from core.engine.workflow import WorkflowEngine
from core.modules.atomic.template.invoke import InvokeTemplate  # noqa: F401


@pytest.fixture(autouse=True)
def _allow_template_invoke(monkeypatch) -> None:
    import core.module_policy as module_policy
    from core.module_policy import ModuleFilter

    monkeypatch.delenv("FLYTO_MODULE_DENYLIST", raising=False)
    monkeypatch.setenv("FLYTO_MODULE_ALLOWLIST", "template.*,string.*")
    monkeypatch.setattr(module_policy, "module_filter", ModuleFilter())


def _engine(invoke_step: dict, *following_steps: dict) -> WorkflowEngine:
    return WorkflowEngine(
        workflow={"steps": [invoke_step, *following_steps]},
        initial_context={"template_definitions": {"child": {"steps": []}}},
    )


def _invoke_step(**overrides) -> dict:
    step = {
        "id": "invoke_child",
        "module": "template.invoke:child",
        "params": {},
    }
    step.update(overrides)
    return step


@pytest.mark.asyncio
async def test_unhandled_template_error_fails_parent_workflow() -> None:
    engine = _engine(_invoke_step())

    with pytest.raises(WorkflowExecutionError, match="TEMPLATE_EMPTY"):
        await engine.execute()

    assert "invoke_child" not in engine.context


@pytest.mark.asyncio
async def test_template_error_respects_continue_policy() -> None:
    engine = _engine(
        _invoke_step(on_error="continue"),
        {
            "id": "after_error",
            "module": "string.uppercase",
            "params": {"text": "continued"},
        },
    )

    await engine.execute()

    assert engine.context["invoke_child"]["ok"] is False
    assert engine.context["after_error"]["data"]["result"] == "CONTINUED"


@pytest.mark.asyncio
async def test_template_error_uses_explicit_error_connection() -> None:
    engine = _engine(
        _invoke_step(connections={"error": ["fallback"]}),
        {
            "id": "success_path",
            "module": "string.uppercase",
            "params": {"text": "must not run"},
        },
        {
            "id": "fallback",
            "module": "string.uppercase",
            "params": {"text": "recovered"},
        },
    )

    await engine.execute()

    assert "success_path" not in engine.context
    assert engine.context["invoke_child"]["__event__"] == "error"
    assert engine.context["fallback"]["data"]["result"] == "RECOVERED"


@pytest.mark.asyncio
async def test_template_invocation_depth_is_bounded(monkeypatch) -> None:
    import core.modules.atomic.template.invoke as invoke_module

    monkeypatch.setattr(invoke_module, "_MAX_TEMPLATE_INVOKE_DEPTH", 2)
    definition = {
        "steps": [
            {
                "id": "again",
                "module": "template.invoke:self",
                "params": {},
            }
        ]
    }
    module = InvokeTemplate(
        {"template_id": "self", "library_id": "self", "timeout_seconds": 1},
        {"template_definitions": {"self": definition}},
    )

    result = await module.execute()

    assert result["__event__"] == "error"
    assert "safe limit of 2" in result["__error__"]["message"]
