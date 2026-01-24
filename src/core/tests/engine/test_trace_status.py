"""
Tests for execution trace status compatibility.
"""

from core.engine.trace import ExecutionTrace, StepTrace, ItemTrace, TraceStatus


def test_execution_trace_status_legacy_mapping():
    trace = ExecutionTrace.create("wf1", "Test", {})
    trace.start()
    assert trace.to_dict()["statusLegacy"] == "running"

    trace.complete(output={})
    assert trace.to_dict()["status"] == TraceStatus.SUCCESS.value
    assert trace.to_dict()["statusLegacy"] == "completed"


def test_step_trace_status_legacy_mapping():
    step = StepTrace(stepId="s1", stepIndex=0, moduleId="m1")
    step.start()
    assert step.to_dict()["statusLegacy"] == "running"

    step.complete()
    assert step.to_dict()["statusLegacy"] == "completed"


def test_item_trace_status_legacy_mapping():
    item = ItemTrace(index=0)
    item.start()
    assert item.to_dict()["statusLegacy"] == "running"

    item.complete(output={"ok": True})
    assert item.to_dict()["statusLegacy"] == "completed"
