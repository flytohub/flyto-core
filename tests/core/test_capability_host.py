# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""The generic capability host (``flyto run --capability-host``).

Everything runs against a fake adapter that records what it was asked, so the
tests pin the host's policy: the per-run allow list, fail-closed physical
confirmation, the resource match, safe stop on timeout/failure, contract-driven
deadlines and observation phases (``settled`` -> adapter ``post_stop``),
verbatim pass-through of adapter refusals, artifact checks, and the workflow
ABI (``capability.invoke`` and a pack step both reach the host).
"""

import asyncio
import base64
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.capability_contract import validate_contract
from core.capability_host import (
    CAPABILITY_HOST_SCHEMA,
    DISPATCHER_CONTEXT_KEY,
    CallRequest,
    CapabilityHost,
    CapabilityHostError,
    registry_contract_lookup,
    resolve_adapter_factory,
)
from core.capability_host import host as host_module
from core.modules.atomic.capability.invoke import RUNTIME_DISPATCHER_CONTEXT_KEY
from core.modules.base import BaseModule
from core.modules.registry import ModuleRegistry

RESOURCE = "resource-01"
ADAPTER = "fake.adapter"

PARAMS = {"distance_m": {"type": "number", "min": 0.05, "max": 2.0, "required": True}}

ADVANCE = validate_contract(
    {
        "actuates": True,
        "safety_class": "movement",
        "requires_safe_stop": True,
        "cancellable": True,
        "idempotent": True,
        "evidence": [
            {
                "kind": "displacement",
                "observe": "pose",
                "phases": ["before", "after", "settled"],
                "measure": {"op": "along", "fields": ["x", "y"], "heading_field": "yaw"},
                "expect": {"argument": "distance_m"},
                "tolerance": {"absolute": 0.03, "relative": 0.3},
                "settle": {"max_drift": 0.02},
            }
        ],
        "expected_duration_ms": 180_000,
    },
    PARAMS,
)
STOP = validate_contract(
    {
        "actuates": True,
        "safety_class": "controlled",
        "requires_safe_stop": False,
        "cancellable": False,
        "idempotent": True,
        "role": "safe_stop",
    }
)
READ = validate_contract(
    {
        "actuates": False,
        "safety_class": "read_only",
        "requires_safe_stop": False,
        "cancellable": False,
        "idempotent": True,
    }
)
CAPTURE = validate_contract(
    {
        "actuates": False,
        "safety_class": "read_only",
        "requires_safe_stop": False,
        "cancellable": False,
        "idempotent": True,
        "artifacts": [{"kind": "image", "media_types": ["image/jpeg"], "max_bytes": 64}],
    }
)

CONTRACTS = {
    "thing.advance": (ADVANCE, 90_000, "declared"),
    "thing.halt": (STOP, None, "declared"),
    "thing.read": (READ, 5_000, "declared"),
    "thing.capture": (CAPTURE, None, "declared"),
}


def lookup(capability_id):
    return CONTRACTS.get(capability_id, (None, None, "absent"))


@dataclass
class Result:
    call_id: str
    outcome: str
    detail: str = ""
    evidence: dict = field(default_factory=dict)


class FakeAdapter:
    """Moves a pose by the commanded distance; records every call."""

    def __init__(self, resource_id, *, mode="simulation", outcome="completed", travel=1.0,
                 evidence=None, refuse_below=None):
        self.resource_id = resource_id
        self.deployment_mode = mode
        self.outcome = outcome
        self.travel = travel
        self.evidence = evidence or {}
        self.refuse_below = refuse_below
        self.calls = []
        self.requests = []
        self.pose = {"x": 0.0, "y": 0.0, "yaw": 0.0}
        self.disconnected = False

    def observe(self, *, phase="preflight", execution_id=None):
        self.calls.append(("observe", phase))
        return {"deployment_mode": self.deployment_mode, "pose": dict(self.pose), "snapshot": phase}

    def invoke(self, request):
        self.calls.append(("invoke", request.capability_id))
        self.requests.append(request)
        if self.refuse_below is not None:
            return Result(request.call_id, "refused", f"clearance below {self.refuse_below} m")
        if request.capability_id == "thing.advance" and self.outcome in ("completed", "timeout"):
            self.pose["x"] += request.arguments["distance_m"] * self.travel
        return Result(request.call_id, self.outcome, "", dict(self.evidence))

    def cancel(self, call_id):
        self.calls.append(("cancel", call_id))
        return Result(call_id, "cancelled")

    def safe_stop(self):
        self.calls.append(("safe_stop",))
        return Result("stop", "completed")

    def disconnect(self):
        self.disconnected = True


def make_host(adapter=None, **kwargs):
    adapter = adapter or FakeAdapter(RESOURCE)
    options = {
        "adapter_id": ADAPTER,
        "resource_id": RESOURCE,
        "adapter_factory": lambda resource_id: adapter,
        "contract_lookup": lookup,
        "run_id": "run-test",
        "sleep": lambda seconds: None,
    }
    options.update(kwargs)
    return CapabilityHost(**options), adapter


def call(host, capability_id, arguments=None, resource_id=RESOURCE):
    return asyncio.run(
        host.invoke({"resource_id": resource_id, "capability_id": capability_id, "arguments": arguments or {}})
    )


# ---------------------------------------------------------------------------
# ABI
# ---------------------------------------------------------------------------


def test_the_context_key_is_the_one_capability_invoke_reads():
    assert DISPATCHER_CONTEXT_KEY == RUNTIME_DISPATCHER_CONTEXT_KEY
    host, _ = make_host()
    assert host.context() == {DISPATCHER_CONTEXT_KEY: host}
    assert getattr(type(host), "_flyto_runtime_opaque", False) is True


def test_identity_is_required():
    with pytest.raises(CapabilityHostError):
        CapabilityHost(adapter_id="", resource_id=RESOURCE)
    with pytest.raises(CapabilityHostError):
        CapabilityHost(adapter_id=ADAPTER, resource_id=" ")
    with pytest.raises(CapabilityHostError):
        CapabilityHost(adapter_id=ADAPTER, resource_id=RESOURCE, allow=[f"c.{i}" for i in range(65)])


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------


def test_an_actuating_capability_is_refused_unless_allowed():
    host, adapter = make_host()
    record = call(host, "thing.advance", {"distance_m": 0.5})
    assert record["outcome"] == "refused" and record["refused_by"] == "host"
    assert "--allow thing.advance" in record["detail"]
    assert not [c for c in adapter.calls if c[0] == "invoke"]


def test_a_capability_without_a_contract_fails_closed_as_actuating():
    host, adapter = make_host()
    record = call(host, "thing.unknown")
    assert record["outcome"] == "refused" and record["contract_status"] == "absent"
    assert record["policy"]["actuates"] is True
    host, adapter = make_host(allow=["thing.unknown"])
    assert call(host, "thing.unknown")["outcome"] == "completed"


def test_a_read_only_capability_needs_no_allow():
    host, adapter = make_host()
    record = call(host, "thing.read")
    assert record["outcome"] == "completed"
    assert record["deadline_seconds"] == 5.0


def test_the_safe_stop_role_is_always_allowed_and_never_prompts_even_on_hardware():
    prompts = []
    host, adapter = make_host(FakeAdapter(RESOURCE, mode="hardware"), confirm=prompts.append)
    record = call(host, "thing.halt")
    assert record["outcome"] == "completed"
    assert prompts == []
    assert record["policy"]["safe_stop_role"] is True


def test_a_physical_deployment_without_a_terminal_is_refused():
    host, adapter = make_host(FakeAdapter(RESOURCE, mode="hardware"), allow=["thing.advance"], confirm=None)
    record = call(host, "thing.advance", {"distance_m": 0.5})
    assert record["outcome"] == "refused"
    assert "no interactive terminal" in record["detail"]
    assert not [c for c in adapter.calls if c[0] == "invoke"]


def test_an_unknown_deployment_counts_as_physical():
    adapter = FakeAdapter(RESOURCE)
    adapter.deployment_mode = None

    def observe(*, phase="preflight", execution_id=None):
        return {"pose": dict(adapter.pose)}

    adapter.observe = observe
    host, _ = make_host(adapter, allow=["thing.advance"])
    record = call(host, "thing.advance", {"distance_m": 0.5})
    assert record["outcome"] == "refused" and record["policy"]["deployment"] == "unknown"


def test_a_physical_deployment_runs_after_an_interactive_yes():
    prompts = []

    def confirm(prompt):
        prompts.append(prompt)
        return True

    host, adapter = make_host(FakeAdapter(RESOURCE, mode="hardware"), allow=["thing.advance"], confirm=confirm)
    record = call(host, "thing.advance", {"distance_m": 0.5})
    assert record["outcome"] == "completed"
    assert record["policy"]["physical_confirmed"] == "interactive"
    assert "thing.advance" in prompts[0] and RESOURCE in prompts[0]


def test_a_declined_or_broken_prompt_refuses():
    host, _ = make_host(FakeAdapter(RESOURCE, mode="hardware"), allow=["thing.advance"], confirm=lambda p: False)
    assert call(host, "thing.advance", {"distance_m": 0.5})["outcome"] == "refused"

    def broken(prompt):
        raise RuntimeError("no stdin")

    host, _ = make_host(FakeAdapter(RESOURCE, mode="hardware"), allow=["thing.advance"], confirm=broken)
    assert call(host, "thing.advance", {"distance_m": 0.5})["outcome"] == "refused"


def test_yes_physical_skips_the_prompt():
    host, _ = make_host(FakeAdapter(RESOURCE, mode="hardware"), allow=["thing.advance"], yes_physical=True)
    record = call(host, "thing.advance", {"distance_m": 0.5})
    assert record["outcome"] == "completed" and record["policy"]["physical_confirmed"] == "flag"


def test_a_request_for_another_resource_is_refused():
    host, adapter = make_host(allow=["thing.advance"])
    record = call(host, "thing.advance", {"distance_m": 0.5}, resource_id="resource-02")
    assert record["outcome"] == "refused" and "resource-02" in record["detail"]
    assert adapter.calls == []


def test_an_adapter_refusal_passes_through_unchanged_and_arguments_are_never_rewritten():
    # Refuse-never-clamp lives in the adapter (e.g. a clearance floor); the host
    # neither retries with smaller arguments nor turns the refusal into success.
    adapter = FakeAdapter(RESOURCE, refuse_below=0.35)
    host, _ = make_host(adapter, allow=["thing.advance"])
    record = call(host, "thing.advance", {"distance_m": 5.0})
    assert record["outcome"] == "refused"
    assert record["detail"] == "clearance below 0.35 m"
    assert "refused_by" not in record
    assert [r.arguments for r in adapter.requests] == [{"distance_m": 5.0}]
    assert ("safe_stop",) not in adapter.calls


# ---------------------------------------------------------------------------
# Execution: deadline, phases, evidence, safe stop
# ---------------------------------------------------------------------------


def test_a_completed_motion_is_observed_and_judged_with_settled_as_post_stop():
    host, adapter = make_host(allow=["thing.advance"])
    record = call(host, "thing.advance", {"distance_m": 0.5})
    assert record["schema"] == CAPABILITY_HOST_SCHEMA
    assert record["outcome"] == "completed"
    assert record["deadline_seconds"] == 180.0  # expected_duration_ms beats timeout_ms
    request = adapter.requests[0]
    assert isinstance(request, CallRequest) and request.call_id == record["call_id"]
    assert request.deadline_seconds == 180.0
    observed = [c[1] for c in adapter.calls if c[0] == "observe"]
    assert observed == ["before", "after", "post_stop"]
    assert set(record["observations"]) == {"before", "after", "settled"}
    verdict = record["verification"]["verdicts"][0]
    assert record["verification"]["verified"] is True
    assert verdict["kind"] == "displacement" and math.isclose(verdict["measured"], 0.5)


def test_a_short_motion_is_recorded_as_unverified_without_changing_the_outcome():
    host, _ = make_host(FakeAdapter(RESOURCE, travel=0.2), allow=["thing.advance"])
    record = call(host, "thing.advance", {"distance_m": 1.0})
    assert record["outcome"] == "completed"
    assert record["verification"]["verified"] is False


def test_a_timeout_cancels_and_safe_stops_then_records_how_far_it_got():
    adapter = FakeAdapter(RESOURCE, outcome="timeout")
    host, _ = make_host(adapter, allow=["thing.advance"])
    record = call(host, "thing.advance", {"distance_m": 0.5})
    assert record["outcome"] == "timeout"
    assert record["safety_recovery"] == "cancel=cancelled, safe_stop=completed"
    names = [c[0] for c in adapter.calls]
    assert names.index("cancel") < names.index("safe_stop") < len(names) - 1
    assert "settled" in record["observations"]


def test_an_adapter_crash_is_a_failure_followed_by_safe_stop():
    adapter = FakeAdapter(RESOURCE)

    def boom(request):
        raise ConnectionError("link down")

    adapter.invoke = boom
    host, _ = make_host(adapter, allow=["thing.advance"])
    record = call(host, "thing.advance", {"distance_m": 0.5})
    assert record["outcome"] == "failed" and "ConnectionError" in record["detail"]
    assert ("safe_stop",) in adapter.calls


def test_a_hung_adapter_is_timed_out_by_the_host_and_safe_stopped():
    import threading
    import time as _time

    release = threading.Event()
    adapter = FakeAdapter(RESOURCE)

    def hang(request):
        adapter.requests.append(request)
        release.wait(10)
        return Result(request.call_id, "completed")

    adapter.invoke = hang
    hung_advance = dict(ADVANCE)
    hung_advance.pop("expected_duration_ms")
    CONTRACTS["thing.hung"] = (hung_advance, 1_000, "declared")
    try:
        host, _ = make_host(adapter, allow=["thing.hung"], deadline_grace_seconds=0.2)
        started = _time.monotonic()
        record = call(host, "thing.hung", {"distance_m": 0.5})
        elapsed = _time.monotonic() - started
    finally:
        release.set()
        del CONTRACTS["thing.hung"]
    assert elapsed < 5
    assert record["outcome"] == "timeout" and record["host_watchdog"] is True
    assert record["safety_recovery"] == "cancel=cancelled, safe_stop=completed"
    assert ("safe_stop",) in adapter.calls


def test_calls_on_one_host_run_one_at_a_time():
    import threading
    import time as _time

    adapter = FakeAdapter(RESOURCE)
    active = {"now": 0, "peak": 0}
    guard = threading.Lock()

    def slow(request):
        with guard:
            active["now"] += 1
            active["peak"] = max(active["peak"], active["now"])
        _time.sleep(0.05)
        with guard:
            active["now"] -= 1
        return Result(request.call_id, "completed")

    adapter.invoke = slow
    host, _ = make_host(adapter)

    async def both():
        request = {"resource_id": RESOURCE, "capability_id": "thing.read", "arguments": {}}
        return await asyncio.gather(host.invoke(request), host.invoke(request))

    records = asyncio.run(both())
    assert [r["outcome"] for r in records] == ["completed", "completed"]
    assert active["peak"] == 1


def test_an_actuating_call_failed_for_missing_artifacts_is_safe_stopped():
    capture_moving = dict(CAPTURE, actuates=True, safety_class="movement", requires_safe_stop=True)
    CONTRACTS["thing.sweep"] = (capture_moving, None, "declared")
    try:
        host, adapter = make_host(FakeAdapter(RESOURCE, evidence={}), allow=["thing.sweep"])
        record = call(host, "thing.sweep")
    finally:
        del CONTRACTS["thing.sweep"]
    assert record["outcome"] == "failed"
    assert record["safety_recovery"] == "cancel=cancelled, safe_stop=completed"


def test_an_unknown_outcome_is_a_failure():
    host, adapter = make_host(FakeAdapter(RESOURCE, outcome="ok"))
    record = call(host, "thing.read")
    assert record["outcome"] == "failed" and "unknown outcome" in record["detail"]
    assert ("safe_stop",) in adapter.calls


def test_the_deadline_falls_back_to_timeout_ms_then_the_default():
    CONTRACTS["thing.timed"] = (READ, 2_500, "declared")
    CONTRACTS["thing.untimed"] = (READ, None, "declared")
    try:
        host, _ = make_host(default_deadline_seconds=42)
        assert call(host, "thing.timed")["deadline_seconds"] == 2.5
        assert call(host, "thing.untimed")["deadline_seconds"] == 42.0
    finally:
        del CONTRACTS["thing.timed"], CONTRACTS["thing.untimed"]


def test_adapter_evidence_is_kept_verbatim():
    evidence = {"clearance_m": 0.8, "nested": {"a": [1, 2]}}
    host, _ = make_host(FakeAdapter(RESOURCE, evidence=evidence))
    assert call(host, "thing.read")["adapter_evidence"] == evidence


def test_call_ids_are_stable_per_run_and_distinct_per_call():
    host, _ = make_host()
    first, second = call(host, "thing.read"), call(host, "thing.read")
    assert first["call_id"] != second["call_id"]
    again, _ = make_host()
    assert call(again, "thing.read")["call_id"] == first["call_id"]
    assert len(host.records()) == 2


# ---------------------------------------------------------------------------
# Artifacts
# ---------------------------------------------------------------------------


def _artifact(data=b"\xff\xd8jpeg", **overrides):
    item = {"kind": "image", "media_type": "image/jpeg", "data_base64": base64.b64encode(data).decode()}
    item.update(overrides)
    return item


def test_a_declared_artifact_is_checked_and_saved(tmp_path):
    adapter = FakeAdapter(RESOURCE, evidence={"artifacts": [_artifact()]})
    host, _ = make_host(adapter, artifact_dir=tmp_path)
    record = call(host, "thing.capture")
    assert record["outcome"] == "completed"
    kept = record["artifacts"][0]
    assert kept["media_type"] == "image/jpeg" and kept["bytes"] == 6
    assert Path(kept["path"]).read_bytes() == b"\xff\xd8jpeg"
    assert record["adapter_evidence"]["artifacts"][0]["data_base64"]  # verbatim


@pytest.mark.parametrize(
    "artifacts, error",
    [
        ([], "no artifact"),
        ([_artifact(kind="map")], "not declared by the contract"),
        ([_artifact(media_type="image/png")], "media type"),
        ([_artifact(data=b"x" * 65)], "bytes"),
        ([_artifact(data_base64="***")], "not valid base64"),
        ([_artifact(data_base64=None)], "no data_base64"),
    ],
)
def test_an_undeclared_or_oversized_artifact_fails_the_call(artifacts, error):
    host, _ = make_host(FakeAdapter(RESOURCE, evidence={"artifacts": artifacts}))
    record = call(host, "thing.capture")
    assert record["outcome"] == "failed"
    assert record["detail"] == "the adapter returned no artifact the contract declares"
    assert error in " ".join(record.get("artifact_errors", [])) or error == "no artifact"


def test_a_missing_artifact_list_fails_a_capture():
    host, _ = make_host(FakeAdapter(RESOURCE, evidence={}))
    record = call(host, "thing.capture")
    assert record["outcome"] == "failed"
    assert record["artifact_errors"] == ["the adapter reported no artifacts"]


# ---------------------------------------------------------------------------
# Stop and close
# ---------------------------------------------------------------------------


def test_stop_now_and_close():
    host, adapter = make_host()
    assert host.stop_now() == "safe_stop=not-connected"
    call(host, "thing.read")
    assert asyncio.run(host.emergency_stop()) == "safe_stop=completed"
    host.close()
    assert adapter.disconnected is True


# ---------------------------------------------------------------------------
# Adapter resolution and the registry lookup
# ---------------------------------------------------------------------------


class _EntryPoint:
    def __init__(self, name, target):
        self.name = name
        self._target = target

    def load(self):
        if isinstance(self._target, Exception):
            raise self._target
        return self._target


def test_adapter_resolution_is_by_exact_unique_name(monkeypatch):
    factory = lambda resource_id: FakeAdapter(resource_id)  # noqa: E731
    points = [_EntryPoint(ADAPTER, factory), _EntryPoint("twice", factory), _EntryPoint("twice", factory),
              _EntryPoint("broken", ImportError("x")), _EntryPoint("value", 3)]
    monkeypatch.setattr(host_module, "_adapter_entry_points", lambda: points)
    assert resolve_adapter_factory(ADAPTER) is factory
    assert host_module.installed_adapters() == ["broken", ADAPTER, "twice", "value"]
    for name, message in (("fake", "not installed"), ("twice", "more than one"),
                          ("broken", "could not be loaded"), ("value", "not callable")):
        with pytest.raises(CapabilityHostError, match=message):
            resolve_adapter_factory(name)
    host = CapabilityHost(adapter_id=ADAPTER, resource_id=RESOURCE, contract_lookup=lookup)
    assert call(host, "thing.read")["outcome"] == "completed"


class _Module(BaseModule):
    async def execute(self):  # pragma: no cover
        return {}


@pytest.fixture
def providers():
    ids = []

    def register(module_id, capability, contract, timeout_ms=None):
        metadata = {
            "module_id": module_id, "category": "hosttest", "stability": "stable",
            "ui_label": module_id, "ui_description": "host test", "provides_capability": capability,
            "params_schema": dict(PARAMS),
        }
        if contract is not None:
            metadata["contract"] = contract
        if timeout_ms is not None:
            metadata["timeout_ms"] = timeout_ms
        ModuleRegistry.register(module_id, _Module, metadata)
        ids.append(module_id)

    yield register
    for module_id in ids:
        ModuleRegistry.unregister(module_id)


def test_registry_lookup_reads_the_declared_contract(providers):
    providers("hosttest.advance", "hosttest.advance", ADVANCE, 90_000)
    contract, timeout_ms, status = registry_contract_lookup("hosttest.advance")
    assert status == "declared" and timeout_ms == 90_000
    assert contract["expected_duration_ms"] == 180_000
    assert registry_contract_lookup("hosttest.none") == (None, None, "absent")


def test_registry_lookup_fails_closed_on_disagreeing_or_missing_contracts(providers):
    providers("hosttest.a", "hosttest.shared", ADVANCE)
    providers("hosttest.b", "hosttest.shared", READ)
    assert registry_contract_lookup("hosttest.shared") == (None, None, "ambiguous")
    providers("hosttest.c", "hosttest.half", READ)
    providers("hosttest.d", "hosttest.half", None)
    assert registry_contract_lookup("hosttest.half") == (None, None, "absent")


# ---------------------------------------------------------------------------
# Through a workflow: capability.invoke reaches the host via initial_context
# ---------------------------------------------------------------------------


def test_capability_invoke_in_a_workflow_runs_through_the_host():
    from core.engine.workflow.engine import WorkflowEngine

    host, adapter = make_host(allow=["thing.advance"])
    workflow = {
        "name": "host smoke",
        "steps": [
            {
                "id": "advance",
                "module": "capability.invoke",
                "params": {
                    "resource_id": RESOURCE,
                    "capability_id": "thing.advance",
                    "arguments": {"distance_m": 0.4},
                },
            }
        ],
    }
    engine = WorkflowEngine(workflow, {}, initial_context=host.context())
    asyncio.run(engine.execute())
    records = host.records()
    assert [r["capability_id"] for r in records] == ["thing.advance"]
    assert records[0]["outcome"] == "completed"
    assert records[0]["verification"]["verified"] is True
    json.dumps(records)  # the evidence file is JSON


# ---------------------------------------------------------------------------
# CLI glue
# ---------------------------------------------------------------------------


def test_cli_builds_a_fail_closed_host_without_a_terminal(monkeypatch, tmp_path):
    from cli import capability_host as cli_host

    monkeypatch.setattr("core.capability_host.installed_adapters", lambda: [ADAPTER])
    monkeypatch.setattr(cli_host, "_interactive", lambda: False)
    args = SimpleNamespace(capability_host=ADAPTER, resource=RESOURCE, allow=["thing.advance, thing.rotate"],
                           yes_physical=False)
    host = cli_host.build_capability_host(args)
    assert host.allowed == {"thing.advance", "thing.rotate"}
    assert host._confirm is None and host.yes_physical is False

    host._factory = lambda resource_id: FakeAdapter(resource_id, mode="hardware")
    host._lookup = lookup
    assert call(host, "thing.advance", {"distance_m": 0.5})["outcome"] == "refused"
    path = cli_host.write_capability_evidence(host, tmp_path / "evidence.json", tmp_path / "w.yaml", {})
    written = json.loads(path.read_text())
    assert written["calls"][0]["outcome"] == "refused"


def test_cli_refuses_a_missing_resource_or_adapter(monkeypatch):
    from cli import capability_host as cli_host

    monkeypatch.setattr("core.capability_host.installed_adapters", lambda: [ADAPTER])
    with pytest.raises(SystemExit) as exit_info:
        cli_host.build_capability_host(SimpleNamespace(capability_host=ADAPTER, resource="", allow=[]))
    assert exit_info.value.code == 2
    with pytest.raises(SystemExit):
        cli_host.build_capability_host(SimpleNamespace(capability_host="other", resource=RESOURCE, allow=[]))
