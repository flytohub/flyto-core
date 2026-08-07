"""What a robot gateway is asked, and what its answer means.

No robot, no network: these are the two decisions robot.plan makes, and both
have to be right before anything is allowed to move.
"""

import json
import math

import pytest

from core.modules.atomic.robot.session import (
    PlanResolutionError,
    closest_range,
    is_terminal,
    outcome,
    plan_request,
    resolve_plan,
    session_state,
)


# -- which plan gets sent -------------------------------------------------


def test_an_inline_plan_must_declare_its_contract():
    with pytest.raises(PlanResolutionError, match="contract_version"):
        resolve_plan(plan={"steps": []})


def test_a_named_plan_is_read_from_the_plans_directory(tmp_path):
    (tmp_path / "turn.json").write_text(json.dumps({"contract_version": "v1", "plan_id": "turn"}))
    assert resolve_plan(plan_path="turn.json", root=str(tmp_path))["plan_id"] == "turn"


@pytest.mark.parametrize("escape", ["../secrets.json", "/etc/passwd", "sub/dir/turn.json"])
def test_a_plan_path_cannot_reach_outside_the_plans_directory(tmp_path, escape):
    """A plan is the one input that ends with a machine moving; naming an
    arbitrary file must not be a way to choose it."""
    (tmp_path / "turn.json").write_text(json.dumps({"contract_version": "v1"}))
    with pytest.raises(PlanResolutionError):
        resolve_plan(plan_path=escape, root=str(tmp_path))


def test_naming_nothing_is_refused_rather_than_defaulted(tmp_path):
    with pytest.raises(PlanResolutionError, match="plan_path"):
        resolve_plan(root=str(tmp_path))


def test_the_request_carries_the_contract_the_gateway_expects():
    body = plan_request({"contract_version": "v1"}, request_id="r-1", requested_at="2026-08-08T00:00:00Z")
    assert body["contract_version"] == "flyto.cloud.plan-run-request.v1"
    assert body["plan"]["contract_version"] == "v1"


# -- what a finished session proved ---------------------------------------


def test_the_gateways_own_terminal_state_is_recognised():
    """MissionState.COMPLETED is "completed". Waiting for "succeeded" — which
    no gateway sends — is how a real mission times out as outcome unknown."""
    assert is_terminal({"status": "completed"})
    assert is_terminal({"status": "failed"})
    assert not is_terminal({"status": "navigating"})
    # Fixtures spell it "state"; both are read.
    assert session_state({"state": "completed"}) == "completed"


def test_a_completed_mission_reports_what_it_measured():
    result = outcome({
        "status": "completed",
        "session_id": "pln-1",
        "pose": {"x": 0.0, "y": 0.0, "yaw": 1.55},
        "minimum_range": 0.5,
    })
    kinds = {item["kind"]: item for item in result["evidence"]}
    assert result["status"] == "succeeded"
    assert set(kinds) == {"arrival.pose", "clearance.measurement"}
    assert "0.50 m" in kinds["clearance.measurement"]["detail"]


def test_a_failed_mission_proves_nothing():
    """Its last pose is not an arrival and its last range is not a clearance."""
    result = outcome({
        "status": "failed",
        "failure_reason": "obstacle_stop",
        "pose": {"x": 0.1},
        "minimum_range": 0.18,
    })
    assert result["status"] == "failed"
    assert result["evidence"] == []
    assert "obstacle_stop" in result["detail"]


def test_an_unmeasured_range_stays_absent_rather_than_becoming_a_number():
    assert closest_range(math.inf) is None
    assert closest_range(None) is None
    assert closest_range(True) is None
    assert closest_range(1.42) == 1.42
    result = outcome({"status": "completed", "pose": {"x": 0.0}, "minimum_range": math.inf})
    assert [item["kind"] for item in result["evidence"]] == ["arrival.pose"]
