# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Regression tests for SSRF guard handling of IPv6 transition addresses.

The SSRF guard (`is_private_ip` / `validate_url_ssrf`) must treat IPv6
transition forms (IPv4-mapped, IPv4-compatible, 6to4, NAT64) as private when
their embedded IPv4 is private, so they cannot be used to bypass the guard and
reach loopback / RFC 1918 / cloud-metadata endpoints.

The second half of this module (FLYA-23) covers two residual gaps found while
verifying GHSA-794r-5rp2-fpg8:
  * NAT64 local-use ``64:ff9b:1::/48`` embedded-IPv4 extraction position
    (RFC 6052 §2.2 — IPv4 is not contiguous in the low 32 bits for /48).
  * DNS-rebinding / validate-then-use TOCTOU on the connect path
    (``core.safe_http`` re-checks resolved IPs at connect time).
"""

import ipaddress

import pytest

from core.utils import (
    is_private_ip,
    validate_url_ssrf,
    SSRFError,
    _extract_embedded_ipv4,
    _nat64_embedded_ipv4,
)


# (address, expected is_private_ip result, description)
TRANSITION_PRIVATE = [
    ("::ffff:127.0.0.1", "IPv4-mapped loopback"),
    ("::ffff:169.254.169.254", "IPv4-mapped cloud metadata"),
    ("::ffff:10.0.0.1", "IPv4-mapped RFC1918"),
    ("64:ff9b::7f00:1", "NAT64-WKP loopback"),
    ("64:ff9b::a9fe:a9fe", "NAT64-WKP cloud metadata"),
    ("64:ff9b:1::a9fe:a9fe", "NAT64 local-use cloud metadata"),
    ("2002:7f00:1::", "6to4 loopback"),
    ("2002:a9fe:a9fe::", "6to4 cloud metadata"),
    ("::7f00:1", "IPv4-compatible loopback"),
]

TRANSITION_PUBLIC = [
    ("::ffff:8.8.8.8", "IPv4-mapped public"),
    ("64:ff9b::808:808", "NAT64-WKP public (8.8.8.8)"),
    ("2002:808:808::", "6to4 public (8.8.8.8)"),
]

NATIVE_PRIVATE = ["127.0.0.1", "169.254.169.254", "10.0.0.1", "::1", "fc00::1"]
NATIVE_PUBLIC = ["8.8.8.8", "1.1.1.1", "2606:4700:4700::1111"]


@pytest.mark.parametrize("addr,desc", TRANSITION_PRIVATE)
def test_transition_private_is_blocked(addr, desc):
    assert is_private_ip(addr) is True, f"{desc} ({addr}) must be classified private"


@pytest.mark.parametrize("addr,desc", TRANSITION_PUBLIC)
def test_transition_public_is_allowed(addr, desc):
    # Embedded IPv4 is public -> not private, must stay reachable.
    assert is_private_ip(addr) is False, f"{desc} ({addr}) must be classified public"


@pytest.mark.parametrize("addr", NATIVE_PRIVATE)
def test_native_private_still_blocked(addr):
    assert is_private_ip(addr) is True


@pytest.mark.parametrize("addr", NATIVE_PUBLIC)
def test_native_public_still_allowed(addr):
    assert is_private_ip(addr) is False


@pytest.mark.parametrize("addr,desc", TRANSITION_PRIVATE)
def test_validate_url_ssrf_rejects_transition_literal(addr, desc):
    # Literal-IP host on an allowed port; the guard must raise SSRFError.
    with pytest.raises(SSRFError):
        validate_url_ssrf(f"http://[{addr}]:8080/latest/meta-data/")


# ---------------------------------------------------------------------------
# FLYA-23 #2 — NAT64 /48 position-aware embedded-IPv4 extraction (RFC 6052 §2.2)
# ---------------------------------------------------------------------------

# In the local-use prefix 64:ff9b:1::/48 the embedded IPv4 straddles the
# reserved "u" octet: octets are at byte positions 6,7 and 9,10 — NOT the low
# 32 bits. 169.254.169.254 (a9.fe.a9.fe) therefore encodes as
# 64:ff9b:1:a9fe:a9:fe00:: (suffix zero).
NAT64_48_CANONICAL_PRIVATE = [
    ("64:ff9b:1:a9fe:a9:fe00::", "169.254.169.254", "NAT64 /48 cloud metadata"),
    ("64:ff9b:1:7f00:0:100::", "127.0.0.1", "NAT64 /48 loopback"),
    ("64:ff9b:1:c0a8:1:100::", "192.168.1.1", "NAT64 /48 RFC1918"),
]


@pytest.mark.parametrize("addr,expected,desc", NAT64_48_CANONICAL_PRIVATE)
def test_nat64_48_canonical_extraction(addr, expected, desc):
    emb = _extract_embedded_ipv4(ipaddress.ip_address(addr))
    assert str(emb) == expected, f"{desc}: extracted {emb}, expected {expected}"
    assert is_private_ip(addr) is True, f"{desc} ({addr}) must be classified private"


def test_nat64_48_public_suffix_bypass_is_blocked():
    """Regression for the /48 extraction bug.

    Encodes 169.254.169.254 in the correct RFC 6052 /48 positions but puts a
    *public* address (8.8.8.8) in the low 32 bits. The old code read the low 32
    bits (raw[-4:]) and saw 8.8.8.8 -> not private -> bypass. Position-aware
    extraction reads the real embedded IPv4 and blocks it.
    """
    addr = "64:ff9b:1:a9fe:a9:fe00:808:808"
    # The decoy the old, buggy extractor would have read:
    raw = int(ipaddress.ip_address(addr)).to_bytes(16, "big")
    assert str(ipaddress.IPv4Address(raw[-4:])) == "8.8.8.8"  # old path = bypass
    # New, position-aware path:
    assert str(_extract_embedded_ipv4(ipaddress.ip_address(addr))) == "169.254.169.254"
    assert is_private_ip(addr) is True


def test_nat64_well_known_96_unchanged():
    # /96 well-known carries IPv4 in the low 32 bits; behaviour must be preserved.
    assert is_private_ip("64:ff9b::a9fe:a9fe") is True
    assert is_private_ip("64:ff9b::808:808") is False  # public stays reachable


@pytest.mark.parametrize("prefix_len,octets", [
    (32, (4, 5, 6, 7)),
    (40, (5, 6, 7, 9)),
    (48, (6, 7, 9, 10)),
    (56, (7, 9, 10, 11)),
    (64, (9, 10, 11, 12)),
    (96, (12, 13, 14, 15)),
])
def test_nat64_position_aware_all_prefix_lengths(prefix_len, octets):
    raw = bytearray(16)
    for octet_pos, value in zip(octets, (10, 1, 2, 3)):
        raw[octet_pos] = value
    assert str(_nat64_embedded_ipv4(bytes(raw), prefix_len)) == "10.1.2.3"


def test_nat64_unsupported_prefix_len_returns_none():
    assert _nat64_embedded_ipv4(bytes(16), 80) is None


# ---------------------------------------------------------------------------
# FLYA-23 #1 — DNS-rebinding / validate-then-use TOCTOU on the connect path
# ---------------------------------------------------------------------------

from core.safe_http import _check_addrs_safe  # noqa: E402


def test_rebind_blocked_at_connect_time():
    """Validation sees a public IP; the host rebinds to a metadata IP before the
    connect-time resolution. The connect-path check must reject it.

    Fails against old code (no connect-time re-validation; the guard returned a
    URL string and the client re-resolved freely). Passes against new.
    """
    host = "rebind.attacker.example"
    # 1) validation-time resolution: public -> allowed
    _check_addrs_safe(host, ["93.184.216.34"], allow_private=False, allowed_hosts=None)
    # 2) connect-time resolution after rebind: metadata -> must raise
    with pytest.raises(SSRFError):
        _check_addrs_safe(host, ["169.254.169.254"], allow_private=False, allowed_hosts=None)


def test_connect_check_fails_closed_on_mixed_addrs():
    # A single private address in a multi-answer result rejects the whole resolve.
    with pytest.raises(SSRFError):
        _check_addrs_safe("h", ["8.8.8.8", "10.0.0.5"], allow_private=False, allowed_hosts=None)


def test_connect_check_blocks_transition_addr():
    # IPv6 transition encodings are caught at connect time too.
    with pytest.raises(SSRFError):
        _check_addrs_safe("h", ["64:ff9b::a9fe:a9fe"], allow_private=False, allowed_hosts=None)


def test_connect_check_allow_private_bypass():
    # Dev / self-hosted escape hatch must still work.
    _check_addrs_safe("h", ["127.0.0.1"], allow_private=True, allowed_hosts=None)


def test_connect_check_allowlist_bypass():
    _check_addrs_safe("internal.corp", ["10.0.0.1"], allow_private=False,
                      allowed_hosts=["internal.corp"])
    _check_addrs_safe("api.corp.com", ["10.0.0.1"], allow_private=False,
                      allowed_hosts=["*.corp.com"])


def test_connect_check_public_passes():
    # No raise for a clean public resolution.
    _check_addrs_safe("good.example", ["93.184.216.34"], allow_private=False,
                      allowed_hosts=None)


def test_ssrf_guarded_resolver_blocks_private():
    """End-to-end resolver test (requires aiohttp). A base resolver returning a
    private IP must make SSRFGuardedResolver.resolve raise SSRFError."""
    pytest.importorskip("aiohttp")
    import asyncio
    from core.safe_http import _get_resolver_cls

    class FakeBase:
        def __init__(self, host_ip):
            self._host_ip = host_ip

        async def resolve(self, host, port=0, family=0):
            return [{
                "hostname": host, "host": self._host_ip, "port": port,
                "family": family, "proto": 0, "flags": 0,
            }]

        async def close(self):
            pass

    resolver_cls = _get_resolver_cls()
    resolver = resolver_cls(allow_private=False, allowed_hosts=None,
                            base=FakeBase("169.254.169.254"))

    async def go():
        with pytest.raises(SSRFError):
            await resolver.resolve("rebind.attacker.example", 443)
        await resolver.close()

    asyncio.run(go())
