# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Base Integration Package

Provides foundational classes for building integrations quickly.
"""

from .credentials import resolve_credential
from .egress import (
    IntegrationCredentialError,
    assert_env_credential_target_allowed,
    trusted_integration_hosts,
)
from .models import APIResponse, IntegrationConfig
from .rate_limiter import RateLimiter
from .webhook import WebhookHandler
from .client import BaseIntegration
from .pagination import PaginatedIntegration

__all__ = [
    "APIResponse",
    "BaseIntegration",
    "IntegrationConfig",
    "IntegrationCredentialError",
    "PaginatedIntegration",
    "RateLimiter",
    "WebhookHandler",
    "assert_env_credential_target_allowed",
    "resolve_credential",
    "trusted_integration_hosts",
]
