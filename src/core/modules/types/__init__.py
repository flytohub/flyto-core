"""
Module Types Package

Defines core types for module system including:
- ModuleLevel: Priority and trust classification
- UIVisibility: UI display behavior
- ContextType: Module context requirements
- ExecutionEnvironment: Where modules can safely run
- NodeType: Workflow node types (v1.1 spec)
- EdgeType: Connection types (control/resource)
- DataType: Port data types
- PortImportance: Port UI visibility level
"""

from .enums import (
    ContextType,
    DataType,
    EdgeType,
    ExecutionEnvironment,
    LEVEL_PRIORITY,
    ModuleLevel,
    ModuleTier,
    NodeType,
    PortImportance,
    StabilityLevel,
    TIER_DISPLAY_ORDER,
    UIVisibility,
)
from .data_types import (
    DATA_TYPE_COMPATIBILITY,
    is_data_type_compatible,
)
from .ports import (
    DEFAULT_PORTS_BY_NODE_TYPE,
    get_default_ports,
)
from .context import (
    CONTEXT_INCOMPATIBLE_PAIRS,
    DEFAULT_CONTEXT_PROVISIONS,
    DEFAULT_CONTEXT_REQUIREMENTS,
    get_context_error_message,
    is_context_compatible,
)
from .visibility import (
    DEFAULT_VISIBILITY_CATEGORIES,
    get_default_visibility,
)
from .environment import (
    LOCAL_ONLY_CATEGORIES,
    MODULE_ENVIRONMENT_OVERRIDES,
    get_module_environment,
    is_module_allowed_in_environment,
)
from .stability import (
    STABILITY_BY_ENV,
    get_allowed_stability_levels,
    get_current_env,
    get_default_stability,
    is_module_visible,
)

__all__ = [
    # Enums
    "ContextType",
    "DataType",
    "EdgeType",
    "ExecutionEnvironment",
    "LEVEL_PRIORITY",
    "ModuleLevel",
    "ModuleTier",
    "NodeType",
    "PortImportance",
    "StabilityLevel",
    "TIER_DISPLAY_ORDER",
    "UIVisibility",
    # Data types
    "DATA_TYPE_COMPATIBILITY",
    "is_data_type_compatible",
    # Ports
    "DEFAULT_PORTS_BY_NODE_TYPE",
    "get_default_ports",
    # Context
    "CONTEXT_INCOMPATIBLE_PAIRS",
    "DEFAULT_CONTEXT_PROVISIONS",
    "DEFAULT_CONTEXT_REQUIREMENTS",
    "get_context_error_message",
    "is_context_compatible",
    # Visibility
    "DEFAULT_VISIBILITY_CATEGORIES",
    "get_default_visibility",
    # Environment
    "LOCAL_ONLY_CATEGORIES",
    "MODULE_ENVIRONMENT_OVERRIDES",
    "get_module_environment",
    "is_module_allowed_in_environment",
    # Stability
    "STABILITY_BY_ENV",
    "get_allowed_stability_levels",
    "get_current_env",
    "get_default_stability",
    "is_module_visible",
]
