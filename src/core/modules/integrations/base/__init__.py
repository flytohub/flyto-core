# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

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
