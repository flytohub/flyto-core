"""
Plugin Runtime Module

Phase 0: Abstraction layer for module invocation.
Phase 1+: Full subprocess plugin support.

This module provides a unified interface for invoking modules,
whether they are in-process legacy modules or subprocess plugins.
"""

# Phase 0: Core invoker
from .invoke import (
    RuntimeInvoker,
    get_invoker,
    invoke,
    parse_module_id,
)

# Types
from .types import (
    InvokeRequest,
    InvokeResponse,
    InvokeMetrics,
    InvokeError,
    InvokeStatus,
    TenantContext,
    SecretRef,
)

# Exceptions
from .exceptions import (
    RuntimeError,
    PluginNotFoundError,
    PluginTimeoutError,
    PluginCrashedError,
    PluginProtocolError,
    PluginUnhealthyError,
    ValidationError,
    PermissionDeniedError,
    SecretNotProvidedError,
    ResourceExhaustedError,
    SchemaIncompatibleError,
)

# Phase 1: Plugin management
from .protocol import (
    JsonRpcRequest,
    JsonRpcResponse,
    ProtocolEncoder,
    ProtocolDecoder,
    ErrorCode,
    PROTOCOL_VERSION,
)
from .process import (
    PluginProcess,
    ProcessConfig,
    ProcessStatus,
    RestartPolicy,
)
from .manager import (
    PluginManager,
    PluginManifest,
    PluginInfo,
)
from .health import (
    HealthChecker,
    HealthCheckConfig,
    HealthStatus,
    PluginHealth,
    HealthRecord,
)
from .config import (
    RuntimeConfig,
    get_config,
    reload_config,
)

# Phase 2: Routing
from .routing import (
    ModuleRouter,
    RoutingConfig,
    RoutingResult,
    RoutingDecision,
    RoutingPreference,
    ModuleRoutingOverride,
    get_router,
)

# Phase F: Frontend Integration
from .transformer import (
    transform_manifest_to_modules,
    transform_step_to_module,
    merge_plugin_modules_with_core,
    transform_modules_for_tiered_response,
)

# Phase M: Multi-Tenant Support
from .pool_router import (
    PoolRouter,
    PoolConfig,
    PoolStats,
    PoolType,
    TenantTier,
    get_pool_router,
    reset_pool_router,
)

# Reset functions for testing
from .invoke import reset_invoker
from .routing import reset_router

__all__ = [
    # Core invoker (Phase 0)
    "RuntimeInvoker",
    "get_invoker",
    "invoke",
    "parse_module_id",

    # Types
    "InvokeRequest",
    "InvokeResponse",
    "InvokeMetrics",
    "InvokeError",
    "InvokeStatus",
    "TenantContext",
    "SecretRef",

    # Exceptions
    "RuntimeError",
    "PluginNotFoundError",
    "PluginTimeoutError",
    "PluginCrashedError",
    "PluginProtocolError",
    "PluginUnhealthyError",
    "ValidationError",
    "PermissionDeniedError",
    "SecretNotProvidedError",
    "ResourceExhaustedError",
    "SchemaIncompatibleError",

    # Protocol (Phase 1)
    "JsonRpcRequest",
    "JsonRpcResponse",
    "ProtocolEncoder",
    "ProtocolDecoder",
    "ErrorCode",
    "PROTOCOL_VERSION",

    # Process management (Phase 1)
    "PluginProcess",
    "ProcessConfig",
    "ProcessStatus",
    "RestartPolicy",

    # Plugin management (Phase 1)
    "PluginManager",
    "PluginManifest",
    "PluginInfo",

    # Health checking (Phase 1)
    "HealthChecker",
    "HealthCheckConfig",
    "HealthStatus",
    "PluginHealth",
    "HealthRecord",

    # Configuration (Phase 1)
    "RuntimeConfig",
    "get_config",
    "reload_config",

    # Routing (Phase 2)
    "ModuleRouter",
    "RoutingConfig",
    "RoutingResult",
    "RoutingDecision",
    "RoutingPreference",
    "ModuleRoutingOverride",
    "get_router",

    # Frontend Integration (Phase F)
    "transform_manifest_to_modules",
    "transform_step_to_module",
    "merge_plugin_modules_with_core",
    "transform_modules_for_tiered_response",

    # Multi-Tenant Support (Phase M)
    "PoolRouter",
    "PoolConfig",
    "PoolStats",
    "PoolType",
    "TenantTier",
    "get_pool_router",
    "reset_pool_router",

    # Testing utilities
    "reset_invoker",
    "reset_router",
    "reset_pool_router",
]
