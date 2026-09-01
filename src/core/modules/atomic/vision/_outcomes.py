# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Whether a raised request error means "it did not happen" or "we cannot say".

Both vision modules wrap their OpenAI call in one bare ``except Exception`` and
return a single ``API_ERROR``. That collapses two facts an operator needs to
keep apart, and it is the same split ``dns.lookup`` makes for NXDOMAIN versus a
timeout — the retry question, wearing a different exception type:

    the connection was never established        FAILED
        No bytes left this machine. The SSRF guard refused the connect target,
        or the socket never came up. Nothing was requested, nothing was billed,
        and we know that rather than infer it.

    anything else                               INDETERMINATE
        A read timeout, a connection dropped mid-flight, a body that would not
        parse. The request may have reached OpenAI, been processed and been
        billed; the answer simply never came back intact. "We do not know
        whether it happened" is the definition of indeterminate, and it is the
        honest default for every failure this function cannot positively place
        on the near side of the wire.

INDETERMINATE is the default on purpose. Being wrong in that direction costs a
consumer some caution; being wrong the other way tells them an effect did not
happen when it may well have.
"""

from __future__ import annotations

from typing import List, Tuple

from ....engine.outcome import Outcome
from ....utils import SSRFError


def _connect_error_types() -> Tuple[type, ...]:
    """Exception types that mean the connection was never established.

    Resolved lazily and defensively: which HTTP client is in play is decided at
    call time by what is installed, and a missing one must not turn this into
    the error it is trying to describe.
    """
    types: List[type] = [SSRFError]
    try:
        import httpx

        # ConnectTimeout is deliberately included and is NOT a subclass of
        # ConnectError: it inherits from TimeoutException. Both mean the
        # connection did not come up, so both are on the near side of the wire.
        # ReadTimeout and WriteTimeout are deliberately NOT here -- by then the
        # request is on the wire and its fate is unknown.
        types.extend([httpx.ConnectError, httpx.ConnectTimeout])
    except Exception:  # pragma: no cover - httpx absent is a supported install
        pass
    try:
        import aiohttp

        types.append(aiohttp.ClientConnectorError)
    except Exception:  # pragma: no cover - aiohttp absent is a supported install
        pass
    return tuple(types)


def classify_request_failure(error: BaseException) -> Tuple[Outcome, str]:
    """``(rung, why)`` for an exception raised around the provider call."""
    if isinstance(error, _connect_error_types()):
        return (
            Outcome.FAILED,
            'the connection was never established, so no bytes reached the '
            'provider: nothing was requested and nothing was billed',
        )
    return (
        Outcome.INDETERMINATE,
        'the call was already on the wire when this raised. The provider may '
        'have received it, processed it and billed for it; we cannot say',
    )
