# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""An adapter's status surface, and the typed resource fault it may report.

An adapter (or the transport of the pack that discovered a resource) may
offer ``connection_status()`` or ``transport_status()``. Both are
feature-detected: an adapter without them stays valid and is served exactly
as before. Each returns a mapping read field by field (:data:`STATUS_FIELDS`)
into one shape, so a host and a platform read the same answer.

**Faults.** "The link is up, and the resource says it cannot work now" is not
a connection state. It travels as one optional field, ``fault``:

* ``"fault": {"reason": <code>, "since": <ISO 8601 with offset>}`` -- the
  resource is faulted, since then, for that reason (the adapter's own code,
  :func:`fault_code` grammar);
* ``"fault": None`` -- the adapter read its fault state and there is none;
* no ``fault`` key -- nobody said: "not faulted, unknown". Every adapter
  written before this field reports this, and it is judged as before.

A ``fault`` that is present and cannot be read is a fault
(:data:`REASON_FAULT_UNREADABLE`), never silence: an adapter that tried to
say something about the resource's health and garbled it has not said it is
fine.

**Raised faults.** An adapter call may raise an exception that carries a
``fault_code`` attribute (:data:`RAISED_CODE_ATTRIBUTE`; :class:`AdapterFaultError`
is a ready-made one). That is a fault, not only a failed call
(:func:`raised_fault`). A host latches it and reports it on the status until
the adapter answers ``fault: None``.

These are the rules flyto-cloud reads (``services/device/equipment_fault.py``,
``local/equipment_faults.py``); the names are identical so a pack written
against this module is read the same way by a Desktop host.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Mapping, Optional

#: The key on a status mapping (and on a connection sample).
FAULT_KEY = "fault"
#: The attribute an adapter's exception carries to say it is a resource fault.
RAISED_CODE_ATTRIBUTE = "fault_code"
#: A fault field nobody can read.
REASON_FAULT_UNREADABLE = "fault_report_unreadable"
#: The code a raised fault carries when it names no readable one.
REASON_FAULT_RAISED = "adapter_fault"

#: The connection states a status may state.
CONNECTION_STATES = ("connected", "reconnecting", "failed", "stopped")
#: Status fields other than ``state`` and ``fault``, each with the one type it is read as.
STATUS_FIELDS: Dict[str, type] = {
    "since": str,
    "attempts": int,
    "last_error": str,
    "error_code": str,
    "accepting_calls": bool,
    "refused": bool,
    "reason_code": str,
    "transport": str,
}
#: Methods a status is read from, in order of preference.
STATUS_METHODS = ("connection_status", "transport_status")
_TEXT_LIMIT = 200

_CODE = re.compile(r"^[a-z][a-z0-9_.:-]{0,63}$")


@dataclass(frozen=True)
class ResourceFault:
    """Why the resource is faulted, and since when (ISO 8601; '' when the report did not say readably)."""

    reason: str
    since: str = ""

    def to_dict(self) -> Dict[str, str]:
        return {"reason": self.reason, "since": self.since}


@dataclass(frozen=True)
class FaultReading:
    """What a status says about faults: whether it said anything, and the fault when there is one."""

    reported: bool
    fault: Optional[ResourceFault] = None

    @property
    def faulted(self) -> bool:
        return self.fault is not None


#: A status with no ``fault`` key.
NOT_REPORTED = FaultReading(reported=False)
#: ``"fault": None``.
REPORTED_CLEAR = FaultReading(reported=True)


class AdapterFaultError(Exception):
    """Raise from an adapter call to say the resource is faulted, not that the call merely failed."""

    def __init__(self, fault_code: str, message: str = "") -> None:
        super().__init__(message or fault_code)
        self.fault_code = fault_code


def fault_code(value: Any) -> str:
    """``value`` as a fault code, or '' when it is not one."""
    text = value.strip() if isinstance(value, str) else ""
    return text if _CODE.match(text) else ""


def _since(value: Any) -> str:
    """A stated instant with its offset, normalized; raises ``ValueError`` when it is not one."""
    if not isinstance(value, str):
        raise ValueError("not an instant")
    moment = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if moment.tzinfo is None:
        raise ValueError("an instant needs its offset")
    return moment.isoformat()


def read_fault(payload: Any) -> FaultReading:
    """What one status mapping says about a fault (module docstring). Pure."""
    if not isinstance(payload, Mapping) or FAULT_KEY not in payload:
        return NOT_REPORTED
    raw = payload[FAULT_KEY]
    if raw is None:
        return REPORTED_CLEAR
    unreadable = FaultReading(reported=True, fault=ResourceFault(REASON_FAULT_UNREADABLE))
    if not isinstance(raw, Mapping):
        return unreadable
    code = fault_code(raw.get("reason"))
    try:
        since = _since(raw.get("since"))
    except ValueError:
        return unreadable
    return FaultReading(reported=True, fault=ResourceFault(code, since)) if code else unreadable


def fault_payload(fault: Optional[ResourceFault]) -> Optional[Dict[str, str]]:
    """The ``fault`` field to write: the fault, or None for "read, and none"."""
    return fault.to_dict() if fault is not None else None


def raised_fault(error: BaseException, *, at: str) -> Optional[ResourceFault]:
    """The fault an adapter's exception declares (:data:`RAISED_CODE_ATTRIBUTE`); None for any other error."""
    declared = getattr(error, RAISED_CODE_ATTRIBUTE, None)
    if declared is None:
        return None
    return ResourceFault(fault_code(declared) or REASON_FAULT_RAISED, at)


def status_payload(raw: Mapping[str, Any]) -> Dict[str, Any]:
    """An adapter's status read field by field: known fields of the right type, and the fault normalized.

    Nothing is coerced and nothing is defaulted: a field of the wrong type is
    dropped, and a status without ``fault`` has no ``fault`` key.
    """
    found: Dict[str, Any] = {}
    if raw.get("state") in CONNECTION_STATES:
        found["state"] = raw["state"]
    for name, kind in STATUS_FIELDS.items():
        value = raw.get(name)
        if type(value) is kind:
            found[name] = value[:_TEXT_LIMIT] if isinstance(value, str) else value
    if FAULT_KEY in raw:
        found[FAULT_KEY] = fault_payload(read_fault(raw).fault)
    return found


__all__ = [
    "CONNECTION_STATES", "FAULT_KEY", "NOT_REPORTED", "RAISED_CODE_ATTRIBUTE", "REASON_FAULT_RAISED",
    "REASON_FAULT_UNREADABLE", "REPORTED_CLEAR", "STATUS_FIELDS", "STATUS_METHODS", "AdapterFaultError",
    "FaultReading", "ResourceFault", "fault_code", "fault_payload", "raised_fault", "read_fault",
    "status_payload",
]
