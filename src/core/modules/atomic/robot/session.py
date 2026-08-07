# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""What a robot gateway is asked, and what its answer means.

Kept free of HTTP and of the module registry so both decisions this module
makes — which plan to send, and what a finished session actually proved — are
testable without a robot, a network, or an engine. The transport in plan.py is
deliberately thin on top of these.
"""

from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional
import json
import math
import os

PLAN_REQUEST_CONTRACT = "flyto.cloud.plan-run-request.v1"

DEFAULT_GATEWAY_URL = "http://127.0.0.1:8766"
DEFAULT_PLAN_ROOT = "/home/ubuntu/flyto-robotics/examples/plans"

# What the gateway calls a mission that is over. These are MissionState values,
# not invented names: a mission that finished its workflow reports "completed".
TERMINAL_STATES = frozenset({"completed", "succeeded", "failed", "cancelled", "aborted"})
SUCCESS_STATES = frozenset({"completed", "succeeded"})


class PlanResolutionError(ValueError):
    """The step did not name a plan this host is allowed to send."""


def gateway_url(explicit: Optional[str] = None) -> str:
    """Where the robot's own gateway is listening.

    A host that drives a robot over a tunnel points this elsewhere; the default
    is the loopback address the gateway binds on the robot itself.
    """
    return (explicit or os.environ.get("FLYTO_ROBOTICS_GATEWAY_URL") or DEFAULT_GATEWAY_URL).rstrip("/")


def plan_root(explicit: Optional[str] = None) -> Path:
    return Path(explicit or os.environ.get("FLYTO_PLAN_ROOT") or DEFAULT_PLAN_ROOT)


def resolve_plan(
    *,
    plan: Optional[Mapping[str, Any]] = None,
    plan_path: Optional[str] = None,
    root: Optional[str] = None,
) -> Dict[str, Any]:
    """The plan to send: inline, or one this host already holds by name.

    A named plan is a bare filename in the plans directory. Anything carrying a
    separator is refused outright rather than reduced to its last component:
    quietly running `turn.json` because the step said `sub/dir/turn.json` means
    a machine moves on an instruction nobody wrote. Refusing is the only answer
    that cannot be wrong.
    """
    if plan is not None:
        if not isinstance(plan, Mapping) or not plan.get("contract_version"):
            raise PlanResolutionError("inline plan must carry a contract_version")
        return dict(plan)

    name = str(plan_path or "").strip()
    if not name:
        raise PlanResolutionError("name a plan_path, or pass an inline plan")
    if name != Path(name).name or name in (".", ".."):
        raise PlanResolutionError(
            "plan_path must be a bare filename in the plans directory, not a path"
        )

    base = plan_root(root).resolve()
    candidate = (base / name).resolve()
    if candidate.parent != base:
        raise PlanResolutionError("plan_path must name a file in the plans directory")
    if not candidate.is_file():
        raise PlanResolutionError(f"no plan named {candidate.name} on this host")
    return json.loads(candidate.read_text())


def plan_request(plan: Mapping[str, Any], *, request_id: str, requested_at: str) -> Dict[str, Any]:
    return {
        "contract_version": PLAN_REQUEST_CONTRACT,
        "request_id": request_id[:128],
        "plan": dict(plan),
        "requested_at": requested_at,
    }


def session_state(session: Mapping[str, Any]) -> str:
    """The gateway spells this "status"; "state" is accepted for fixtures."""
    return str(session.get("status") or session.get("state") or "").lower()


def is_terminal(session: Mapping[str, Any]) -> bool:
    return session_state(session) in TERMINAL_STATES


def closest_range(value: Any) -> Optional[float]:
    """A measured distance, or None when the sensor had nothing to say.

    Infinity is how "nothing measured there" is spelled inside the controller,
    and it must not travel outward as a number: a clearance of `inf` reads as a
    wide open corridor.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value):
        return None
    return float(value)


def outcome(session: Mapping[str, Any]) -> Dict[str, Any]:
    """What a finished session proved, in the evidence vocabulary.

    Only a mission that finished reports anything: not knowing where the robot
    ended up must never be written down as an arrival, and the last range read
    before a failure is not a clearance anyone should act on.
    """
    state = session_state(session)
    succeeded = state in SUCCESS_STATES
    pose = session.get("pose") or session.get("final_pose")
    nearest = closest_range(session.get("minimum_range"))

    evidence: List[Dict[str, Any]] = []
    if succeeded and pose is not None:
        evidence.append({
            "kind": "arrival.pose",
            "usable": True,
            "detail": json.dumps(pose, sort_keys=True)[:200],
        })
    if succeeded and nearest is not None:
        evidence.append({
            "kind": "clearance.measurement",
            "usable": True,
            "detail": f"nearest obstacle {nearest:.2f} m",
        })

    return {
        "status": "succeeded" if succeeded else "failed",
        "state": state,
        "session_id": str(session.get("session_id") or ""),
        "pose": pose,
        "minimum_range": nearest,
        "detail": str(session.get("failure_reason") or session.get("reason") or state)[:300],
        "evidence": evidence,
    }
