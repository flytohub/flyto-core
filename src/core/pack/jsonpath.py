# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""The JSONPath subset a connector declares: ``$``, ``.name``, ``['name']``, ``[n]``, ``[*]``.

A connector names parts of a response — where its scope value is
(``result_scope``), which leaves are sensitive (``sensitive``) — as JSONPath.
Only the subset a declaration needs is accepted, and it is parsed when the
pack is validated, so a path that does not parse refuses the pack instead of
silently naming nothing at run time. Filters, recursive descent, slices and
unions are refused: a sensitive path has to name the same leaves for every
reader, and those features do not.

:func:`parse` returns a tuple of steps — a ``str`` key, an ``int`` index, or
:data:`WILDCARD` — and :func:`expand` turns one parsed path into the concrete
``(key | index, ...)`` tuples it names in a document, which is the path shape
``BaseModule.sensitive_paths`` already uses.
"""

from __future__ import annotations

import re
from typing import Any, Iterator, List, Tuple, Union

__all__ = ["WILDCARD", "JsonPathError", "parse", "expand"]

MAX_PATH_LENGTH = 256
MAX_STEPS = 32


class _Wildcard:
    __slots__ = ()

    def __repr__(self) -> str:
        return "*"


WILDCARD = _Wildcard()
Step = Union[str, int, _Wildcard]

_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")
_INDEX = re.compile(r"\[(0|[1-9][0-9]{0,5})\]")
_QUOTED = re.compile(r"\['((?:[^'\\]|\\.){1,128})'\]")


class JsonPathError(ValueError):
    """The text is not a path in the accepted subset."""


def _step(text: str, at: int) -> Tuple[Step, int]:
    """One step starting at ``at``; returns it and the index after it."""
    if text.startswith(".*", at):
        return WILDCARD, at + 2
    if text.startswith("[*]", at):
        return WILDCARD, at + 3
    if text.startswith(".", at):
        match = _NAME.match(text, at + 1)
        if match is None:
            raise JsonPathError("a '.' must be followed by a name")
        return match.group(0), match.end()
    match = _INDEX.match(text, at)
    if match is not None:
        return int(match.group(1)), match.end()
    match = _QUOTED.match(text, at)
    if match is not None:
        return re.sub(r"\\(.)", r"\1", match.group(1)), match.end()
    raise JsonPathError("unsupported JSONPath syntax")


def parse(text: Any) -> Tuple[Step, ...]:
    """Parse ``text`` or raise :class:`JsonPathError`."""
    if type(text) is not str or not text.startswith("$") or len(text) > MAX_PATH_LENGTH:
        raise JsonPathError("a path is text that starts with '$'")
    steps: List[Step] = []
    at = 1
    while at < len(text):
        step, at = _step(text, at)
        steps.append(step)
        if len(steps) > MAX_STEPS:
            raise JsonPathError("path has too many steps")
    return tuple(steps)


def expand(steps: Tuple[Step, ...], document: Any) -> Iterator[Tuple[Union[str, int], ...]]:
    """Every concrete path ``steps`` names in ``document``; absent parts name nothing."""
    if not steps:
        yield ()
        return
    head, rest = steps[0], steps[1:]
    if head is WILDCARD:
        if isinstance(document, list):
            keys: List[Union[str, int]] = list(range(len(document)))
        elif isinstance(document, dict):
            keys = list(document)
        else:
            return
    elif isinstance(head, int):
        if not isinstance(document, list) or head >= len(document):
            return
        keys = [head]
    else:
        if not isinstance(document, dict) or head not in document:
            return
        keys = [head]
    for key in keys:
        for tail in expand(rest, document[key]):
            yield (key, *tail)
