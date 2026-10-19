# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""The connector pre-check: entitlements, quota and data scope, for every operation.

The provider is the source of truth for its own product. A customer can use
the provider directly, without Flyto2, and the provider's own access control
always applies underneath. This pre-check adds Flyto2's collaboration policy
on top: it hides operations the account does not hold and stops a call early.
It never authorizes provider access. Whatever the cached answer said, a
provider refusal of the call is final and comes back as its own typed
failure.

Three facts are read, each from one source:

* **Features and meters** come from the provider, through the pack's
  ``entitlements`` probe: an ordinary observe operation whose answer is mapped
  to a set of feature keys and ``meter -> remaining`` through declared
  JSONPaths. The answer is cached per credential for the pack's ``max_age_s``.
  A read may use the cache; a write, a quota-consuming call, or any call after
  a provider error reads again. A failed or misshapen read drops the cached
  answer and refuses every feature-gated operation
  (``PROVIDER_ENTITLEMENT_UNREADABLE``).
* **Scope grants** come from the caller's execution context
  (``scope_grants: {dimension: [values] | "*"}``). They only narrow what Flyto2
  runs for a member; they never widen what the provider credential can see.
  A declared dimension with no grant is refused (``SCOPE_GRANT_MISSING``),
  never read as ``"*"``.
* **What an operation needs** comes from its declaration: ``requires.features``,
  ``consumes``, each input's ``scope`` and ``result_scope``.

:func:`admit` is the one gate. ``ConnectorTransport.call`` runs it for every
operation, before the request; :func:`filter_result` runs on the answer.
Nothing here knows any provider or product: the keys are the pack's data.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .jsonpath import WILDCARD, expand, parse

__all__ = [
    "DEFAULT_MAX_AGE_S",
    "EntitlementAnswer",
    "EntitlementCache",
    "PrecheckError",
    "Admission",
    "admit",
    "filter_result",
    "missing_features",
    "needs_entitlements",
    "needs_fresh_read",
    "read_answer",
    "scope_dimensions",
]

#: How long a probe answer may admit a read when the pack does not say.
DEFAULT_MAX_AGE_S = 900
#: The grant value that admits every value of a dimension.
ALL_VALUES = "*"


def _now() -> float:
    return time.monotonic()


class PrecheckError(Exception):
    """A pre-check refusal: a typed code, a message, and the facts that explain it."""

    def __init__(self, code: str, message: str, **details: Any):
        super().__init__(message)
        self.code = code
        self.details = details

    def result(self) -> Dict[str, Any]:
        return {"ok": False, "error": str(self), "error_code": self.code, **self.details}


# -- what an operation needs -----------------------------------------------------------


def missing_features(requires: Any, features: frozenset) -> List[str]:
    """The required feature keys the account does not hold; empty when it holds enough.

    ``requires.features`` is a list (all needed) or ``{"any": [...]}`` (one is
    enough). For ``any``, every listed key is missing when none is held.
    """
    if isinstance(requires, Mapping):
        keys = list(requires.get("any") or [])
        return [] if not keys or any(key in features for key in keys) else keys
    return [key for key in (requires or []) if key not in features]


def _required(op: Mapping[str, Any]) -> Any:
    return (op.get("requires") or {}).get("features") or []


def needs_entitlements(op: Mapping[str, Any]) -> bool:
    """Whether the operation is feature-gated or consumes a meter, so it needs the probe."""
    return bool(_required(op)) or op.get("consumes") is not None


def needs_fresh_read(op: Mapping[str, Any]) -> bool:
    """A write or a quota-consuming call may not be admitted by a cached answer."""
    return op.get("consequence") != "observe" or op.get("consumes") is not None


def scope_dimensions(op: Mapping[str, Any]) -> List[str]:
    """Every scope dimension the operation's inputs or result are split by."""
    dims = {spec["scope"] for spec in op["inputs"].values() if spec.get("scope")}
    if op.get("result_scope"):
        dims.add(op["result_scope"]["dimension"])
    return sorted(dims)


# -- the probe answer -------------------------------------------------------------------


@dataclass(frozen=True)
class EntitlementAnswer:
    """What the provider says one credential holds."""

    features: frozenset
    meters: Mapping[str, int]


def _unreadable(message: str) -> PrecheckError:
    return PrecheckError("PROVIDER_ENTITLEMENT_UNREADABLE", f"the provider's entitlement answer is unreadable: {message}")


def _container_paths(steps: Tuple[Any, ...], document: Any) -> List[Tuple[Any, ...]]:
    """Where the lists under a path's last wildcard sit in ``document``."""
    last = max(i for i, step in enumerate(steps) if step is WILDCARD)
    return list(expand(steps[:last], document))


def _at(document: Any, path: Tuple[Any, ...]) -> Any:
    for key in path:
        document = document[key]
    return document


def read_answer(declaration: Mapping[str, Any], body: Any) -> EntitlementAnswer:
    """Map a probe body to features and meters, or refuse it as outside its shape.

    The features path names a list of feature keys (its last step is ``[*]``,
    or the path names the list itself). A key the pack does not declare is
    ignored: no operation can require it. Every declared meter must be present
    as a non-negative integer.
    """
    steps = parse(declaration["features"]["path"])
    if WILDCARD in steps:
        containers = _container_paths(steps, body)
        if not containers:
            raise _unreadable("the features list is absent")
        for container in containers:
            if not isinstance(_at(body, container), list):
                raise _unreadable("the features are not a list")
        values = [_at(body, path) for path in expand(steps, body)]
    else:
        listed = [_at(body, path) for path in expand(steps, body)]
        if len(listed) != 1 or not isinstance(listed[0], list):
            raise _unreadable("the features are not a list")
        values = listed[0]
    if any(type(value) is not str for value in values):
        raise _unreadable("a feature is not a key")
    declared = set(declaration["features"]["keys"])
    features = frozenset(value for value in values if value in declared)

    meters: Dict[str, int] = {}
    for name, path in declaration["meters"].items():
        found = [_at(body, at) for at in expand(parse(path), body)]
        if len(found) != 1 or type(found[0]) is not int or found[0] < 0:
            raise _unreadable(f"meter {name} is not a remaining amount")
        meters[name] = found[0]
    return EntitlementAnswer(features=features, meters=meters)


@dataclass
class _Entry:
    answer: EntitlementAnswer
    read_at: float


@dataclass
class EntitlementCache:
    """Probe answers per credential, each admitting reads for a bounded time.

    A key is a digest of the credential name and value, so two Spaces with two
    credentials for one pack never share an answer, and no value is kept.
    """

    max_age_s: int
    _entries: Dict[str, _Entry] = field(default_factory=dict)
    _after_error: set = field(default_factory=set)

    @staticmethod
    def key(credential: str, value: Any) -> str:
        text = json.dumps([credential, value], sort_keys=True, default=str)
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def fresh(self, key: str) -> Optional[EntitlementAnswer]:
        """The cached answer when it may still admit a read."""
        entry = self._entries.get(key)
        if entry is None or key in self._after_error or _now() - entry.read_at >= self.max_age_s:
            return None
        return entry.answer

    def store(self, key: str, answer: EntitlementAnswer) -> None:
        self._entries[key] = _Entry(answer, _now())
        self._after_error.discard(key)

    def drop(self, key: str) -> None:
        """A failed read shortens the grant: the old answer admits nothing more."""
        self._entries.pop(key, None)

    def provider_error(self, key: str) -> None:
        """The next call on this credential reads the probe again."""
        self._after_error.add(key)

    def clear(self) -> None:
        self._entries.clear()
        self._after_error.clear()


# -- scope -----------------------------------------------------------------------------


def _grant(grants: Any, dimension: str) -> Any:
    """The allowed values for one dimension: ``"*"`` or a frozenset; refuses when there is none."""
    value = grants.get(dimension) if isinstance(grants, Mapping) else None
    if value == ALL_VALUES:
        return ALL_VALUES
    if isinstance(value, (list, tuple)) and all(type(item) is str for item in value):
        return frozenset(value)
    raise PrecheckError("SCOPE_GRANT_MISSING", f"no scope grant for dimension {dimension}; nothing is assumed",
                      dimension=dimension)


def _scalar(value: Any) -> Optional[str]:
    if type(value) is str:
        return value
    if type(value) is int:
        return str(value)
    return None


def _inside(value: Any, allowed: Any) -> bool:
    return allowed == ALL_VALUES or value in allowed


def _check_inputs(op: Mapping[str, Any], params: Mapping[str, Any], grants: Mapping[str, Any]) -> None:
    for name, spec in op["inputs"].items():
        dimension = spec.get("scope")
        if not dimension or params.get(name) is None:
            continue
        allowed = grants[dimension]
        raw = params[name]
        values = raw if isinstance(raw, list) else [raw]
        for value in values:
            text = _scalar(value)
            if text is None or not _inside(text, allowed):
                raise PrecheckError("OUT_OF_SCOPE", f"input {name} is outside the {dimension} scope granted here",
                                  dimension=dimension, input=name)


# -- the gate --------------------------------------------------------------------------


@dataclass(frozen=True)
class Admission:
    """What the gate admitted the call on; it becomes the result's ``precheck`` metadata."""

    features: Tuple[str, ...]
    entitlements: str  # "provider", "cache" or "not_required"
    grants: Mapping[str, Any]
    meter: Optional[Mapping[str, Any]] = None


def admit(op: Mapping[str, Any], params: Mapping[str, Any], scope_grants: Any,
          answer: Optional[EntitlementAnswer], source: str) -> Admission:
    """The one pre-check: features, then data scope, then quota. Raises :class:`PrecheckError`.

    ``answer`` is the probe answer the caller read (or ``None`` when the
    operation needs none) and ``source`` says where it came from.
    """
    required = _required(op)
    if answer is not None:
        missing = missing_features(required, answer.features)
        if missing:
            raise PrecheckError("FEATURE_NOT_ENTITLED",
                              f"the provider account does not hold {', '.join(missing)}",
                              missing_features=missing)
    grants = {dimension: _grant(scope_grants, dimension) for dimension in scope_dimensions(op)}
    _check_inputs(op, params, grants)
    meter = None
    consumes = op.get("consumes")
    if consumes is not None and answer is not None:
        remaining = answer.meters[consumes["meter"]]
        if remaining < consumes["amount"]:
            raise PrecheckError("QUOTA_EXHAUSTED",
                              f"meter {consumes['meter']} has {remaining} remaining; the call uses "
                              f"{consumes['amount']}", meter=consumes["meter"], remaining=remaining,
                              amount=consumes["amount"])
        meter = {"meter": consumes["meter"], "amount": consumes["amount"], "before": remaining}
    features = tuple(required.get("any", ()) if isinstance(required, Mapping) else required)
    return Admission(features=features, entitlements=source if answer is not None else "not_required",
                     grants=grants, meter=meter)


def filter_result(op: Mapping[str, Any], data: Any, grants: Mapping[str, Any]) -> Tuple[Any, Optional[Dict]]:
    """Drop result items outside the grant and count them; refuse a result that does not name its scope.

    ``result_scope.path`` is rooted at the operation's data. The items are the
    elements of the list under its last ``[*]``; the rest of the path names
    each item's scope value. Without a ``[*]`` the whole result is one item,
    and one outside the grant is refused (``OUT_OF_SCOPE``) rather than shown
    as empty.
    """
    declared = op.get("result_scope")
    if not declared:
        return data, None
    dimension = declared["dimension"]
    allowed = grants[dimension]
    steps = parse(declared["path"])
    if WILDCARD not in steps:
        value = _one_value(steps, data)
        if not _inside(value, allowed):
            raise PrecheckError("OUT_OF_SCOPE", f"the result is outside the {dimension} scope granted here",
                              dimension=dimension)
        return data, {"dimension": dimension, "kept": 1, "dropped": 0}
    last = max(i for i, step in enumerate(steps) if step is WILDCARD)
    tail = steps[last + 1:]
    containers = _container_paths(steps, data)
    if not containers:
        raise _result_unreadable()
    out = json.loads(json.dumps(data))
    kept = dropped = 0
    # Deepest containers first, so filtering one list never shifts the path of another.
    for path in sorted(containers, key=len, reverse=True):
        items = _at(out, path)
        if not isinstance(items, list):
            raise _result_unreadable()
        survivors = []
        for item in items:
            if _inside(_one_value(tail, item), allowed):
                survivors.append(item)
            else:
                dropped += 1
        kept += len(survivors)
        if path:
            _at(out, path[:-1])[path[-1]] = survivors
        else:
            out = survivors
    return out, {"dimension": dimension, "kept": kept, "dropped": dropped}


def _one_value(steps: Tuple[Any, ...], item: Any) -> str:
    found = [_at(item, at) for at in expand(steps, item)]
    text = _scalar(found[0]) if len(found) == 1 else None
    if text is None:
        raise _result_unreadable()
    return text


def _result_unreadable() -> PrecheckError:
    return PrecheckError("RESULT_SCOPE_UNREADABLE",
                       "a result item does not name its scope value; the result is withheld, not shown unfiltered")
