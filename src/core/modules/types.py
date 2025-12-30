"""
Module Types

DEPRECATED: This file is maintained for backwards compatibility.
Please import from core.modules.types instead:

    from core.modules.types import (
        ModuleLevel,
        UIVisibility,
        ContextType,
        ExecutionEnvironment,
        NodeType,
        DataType,
    )

All functionality has been split into:
- core/modules/types/enums.py - All enum classes
- core/modules/types/data_types.py - Type compatibility matrix
- core/modules/types/ports.py - Port configurations
- core/modules/types/context.py - Context compatibility
- core/modules/types/visibility.py - UI visibility
- core/modules/types/environment.py - Environment restrictions
"""

# Re-export for backwards compatibility
from .types import (
    # Enums
    ContextType,
    DataType,
    EdgeType,
    ExecutionEnvironment,
    LEVEL_PRIORITY,
    ModuleLevel,
    NodeType,
    PortImportance,
    UIVisibility,
    # Data types
    DATA_TYPE_COMPATIBILITY,
    is_data_type_compatible,
    # Ports
    DEFAULT_PORTS_BY_NODE_TYPE,
    get_default_ports,
    # Context
    CONTEXT_INCOMPATIBLE_PAIRS,
    DEFAULT_CONTEXT_PROVISIONS,
    DEFAULT_CONTEXT_REQUIREMENTS,
    get_context_error_message,
    is_context_compatible,
    # Visibility
    DEFAULT_VISIBILITY_CATEGORIES,
    get_default_visibility,
    # Environment
    LOCAL_ONLY_CATEGORIES,
    MODULE_ENVIRONMENT_OVERRIDES,
    get_module_environment,
    is_module_allowed_in_environment,
)

__all__ = [
    # Enums
    "ContextType",
    "DataType",
    "EdgeType",
    "ExecutionEnvironment",
    "LEVEL_PRIORITY",
    "ModuleLevel",
    "NodeType",
    "PortImportance",
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
]
