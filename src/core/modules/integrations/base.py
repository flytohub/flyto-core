"""
Base Integration Classes

DEPRECATED: This file is maintained for backwards compatibility.
Please import from core.modules.integrations.base instead:

    from core.modules.integrations.base import (
        BaseIntegration,
        IntegrationConfig,
        APIResponse,
    )

All functionality has been split into:
- core/modules/integrations/base/models.py - IntegrationConfig, APIResponse
- core/modules/integrations/base/rate_limiter.py - RateLimiter
- core/modules/integrations/base/webhook.py - WebhookHandler
- core/modules/integrations/base/client.py - BaseIntegration
- core/modules/integrations/base/pagination.py - PaginatedIntegration
"""

# Re-export for backwards compatibility
from .base import (
    APIResponse,
    BaseIntegration,
    IntegrationConfig,
    PaginatedIntegration,
    RateLimiter,
    WebhookHandler,
)

__all__ = [
    "APIResponse",
    "BaseIntegration",
    "IntegrationConfig",
    "PaginatedIntegration",
    "RateLimiter",
    "WebhookHandler",
]
