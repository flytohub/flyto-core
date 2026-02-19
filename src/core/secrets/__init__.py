# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Secrets Management Module

Provides secure secret handling for plugins via proxy pattern.
Plugins receive secret references, not raw values.
"""

from .proxy import (
    SecretsProxy,
    SecretRef,
    SecretResolution,
    get_secrets_proxy,
)

__all__ = [
    "SecretsProxy",
    "SecretRef",
    "SecretResolution",
    "get_secrets_proxy",
]
