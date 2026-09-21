"""Runtime-only consumption of canonical capability requests.

Authoring modules may describe desired work without owning transport or execution
placement. A request becomes executable only when the hosting runtime injects an
opaque dispatcher into the engine context. JSON workflow data therefore cannot
grant itself execution authority.
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from typing import Any

CAPABILITY_REQUEST_VERSION = "flyto.capability-request.v1"
RUNTIME_DISPATCHER_KEY = "_flyto_capability_dispatcher"
_COMPLETED = "completed"


class CapabilityDispatchError(RuntimeError):
    """A canonical capability request could not be executed safely."""


def _request_from(result: Any) -> Mapping[str, Any] | None:
    if not isinstance(result, Mapping):
        return None
    request = result.get("capability_request")
    return request if isinstance(request, Mapping) else None


def _runtime_dispatcher(context: Mapping[str, Any]) -> Any | None:
    candidate = context.get(RUNTIME_DISPATCHER_KEY)
    if candidate is None:
        return None
    if (
        getattr(type(candidate), "_flyto_runtime_opaque", False) is not True
        or not callable(getattr(candidate, "invoke", None))
    ):
        raise CapabilityDispatchError(
            "capability dispatcher is not a runtime-owned opaque dispatcher"
        )
    return candidate


def _validate_request(request: Mapping[str, Any]) -> dict[str, Any]:
    if request.get("contract_version") != CAPABILITY_REQUEST_VERSION:
        raise CapabilityDispatchError("unsupported capability request contract")
    required = ("resource_id", "capability_id", "arguments", "goal")
    if any(key not in request for key in required):
        raise CapabilityDispatchError("capability request is incomplete")
    resource_id = request.get("resource_id")
    capability_id = request.get("capability_id")
    arguments = request.get("arguments")
    goal = request.get("goal")
    if not isinstance(resource_id, str) or not resource_id.strip():
        raise CapabilityDispatchError("capability request has no commanded resource")
    if not isinstance(capability_id, str) or not capability_id.strip():
        raise CapabilityDispatchError("capability request has no capability")
    if not isinstance(arguments, Mapping):
        raise CapabilityDispatchError("capability request arguments must be an object")
    if not isinstance(goal, str):
        raise CapabilityDispatchError("capability request goal must be text")
    return {
        "contract_version": CAPABILITY_REQUEST_VERSION,
        "resource_id": resource_id.strip(),
        "capability_id": capability_id.strip(),
        "arguments": dict(arguments),
        "goal": goal,
    }


async def consume_capability_request(result: Any, context: Mapping[str, Any]) -> Any:
    """Execute one declared capability through runtime authority, when present.

    With no runtime dispatcher the payload remains declaration-only. This keeps
    builder/preview/registration execution non-actuating. When authority is
    injected, malformed requests and non-completed outcomes fail closed.
    """
    request = _request_from(result)
    if request is None:
        return result
    dispatcher = _runtime_dispatcher(context)
    if dispatcher is None:
        return result

    canonical = _validate_request(request)
    execution = dispatcher.invoke(dict(canonical))
    if inspect.isawaitable(execution):
        execution = await execution
    if not isinstance(execution, Mapping):
        raise CapabilityDispatchError("capability dispatcher returned no execution record")

    record = dict(execution)
    outcome = str(record.get("outcome") or "").strip().lower()
    if outcome != _COMPLETED:
        detail = str(record.get("detail") or outcome or "capability execution failed")
        raise CapabilityDispatchError(detail[:500])

    merged = dict(result)
    merged["dispatched"] = True
    merged["execution"] = record
    return merged
