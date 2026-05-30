# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Regression tests for SSRF guard handling of IPv6 transition addresses.

The SSRF guard (`is_private_ip` / `validate_url_ssrf`) must treat IPv6
transition forms (IPv4-mapped, IPv4-compatible, 6to4, NAT64) as private when
their embedded IPv4 is private, so they cannot be used to bypass the guard and
reach loopback / RFC 1918 / cloud-metadata endpoints.
"""

import pytest

from core.utils import is_private_ip, validate_url_ssrf, SSRFError


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
