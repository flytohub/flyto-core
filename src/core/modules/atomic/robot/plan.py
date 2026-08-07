# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Robot Plan Module — run one bounded plan on a robot and report what it proved.

A robot is reached through its own gateway, which is the only thing that owns
the machine: it validates a plan against the robot's identity and safety
envelope, drives the wheels, and stops them. This module drives nothing. It
hands over a plan the gateway already accepts and reports the session's answer.

That division is why a robot needs no execution engine on board. The gateway
runs on the robot; this module runs anywhere that can reach it — the robot
itself, or a workstation with a tunnel open.

``robot.actuate`` is declared dangerous, so this module is refused unless an
operator has granted it. Every other module in that class can cost data or
money; this one moves something in the physical world, and a workflow that
reached a robot because nobody had thought about it is the failure mode worth
being loud about.
"""

from typing import Any, Dict
import asyncio
import json
import os
import time
import urllib.error
import urllib.request

from ...registry import register_module
from ...errors import InvalidValueError, ValidationError
from .session import (
    PlanResolutionError,
    gateway_url,
    is_terminal,
    outcome,
    plan_request,
    resolve_plan,
)

DEFAULT_TIMEOUT_SECONDS = 300.0
POLL_SECONDS = 1.0


def _call(url: str, *, token: str, body: Any = None, timeout: float = 20.0) -> Dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=None if body is None else json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            **({"Content-Type": "application/json"} if body is not None else {}),
        },
        method="POST" if body is not None else "GET",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
        return json.loads(raw) if raw else {}


def _run_plan_blocking(params: Dict[str, Any]) -> Dict[str, Any]:
    token = str(
        params.get("token") or os.environ.get("FLYTO_ROBOTICS_DELIVERY_TOKEN") or ""
    ).strip()
    if not token:
        raise ValidationError(
            "No robot gateway credential. Set FLYTO_ROBOTICS_DELIVERY_TOKEN on "
            "the host that runs this step.",
            field="token",
        )

    base = gateway_url(params.get("gateway_url"))
    plan = resolve_plan(
        plan=params.get("plan"),
        plan_path=params.get("plan_path"),
        root=params.get("plan_root"),
    )

    request_id = str(params.get("request_id") or f"module-{int(time.time() * 1000)}")
    started = _call(
        f"{base}/v1/plans",
        token=token,
        body=plan_request(
            plan,
            request_id=request_id,
            requested_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        ),
        timeout=20.0,
    )
    session_id = str(started.get("session_id") or "")
    if not session_id:
        raise InvalidValueError("the gateway accepted no session for this plan", field="plan")

    deadline = time.monotonic() + float(params.get("timeout_seconds") or DEFAULT_TIMEOUT_SECONDS)
    latest = started
    while not is_terminal(latest):
        if time.monotonic() >= deadline:
            # The gateway still owns the robot. Not knowing is not the same as
            # failing to move, and it is certainly not success.
            return {
                "status": "failed",
                "state": "unknown",
                "session_id": session_id,
                "pose": None,
                "minimum_range": None,
                "detail": "outcome unknown before the step's timeout",
                "evidence": [],
            }
        time.sleep(POLL_SECONDS)
        latest = _call(f"{base}/v1/deliveries/{session_id}", token=token, timeout=20.0)
    return outcome(latest)


@register_module(
    module_id='robot.plan',
    version='1.0.0',
    category='robot',
    tags=['robot', 'plan', 'motion', 'device'],
    label='Run Robot Plan',
    label_key='modules.robot.plan.label',
    description='Run one bounded plan on a robot through its gateway and report what it proved',
    description_key='modules.robot.plan.description',
    icon='Bot',
    color='#0EA5E9',
    input_types=['object'],
    output_types=['object'],
    can_receive_from=['*'],
    can_connect_to=['*'],
    # Never retried automatically: re-running something that may already have
    # moved a robot, on the assumption it did not, is how a retry becomes a
    # collision.
    retryable=False,
    # One mission at a time is the gateway's own rule; two steps racing it
    # would only produce a rejected session.
    concurrent_safe=False,
    requires_credentials=True,
    handles_sensitive_data=False,
    required_permissions=['robot.actuate'],
    params_schema={
        'type': 'object',
        'properties': {
            'plan_path': {
                'type': 'string',
                'label': 'Plan file',
                'description': 'Bare filename of a plan this host holds, e.g. shortcut-turn-left-90deg.json',
                'placeholder': 'shortcut-turn-left-90deg.json',
                'componentType': 'input',
            },
            'plan': {
                'type': 'object',
                'label': 'Inline plan',
                'description': 'A full plan document, when it is not a file on this host',
            },
            'gateway_url': {
                'type': 'string',
                'label': 'Gateway URL',
                'description': 'Defaults to FLYTO_ROBOTICS_GATEWAY_URL, then the robot loopback address',
                'placeholder': 'http://127.0.0.1:8766',
                'componentType': 'input',
            },
            'timeout_seconds': {
                'type': 'number',
                'label': 'Timeout (seconds)',
                'description': 'How long to watch one mission before reporting the outcome unknown',
                'default': DEFAULT_TIMEOUT_SECONDS,
            },
        },
        'required': [],
    },
    output_schema={
        'status': {'type': 'string', 'description': 'succeeded or failed'},
        'state': {'type': 'string', 'description': "The gateway's own final mission state"},
        'session_id': {'type': 'string', 'description': 'The mission session this step ran'},
        'pose': {'type': 'object', 'description': 'Where odometry closed, when the mission finished'},
        'minimum_range': {'type': 'number', 'description': 'Nearest lidar return during the mission, if any'},
        'evidence': {'type': 'array', 'description': 'What the mission proved, in the evidence vocabulary'},
    },
    examples=[
        {
            'name': 'Sweep the lidar by turning in place',
            'params': {'plan_path': 'shortcut-turn-left-90deg.json'},
            'expected_output': {
                'status': 'succeeded',
                'evidence': [{'kind': 'arrival.pose'}, {'kind': 'clearance.measurement'}],
            },
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=310000,
)
async def robot_plan(context: Dict[str, Any]) -> Dict[str, Any]:
    """Run one plan on the robot this host can reach."""
    params = context.get('params') or {}
    try:
        # Blocking by construction — one call plus a poll loop. Run it off the
        # event loop so one mission cannot stall everything else on it.
        result = await asyncio.to_thread(_run_plan_blocking, params)
    except PlanResolutionError as exc:
        raise InvalidValueError(str(exc), field="plan_path") from exc
    except urllib.error.URLError as exc:
        raise InvalidValueError(
            f"no robot gateway answered at {gateway_url(params.get('gateway_url'))}: "
            f"{getattr(exc, 'reason', exc)}",
            field="gateway_url",
        ) from exc

    return {'ok': result['status'] == 'succeeded', 'data': result}
