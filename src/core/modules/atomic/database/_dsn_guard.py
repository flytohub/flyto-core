# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Shared SSRF / DSN guard for the database.* modules.

A caller-supplied connection_string (or host/port/user/password) lets an
untrusted client point a DB module at ANY host — postgres://169.254.169.254,
postgres://internal-rds:5432 — turning the module into an SSRF-to-internal-DB
primitive plus arbitrary SQL/DDL. The database.* modules are already denied by
default at the capability layer (core.module_policy); this is defense-in-depth
for operators who deliberately opt them in.

Two controls, applied at the top of every database.* handler:

  guard_client_dsn(params)       — reject a client connection_string unless
                                   FLYTO_ALLOW_CLIENT_DB_DSN is set; reject a
                                   client-supplied host/port/credentials likewise
                                   (forcing server-side env config).

  guard_resolved_host(host)      — when a host IS used, reject SSRF targets
                                   (RFC1918 / loopback / link-local / metadata
                                   169.254.169.254 / NAT64) before connecting.

Set FLYTO_ALLOW_CLIENT_DB_DSN=1 to allow client-supplied connection targets
(only for trusted callers).
"""

import ipaddress
import os
import socket
from typing import Any, Dict, Optional
from urllib.parse import urlparse

_TRUTHY = {"1", "true", "yes", "on"}

# Param keys that, when supplied by the client, point the connection at a
# client-chosen target. host/port/user/password/database let a caller assemble a
# DSN even without connection_string (the query.py host-param bypass).
_CLIENT_TARGET_KEYS = ("connection_string", "host", "port", "user", "password", "database")


class DatabaseTargetError(ValueError):
    """Raised when a DB connection target is client-controlled or hits an SSRF range."""


def allow_client_dsn() -> bool:
    return os.environ.get("FLYTO_ALLOW_CLIENT_DB_DSN", "").strip().lower() in _TRUTHY


def _is_blocked_ip(ip: ipaddress._BaseAddress) -> bool:
    if ip.is_loopback or ip.is_link_local or ip.is_private or ip.is_reserved or ip.is_unspecified:
        return True
    # Cloud metadata endpoint (link_local already covers 169.254.0.0/16, but be explicit).
    if str(ip) == "169.254.169.254":
        return True
    # NAT64 well-known prefix 64:ff9b::/96 — extract the embedded IPv4 and re-check.
    if isinstance(ip, ipaddress.IPv6Address):
        try:
            if ip in ipaddress.ip_network("64:ff9b::/96"):
                embedded = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
                return _is_blocked_ip(embedded)
            # IPv4-mapped ::ffff:a.b.c.d
            if ip.ipv4_mapped is not None:
                return _is_blocked_ip(ip.ipv4_mapped)
        except Exception:
            return True
    return False


def guard_resolved_host(host: Optional[str]) -> None:
    """Reject a hostname/IP that resolves into an SSRF-sensitive range."""
    if not host:
        return
    host = host.strip().strip("[]")  # tolerate bracketed IPv6 literals
    if not host:
        return
    # Resolve every A/AAAA record; block if ANY resolves into a denied range
    # (defends against DNS records that point at internal space).
    addrs = set()
    try:
        ipaddress.ip_address(host)
        addrs.add(host)
    except ValueError:
        try:
            for info in socket.getaddrinfo(host, None):
                addrs.add(info[4][0])
        except socket.gaierror:
            # Unresolvable — let the driver surface the connection error rather
            # than fabricating a pass; but a name that won't resolve can't be an
            # exploit target either, so do not hard-fail here.
            return
    for addr in addrs:
        try:
            ip = ipaddress.ip_address(addr.split("%")[0])  # strip zone id
        except ValueError:
            continue
        if _is_blocked_ip(ip):
            raise DatabaseTargetError(
                f"database host {host!r} resolves to a blocked SSRF range ({addr}); "
                "internal/loopback/link-local/metadata targets are refused"
            )


def guard_client_dsn(params: Dict[str, Any]) -> None:
    """Reject client-supplied connection targets unless explicitly allowed.

    Call this at the top of every database.* handler. When client DSNs are
    allowed (FLYTO_ALLOW_CLIENT_DB_DSN=1), the resolved host is still validated
    against the SSRF denylist so an opted-in operator can't be pointed at the
    metadata endpoint / internal services.
    """
    client_keys = [k for k in _CLIENT_TARGET_KEYS if params.get(k) is not None]
    if not client_keys:
        return  # fully server-configured (env) — nothing client-controlled
    if not allow_client_dsn():
        raise DatabaseTargetError(
            "client-supplied database connection target "
            f"({', '.join(client_keys)}) is disabled; configure the connection "
            "server-side via env (DATABASE_URL / POSTGRES_* / MYSQL_*). Set "
            "FLYTO_ALLOW_CLIENT_DB_DSN=1 to override for trusted callers."
        )
    # Allowed — still validate the target host against the SSRF denylist.
    host = params.get("host")
    if not host and params.get("connection_string"):
        try:
            host = urlparse(str(params["connection_string"])).hostname
        except Exception:
            host = None
    guard_resolved_host(host)
