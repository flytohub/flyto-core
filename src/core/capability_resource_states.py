# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""The two rules a host applies to ``establishes`` and ``occupies`` (2.41.0).

``core.capability_contract`` admits the keys; this module is the reference
reading of them, so every host decides the same way. Both functions take
contracts already normalized by ``validate_contract``.

* :func:`occupancy_overlaps` -- whether two calls running at once on one
  resource conflict. A call that declares no ``occupies`` holds the whole
  resource; two calls that both declare parts conflict only when they share
  one. A ``safe_stop`` conflicts with nothing: it must be admitted whatever
  runs. Whether a call takes a hold at all (a read may not) is the host's
  grading, not this rule's.
* :func:`unmet_requires` -- the states a call ``requires`` that the states
  earlier completed calls ``establishes`` do not cover, in ``requires`` order.

``tests/core/vectors/capability_contract_resource_states.json`` holds the
vectors (``overlaps``, ``satisfies``) a re-implementing host must reproduce.
"""

from __future__ import annotations

from typing import Any, Iterable, List, Mapping

__all__ = ["occupancy_overlaps", "unmet_requires"]

_SAFE_STOP = "safe_stop"


def occupancy_overlaps(first: Mapping[str, Any], second: Mapping[str, Any]) -> bool:
    """Whether two normalized contracts' calls conflict when they run at once on one resource."""
    if first.get("role") == _SAFE_STOP or second.get("role") == _SAFE_STOP:
        return False
    if "occupies" not in first or "occupies" not in second:
        return True
    return not set(first["occupies"]).isdisjoint(second["occupies"])


def unmet_requires(requires: Iterable[str], established: Iterable[str]) -> List[str]:
    """The required states nothing established, in ``requires`` order."""
    have = set(established)
    return [state for state in requires if state not in have]
