# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Outbound host guard for a database connection string.

``db.mysql.query`` takes its target as a bare ``host`` and runs
``enforce_outbound_host`` on it. Its siblings take a whole DSN instead, and a
DSN hides the host from every check the project already had: the registry-wide
sweep in ``tests/core/test_outbound_guard_coverage.py`` matches parameters by
name, and ``connection_string`` does not look like a network target. That is
why GHSA-9x26-9vhm-2qhw could describe ``postgresql://…@169.254.169.254/x``
reaching the metadata endpoint while the family next door was guarded.

This pulls the hosts back out of the DSN so they get the same check. The guard
runs on the value whatever its origin — a host from ``POSTGRESQL_URL`` is
operator configuration and gets the same treatment as a caller's, exactly as
``db.mysql.query`` treats ``MYSQL_HOST``; ``FLYTO_ALLOWED_HOSTS`` is how an
operator widens it.
"""

from typing import Iterator
from urllib.parse import urlsplit

from .....utils import enforce_outbound_host


def dsn_hosts(dsn: str) -> Iterator[str]:
    """Yield every host named in a DSN's authority section.

    MongoDB replica-set URIs list several hosts in one authority
    (``mongodb://a:27017,b:27017/db``), and ``urlsplit().hostname`` reports only
    the first — so a URI whose first host is innocuous would otherwise carry an
    internal second host past the check.
    """
    authority = urlsplit(dsn).netloc
    if '@' in authority:
        authority = authority.rsplit('@', 1)[1]

    for chunk in authority.split(','):
        host = _without_port(chunk.strip())
        if host:
            yield host


def _without_port(entry: str) -> str:
    """One authority entry with its port removed, IPv6 literals included."""
    if entry.startswith('['):  # bracketed IPv6 literal: [::1]:27017
        return entry[1:].split(']', 1)[0]
    return entry.split(':', 1)[0]


def enforce_dsn_target(dsn: str, *, purpose: str) -> str:
    """Run the outbound host guard over every host in ``dsn``.

    Args:
        dsn: The connection string about to be handed to a driver.
        purpose: Short noun for the error message (e.g. 'PostgreSQL').

    Returns:
        The DSN, unchanged, so callers can use this inline.

    Raises:
        SSRFError: If any host in the DSN is blocked by policy.

    Note:
        A ``mongodb+srv://`` URI names a service record rather than a server, so
        only that name is checked here; the hosts the SRV lookup returns are
        resolved inside the driver and are out of reach of this guard.
    """
    for host in dsn_hosts(dsn):
        enforce_outbound_host(host, purpose=purpose)
    return dsn
