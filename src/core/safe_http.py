# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""SSRF-safe outbound HTTP helpers (DNS-rebinding / TOCTOU defense).

``validate_url_ssrf`` range-checks a hostname's resolved IPs *at validation
time* and returns a URL string; the HTTP client then re-resolves DNS when it
actually connects. A hostname under attacker control can answer with a public IP
during validation and a private / cloud-metadata IP at connect time (DNS
rebinding / validate-then-use TOCTOU, CWE-918), bypassing the guard.

This module closes that window by routing outbound aiohttp traffic through a
resolver that re-applies the SSRF IP check at *resolve* time and hands the vetted
address straight to the connector. aiohttp dials the addresses the resolver
returns without performing a second lookup, so the IP that is range-checked is
exactly the IP that is connected to — validation and connection become atomic.

This complements (does not replace) ``validate_url_ssrf``: that guard still
rejects bad schemes / ports, blocked hostnames, and literal private-IP hosts up
front (literal IPs cannot rebind). The resolver here covers the residual
hostname-rebinding case. Both fail closed.
"""

import socket
import logging
from typing import Optional, Sequence

from .utils import is_private_ip, SSRFError, get_ssrf_config

logger = logging.getLogger(__name__)


def _host_allowlisted(host: str, allowed_hosts: Optional[Sequence[str]]) -> bool:
    """Mirror of the allowlist match used by ``validate_url_ssrf``."""
    if not allowed_hosts:
        return False
    host = (host or "").lower()
    for allowed in allowed_hosts:
        allowed = allowed.lower()
        if host == allowed:
            return True
        # Wildcard suffix match: *.example.com
        if allowed.startswith("*.") and host.endswith(allowed[1:]):
            return True
    return False


def _check_addrs_safe(
    host: str,
    addrs: Sequence[str],
    *,
    allow_private: bool = False,
    allowed_hosts: Optional[Sequence[str]] = None,
) -> None:
    """Raise ``SSRFError`` if any resolved address is private/internal.

    Pure helper (no aiohttp dependency) so the rebind defense is unit-testable.
    Fails closed: a single private address in ``addrs`` rejects the whole
    resolution. ``allow_private`` and an allowlisted ``host`` bypass the check,
    matching ``validate_url_ssrf`` semantics.
    """
    if allow_private or _host_allowlisted(host, allowed_hosts):
        return
    for addr in addrs:
        if is_private_ip(addr):
            logger.warning(
                "SSRF guard blocked a connect-time resolution to a "
                "private/internal address"
            )
            raise SSRFError(
                f"DNS resolution for {host} returned a private/internal IP "
                f"({addr}) at connect time. Possible DNS rebinding; refusing to "
                f"connect (fail-closed)."
            )


# The resolver subclasses aiohttp's AbstractResolver, which requires aiohttp at
# definition time. aiohttp is an optional dependency in this codebase (modules
# import it lazily), so the class is built on first use and cached here.
_resolver_cls = None


def _get_resolver_cls():
    global _resolver_cls
    if _resolver_cls is not None:
        return _resolver_cls

    import aiohttp
    from aiohttp.abc import AbstractResolver

    class SSRFGuardedResolver(AbstractResolver):
        """aiohttp resolver that fails closed on private/internal addresses.

        Wraps a base resolver, then range-checks every returned address. Because
        aiohttp dials the addresses this resolver returns (no second lookup), a
        rebind that flips a hostname to a private IP after URL validation is
        caught here, at connect time.
        """

        def __init__(self, *, allow_private=False, allowed_hosts=None, base=None):
            self._allow_private = bool(allow_private)
            self._allowed_hosts = list(allowed_hosts or [])
            self._base = base if base is not None else aiohttp.ThreadedResolver()

        async def resolve(self, host, port=0, family=socket.AF_INET):
            infos = await self._base.resolve(host, port, family)
            _check_addrs_safe(
                host,
                [info["host"] for info in infos],
                allow_private=self._allow_private,
                allowed_hosts=self._allowed_hosts,
            )
            return infos

        async def close(self):
            await self._base.close()

    _resolver_cls = SSRFGuardedResolver
    return _resolver_cls


def _resolve_config(allow_private, allowed_hosts):
    """Fall back to env-based SSRF config when caller passes neither flag."""
    if allow_private is None and allowed_hosts is None:
        cfg = get_ssrf_config()
        return cfg["allow_private"], cfg["allowed_hosts"]
    return bool(allow_private), allowed_hosts


def create_ssrf_safe_connector(
    *,
    allow_private=None,
    allowed_hosts=None,
    base_resolver=None,
    **connector_kwargs,
):
    """Build an ``aiohttp.TCPConnector`` whose resolver re-checks SSRF on connect.

    When ``allow_private`` / ``allowed_hosts`` are left as ``None`` they are read
    from the environment via ``get_ssrf_config()``, so behaviour matches
    ``validate_url_with_env_config`` (honors ``FLYTO_ALLOW_PRIVATE_NETWORK``,
    ``FLYTO_ALLOWED_HOSTS``, ``FLYTO_VSCODE_LOCAL_MODE``).
    """
    import aiohttp

    allow_private, allowed_hosts = _resolve_config(allow_private, allowed_hosts)
    resolver = _get_resolver_cls()(
        allow_private=allow_private,
        allowed_hosts=allowed_hosts,
        base=base_resolver,
    )
    return aiohttp.TCPConnector(resolver=resolver, **connector_kwargs)


def create_ssrf_safe_session(
    *,
    timeout=None,
    allow_private=None,
    allowed_hosts=None,
    **session_kwargs,
):
    """Build an ``aiohttp.ClientSession`` wired with an SSRF-guarded connector.

    Drop-in replacement for ``aiohttp.ClientSession(...)`` in outbound modules.
    The session owns the connector (``connector_owner`` defaults to ``True``), so
    closing the session closes the connector and its resolver.
    """
    import aiohttp

    connector = create_ssrf_safe_connector(
        allow_private=allow_private, allowed_hosts=allowed_hosts
    )
    return aiohttp.ClientSession(connector=connector, timeout=timeout, **session_kwargs)
