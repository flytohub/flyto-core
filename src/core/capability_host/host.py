# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""A generic capability host, so an installed pack runs with flyto-core alone.

A capability pack registers steps with ``@register_module(provides_capability=
..., contract=...)``. At run time such a step hands ``{resource_id,
capability_id, arguments}`` to the opaque dispatcher found in the workflow
context under ``_flyto_runtime_external_capability_dispatcher`` (the key
``capability.invoke`` reads too). Flyto2 Desktop builds that dispatcher itself.
:class:`CapabilityHost` is the same authority for a plain ``flyto run``:

* it resolves the adapter by exact name from the ``flyto2.external_adapters``
  entry-point group and builds it for one commanded resource;
* it reads each capability's contract from the registry and enforces it
  generically: no provider id, capability id, unit or threshold lives here;
* an actuating capability (or one with no contract, which fails closed as
  actuating) runs only when the run named it in ``allow``; a capability whose
  contract has ``role: safe_stop`` is always allowed and never waits for a
  confirmation, because stopping must stay immediate;
* when the adapter does not report a simulation deployment, an actuating call
  needs ``yes_physical`` or an interactive ``confirm`` that answers yes. With
  neither (no TTY) it is refused: the host fails closed;
* the deadline comes from the contract's ``expected_duration_ms``, else the
  module's ``timeout_ms``, else a default;
* the observation phases come from the contract's evidence specs; the
  contract phase ``settled`` is the adapter phase ``post_stop`` (the adapter
  API keeps its name because released hosts call it);
* a call that ends ``timeout`` or ``failed`` is followed by ``cancel`` and the
  adapter's ``safe_stop``. The deadline is enforced by the host too: an
  adapter call that has not returned by the deadline plus a short grace is
  recorded as ``timeout`` and safe-stopped, so a hung adapter cannot keep a
  resource moving. Calls on one host run one at a time;
* the adapter's outcome, detail and evidence are recorded verbatim. A refusal
  stays a refusal: the host never rewrites arguments, so an adapter's
  refuse-never-clamp bounds (a clearance floor, a speed limit) pass through
  unchanged. Contract evidence is judged with :func:`core.capability_contract.judge`
  and recorded beside the outcome; artifacts are checked against the
  contract's ``artifacts`` declaration.

The host holds no thresholds. Safety floors stay in the adapter that owns the
equipment.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import logging
import math
import sys
import threading
import time
from dataclasses import dataclass, field
from importlib.metadata import entry_points
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Tuple

from ..capability_contract import PHASES, judge

logger = logging.getLogger(__name__)

__all__ = [
    "ADAPTER_ENTRYPOINT_GROUP",
    "CAPABILITY_HOST_SCHEMA",
    "DISPATCHER_CONTEXT_KEY",
    "OUTCOME_CANCELLED",
    "OUTCOME_COMPLETED",
    "OUTCOME_FAILED",
    "OUTCOME_REFUSED",
    "OUTCOME_TIMEOUT",
    "CallRequest",
    "CapabilityHost",
    "CapabilityHostError",
    "installed_adapters",
    "registry_contract_lookup",
    "resolve_adapter_factory",
    "tty_confirm",
]

#: Schema stamped on every call record this host produces.
CAPABILITY_HOST_SCHEMA = "flyto.capability-host.v1"

#: Entry-point group an adapter package registers its factory in. The factory
#: takes the commanded resource id and returns an adapter object.
ADAPTER_ENTRYPOINT_GROUP = "flyto2.external_adapters"

#: Workflow context key a pack step and ``capability.invoke`` read. The value is
#: an ABI detail shared with Flyto2 Desktop, not a Runtime requirement.
DISPATCHER_CONTEXT_KEY = "_flyto_runtime_external_capability_dispatcher"

OUTCOME_COMPLETED = "completed"
OUTCOME_REFUSED = "refused"
OUTCOME_TIMEOUT = "timeout"
OUTCOME_CANCELLED = "cancelled"
OUTCOME_FAILED = "failed"
_OUTCOMES = frozenset(
    (OUTCOME_COMPLETED, OUTCOME_REFUSED, OUTCOME_TIMEOUT, OUTCOME_CANCELLED, OUTCOME_FAILED)
)
_SAFETY_STOP_OUTCOMES = frozenset((OUTCOME_TIMEOUT, OUTCOME_FAILED))

# Contract phase -> the phase name the adapter's observe() is called with.
_ADAPTER_PHASE = {"before": "before", "after": "after", "settled": "post_stop"}

_DEFAULT_DEADLINE_SECONDS = 60.0
_MIN_DEADLINE_SECONDS = 1.0
_MAX_DEADLINE_SECONDS = 3600.0
# How long past its deadline an adapter call may run before the host's own
# watchdog declares it timed out and safe-stops the resource.
_DEFAULT_DEADLINE_GRACE_SECONDS = 5.0
_MAX_ALLOW = 64
_MAX_ID = 128
_DETAIL_MAX = 500

ContractLookup = Callable[[str], Tuple[Optional[Dict[str, Any]], Optional[int], str]]
Confirm = Callable[[str], bool]


class CapabilityHostError(RuntimeError):
    """The host cannot be built, or its adapter cannot be resolved."""


@dataclass(frozen=True)
class CallRequest:
    """One adapter call; the same attributes Flyto2 Desktop's request carries.

    ``call_id`` is the adapter's idempotency key: a retry with the same id must
    not repeat the effect.
    """

    call_id: str
    capability_id: str
    arguments: Mapping[str, Any] = field(default_factory=dict)
    deadline_seconds: float = _DEFAULT_DEADLINE_SECONDS


# ---------------------------------------------------------------------------
# Adapter resolution
# ---------------------------------------------------------------------------


def _adapter_entry_points() -> List[Any]:
    if sys.version_info >= (3, 10):
        return list(entry_points(group=ADAPTER_ENTRYPOINT_GROUP))
    return list(entry_points().get(ADAPTER_ENTRYPOINT_GROUP, []))  # pragma: no cover


def installed_adapters() -> List[str]:
    """Names of the installed adapter entry points, sorted."""
    return sorted({entry.name for entry in _adapter_entry_points()})


def resolve_adapter_factory(adapter_id: str) -> Callable[[str], Any]:
    """Load the one adapter factory registered under exactly ``adapter_id``."""
    matches = [entry for entry in _adapter_entry_points() if entry.name == adapter_id]
    if len(matches) != 1:
        found = "not installed" if not matches else "registered by more than one package"
        raise CapabilityHostError(f"adapter {adapter_id!r} is {found} on this host")
    try:
        factory = matches[0].load()
    except Exception as error:  # noqa: BLE001 - any import failure means unusable
        raise CapabilityHostError(f"adapter {adapter_id!r} could not be loaded: {type(error).__name__}") from error
    if not callable(factory):
        raise CapabilityHostError(f"adapter {adapter_id!r} entry point is not callable")
    return factory


# ---------------------------------------------------------------------------
# Contract lookup
# ---------------------------------------------------------------------------


def registry_contract_lookup(capability_id: str) -> Tuple[Optional[Dict[str, Any]], Optional[int], str]:
    """The contract and ``timeout_ms`` the installed modules declare for a capability.

    Returns ``(contract, timeout_ms, status)`` where status is ``declared``,
    ``absent`` (no provider, or a provider without a contract) or
    ``ambiguous`` (providers declare different contracts). Only ``declared``
    carries a contract; the others make the host fail closed.
    """
    from ..modules.registry import ModuleRegistry

    providers = ModuleRegistry.capabilities().get(capability_id, [])
    contracts: List[Dict[str, Any]] = []
    timeouts: List[int] = []
    for module_id in providers:
        metadata = ModuleRegistry.get_metadata(module_id) or {}
        contract = metadata.get("contract")
        if contract is None:
            return None, None, "absent"
        if contract not in contracts:
            contracts.append(contract)
        timeout_ms = metadata.get("timeout_ms")
        if type(timeout_ms) is int and timeout_ms > 0:
            timeouts.append(timeout_ms)
    if not contracts:
        return None, None, "absent"
    if len(contracts) > 1:
        return None, None, "ambiguous"
    return contracts[0], (max(timeouts) if timeouts else None), "declared"


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _bounded_id(value: Any, what: str) -> str:
    text = str(value or "").strip()
    if not text or len(text) > _MAX_ID:
        raise CapabilityHostError(f"{what} must be a non-empty string of at most {_MAX_ID} characters")
    return text


def _call_id(run_id: str, ordinal: int, resource_id: str, capability_id: str) -> str:
    seed = "\x1f".join((run_id, str(ordinal), resource_id, capability_id))
    return "cap-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]


def _outcome_of(result: Any) -> Tuple[str, str, Dict[str, Any]]:
    """``(outcome, detail, evidence)`` from an adapter result, never trusted blindly."""
    if isinstance(result, Mapping):
        outcome, detail, evidence = result.get("outcome"), result.get("detail"), result.get("evidence")
    else:
        outcome = getattr(result, "outcome", None)
        detail = getattr(result, "detail", None)
        evidence = getattr(result, "evidence", None)
    outcome = str(outcome or "")
    detail = str(detail or "")[:_DETAIL_MAX]
    if outcome not in _OUTCOMES:
        detail = f"adapter returned unknown outcome {outcome!r}" + (f": {detail}" if detail else "")
        outcome = OUTCOME_FAILED
    return outcome, detail[:_DETAIL_MAX], dict(evidence) if isinstance(evidence, Mapping) else {}


def _deadline_seconds(contract: Optional[Mapping[str, Any]], timeout_ms: Optional[int], default: float) -> float:
    if contract is not None and type(contract.get("expected_duration_ms")) is int:
        seconds = contract["expected_duration_ms"] / 1000.0
    elif timeout_ms:
        seconds = timeout_ms / 1000.0
    else:
        seconds = default
    return max(_MIN_DEADLINE_SECONDS, min(_MAX_DEADLINE_SECONDS, float(seconds)))


def _declared_phases(contract: Optional[Mapping[str, Any]]) -> List[str]:
    declared = set()
    for spec in (contract or {}).get("evidence") or []:
        declared.update(spec.get("phases") or [])
    return [phase for phase in PHASES if phase in declared]


def _phase_values(bundles: Mapping[str, Any], observe: str) -> Dict[str, Any]:
    """``{phase: bundle[observe]}`` for the judge, from whole observation bundles."""
    values: Dict[str, Any] = {}
    for phase, bundle in bundles.items():
        if isinstance(bundle, Mapping) and isinstance(bundle.get(observe), Mapping):
            values[phase] = dict(bundle[observe])
    return values


def _json_safe(value: Any, depth: int = 0) -> Any:
    """A JSON-safe copy of an adapter observation for the evidence record."""
    if depth > 8:
        return None
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item, depth + 1) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item, depth + 1) for item in value]
    return str(value)


def tty_confirm(prompt: str) -> bool:
    """Ask on the terminal; only a typed ``yes`` confirms."""
    try:
        answer = input(f"{prompt}\nType 'yes' to run it on the physical deployment: ")
    except (EOFError, KeyboardInterrupt):
        return False
    return answer.strip().lower() == "yes"


# ---------------------------------------------------------------------------
# The host
# ---------------------------------------------------------------------------


class CapabilityHost:
    """Opaque, run-scoped authority over one adapter and one commanded resource.

    Built by the process that starts the run (``flyto run --capability-host``,
    or an embedding host) and injected with :meth:`context`. Workflow data can
    never construct one: trust is checked on the type's
    ``_flyto_runtime_opaque`` attribute.
    """

    _flyto_runtime_opaque = True

    def __init__(
        self,
        *,
        adapter_id: str,
        resource_id: str,
        allow: Iterable[str] = (),
        yes_physical: bool = False,
        confirm: Optional[Confirm] = None,
        adapter_factory: Optional[Callable[[str], Any]] = None,
        contract_lookup: Optional[ContractLookup] = None,
        run_id: Optional[str] = None,
        settle_seconds: float = 1.0,
        default_deadline_seconds: float = _DEFAULT_DEADLINE_SECONDS,
        deadline_grace_seconds: float = _DEFAULT_DEADLINE_GRACE_SECONDS,
        artifact_dir: Optional[Path] = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.adapter_id = _bounded_id(adapter_id, "adapter id")
        self.resource_id = _bounded_id(resource_id, "resource id")
        allowed = [str(item or "").strip() for item in allow]
        allowed = [item for item in allowed if item]
        if len(allowed) > _MAX_ALLOW:
            raise CapabilityHostError(f"at most {_MAX_ALLOW} capabilities may be allowed per run")
        self.allowed = frozenset(_bounded_id(item, "allowed capability id") for item in allowed)
        self.yes_physical = bool(yes_physical)
        self._confirm = confirm
        self._factory = adapter_factory
        self._lookup = contract_lookup or registry_contract_lookup
        self.run_id = str(run_id or f"run-{time.time_ns()}")
        self._settle_seconds = max(0.0, float(settle_seconds))
        self._default_deadline = float(default_deadline_seconds)
        self._deadline_grace = max(0.0, float(deadline_grace_seconds))
        self._artifact_dir = Path(artifact_dir) if artifact_dir is not None else None
        self._sleep = sleep
        self._adapter: Any = None
        self._ordinal = 0
        self._lock = threading.Lock()
        # One commanded resource, one call at a time. stop_now() never takes it.
        self._call_lock = threading.Lock()
        self._records: List[Dict[str, Any]] = []

    # -- injection --------------------------------------------------------

    def context(self) -> Dict[str, Any]:
        """The workflow ``initial_context`` that makes this host the run's dispatcher."""
        return {DISPATCHER_CONTEXT_KEY: self}

    def records(self) -> List[Dict[str, Any]]:
        """Every call record of this run, in call order (copies)."""
        with self._lock:
            return [dict(record) for record in self._records]

    # -- adapter ----------------------------------------------------------

    def _build_adapter(self) -> Any:
        if self._adapter is None:
            factory = self._factory or resolve_adapter_factory(self.adapter_id)
            self._adapter = factory(self.resource_id)
        return self._adapter

    def _deployment(self, adapter: Any) -> str:
        """``simulation`` only when the adapter says so; anything else is physical."""
        try:
            reported = getattr(adapter, "deployment_mode", None)
            if callable(reported):
                reported = reported()
            if reported is None:
                observe = getattr(adapter, "observe", None)
                bundle = observe(phase="preflight") if callable(observe) else None
                reported = bundle.get("deployment_mode") if isinstance(bundle, Mapping) else None
        except Exception:  # noqa: BLE001 - an adapter that cannot say is physical
            logger.warning("adapter %s did not report its deployment", self.adapter_id, exc_info=True)
            return "unknown"
        mode = str(reported or "").strip().lower()
        return "simulation" if mode == "simulation" else (mode or "unknown")

    def _observe(self, adapter: Any, phase: str, call_id: str) -> Optional[Dict[str, Any]]:
        observe = getattr(adapter, "observe", None)
        if not callable(observe):
            return None
        try:
            bundle = observe(phase=_ADAPTER_PHASE[phase], execution_id=call_id)
        except Exception:  # noqa: BLE001 - a missing phase makes evidence unusable, not the call
            logger.warning("could not observe %s for %s", phase, call_id, exc_info=True)
            return None
        return dict(bundle) if isinstance(bundle, Mapping) else None

    def _wait_settled(self, adapter: Any) -> None:
        wait = getattr(adapter, "wait_until_stationary", None)
        if callable(wait):
            try:
                if wait(self._settle_seconds) is not None:
                    return
            except Exception:  # noqa: BLE001 - fall back to a plain wait
                logger.warning("wait_until_stationary failed", exc_info=True)
        if self._settle_seconds:
            self._sleep(self._settle_seconds)

    def _safety_stop(self, adapter: Any, call_id: str) -> str:
        details: List[str] = []
        try:
            outcome, _, _ = _outcome_of(adapter.cancel(call_id))
            details.append(f"cancel={outcome}")
        except Exception as error:  # noqa: BLE001 - always go on to safe_stop
            details.append(f"cancel={type(error).__name__}")
        try:
            outcome, _, _ = _outcome_of(adapter.safe_stop())
            details.append(f"safe_stop={outcome}")
        except Exception as error:  # noqa: BLE001 - reported, never swallowed silently
            details.append(f"safe_stop={type(error).__name__}")
        return ", ".join(details)

    # -- policy -----------------------------------------------------------

    def _policy_refusal(
        self, adapter: Any, capability_id: str, arguments: Mapping[str, Any], contract: Optional[Mapping[str, Any]]
    ) -> Tuple[Optional[str], Dict[str, Any]]:
        """``(refusal or None, policy facts)`` for one call."""
        is_stop = contract is not None and contract.get("role") == "safe_stop"
        actuates = contract is None or bool(contract.get("actuates"))
        facts: Dict[str, Any] = {"actuates": actuates, "safe_stop_role": is_stop}
        if is_stop or not actuates:
            return None, facts
        if capability_id not in self.allowed:
            return (
                f"{capability_id} actuates (or declares no contract) and this run did not allow it; "
                f"pass --allow {capability_id} to permit it",
                facts,
            )
        deployment = self._deployment(adapter)
        facts["deployment"] = deployment
        if deployment == "simulation":
            return None, facts
        if self.yes_physical:
            facts["physical_confirmed"] = "flag"
            return None, facts
        if self._confirm is None:
            return (
                f"{capability_id} would actuate a physical deployment ({deployment}); "
                "no interactive terminal to confirm it and --yes-physical was not given",
                facts,
            )
        prompt = (
            f"{capability_id} on {self.resource_id} via {self.adapter_id} "
            f"with {dict(arguments)!r} will actuate a physical deployment ({deployment})."
        )
        try:
            confirmed = bool(self._confirm(prompt))
        except Exception:  # noqa: BLE001 - a broken prompt is not a yes
            confirmed = False
        facts["physical_confirmed"] = "interactive" if confirmed else "declined"
        if not confirmed:
            return f"{capability_id} on a physical deployment was not confirmed", facts
        return None, facts

    # -- artifacts --------------------------------------------------------

    def _check_artifacts(
        self, contract: Mapping[str, Any], evidence: Mapping[str, Any], call_id: str
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        declared = {item["kind"]: item for item in contract.get("artifacts") or []}
        kept: List[Dict[str, Any]] = []
        errors: List[str] = []
        reported = evidence.get("artifacts")
        if not isinstance(reported, list):
            return kept, (["the adapter reported no artifacts"] if declared else [])
        for index, item in enumerate(reported[:16]):
            if not isinstance(item, Mapping):
                errors.append(f"artifacts[{index}] is not a mapping")
                continue
            kind, media_type = str(item.get("kind") or ""), str(item.get("media_type") or "")
            declaration = declared.get(kind)
            if declaration is None:
                errors.append(f"artifacts[{index}] kind {kind!r} is not declared by the contract")
                continue
            if media_type not in declaration["media_types"]:
                errors.append(f"artifacts[{index}] media type {media_type!r} is not declared for {kind}")
                continue
            raw = item.get("data_base64")
            # Refuse on the encoded length before decoding an oversized blob.
            if not isinstance(raw, str) or len(raw) > (declaration["max_bytes"] * 4) // 3 + 4:
                errors.append(f"artifacts[{index}] has no data_base64 within {declaration['max_bytes']} bytes")
                continue
            try:
                data = base64.b64decode(raw, validate=True)
            except (binascii.Error, ValueError):
                errors.append(f"artifacts[{index}] data_base64 is not valid base64")
                continue
            if not data or len(data) > declaration["max_bytes"]:
                errors.append(f"artifacts[{index}] is {len(data)} bytes, outside 1..{declaration['max_bytes']}")
                continue
            entry: Dict[str, Any] = {
                "kind": kind,
                "media_type": media_type,
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
            if self._artifact_dir is not None:
                folder = self._artifact_dir / self.run_id
                folder.mkdir(parents=True, exist_ok=True)
                subtype = media_type.split("/", 1)[1].split("+", 1)[0]
                path = folder / f"{call_id}-{index}-{kind}.{subtype}"
                path.write_bytes(data)
                entry["path"] = str(path)
            kept.append(entry)
        return kept, errors

    # -- the call ---------------------------------------------------------

    def _invoke_sync(self, request: Mapping[str, Any]) -> Dict[str, Any]:
        resource_id = str(request.get("resource_id") or "").strip()
        capability_id = str(request.get("capability_id") or "").strip()
        raw_arguments = request.get("arguments")
        arguments = dict(raw_arguments) if isinstance(raw_arguments, Mapping) else {}
        with self._lock:
            self._ordinal += 1
            ordinal = self._ordinal
        call_id = _call_id(self.run_id, ordinal, resource_id, capability_id)
        record: Dict[str, Any] = {
            "schema": CAPABILITY_HOST_SCHEMA,
            "call_id": call_id,
            "run_id": self.run_id,
            "adapter_id": self.adapter_id,
            "commanded_resource_id": self.resource_id,
            "capability_id": capability_id,
            "arguments": _json_safe(arguments),
            "started_at": time.time(),
        }
        try:
            with self._call_lock:
                self._run_call(record, resource_id, capability_id, arguments, call_id)
        finally:
            record["finished_at"] = time.time()
            with self._lock:
                self._records.append(record)
        return record

    def _refuse(self, record: Dict[str, Any], detail: str) -> None:
        record["outcome"] = OUTCOME_REFUSED
        record["detail"] = detail[:_DETAIL_MAX]
        record["refused_by"] = "host"

    def _run_call(
        self, record: Dict[str, Any], resource_id: str, capability_id: str, arguments: Dict[str, Any], call_id: str
    ) -> None:
        if resource_id != self.resource_id:
            self._refuse(record, f"the request names resource {resource_id!r}; this run commands {self.resource_id!r}")
            return
        if not capability_id or len(capability_id) > _MAX_ID:
            self._refuse(record, "the request names no valid capability")
            return

        contract, timeout_ms, status = self._lookup(capability_id)
        record["contract_status"] = status
        adapter = self._build_adapter()
        refusal, facts = self._policy_refusal(adapter, capability_id, arguments, contract)
        record["policy"] = facts
        if refusal is not None:
            self._refuse(record, refusal)
            return

        deadline = _deadline_seconds(contract, timeout_ms, self._default_deadline)
        record["deadline_seconds"] = deadline
        phases = _declared_phases(contract)
        bundles: Dict[str, Any] = {}
        if "before" in phases:
            bundles["before"] = self._observe(adapter, "before", call_id)

        outcome, detail, evidence = self._invoke_with_watchdog(
            adapter,
            CallRequest(
                call_id=call_id,
                capability_id=capability_id,
                arguments=dict(arguments),
                deadline_seconds=deadline,
            ),
            record,
        )
        record["outcome"] = outcome
        record["detail"] = detail
        # Verbatim: the host adds nothing to, and removes nothing from, what
        # the adapter reported.
        record["adapter_evidence"] = evidence

        if outcome in _SAFETY_STOP_OUTCOMES:
            safety = self._safety_stop(adapter, call_id)
            record["safety_recovery"] = safety
            record["detail"] = ((detail + "; ") if detail else "") + safety

        if outcome == OUTCOME_COMPLETED and contract is not None and contract.get("artifacts"):
            kept, errors = self._check_artifacts(contract, evidence, call_id)
            record["artifacts"] = kept
            if errors:
                record["artifact_errors"] = errors
            if not kept:
                record["outcome"] = OUTCOME_FAILED
                record["detail"] = "the adapter returned no artifact the contract declares"
                if facts.get("actuates"):
                    # A failed actuating call is always followed by a safe stop.
                    safety = self._safety_stop(adapter, call_id)
                    record["safety_recovery"] = safety
                    record["detail"] += "; " + safety
                return

        # Observe after a completed call, and after an actuating call that
        # stopped short, so the record says how far it got.
        moved = outcome == OUTCOME_COMPLETED or (
            facts.get("actuates") and outcome in (OUTCOME_TIMEOUT, OUTCOME_FAILED, OUTCOME_CANCELLED)
        )
        if not moved or "after" not in phases:
            return
        bundles["after"] = self._observe(adapter, "after", call_id)
        if "settled" in phases:
            self._wait_settled(adapter)
            bundles["settled"] = self._observe(adapter, "settled", call_id)
        record["observations"] = {phase: _json_safe(bundle) for phase, bundle in bundles.items()}
        verdicts = []
        for spec in contract.get("evidence") or []:
            verdict = judge(spec, arguments, _phase_values(bundles, spec["observe"]))
            verdicts.append({"kind": spec["kind"], **verdict})
        record["verification"] = {
            "verified": all(item["usable"] for item in verdicts) if verdicts else None,
            "verdicts": verdicts,
        }

    def _invoke_with_watchdog(
        self, adapter: Any, request: CallRequest, record: Dict[str, Any]
    ) -> Tuple[str, str, Dict[str, Any]]:
        """Run ``adapter.invoke`` and hold it to the deadline from the host side.

        The adapter is expected to honour ``request.deadline_seconds`` itself.
        If it has not returned by then plus the grace period, the call is
        recorded as ``timeout`` (the caller then cancels and safe-stops it);
        the abandoned adapter thread is left to finish on its own.
        """
        box: Dict[str, Any] = {}

        def run() -> None:
            try:
                box["result"] = _outcome_of(adapter.invoke(request))
            except Exception as error:  # noqa: BLE001 - an adapter crash is a failed call
                box["result"] = (OUTCOME_FAILED, f"adapter raised {type(error).__name__}", {})

        worker = threading.Thread(target=run, name=f"capability-call-{request.call_id}", daemon=True)
        worker.start()
        worker.join(request.deadline_seconds + self._deadline_grace)
        if "result" in box:
            return box["result"]
        record["host_watchdog"] = True
        return (
            OUTCOME_TIMEOUT,
            f"adapter did not return within {request.deadline_seconds:g} s "
            f"(+{self._deadline_grace:g} s grace)",
            {},
        )

    async def invoke(self, request: Mapping[str, Any]) -> Dict[str, Any]:
        """Dispatch one ``{resource_id, capability_id, arguments}`` request."""
        return await asyncio.to_thread(self._invoke_sync, dict(request))

    # -- stop and close ---------------------------------------------------

    def stop_now(self) -> str:
        """Safe-stop the adapter immediately (no approval, no queue)."""
        adapter = self._adapter
        if adapter is None:
            return "safe_stop=not-connected"
        try:
            outcome, _, _ = _outcome_of(adapter.safe_stop())
            return f"safe_stop={outcome}"
        except Exception as error:  # noqa: BLE001
            return f"safe_stop={type(error).__name__}"

    async def emergency_stop(self) -> str:
        return await asyncio.to_thread(self.stop_now)

    def close(self) -> None:
        adapter, self._adapter = self._adapter, None
        disconnect = getattr(adapter, "disconnect", None)
        if callable(disconnect):
            try:
                disconnect()
            except Exception:  # noqa: BLE001
                logger.warning("adapter %s did not disconnect cleanly", self.adapter_id, exc_info=True)
