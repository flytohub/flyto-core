"""GHSA-pfg2-w999-497v / GHSA-6pm8-6f34-9v3g — DNS-rebinding SSRF guard.

validate_url_ssrf used to resolve + check the host and then return the hostname,
leaving aiohttp to perform an independent second lookup at connect time (a
resolve-then-connect TOCTOU). The guarded resolver pins the check to the
connection: one lookup, and its IPs are what aiohttp connects to. These tests
exercise the resolver directly (private → blocked, allowlisted → permitted) and
the guarded session's connect-time block, without needing attacker DNS.
"""
import socket

import pytest

from core.utils import _SSRFGuardedResolver, guarded_client_session, SSRFError


@pytest.mark.asyncio
async def test_resolver_blocks_private_resolution():
    # 'localhost' resolves to 127.0.0.1 (private) → rejected at resolve time.
    r = _SSRFGuardedResolver()
    try:
        with pytest.raises(SSRFError):
            await r.resolve("localhost", 80, socket.AF_INET)
    finally:
        await r.close()


@pytest.mark.asyncio
async def test_resolver_allows_allowlisted_private_host():
    r = _SSRFGuardedResolver(allowed_hosts=["localhost"])
    try:
        infos = await r.resolve("localhost", 80, socket.AF_INET)
        assert any(i["host"] == "127.0.0.1" for i in infos)
    finally:
        await r.close()


@pytest.mark.asyncio
async def test_resolver_allows_when_allow_private():
    r = _SSRFGuardedResolver(allow_private=True)
    try:
        infos = await r.resolve("localhost", 80, socket.AF_INET)
        assert infos  # not blocked
    finally:
        await r.close()


@pytest.mark.asyncio
async def test_guarded_session_blocks_private_hostname_at_connect():
    # A hostname that resolves to a private IP must be refused at connect time
    # (the rebinding vector) rather than fetched.
    with pytest.raises(SSRFError):
        async with guarded_client_session() as s:
            async with s.get("http://localhost:9/"):
                pass
