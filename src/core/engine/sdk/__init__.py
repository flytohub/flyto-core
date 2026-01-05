"""
Engine SDK

Stable interface for flyto-cloud and other consumers.

Usage:
    from core.engine.sdk import get_sdk, EngineSDK

    sdk = get_sdk()
    result = await sdk.execute(workflow, inputs)
    catalog = sdk.introspect(workflow, node_id)
"""

from .models import (
    # Enums
    ContextLayer,
    EventType,
    ExecutionStatus,
    IntrospectionMode,
    ResolutionMode,
    VarAvailability,
    VarSource,
    # VarCatalog models
    NodeVarInfo,
    PortVarInfo,
    VarCatalog,
    VarInfo,
    # Event models
    EngineEvent,
    # Execution models
    ExecutionOptions,
    ExecutionResult,
    ExecutionTrace,
    NodeSnapshot,
    # Validation models
    ValidationError,
    ValidationResult,
    ValidationWarning,
    # Expression models
    AutocompleteItem,
    AutocompleteResult,
    ExpressionToken,
    ParsedExpression,
)

from .resolver import (
    ExpressionParser,
    ExpressionSyntaxError,
    VariableNotFoundError,
    VariableResolver,
    create_resolver,
)

from .interface import (
    EngineSDK,
    EngineSDKInterface,
    get_sdk,
)

__all__ = [
    # Enums
    "ContextLayer",
    "EventType",
    "ExecutionStatus",
    "IntrospectionMode",
    "ResolutionMode",
    "VarAvailability",
    "VarSource",
    # VarCatalog models
    "NodeVarInfo",
    "PortVarInfo",
    "VarCatalog",
    "VarInfo",
    # Event models
    "EngineEvent",
    # Execution models
    "ExecutionOptions",
    "ExecutionResult",
    "ExecutionTrace",
    "NodeSnapshot",
    # Validation models
    "ValidationError",
    "ValidationResult",
    "ValidationWarning",
    # Expression models
    "AutocompleteItem",
    "AutocompleteResult",
    "ExpressionToken",
    "ParsedExpression",
    # Resolver
    "ExpressionParser",
    "ExpressionSyntaxError",
    "VariableNotFoundError",
    "VariableResolver",
    "create_resolver",
    # SDK
    "EngineSDK",
    "EngineSDKInterface",
    "get_sdk",
]
