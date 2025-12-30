"""
Base Integration Package

Provides foundational classes for building integrations quickly.
"""

from .models import APIResponse, IntegrationConfig
from .rate_limiter import RateLimiter
from .webhook import WebhookHandler
from .client import BaseIntegration
from .pagination import PaginatedIntegration

__all__ = [
    "APIResponse",
    "BaseIntegration",
    "IntegrationConfig",
    "PaginatedIntegration",
    "RateLimiter",
    "WebhookHandler",
]
