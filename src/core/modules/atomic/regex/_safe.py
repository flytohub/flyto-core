# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Shared ReDoS safeguards for the ``regex.*`` modules.

User-controlled patterns compiled with the stdlib ``re`` engine can exhibit
catastrophic (exponential) backtracking on crafted inputs such as ``(a|a)*$``.
Two properties of CPython make this a whole-server hazard rather than a slow
request: ``re`` matching is synchronous *and* holds the GIL for the entire
match, so it cannot be interrupted by a signal or made concurrent by moving it
to a thread. Running it inline in an async module body therefore freezes the
event loop — every other request (including health checks) is starved for the
full backtracking duration, and the module-level ``asyncio.wait_for`` backstop
never gets to run.

The fix uses the third-party ``regex`` engine, which (unlike stdlib ``re``)
releases the GIL during matching and supports a native per-call ``timeout``.
That gives us two things stdlib ``re`` cannot:

1. A hard, interruptible time limit on each match (``REGEX_TIMEOUT_SECONDS``).
2. Real concurrency — because the GIL is released, running the match in a
   worker thread keeps the event loop responsive instead of frozen.

``compile_guarded`` returns a pattern wrapper that pre-binds the timeout onto
every match method, and ``run_regex_safely`` runs the (now interruptible) match
off the event loop. Input-length caps are kept as cheap defense-in-depth.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, List, Optional, TypeVar

import regex

from ...errors import ValidationError

# Cap inputs so a single request cannot submit an unbounded matching job.
MAX_PATTERN_LENGTH = 1000
MAX_TEXT_LENGTH = 1_000_000  # 1 MB

# Hard per-match wall-clock limit enforced by the regex engine itself.
REGEX_TIMEOUT_SECONDS = 2.0

# Dedicated pool so guarded matches never contend with the event loop's default
# executor. Bounded for backpressure; the regex timeout guarantees each worker
# frees its slot within REGEX_TIMEOUT_SECONDS.
_REGEX_EXECUTOR = ThreadPoolExecutor(
    max_workers=4,
    thread_name_prefix="regex-guard",
)

T = TypeVar("T")


def validate_regex_inputs(pattern: str, text: str) -> None:
    """Reject over-long patterns/inputs before any matching happens."""
    if len(pattern) > MAX_PATTERN_LENGTH:
        raise ValidationError(
            "Pattern too long: {} > {} characters".format(
                len(pattern), MAX_PATTERN_LENGTH
            ),
            field="pattern",
        )
    if len(text) > MAX_TEXT_LENGTH:
        raise ValidationError(
            "Text too long: {} > {} characters".format(len(text), MAX_TEXT_LENGTH),
            field="text",
        )


class GuardedPattern:
    """A compiled pattern whose match methods carry a hard timeout.

    Mirrors the small slice of the ``re`` pattern API the ``regex.*`` modules
    use. Every method passes ``timeout=REGEX_TIMEOUT_SECONDS`` to the ``regex``
    engine, so a catastrophic match self-terminates instead of hanging.
    """

    __slots__ = ("_compiled",)

    def __init__(self, compiled: "regex.Pattern") -> None:
        self._compiled = compiled

    def search(self, text: str) -> Optional[Any]:
        return self._compiled.search(text, timeout=REGEX_TIMEOUT_SECONDS)

    def fullmatch(self, text: str) -> Optional[Any]:
        return self._compiled.fullmatch(text, timeout=REGEX_TIMEOUT_SECONDS)

    def finditer(self, text: str) -> List[Any]:
        # Force evaluation here so the timeout applies while we still hold it.
        return list(self._compiled.finditer(text, timeout=REGEX_TIMEOUT_SECONDS))

    def findall(self, text: str) -> List[Any]:
        return self._compiled.findall(text, timeout=REGEX_TIMEOUT_SECONDS)

    def sub(self, replacement: str, text: str, count: int = 0) -> str:
        return self._compiled.sub(
            replacement, text, count=count, timeout=REGEX_TIMEOUT_SECONDS
        )

    def split(self, text: str, maxsplit: int = 0) -> List[str]:
        return self._compiled.split(
            text, maxsplit=maxsplit, timeout=REGEX_TIMEOUT_SECONDS
        )


def compile_guarded(pattern: str, flags: int = 0) -> GuardedPattern:
    """Compile ``pattern`` with the interruptible ``regex`` engine.

    Raises ``ValidationError`` on an invalid pattern (the ``regex`` engine is
    drop-in compatible with stdlib ``re`` flag values).
    """
    try:
        return GuardedPattern(regex.compile(pattern, flags))
    except regex.error as exc:
        raise ValidationError(
            "Invalid regex pattern: {}".format(exc), field="pattern"
        ) from exc


async def run_regex_safely(operation: Callable[[], T]) -> T:
    """Run a guarded regex ``operation`` off the event loop.

    Because the ``regex`` engine releases the GIL, the event loop (and every
    other request) stays responsive while the match runs. A catastrophic match
    is stopped by the engine's own timeout, which surfaces here as a
    ``ValidationError`` rather than a hung server.
    """
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(_REGEX_EXECUTOR, operation)
    except TimeoutError as exc:
        # regex raises builtin TimeoutError when a match exceeds its timeout.
        raise ValidationError(
            "Regex matching timed out after {:g}s — pattern may be too complex "
            "(possible catastrophic backtracking)".format(REGEX_TIMEOUT_SECONDS),
            field="pattern",
        ) from exc
