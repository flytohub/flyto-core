# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.
"""Adapter template runner: one simulated linear axis, served over JSON-RPC on stdio.

Standard library only. Replace ``Axis`` with your device; keep the rest.

What a host relies on, and this template shows:

* Every call is answered, as ``{"ok": true, "data": ...}`` or
  ``{"ok": false, "error": {"code", "message"}}``. Never a crash, never silence.
* A value outside the travel published in ``flyto-pack.json`` is **refused,
  never clamped**. The host refuses it too, but the adapter owns the device and
  must not rely on the host.
* The stop (``positioner.halt``) is its own capability and always answers.
* ``move_to`` reports the measured position it ended at, so the host can judge
  the contract's evidence itself rather than trusting an ``ok``.

Run ``flyto pack conform examples/packs/adapter-template`` to check it.
"""

from __future__ import annotations

import json
import sys

PACK_VERSION = "0.1.0"
# The travel published in flyto-pack.json (params_schema.target_mm.min/max).
TRAVEL_MM = (0.0, 300.0)


class RefusedError(Exception):
    """A request the device will not run. ``code`` is stable; the message is for people."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class Axis:
    """A simulated axis. A real adapter talks to its controller here."""

    def __init__(self) -> None:
        self.position_mm = 0.0
        self.stopped = False

    def move_to(self, target: float) -> float:
        low, high = TRAVEL_MM
        if not low <= target <= high:
            raise RefusedError("OUT_OF_BOUNDS", f"target {target} mm is outside the travel {low}..{high} mm")
        self.stopped = False
        self.position_mm = float(target)
        return self.position_mm

    def halt(self) -> None:
        self.stopped = True


AXIS = Axis()


def _number(value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RefusedError("INVALID_ARGUMENT", "target_mm must be a number")
    return float(value)


def move_to(params: dict) -> dict:
    reached = AXIS.move_to(_number(params.get("target_mm")))
    return {"axis_position": {"position_mm": reached}}


def read_position(_params: dict) -> dict:
    return {"axis_position": {"position_mm": AXIS.position_mm}, "stopped": AXIS.stopped}


def halt(_params: dict) -> dict:
    AXIS.halt()
    return {"stopped": True}


# module_id -> handler: the one place a call is routed.
HANDLERS = {
    "positioner.move_to": move_to,
    "positioner.read_position": read_position,
    "positioner.halt": halt,
}


def _invoke(params: dict) -> dict:
    handler = HANDLERS.get(params.get("step"))
    if handler is None:
        return {"ok": False, "error": {"code": "UNKNOWN_MODULE", "message": "this pack does not serve that module"}}
    try:
        return {"ok": True, "data": handler(params.get("input") or {})}
    except RefusedError as refused:
        return {"ok": False, "error": {"code": refused.code, "message": str(refused)}}


METHODS = {
    "handshake": lambda params: {"pluginVersion": PACK_VERSION, "protocolVersion": params.get("protocolVersion")},
    "ping": lambda _params: {},
    "invoke": _invoke,
}


def _reply(message_id, result=None, error=None) -> None:
    message = {"jsonrpc": "2.0", "id": message_id}
    message.update({"error": error} if error else {"result": result})
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def serve() -> None:
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
        except ValueError:
            continue
        method, message_id = request.get("method"), request.get("id")
        if method == "shutdown":
            _reply(message_id, {})
            return
        handler = METHODS.get(method)
        if handler is None:
            _reply(message_id, error={"code": -32601, "message": f"unknown method {method}"})
            continue
        _reply(message_id, handler(request.get("params") or {}))


if __name__ == "__main__":
    serve()
