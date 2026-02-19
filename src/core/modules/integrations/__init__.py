# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

"""
Integration Framework

Rapid integration development framework for connecting to external services.
Provides base classes, OAuth helpers, and common patterns.

Features:
- BaseIntegration class for quick module creation
- OAuth 2.0 helper for authentication flows
- Rate limiting and retry logic
- Webhook support
- Schema validation

Usage:
    from integrations import BaseIntegration, OAuthClient

    class SlackIntegration(BaseIntegration):
        service_name = "slack"
        base_url = "https://slack.com/api"
        ...
"""

from .base import (
    BaseIntegration,
    IntegrationConfig,
    RateLimiter,
    WebhookHandler,
)

from .oauth import (
    OAuthClient,
    OAuthToken,
    OAuthConfig,
    OAuthProvider,
)

__all__ = [
    # Base classes
    "BaseIntegration",
    "IntegrationConfig",
    "RateLimiter",
    "WebhookHandler",
    # OAuth
    "OAuthClient",
    "OAuthToken",
    "OAuthConfig",
    "OAuthProvider",
]
