# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Outbound guard for the storage endpoint inside an Azure connection string.

``cloud.azure.{upload,download}`` take their whole destination as one
``connection_string``, and an Azure connection string can name the endpoint
outright (``BlobEndpoint=http://169.254.169.254/``). That is the same shape as
the DSN in GHSA-9x26-9vhm-2qhw and of the hosts in GHSA-xgfr-24jq-vv8h: a
caller-chosen network target that no parameter called ``host`` or ``url`` ever
reveals.

Pulling the endpoint back out gives it the check every other outbound target
gets. It does not make the module safe to point at a stranger's account — that
is inherent to a module whose purpose is to take destination credentials — but
it does stop the account-less forms that reach inside the runner's own network.
"""

from typing import Dict

from ....utils import enforce_outbound_host, enforce_outbound_url

DEFAULT_ENDPOINT_SUFFIX = 'core.windows.net'


def parse_connection_string(connection_string: str) -> Dict[str, str]:
    """The ``key=value;`` pairs of an Azure connection string, keys lowercased.

    Values may themselves contain ``=`` (account keys are base64), so each pair
    is split once and only once.
    """
    pairs = {}
    for chunk in (connection_string or '').split(';'):
        if '=' not in chunk:
            continue
        key, value = chunk.split('=', 1)
        key = key.strip().lower()
        if key:
            pairs[key] = value.strip()
    return pairs


def enforce_azure_endpoint(connection_string: str) -> str:
    """Run the outbound guard on the endpoint an Azure connection string names.

    Args:
        connection_string: The caller-supplied or operator-supplied connection
            string about to be handed to the Azure SDK.

    Returns:
        The connection string, unchanged, so callers can use this inline.

    Raises:
        SSRFError: If the endpoint it names is blocked by policy.

    Note:
        A connection string that names neither an explicit endpoint nor an
        account (``UseDevelopmentStorage=true``) is left alone: it resolves to
        the local emulator, which the host guard permits anyway.
    """
    fields = parse_connection_string(connection_string)

    explicit_endpoint = fields.get('blobendpoint')
    if explicit_endpoint:
        enforce_outbound_url(explicit_endpoint)
        return connection_string

    account = fields.get('accountname')
    if account:
        suffix = fields.get('endpointsuffix') or DEFAULT_ENDPOINT_SUFFIX
        enforce_outbound_host(f'{account}.blob.{suffix}', purpose='Azure Blob Storage')

    return connection_string
