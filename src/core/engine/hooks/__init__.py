# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Executor Hooks Module

Provides extension points for workflow execution lifecycle.
"""

from typing import List, Optional

from .models import (
    HookAction,
    HookContext,
    HookResult,
)
from .base import (
    ExecutorHooks,
    NullHooks,
)
from .implementations import (
    CompositeHooks,
    LoggingHooks,
    MetricsHooks,
)
from .metering import (
    MeteringHook,
    UsageRecord,
)


def create_hooks(
    logging_enabled: bool = False,
    metrics_enabled: bool = False,
    metering_enabled: bool = False,
    metering_callback: Optional[object] = None,
    custom_hooks: Optional[List[ExecutorHooks]] = None,
    log_params: bool = False,
    log_results: bool = False,
) -> ExecutorHooks:
    """
    Create a hooks instance with common configurations.

    Args:
        logging_enabled: Enable logging hooks
        metrics_enabled: Enable metrics hooks
        metering_enabled: Enable usage metering hooks (Pro license required)
        metering_callback: Optional callback for metering records
        custom_hooks: Additional custom hooks
        log_params: Log step parameters (if logging enabled)
        log_results: Log step results (if logging enabled)

    Returns:
        Configured ExecutorHooks instance
    """
    hooks_list: List[ExecutorHooks] = []

    if logging_enabled:
        hooks_list.append(LoggingHooks(
            log_params=log_params,
            log_results=log_results,
        ))

    if metrics_enabled:
        hooks_list.append(MetricsHooks())

    if metering_enabled:
        hooks_list.append(MeteringHook(
            on_record=metering_callback,
        ))

    if custom_hooks:
        hooks_list.extend(custom_hooks)

    if not hooks_list:
        return NullHooks()

    if len(hooks_list) == 1:
        return hooks_list[0]

    return CompositeHooks(hooks_list)


__all__ = [
    # Models
    "HookAction",
    "HookContext",
    "HookResult",
    # Base
    "ExecutorHooks",
    "NullHooks",
    # Implementations
    "CompositeHooks",
    "LoggingHooks",
    "MetricsHooks",
    # Metering
    "MeteringHook",
    "UsageRecord",
    # Factory
    "create_hooks",
]
