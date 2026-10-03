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
MEASURE_OPS = ("distance", "along", "delta", "angle_delta", "abs_angle_delta")

#: Operators whose measured quantity is an angle in radians.
ANGLE_OPS = ("angle_delta", "abs_angle_delta")

# The bounded identifier grammar the registry already uses for capability ids
# and semantic identifiers.
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
_IDENTIFIER_MAX = 96

_REQUIRED_BOOLEANS = ("actuates", "requires_safe_stop", "cancellable", "idempotent")
_REQUIRED_KEYS = frozenset((*_REQUIRED_BOOLEANS, "safety_class"))
_OPTIONAL_KEYS = frozenset(("schema", "effects", "requires", "evidence"))
_IDENTIFIER_LISTS = ("effects", "requires")
_IDENTIFIER_LIST_MAX = 16
_EVIDENCE_MAX = 8

_EVIDENCE_REQUIRED = frozenset(("kind", "observe", "phases", "measure", "expect", "tolerance"))
_EVIDENCE_OPTIONAL = frozenset(("settle",))
_MEASURE_KEYS = frozenset(("op", "fields"))
_MEASURE_OPTIONAL = frozenset(("heading_field",))
_TOLERANCE_KEYS = frozenset(("absolute", "relative"))
_SETTLE_KEYS = frozenset(("max_drift",))

_NUMERIC_PARAM_TYPES = frozenset(("number", "integer"))

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
    if "before" not in phases or "after" not in phases:
        raise ValueError(f"{where}.phases must include before and after")

    measure = evidence["measure"]
    if type(measure) is not dict:
        raise ValueError(f"{where}.measure must be a mapping")
    _check_keys(measure, _MEASURE_KEYS, _MEASURE_OPTIONAL, f"{where}.measure")
    op = measure["op"]
    if type(op) is not str or op not in MEASURE_OPS:
        raise ValueError(f"{where}.measure.op must be one of {', '.join(MEASURE_OPS)}")
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
        if op != "distance" and len(fields) != 1:
            raise ValueError(f"{where}.measure.op {op} takes exactly one field")

    expect = evidence["expect"]
    if (
        type(expect) is not dict
        or set(expect) not in ({"argument"}, {"argument", "scale"}, {"value"})
    ):
        raise ValueError(
            f"{where}.expect must be exactly one of {{'argument': name[, 'scale': number]}} "
            "or {'value': number}"
        )
    if "argument" in expect:
        argument = expect["argument"]
        if type(argument) is not str or not argument:
            raise ValueError(f"{where}.expect.argument must be a parameter name")
        if params_schema is not None:
            definition = params_schema.get(argument)
            if type(definition) is not dict:
                raise ValueError(f"{where}.expect.argument {argument!r} is not a key in params_schema")
            if definition.get("type") not in _NUMERIC_PARAM_TYPES:
                raise ValueError(
                    f"{where}.expect.argument {argument!r} must name a number or integer parameter"
                )
        scale = expect.get("scale", 1)
        if not _is_number(scale) or scale == 0:
            raise ValueError(f"{where}.expect.scale must be a finite non-zero number")
        normalized_expect: Dict[str, Any] = {"argument": argument, "scale": scale}
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


def validate_contract(contract: Any, params_schema: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Validate a capability contract and return its normalized form.

    The returned dict is built from fresh plain containers (nothing aliases
    the caller's objects) and always carries ``schema``, ``effects``,
    ``requires`` and ``evidence``, so every consumer reads one shape.

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

    Always a magnitude: euclidean over the fields for ``distance`` and
    ``along``, ``|delta|`` for ``delta``, ``|wrap(delta)|`` for angle ops.
    """
    op, fields = measure["op"], measure["fields"]
    if op in ("distance", "along"):
        return _euclidean(fields, after, settled)
    difference = settled[fields[0]] - after[fields[0]]
    return abs(wrap_angle(difference)) if op in ANGLE_OPS else abs(difference)


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
            each phase a mapping of field name to number.

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

    if not isinstance(observations, Mapping):
        return _verdict(False, "observations must be a mapping of phases")
    phases: Dict[str, Dict[str, float]] = {}
    for phase in spec["phases"]:
        values = observations.get(phase)
        if not isinstance(values, Mapping):
            return _verdict(False, f"phase {phase!r} was not observed")
        needed = list(fields)
        if phase == "before" and "heading_field" in measure:
            needed.append(measure["heading_field"])
        for field in needed:
            value = values.get(field)
            if not _is_number(value):
                return _verdict(False, f"phase {phase!r} has no finite numeric field {field!r}")
        phases[phase] = {field: float(values[field]) for field in needed}

    expect = spec["expect"]
    if "argument" in expect:
        raw = arguments.get(expect["argument"]) if isinstance(arguments, Mapping) else None
        if not _is_number(raw):
            return _verdict(False, f"argument {expect['argument']!r} is missing or not a finite number")
        expected = float(expect["scale"]) * float(raw)
        if op == "abs_angle_delta":
            expected = abs(expected)
    else:
        expected = float(expect["value"])

    tolerance = spec["tolerance"]
    allowed = max(float(tolerance["absolute"]), float(tolerance["relative"]) * abs(expected))

    # Measured from `before` to the last declared phase: `settled` when the
    # spec lists it, otherwise `after`.
    last = spec["phases"][-1]
    measured = _measure(measure, phases["before"], phases[last])
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
