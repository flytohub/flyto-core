# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

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

# Importing the service packages is what executes their @register_module
# decorators. Without these three lines the Jira, Salesforce and Slack modules
# were declared in the source, listed in the generated module reference and
# translated into every locale, while `execute_module` answered "Module not
# found" for all seven of them.
from . import jira  # noqa: F401
from . import salesforce  # noqa: F401
from . import slack  # noqa: F401

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
