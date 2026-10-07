# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Capability contract — ``flyto.capability-contract.v1``.

A capability provider (a device driver, an ERP connector, a lift controller,
any package that registers modules through the ``flyto.modules`` entry point)
describes what its capability does to the world as *data*, on the same
``@register_module`` call that registers it::

    @register_module(
        module_id="lift.move_to_floor",
        provides_capability="lift.move_to_floor",
        params_schema={"floor": {"type": "integer", "min": 0, "max": 40, "required": True}},
        contract={
            "actuates": True,
            "safety_class": "movement",
            "requires_safe_stop": True,
            "cancellable": True,
            "idempotent": True,
            "effects": ["position.changed"],
            "evidence": [...],
        },
        ...
    )

A host reads the contract from the registry (catalog detail, or the
capability manifest's ``contracts`` key) and enforces it generically, so the
host contains no provider-specific code.

This module owns the two pieces of logic every party must agree on:

* :func:`validate_contract` — the closed schema, enforced at registration by
  both ``register_module`` and ``ModuleRegistry.register``.
* :func:`judge` — the evidence arithmetic. It is pure and deliberately tiny,
  because hosts that may not import Core re-implement it from
  ``docs/CAPABILITY_CONTRACT.md`` and must reach identical verdicts.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any, Dict, List, Mapping, Optional

__all__ = [
    "CONTRACT_SCHEMA",
    "SAFETY_CLASSES",
    "PHASES",
    "MEASURE_OPS",
    "ANGLE_OPS",
    "ABSOLUTE_OPS",
    "ROLES",
    "OPTIONAL_FIELDS",
    "EXPECTED_DURATION_MS_MAX",
    "ARTIFACT_MAX_BYTES",
    "RECOVERY_FIELDS",
    "RECOVERY_STOP_FAMILIES",
    "RECOVERY_PRESERVES",
    "RECOVERY_RESOURCE_SCOPES",
    "RECOVERY_ROLE_PATTERN",
    "RECOVERY_ROLES_MAX",
    "validate_contract",
    "validate_evidence",
    "judge",
    "wrap_angle",
]

#: Schema identifier stamped on every validated contract.
CONTRACT_SCHEMA = "flyto.capability-contract.v1"

#: Ordered from least to most consequential.
SAFETY_CLASSES = ("read_only", "controlled", "movement", "dangerous")

#: Observation phases, in the only order they may be declared.
PHASES = ("before", "after", "settled")

#: Measurement operators understood by :func:`judge`.
MEASURE_OPS = ("distance", "along", "delta", "angle_delta", "abs_angle_delta", "distance_to", "angle_to")

#: Operators whose measured quantity is an angle in radians.
ANGLE_OPS = ("angle_delta", "abs_angle_delta", "angle_to")

#: Operators (2.38.0) that compare the last declared phase with an absolute
#: target taken from the call's arguments, instead of a change between phases.
#: "The robot ended at map (x, y)" or "the car ended on floor N" is an end
#: state, which no relative measure can prove.
ABSOLUTE_OPS = ("distance_to", "angle_to")

# The bounded identifier grammar the registry already uses for capability ids
# and semantic identifiers.
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
_IDENTIFIER_MAX = 96

_REQUIRED_BOOLEANS = ("actuates", "requires_safe_stop", "cancellable", "idempotent")
_REQUIRED_KEYS = frozenset((*_REQUIRED_BOOLEANS, "safety_class"))
#: Optional keys added in flyto-core 2.36.0. A provider that must also load on
#: an older core (whose closed schema rejects them) feature-detects them with
#: ``"role" in core.capability_contract.OPTIONAL_FIELDS`` before sending them.
#: Each appears in the normalized contract only when declared, so a contract
#: that declares none of them normalizes, and hashes, exactly as on 2.35.
OPTIONAL_FIELDS = frozenset(("role", "artifacts", "recovery", "expected_duration_ms"))
_OPTIONAL_KEYS = frozenset(("schema", "effects", "requires", "evidence")) | OPTIONAL_FIELDS
_IDENTIFIER_LISTS = ("effects", "requires")
_IDENTIFIER_LIST_MAX = 16
_EVIDENCE_MAX = 8

_EVIDENCE_REQUIRED = frozenset(("kind", "observe", "phases", "measure", "expect", "tolerance"))
_EVIDENCE_OPTIONAL = frozenset(("settle",))
_MEASURE_KEYS = frozenset(("op", "fields"))
_MEASURE_OPTIONAL = frozenset(("heading_field", "frame"))
_TOLERANCE_KEYS = frozenset(("absolute", "relative"))
_SETTLE_KEYS = frozenset(("max_drift",))

_NUMERIC_PARAM_TYPES = frozenset(("number", "integer"))

#: Roles a capability may play for a host. ``safe_stop`` marks the capability
#: that stops the resource: a host issues it (or the adapter's own safe stop)
#: without approval queues, and it must itself be uncancellable, idempotent and
#: need no further safe stop.
ROLES = ("safe_stop",)

#: Upper bound of ``expected_duration_ms`` (one hour).
EXPECTED_DURATION_MS_MAX = 3_600_000

#: Upper bound of an artifact's declared ``max_bytes`` (20 MiB).
ARTIFACT_MAX_BYTES = 20 * 1024 * 1024
_ARTIFACTS_MAX = 8
_ARTIFACT_KEYS = frozenset(("kind", "media_types", "max_bytes"))
_MEDIA_TYPES_MAX = 8
# type/subtype, lower case, no parameters: what a host compares, not a header.
_MEDIA_TYPE = re.compile(r"^[a-z0-9][a-z0-9!#$&^_.+-]{0,63}/[a-z0-9][a-z0-9!#$&^_.+-]{0,63}$")
# The host's recovery report (2.36.0): substitutes, the observation that
# explains a failure, and planner-facing text.
_RECOVERY_REPORT_KEYS = frozenset(("capabilities", "observe", "guidance"))
_RECOVERY_CAPABILITIES_MAX = 8
_GUIDANCE_MAX = 500

#: Stop-reason families a recovery declaration may answer (2.39.0).
#: ``obstruction``: something stood in the way of the call. ``no_passage``: no
#: way through to the requested end state exists. ``stopped_short``: the call
#: ended before it delivered the requested amount.
RECOVERY_STOP_FAMILIES = ("obstruction", "no_passage", "stopped_short")
#: What a way round must still reach (2.39.0).
RECOVERY_PRESERVES = ("destination", "target")
#: Where a way round may run (2.39.0): only the resource whose call stopped.
RECOVERY_RESOURCE_SCOPES = ("same_resource",)
#: Grammar of a semantic role named in ``alternatives`` and ``fills``. A role
#: is a meaning ("reposition"), never a capability id, so it shares the
#: identifier grammar but is checked under its own name.
RECOVERY_ROLE_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
#: At most this many roles in ``alternatives`` and in ``fills``.
RECOVERY_ROLES_MAX = 8
# The recovery semantics (2.39.0): what a stopped call may be worked round
# with, stated as roles, and which roles this capability itself fills.
_RECOVERY_SEMANTIC_KEYS = frozenset(("on", "alternatives", "preserves", "resource_scope", "fills"))
#: Every key a ``recovery`` block may hold. A provider that must also load on
#: an older core (whose closed schema rejects the semantic keys and requires
#: ``capabilities``) feature-detects them with
#: ``"fills" in core.capability_contract.RECOVERY_FIELDS`` (exists from 2.39.0).
RECOVERY_FIELDS = _RECOVERY_REPORT_KEYS | _RECOVERY_SEMANTIC_KEYS

_TWO_PI = 2.0 * math.pi


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _is_number(value: Any) -> bool:
    """A finite int or float. ``bool`` is excluded: ``True`` is not a quantity."""
    return (
        type(value) in (int, float)
        and math.isfinite(value)
    )


def _check_identifier(value: Any, where: str) -> str:
    if type(value) is not str or not value:
        raise ValueError(f"{where} must be a non-empty string identifier")
    if len(value) > _IDENTIFIER_MAX:
        raise ValueError(f"{where} is longer than {_IDENTIFIER_MAX} characters")
    if not _IDENTIFIER.fullmatch(value):
        raise ValueError(
            f"{where} {value!r} does not match the identifier grammar "
            "^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$"
        )
    return value


def _check_identifier_list(value: Any, where: str, minimum: int, maximum: int) -> List[str]:
    if type(value) is not list:
        raise ValueError(f"{where} must be a list of identifiers")
    if not minimum <= len(value) <= maximum:
        raise ValueError(f"{where} must hold {minimum}..{maximum} identifiers, got {len(value)}")
    items = [_check_identifier(item, f"{where}[{index}]") for index, item in enumerate(value)]
    if len(set(items)) != len(items):
        raise ValueError(f"{where} contains duplicate identifiers")
    return items


def _check_keys(value: Mapping[str, Any], required: frozenset, optional: frozenset, where: str) -> None:
    keys = set(value)
    unknown = keys - required - optional
    if unknown:
        raise ValueError(f"{where} has unknown keys: {', '.join(sorted(map(str, unknown)))}")
    missing = required - keys
    if missing:
        raise ValueError(f"{where} is missing required keys: {', '.join(sorted(missing))}")


def _check_non_negative(value: Any, where: str) -> float:
    if not _is_number(value) or value < 0:
        raise ValueError(f"{where} must be a finite non-negative number")
    return value


def _check_numeric_argument(argument: Any, params_schema: Optional[Mapping[str, Any]], where: str) -> str:
    """A parameter name that ``params_schema`` (when given) declares as a number."""
    if type(argument) is not str or not argument:
        raise ValueError(f"{where} must be a parameter name")
    if params_schema is not None:
        definition = params_schema.get(argument)
        if type(definition) is not dict:
            raise ValueError(f"{where} {argument!r} is not a key in params_schema")
        if definition.get("type") not in _NUMERIC_PARAM_TYPES:
            raise ValueError(f"{where} {argument!r} must name a number or integer parameter")
    return argument


def _check_absolute_expect(
    expect: Any,
    op: str,
    fields: List[str],
    params_schema: Optional[Mapping[str, Any]],
    where: str,
) -> Dict[str, Any]:
    """The target of an absolute op, read from the call's arguments.

    ``distance_to`` takes ``{"arguments": {field: parameter, ...}}`` naming a
    parameter for every measured field. ``angle_to`` takes ``{"argument":
    parameter}``, plus ``"optional": true`` when the call may leave the target
    out (the check then has nothing to compare and holds).
    """
    if op == "distance_to":
        if type(expect) is not dict or set(expect) != {"arguments"}:
            raise ValueError(f"{where}.expect must be {{'arguments': {{field: parameter, ...}}}} for op distance_to")
        targets = expect["arguments"]
        if type(targets) is not dict or set(targets) != set(fields):
            raise ValueError(f"{where}.expect.arguments must name a parameter for exactly the measured fields")
        return {
            "arguments": {
                field: _check_numeric_argument(targets[field], params_schema, f"{where}.expect.arguments.{field}")
                for field in fields
            }
        }
    # angle_to
    if type(expect) is not dict or set(expect) not in ({"argument"}, {"argument", "optional"}):
        raise ValueError(f"{where}.expect must be {{'argument': parameter[, 'optional': bool]}} for op angle_to")
    argument = _check_numeric_argument(expect["argument"], params_schema, f"{where}.expect.argument")
    optional = expect.get("optional", False)
    if type(optional) is not bool:
        raise ValueError(f"{where}.expect.optional must be a bool")
    normalized: Dict[str, Any] = {"argument": argument}
    if optional:
        if params_schema is not None and params_schema[argument].get("required") is True:
            raise ValueError(f"{where}.expect.optional contradicts required parameter {argument!r}")
        normalized["optional"] = True
    return normalized


def validate_evidence(
    evidence: Any,
    params_schema: Optional[Mapping[str, Any]] = None,
    where: str = "evidence",
) -> Dict[str, Any]:
    """Validate one evidence spec and return a detached, normalized copy.

    ``params_schema`` is consulted only for ``expect.argument``; pass ``None``
    to skip that check (as :func:`judge` does, since it has no schema).
    """
    if type(evidence) is not dict:
        raise ValueError(f"{where} must be a mapping")
    _check_keys(evidence, _EVIDENCE_REQUIRED, _EVIDENCE_OPTIONAL, where)

    kind = _check_identifier(evidence["kind"], f"{where}.kind")
    observe = _check_identifier(evidence["observe"], f"{where}.observe")

    phases = evidence["phases"]
    if type(phases) is not list or not phases:
        raise ValueError(f"{where}.phases must be a non-empty list")
    if any(type(phase) is not str or phase not in PHASES for phase in phases):
        raise ValueError(f"{where}.phases may only contain {', '.join(PHASES)}")
    if len(set(phases)) != len(phases):
        raise ValueError(f"{where}.phases contains duplicates")
    if list(phases) != [phase for phase in PHASES if phase in phases]:
        raise ValueError(f"{where}.phases must be ordered before, after, settled")

    measure = evidence["measure"]
    if type(measure) is not dict:
        raise ValueError(f"{where}.measure must be a mapping")
    _check_keys(measure, _MEASURE_KEYS, _MEASURE_OPTIONAL, f"{where}.measure")
    op = measure["op"]
    if type(op) is not str or op not in MEASURE_OPS:
        raise ValueError(f"{where}.measure.op must be one of {', '.join(MEASURE_OPS)}")
    absolute = op in ABSOLUTE_OPS
    if absolute:
        # An absolute target is compared with the last declared phase alone;
        # `before` is allowed but never read.
        if "after" not in phases:
            raise ValueError(f"{where}.phases must include after")
    elif "before" not in phases or "after" not in phases:
        raise ValueError(f"{where}.phases must include before and after")
    fields = _check_identifier_list(measure["fields"], f"{where}.measure.fields", 1, 3)
    normalized_measure: Dict[str, Any] = {"op": op, "fields": fields}
    if op == "along":
        if len(fields) != 2:
            raise ValueError(f"{where}.measure.op along takes exactly two position fields")
        if "heading_field" not in measure:
            raise ValueError(f"{where}.measure.op along requires heading_field")
        heading = _check_identifier(measure["heading_field"], f"{where}.measure.heading_field")
        if heading in fields:
            raise ValueError(f"{where}.measure.heading_field must not be one of the position fields")
        normalized_measure["heading_field"] = heading
    else:
        if "heading_field" in measure:
            raise ValueError(f"{where}.measure.heading_field is only allowed with op along")
        if op not in ("distance", "distance_to") and len(fields) != 1:
            raise ValueError(f"{where}.measure.op {op} takes exactly one field")
    if "frame" in measure:
        normalized_measure["frame"] = _check_identifier(measure["frame"], f"{where}.measure.frame")

    expect = evidence["expect"]
    normalized_expect: Dict[str, Any]
    if absolute:
        normalized_expect = _check_absolute_expect(expect, op, fields, params_schema, where)
    elif (
        type(expect) is not dict
        or set(expect) not in ({"argument"}, {"argument", "scale"}, {"value"})
    ):
        raise ValueError(
            f"{where}.expect must be exactly one of {{'argument': name[, 'scale': number]}} "
            "or {'value': number}"
        )
    elif "argument" in expect:
        argument = _check_numeric_argument(expect["argument"], params_schema, f"{where}.expect.argument")
        scale = expect.get("scale", 1)
        if not _is_number(scale) or scale == 0:
            raise ValueError(f"{where}.expect.scale must be a finite non-zero number")
        normalized_expect = {"argument": argument, "scale": scale}
    else:
        value = expect["value"]
        if not _is_number(value):
            raise ValueError(f"{where}.expect.value must be a finite number")
        normalized_expect = {"value": value}

    tolerance = evidence["tolerance"]
    if type(tolerance) is not dict or not tolerance:
        raise ValueError(f"{where}.tolerance must be a mapping with absolute and/or relative")
    _check_keys(tolerance, frozenset(), _TOLERANCE_KEYS, f"{where}.tolerance")
    normalized_tolerance = {
        key: _check_non_negative(tolerance.get(key, 0), f"{where}.tolerance.{key}")
        for key in ("absolute", "relative")
    }
    if absolute and normalized_tolerance["relative"] != 0:
        # The target is a place, not an amount: there is nothing for a
        # fraction to be a fraction of.
        raise ValueError(f"{where}.tolerance.relative must be 0 for op {op}; use absolute")

    normalized: Dict[str, Any] = {
        "kind": kind,
        "observe": observe,
        "phases": list(phases),
        "measure": normalized_measure,
        "expect": normalized_expect,
        "tolerance": normalized_tolerance,
    }

    if "settle" in evidence:
        settle = evidence["settle"]
        if type(settle) is not dict:
            raise ValueError(f"{where}.settle must be a mapping")
        _check_keys(settle, _SETTLE_KEYS, frozenset(), f"{where}.settle")
        if "settled" not in phases:
            raise ValueError(f"{where}.settle requires 'settled' in phases")
        normalized["settle"] = {
            "max_drift": _check_non_negative(settle["max_drift"], f"{where}.settle.max_drift")
        }
    return normalized


def _check_params_schema(params_schema: Any, actuates: bool) -> Mapping[str, Any]:
    if params_schema is None:
        params_schema = {}
    if type(params_schema) is not dict:
        raise ValueError("params_schema must be a mapping when a contract is declared")
    if actuates:
        for name, definition in params_schema.items():
            if type(definition) is not dict or definition.get("type") not in _NUMERIC_PARAM_TYPES:
                continue
            low, high = definition.get("min"), definition.get("max")
            if not _is_number(low) or not _is_number(high):
                raise ValueError(
                    f"params_schema.{name}: a numeric parameter of an actuating contract "
                    "must declare finite 'min' and 'max'"
                )
            if low > high:
                raise ValueError(f"params_schema.{name}: 'min' is greater than 'max'")
    try:
        # The schema travels beside the contract in the capability manifest,
        # whose hash is taken over canonical JSON. A value JSON cannot carry
        # would break every manifest build, not just this module's.
        json.dumps(params_schema, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"params_schema must be JSON-serializable when a contract is declared: {exc}") from None
    return params_schema


def _check_artifacts(value: Any) -> List[Dict[str, Any]]:
    where = "contract.artifacts"
    if type(value) is not list or not 1 <= len(value) <= _ARTIFACTS_MAX:
        raise ValueError(f"{where} must be a list of 1..{_ARTIFACTS_MAX} artifact declarations")
    normalized: List[Dict[str, Any]] = []
    for index, item in enumerate(value):
        here = f"{where}[{index}]"
        if type(item) is not dict:
            raise ValueError(f"{here} must be a mapping")
        _check_keys(item, _ARTIFACT_KEYS, frozenset(), here)
        kind = _check_identifier(item["kind"], f"{here}.kind")
        media_types = item["media_types"]
        if type(media_types) is not list or not 1 <= len(media_types) <= _MEDIA_TYPES_MAX:
            raise ValueError(f"{here}.media_types must be a list of 1..{_MEDIA_TYPES_MAX} media types")
        for position, media_type in enumerate(media_types):
            if type(media_type) is not str or not _MEDIA_TYPE.fullmatch(media_type):
                raise ValueError(
                    f"{here}.media_types[{position}] must be a lower-case type/subtype media type"
                )
        if len(set(media_types)) != len(media_types):
            raise ValueError(f"{here}.media_types contains duplicates")
        max_bytes = item["max_bytes"]
        if type(max_bytes) is not int or not 1 <= max_bytes <= ARTIFACT_MAX_BYTES:
            raise ValueError(f"{here}.max_bytes must be an integer in 1..{ARTIFACT_MAX_BYTES}")
        normalized.append({"kind": kind, "media_types": list(media_types), "max_bytes": max_bytes})
    kinds = [item["kind"] for item in normalized]
    if len(set(kinds)) != len(kinds):
        raise ValueError(f"{where} declares the same kind twice")
    return normalized


def _check_roles(value: Any, where: str) -> List[str]:
    if type(value) is not list:
        raise ValueError(f"{where} must be a list of roles")
    if not 1 <= len(value) <= RECOVERY_ROLES_MAX:
        raise ValueError(f"{where} must hold 1..{RECOVERY_ROLES_MAX} roles, got {len(value)}")
    for index, item in enumerate(value):
        if type(item) is not str or len(item) > _IDENTIFIER_MAX or not RECOVERY_ROLE_PATTERN.fullmatch(item):
            raise ValueError(
                f"{where}[{index}] must be a role of at most {_IDENTIFIER_MAX} characters "
                f"matching {RECOVERY_ROLE_PATTERN.pattern}"
            )
    if len(set(value)) != len(value):
        raise ValueError(f"{where} names a role twice")
    return list(value)


def _check_closed_list(value: Any, allowed: tuple, where: str) -> List[str]:
    if type(value) is not list or not 1 <= len(value) <= len(allowed):
        raise ValueError(f"{where} must be a list of 1..{len(allowed)} of {', '.join(allowed)}")
    if any(type(item) is not str or item not in allowed for item in value):
        raise ValueError(f"{where} may name only {', '.join(allowed)}")
    if len(set(value)) != len(value):
        raise ValueError(f"{where} contains duplicates")
    return list(value)


def _check_recovery_report(value: Mapping[str, Any], where: str, normalized: Dict[str, Any]) -> None:
    """The host's recovery report keys (2.36.0), into ``normalized`` when declared."""
    if "capabilities" in value:
        normalized["capabilities"] = _check_identifier_list(
            value["capabilities"], f"{where}.capabilities", 1, _RECOVERY_CAPABILITIES_MAX
        )
    if "observe" in value:
        normalized["observe"] = _check_identifier(value["observe"], f"{where}.observe")
    if "guidance" in value:
        guidance = value["guidance"]
        if type(guidance) is not str or not guidance.strip() or len(guidance) > _GUIDANCE_MAX:
            raise ValueError(f"{where}.guidance must be non-empty text of at most {_GUIDANCE_MAX} characters")
        normalized["guidance"] = guidance


def _check_recovery_semantics(value: Mapping[str, Any], where: str, normalized: Dict[str, Any]) -> None:
    """The recovery semantics (2.39.0), into ``normalized`` when declared.

    A way round is declared whole or not at all: ``on`` and ``alternatives``
    come together, and with them ``resource_scope``; ``preserves`` and
    ``resource_scope`` describe a way round and mean nothing without one.
    """
    if "on" in value:
        normalized["on"] = _check_closed_list(value["on"], RECOVERY_STOP_FAMILIES, f"{where}.on")
    if "alternatives" in value:
        normalized["alternatives"] = _check_roles(value["alternatives"], f"{where}.alternatives")
    if "preserves" in value:
        normalized["preserves"] = _check_closed_list(value["preserves"], RECOVERY_PRESERVES, f"{where}.preserves")
    if "resource_scope" in value:
        scope = value["resource_scope"]
        if type(scope) is not str or scope not in RECOVERY_RESOURCE_SCOPES:
            raise ValueError(f"{where}.resource_scope must be one of {', '.join(RECOVERY_RESOURCE_SCOPES)}")
        normalized["resource_scope"] = scope
    if "fills" in value:
        normalized["fills"] = _check_roles(value["fills"], f"{where}.fills")
    recovers = "alternatives" in normalized
    if ("on" in normalized) != recovers:
        raise ValueError(f"{where}.on and {where}.alternatives are declared together")
    if recovers and "resource_scope" not in normalized:
        raise ValueError(f"{where}.alternatives requires {where}.resource_scope")
    if not recovers and ("preserves" in normalized or "resource_scope" in normalized):
        raise ValueError(f"{where}.preserves and {where}.resource_scope describe a way round; declare its alternatives")


def _check_recovery(value: Any) -> Dict[str, Any]:
    """The ``recovery`` block: the host's report, the recovery semantics, or both.

    Every key is optional, but the block must state something a host can act
    on: substitute ``capabilities``, a way round (``alternatives``), or roles
    the capability ``fills``. Keys appear in the normalized block only when
    declared, so a 2.36 block normalizes and hashes exactly as before.
    """
    where = "contract.recovery"
    if type(value) is not dict:
        raise ValueError(f"{where} must be a mapping")
    _check_keys(value, frozenset(), RECOVERY_FIELDS, where)
    normalized: Dict[str, Any] = {}
    _check_recovery_report(value, where, normalized)
    _check_recovery_semantics(value, where, normalized)
    if not {"capabilities", "alternatives", "fills"} & set(normalized):
        raise ValueError(f"{where} must declare capabilities, alternatives or fills")
    return normalized


def _check_optional_fields(contract: Mapping[str, Any], normalized: Dict[str, Any]) -> None:
    """Validate the 2.36.0 optional keys into ``normalized``, only when declared."""
    if "role" in contract:
        role = contract["role"]
        if type(role) is not str or role not in ROLES:
            raise ValueError(f"contract.role must be one of {', '.join(ROLES)}")
        if role == "safe_stop" and (
            normalized["cancellable"] or normalized["requires_safe_stop"] or not normalized["idempotent"]
        ):
            raise ValueError(
                "contract.role safe_stop requires cancellable: false, "
                "requires_safe_stop: false and idempotent: true"
            )
        normalized["role"] = role
    if "artifacts" in contract:
        normalized["artifacts"] = _check_artifacts(contract["artifacts"])
    if "recovery" in contract:
        normalized["recovery"] = _check_recovery(contract["recovery"])
    if "expected_duration_ms" in contract:
        duration = contract["expected_duration_ms"]
        if type(duration) is not int or not 1 <= duration <= EXPECTED_DURATION_MS_MAX:
            raise ValueError(
                f"contract.expected_duration_ms must be an integer in 1..{EXPECTED_DURATION_MS_MAX}"
            )
        normalized["expected_duration_ms"] = duration


def validate_contract(contract: Any, params_schema: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Validate a capability contract and return its normalized form.

    The returned dict is built from fresh plain containers (nothing aliases
    the caller's objects) and always carries ``schema``, ``effects``,
    ``requires`` and ``evidence``, so every consumer reads one shape. The
    optional ``role``, ``artifacts``, ``recovery`` and ``expected_duration_ms``
    appear only when declared.

    Raises:
        ValueError: with a message naming the offending key on any violation.
    """
    if type(contract) is not dict:
        raise ValueError("contract must be a mapping")
    _check_keys(contract, _REQUIRED_KEYS, _OPTIONAL_KEYS, "contract")

    if "schema" in contract and contract["schema"] != CONTRACT_SCHEMA:
        raise ValueError(f"contract.schema must be {CONTRACT_SCHEMA!r}")

    for key in _REQUIRED_BOOLEANS:
        if type(contract[key]) is not bool:
            raise ValueError(f"contract.{key} must be a bool")

    safety_class = contract["safety_class"]
    if type(safety_class) is not str or safety_class not in SAFETY_CLASSES:
        raise ValueError(f"contract.safety_class must be one of {', '.join(SAFETY_CLASSES)}")
    if safety_class == "read_only" and contract["actuates"]:
        raise ValueError("contract.safety_class read_only contradicts actuates: true")

    schema = _check_params_schema(params_schema, contract["actuates"])

    normalized: Dict[str, Any] = {
        "schema": CONTRACT_SCHEMA,
        "actuates": contract["actuates"],
        "safety_class": safety_class,
        "requires_safe_stop": contract["requires_safe_stop"],
        "cancellable": contract["cancellable"],
        "idempotent": contract["idempotent"],
    }
    for key in _IDENTIFIER_LISTS:
        normalized[key] = _check_identifier_list(
            contract.get(key, []), f"contract.{key}", 0, _IDENTIFIER_LIST_MAX
        )

    evidence = contract.get("evidence", [])
    if type(evidence) is not list or len(evidence) > _EVIDENCE_MAX:
        raise ValueError(f"contract.evidence must be a list of at most {_EVIDENCE_MAX} items")
    normalized["evidence"] = [
        validate_evidence(item, schema, f"contract.evidence[{index}]")
        for index, item in enumerate(evidence)
    ]
    _check_optional_fields(contract, normalized)
    return normalized


# ---------------------------------------------------------------------------
# Judgement
# ---------------------------------------------------------------------------


def wrap_angle(angle: float) -> float:
    """Wrap radians into the half-open interval (-pi, pi].

    ``math.remainder`` gives ``angle - 2*pi*n`` with ``n`` the nearest integer
    to ``angle / (2*pi)`` (ties to even), which lies in [-pi, pi]. The single
    value -pi is then moved to +pi so the interval is half-open.
    """
    wrapped = math.remainder(angle, _TWO_PI)
    if wrapped <= -math.pi:
        wrapped += _TWO_PI
    return wrapped


def _euclidean(fields: List[str], start: Mapping[str, float], end: Mapping[str, float]) -> float:
    return math.sqrt(sum((end[field] - start[field]) ** 2 for field in fields))


def _measure(measure: Mapping[str, Any], start: Mapping[str, float], end: Mapping[str, float]) -> float:
    """The measured quantity from phase ``start`` to phase ``end``."""
    op, fields = measure["op"], measure["fields"]
    if op == "distance":
        return _euclidean(fields, start, end)
    if op == "along":
        # Signed displacement projected onto the heading held at `start`.
        heading = start[measure["heading_field"]]
        x, y = fields
        return (end[x] - start[x]) * math.cos(heading) + (end[y] - start[y]) * math.sin(heading)
    difference = end[fields[0]] - start[fields[0]]
    if op == "delta":
        return difference
    if op == "angle_delta":
        return wrap_angle(difference)
    return abs(wrap_angle(difference))  # abs_angle_delta


def _drift(measure: Mapping[str, Any], after: Mapping[str, float], settled: Mapping[str, float]) -> float:
    """How far the observation still moved between ``after`` and ``settled``.

    Always a magnitude: euclidean over the fields for ``distance``,
    ``along`` and ``distance_to``, ``|delta|`` for ``delta``,
    ``|wrap(delta)|`` for angle ops (``angle_to`` included).
    """
    op, fields = measure["op"], measure["fields"]
    if op in ("distance", "along", "distance_to"):
        return _euclidean(fields, after, settled)
    difference = settled[fields[0]] - after[fields[0]]
    return abs(wrap_angle(difference)) if op in ANGLE_OPS else abs(difference)


def _not_given(arguments: Any, name: str) -> bool:
    """The call left this argument out (absent, or an explicit null)."""
    return isinstance(arguments, Mapping) and arguments.get(name) is None


def _verdict(
    usable: bool,
    reason: str,
    measured: Optional[float] = None,
    expected: Optional[float] = None,
    allowed: Optional[float] = None,
    settle_drift: Optional[float] = None,
) -> Dict[str, Any]:
    return {
        "usable": usable,
        "measured": measured,
        "expected": expected,
        "allowed": allowed,
        "settle_drift": settle_drift,
        "reason": reason,
    }


def judge(
    evidence_spec: Mapping[str, Any],
    arguments: Mapping[str, Any],
    observations: Mapping[str, Any],
) -> Dict[str, Any]:
    """Decide whether reported observations prove one evidence spec.

    Args:
        evidence_spec: one item of a contract's ``evidence`` list.
        arguments: the arguments the capability was invoked with.
        observations: ``{"before": {...}, "after": {...}, "settled": {...}}``,
            each phase a mapping of field name to number (and ``frame``, a
            string, when the spec's measure names one).

    Returns:
        ``{"usable", "measured", "expected", "allowed", "settle_drift",
        "reason"}``. ``measured``/``expected``/``allowed`` are ``None`` when
        they could not be computed; ``settle_drift`` is ``None`` when the spec
        declares no ``settle``.

    Raises:
        ValueError: if ``evidence_spec`` itself is malformed. Missing or
        non-numeric *observations* or *arguments* are never an exception —
        they are an unusable verdict with a reason.

    The arithmetic is specified in ``docs/CAPABILITY_CONTRACT.md``.
    """
    spec = validate_evidence(dict(evidence_spec) if type(evidence_spec) is not dict else evidence_spec)
    measure = spec["measure"]
    op = measure["op"]
    fields = measure["fields"]
    expect = spec["expect"]

    if op == "angle_to" and expect.get("optional") and _not_given(arguments, expect["argument"]):
        # The caller asked for no target, so there is nothing to compare.
        return _verdict(True, f"argument {expect['argument']!r} was not given; no target to check")

    if not isinstance(observations, Mapping):
        return _verdict(False, "observations must be a mapping of phases")
    frame = measure.get("frame")
    phases: Dict[str, Dict[str, float]] = {}
    for phase in spec["phases"]:
        values = observations.get(phase)
        if not isinstance(values, Mapping):
            return _verdict(False, f"phase {phase!r} was not observed")
        if frame is not None and values.get("frame") != frame:
            return _verdict(False, f"phase {phase!r} is not in frame {frame!r}")
        needed = list(fields)
        if phase == "before" and "heading_field" in measure:
            needed.append(measure["heading_field"])
        for field in needed:
            value = values.get(field)
            if not _is_number(value):
                return _verdict(False, f"phase {phase!r} has no finite numeric field {field!r}")
        phases[phase] = {field: float(values[field]) for field in needed}

    # Measured on the last declared phase: `settled` when the spec lists it,
    # otherwise `after`. A relative op measures from `before` to it.
    last = spec["phases"][-1]
    if op == "distance_to":
        target: Dict[str, float] = {}
        for field in fields:
            name = expect["arguments"][field]
            raw = arguments.get(name) if isinstance(arguments, Mapping) else None
            if not _is_number(raw):
                return _verdict(False, f"argument {name!r} is missing or not a finite number")
            target[field] = float(raw)
        measured = _euclidean(fields, target, phases[last])
        expected = 0.0
    elif "argument" in expect:
        raw = arguments.get(expect["argument"]) if isinstance(arguments, Mapping) else None
        if not _is_number(raw):
            return _verdict(False, f"argument {expect['argument']!r} is missing or not a finite number")
        if op == "angle_to":
            measured = phases[last][fields[0]]
            expected = float(raw)
        else:
            expected = float(expect["scale"]) * float(raw)
            if op == "abs_angle_delta":
                expected = abs(expected)
            measured = _measure(measure, phases["before"], phases[last])
    else:
        expected = float(expect["value"])
        measured = _measure(measure, phases["before"], phases[last])

    tolerance = spec["tolerance"]
    allowed = max(float(tolerance["absolute"]), float(tolerance["relative"]) * abs(expected))
    error = abs(wrap_angle(measured - expected)) if op in ANGLE_OPS else abs(measured - expected)

    settle_drift: Optional[float] = None
    if "settle" in spec:
        settle_drift = _drift(measure, phases["after"], phases["settled"])

    if error > allowed:
        return _verdict(
            False,
            f"measured {measured:.6g}, expected {expected:.6g}, error {error:.6g} exceeds allowed {allowed:.6g}",
            measured, expected, allowed, settle_drift,
        )
    if settle_drift is not None and settle_drift > spec["settle"]["max_drift"]:
        return _verdict(
            False,
            f"drifted {settle_drift:.6g} after stopping, exceeds max_drift {spec['settle']['max_drift']:.6g}",
            measured, expected, allowed, settle_drift,
        )
    return _verdict(
        True,
        f"measured {measured:.6g} within {allowed:.6g} of expected {expected:.6g}",
        measured, expected, allowed, settle_drift,
    )
