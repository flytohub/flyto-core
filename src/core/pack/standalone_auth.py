# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Credential values for a standalone pack: from the environment or the OS keychain, by name.

A pack names its credentials; it never carries one. Run standalone, the
value of each name is read at call time from, in order:

1. the environment variable ``FLYTO_CREDENTIAL_<NAME>``;
2. the OS keychain, service ``flyto.pack.<pack id>``, account ``<name>``,
   through the platform's own tool (:data:`KEYCHAIN_READERS`), unless
   ``FLYTO_PACK_NO_KEYCHAIN=1``.

In a Flyto2 Space the same names are resolved by the Space's ``secrets``
layer instead; the connector runtime sees the same ``{name: value}``
mapping either way. Nothing here logs, prints or caches a value.
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Any, Callable, Dict, List, Mapping, Optional

__all__ = ["KEYCHAIN_READERS", "KEYCHAIN_STORE_HINTS", "NO_KEYCHAIN_ENV", "CredentialResolver", "read_keychain"]

#: Set to ``1`` to read credentials from the environment only (CI, containers).
NO_KEYCHAIN_ENV = "FLYTO_PACK_NO_KEYCHAIN"

#: ``sys.platform`` -> the argv that prints one secret, ``{service}`` and
#: ``{account}`` filled in. Run without a shell; a non-zero exit is "absent".
KEYCHAIN_READERS: Mapping[str, tuple] = {
    "darwin": ("security", "find-generic-password", "-s", "{service}", "-a", "{account}", "-w"),
    "linux": ("secret-tool", "lookup", "service", "{service}", "account", "{account}"),
}

#: How a person stores one, for the generated README.
KEYCHAIN_STORE_HINTS: Mapping[str, str] = {
    "macOS": "security add-generic-password -s {service} -a {account} -w",
    "Linux": "secret-tool store --label={service} service {service} account {account}",
    "Windows": "set the environment variable (the Credential Manager reader needs the keyring package)",
}

_KEYCHAIN_TIMEOUT_S = 10
_MAX_SECRET_BYTES = 64 * 1024

Keychain = Callable[[str, str], Optional[str]]


def _windows_keyring(service: str, account: str) -> Optional[str]:
    try:
        import keyring  # type: ignore[import-not-found]
    except ImportError:
        return None
    try:
        value = keyring.get_password(service, account)
    except Exception:  # noqa: BLE001 - an unreadable keychain is an absent credential
        return None
    return value or None


def read_keychain(service: str, account: str, *, platform: Optional[str] = None,
                  run: Callable[..., Any] = subprocess.run) -> Optional[str]:
    """One secret from the OS keychain, or ``None`` when it is absent or unreadable."""
    platform = platform or sys.platform
    if platform.startswith("win"):
        return _windows_keyring(service, account)
    template = KEYCHAIN_READERS.get(platform)
    if template is None:
        return None
    argv = [part.format(service=service, account=account) for part in template]
    try:
        done = run(argv, capture_output=True, text=True, timeout=_KEYCHAIN_TIMEOUT_S, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    value = (done.stdout or "").rstrip("\r\n")
    if not value or len(value.encode("utf-8")) > _MAX_SECRET_BYTES:
        return None
    return value


class CredentialResolver:
    """Resolve a standalone pack's credential names to values, per call."""

    def __init__(self, standalone: Mapping[str, Any], *, env: Optional[Mapping[str, str]] = None,
                 keychain: Optional[Keychain] = None):
        self._credentials = list(standalone.get("credentials") or ())
        self._env = os.environ if env is None else env
        self._keychain = keychain if keychain is not None else read_keychain

    def _lookup(self, item: Mapping[str, Any]) -> tuple:
        value = self._env.get(item["env"])
        if value:
            return value, "env"
        if self._env.get(NO_KEYCHAIN_ENV) == "1":
            return None, "missing"
        value = self._keychain(item["keychain"]["service"], item["keychain"]["account"])
        if value:
            return value, "keychain"
        return None, "missing"

    def resolve(self) -> Dict[str, str]:
        """``{name: value}`` for every credential that resolves; absent ones are left out."""
        values: Dict[str, str] = {}
        for item in self._credentials:
            value, _ = self._lookup(item)
            if value is not None:
                values[item["name"]] = value
        return values

    def status(self) -> List[Dict[str, str]]:
        """Where each credential would come from — names and sources, never values."""
        return [{"name": item["name"], "source": self._lookup(item)[1]} for item in self._credentials]
