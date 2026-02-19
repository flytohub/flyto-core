# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

"""
Error Handling Modules

Resilience and fault-tolerance patterns for workflow execution:
- retry: Wrap operations with configurable retry logic
- fallback: Provide fallback values when operations fail
- circuit_breaker: Protect against cascading failures

These modules provide "tool-level" error handling infrastructure.
They define patterns without containing decision-making intelligence.
"""

from .retry import RetryModule
from .fallback import FallbackModule
from .circuit_breaker import CircuitBreakerModule

__all__ = [
    'RetryModule',
    'FallbackModule',
    'CircuitBreakerModule',
]
