# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Outbound guards for the integration family.

``BaseIntegration._request`` is one sink shared by every ``integration.*``
module, and it had neither of the two controls its siblings elsewhere in the
tree carry (GHSA-4346-4gqg-59f9):

* **Where the request may go.** Jira builds its base URL from a caller-supplied
  ``domain`` and Salesforce from a caller-supplied ``instance_url``, so the
  request target is caller input like any other URL — ``enforce_outbound_url``
  is the project's answer and is applied in :mod:`.client`.
* **Where the operator's credential may go.** The SSRF guard cannot answer
  this: ``attacker.example.com`` is a perfectly ordinary public host, and the
  first request carries ``Authorization`` before any redirect. That is what
  :func:`assert_env_credential_target_allowed` below is for.

The two are deliberately separate. Vendor-domain suffixes are not a safe
shortcut for the second one: anybody can register ``evil.atlassian.net`` or a
Salesforce org of their choosing, so "the host ends in the vendor's domain"
would still hand the operator's token to an attacker. An environment credential
therefore travels only to the host the *operator* named, or to a host the
operator allowlisted.
"""

import fnmatch
import os
from typing import Iterable, Optional, Sequence
from urllib.parse import urlparse


class IntegrationCredentialError(ValueError):
    """Raised when an environment credential would be sent to a host the
    operator never named."""


def _hostname(value: str) -> str:
    """The host part of a URL, or of a bare domain written without a scheme."""
    text = (value or '').strip()
    if not text:
        return ''
    if '://' not in text:
        text = f'//{text}'
    return (urlparse(text).hostname or '').lower()


def trusted_integration_hosts() -> Sequence[str]:
    """Operator allowlist of hosts an environment credential may reach.

    FLYTO_TRUSTED_INTEGRATION_HOSTS — comma-separated hostnames or fnmatch
    globs (e.g. "jira-proxy.internal,*.mycorp.com"). Empty by default, and the
    only way to widen the rule short of supplying the credential per call.
    """
    raw = os.environ.get('FLYTO_TRUSTED_INTEGRATION_HOSTS', '')
    return [pattern.strip().lower() for pattern in raw.split(',') if pattern.strip()]


def assert_env_credential_target_allowed(
    url: str,
    *,
    service_name: str,
    operator_hosts: Iterable[Optional[str]],
    credentials_from_env: bool,
) -> None:
    """Refuse to attach an operator credential to a host the operator never named.

    Args:
        url: The request target about to be sent with an Authorization header.
        service_name: Short service noun for the error message (e.g. 'jira').
        operator_hosts: Hosts the operator configured for this service — for
            Jira ``JIRA_DOMAIN``, for Salesforce ``SALESFORCE_INSTANCE_URL``.
            URLs and bare domains are both accepted; empty entries are ignored.
        credentials_from_env: True when the credential came from the
            environment rather than from the caller. A caller's own token is
            the caller's own secret and is not this guard's business.

    Raises:
        IntegrationCredentialError: If the target is neither an operator host
            nor on FLYTO_TRUSTED_INTEGRATION_HOSTS.
    """
    if not credentials_from_env:
        return

    target = _hostname(url)
    if not target:
        return

    for configured in operator_hosts:
        if configured and _hostname(configured) == target:
            return

    for pattern in trusted_integration_hosts():
        if fnmatch.fnmatch(target, pattern):
            return

    raise IntegrationCredentialError(
        f"Refusing to send the environment-provided {service_name} credential to "
        f"'{target}', which is not the host this operator configured. Supply the "
        f"credential explicitly for a caller-chosen host, or add the host to "
        f"FLYTO_TRUSTED_INTEGRATION_HOSTS."
    )
