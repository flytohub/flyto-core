# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

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
