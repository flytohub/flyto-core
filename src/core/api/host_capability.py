# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Execution-scoped proxy to a trusted host capability dispatcher.

The proxy is created by the Core HTTP boundary from host-only request metadata.
It is never accepted from workflow data and only connects to a literal loopback
endpoint, so equipment/vendor transports remain outside Core.
"""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

MAX_RESPONSE_BYTES = 256 * 1024


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        raise HostCapabilityProxyError("host capability dispatcher redirect refused")


def validate_host_capability_endpoint(value: str) -> str:
    """Accept only an explicit IPv4 loopback HTTP endpoint."""

    parsed = urlsplit(value)
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.port is None
        or not parsed.path.startswith("/")
    ):
        raise ValueError(
            "host capability endpoint must be an explicit 127.0.0.1 HTTP URL"
        )
    return value


class HostCapabilityProxyError(RuntimeError):
    """The trusted execution host did not return a valid capability result."""


class HostCapabilityProxy:
    """Opaque Core runtime authority backed by one loopback host endpoint."""

    _flyto_runtime_opaque = True

    def __init__(self, *, endpoint: str, token: str, timeout_seconds: float = 65.0) -> None:
        self._endpoint = endpoint
        self._token = token
        self._timeout_seconds = max(1.0, min(300.0, float(timeout_seconds)))

    def _invoke_sync(self, request: Mapping[str, Any]) -> dict[str, Any]:
        body = json.dumps(
            {"request": dict(request)},
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
        http_request = urllib.request.Request(
            self._endpoint,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            opener = urllib.request.build_opener(_NoRedirect())
            with opener.open(
                http_request,
                timeout=self._timeout_seconds,
            ) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as error:
            raise HostCapabilityProxyError(
                f"host capability dispatcher refused the call ({error.code})"
            ) from None
        except HostCapabilityProxyError:
            raise
        except (urllib.error.URLError, TimeoutError, OSError):
            raise HostCapabilityProxyError(
                "host capability dispatcher is unavailable"
            ) from None

        if len(raw) > MAX_RESPONSE_BYTES:
            raise HostCapabilityProxyError("host capability response is too large")
        try:
            value = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise HostCapabilityProxyError(
                "host capability dispatcher returned invalid JSON"
            ) from None
        if not isinstance(value, Mapping):
            raise HostCapabilityProxyError(
                "host capability dispatcher returned a non-object result"
            )
        return dict(value)

    async def invoke(self, request: Mapping[str, Any]) -> dict[str, Any]:
        return await asyncio.to_thread(self._invoke_sync, dict(request))
