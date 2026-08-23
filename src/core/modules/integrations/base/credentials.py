# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Credential resolution that remembers where the credential came from.

The env fallback used to be written inline as ``params.get(x) or
os.getenv(Y)``, which loses the one fact the credential-endpoint guard needs:
whether the secret belongs to the caller or to the operator. Worse, both the
module wrapper and the integration class did it, so by the time the request was
built a value read from ``JIRA_API_TOKEN`` was indistinguishable from one the
caller typed — the laundering step behind GHSA-4346-4gqg-59f9.

The environment value is passed in rather than the variable's *name* on purpose:
``scripts/generate_reference.py`` builds the environment-variable reference by
finding literal ``os.getenv`` calls in the sources, so moving the name inside
this helper would quietly delete three documented credentials from that
reference.
"""

from typing import Optional, Tuple


def resolve_credential(
    explicit: Optional[str], from_environment: Optional[str]
) -> Tuple[Optional[str], bool]:
    """Resolve a credential and report its origin.

    Args:
        explicit: The value the caller supplied, if any.
        from_environment: The value the operator's environment offers, if any.

    Returns:
        ``(value, came_from_env)`` — ``came_from_env`` is True only when the
        caller supplied nothing and the environment did.
    """
    if explicit:
        return explicit, False
    return from_environment, bool(from_environment)
