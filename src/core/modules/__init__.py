"""
Module System - Core Registration and Execution

Organized by architecture:
- Atomic: Core building blocks, no external dependencies (Level 1)
- Third-party: External service integrations (Level 2)
- AI Tools: AI-powered analysis tools (Level 3)
- External: MCP and remote agents (Level 4)
- Composite: High-level workflow templates (v1.1)

Key classes:
- ModuleResult: Standardized execution result
- ModuleError: Exception hierarchy for module errors
- execute_module: Unified execution wrapper
"""

from .registry import ModuleRegistry
from .registry import register_module
from .base import BaseModule
from .express import module, mod, ParamHelper, create_simple_module
from .result import ModuleResult
from .items import (
    Item,
    ItemMeta,
    ItemError,
    ItemContext,
    PairedItemInfo,
    BinaryData,
    NodeExecutionResult,
    ExecutionStatus,
    ExecutionMeta,
    NodeError,
    StepInputItems,
    EdgeType,
    EdgeInfo,
    MergeStrategy,
    wrap_legacy_result,
    items_to_legacy_context,
    merge_items,
    merge_items_append,
    merge_items_multiplex,
)
from .errors import (
    ModuleError,
    ValidationError,
    InvalidTypeError,
    InvalidValueError,
    ParamOutOfRangeError,
    ConfigMissingError,
    InvalidConfigError,
    ExecutionTimeoutError,
    RetryExhaustedError,
    CancelledError,
    NetworkError,
    APIError,
    RateLimitedError,
    AuthenticationError,
    ForbiddenError,
    NotFoundError,
    ElementNotFoundError,
    ElementNotVisibleError,
    NavigationError,
    BrowserError,
    FileNotFoundError,
    FileAccessDeniedError,
    FileReadError,
    FileWriteError,
    TypeMismatchError,
    InvalidConnectionError,
    DependencyError,
    ModuleNotFoundError,
    AIResponseError,
    AIContextTooLongError,
    ModelNotAvailableError,
    UnsupportedError,
    error_from_code,
)
from .runtime import (
    execute_module,
    execute_module_with_retry,
    wrap_sync_module,
    check_capabilities,
)
from .catalog import (
    scrub_catalog_metadata,
    scrub_all_metadata,
    get_public_catalog_view,
    get_public_catalog,
    PUBLIC_FIELDS,
    FORBIDDEN_FIELDS,
)
from .lint import (
    lint_module,
    lint_all_modules,
    lint_from_registry,
    LintResult,
    LintReport,
    Severity,
)
from .validation import (
    ValidationResult,
    ValidationError as FieldValidationError,
    ValidationWarning,
    SchemaValidator,
)
from .types import (
    ModuleLevel,
    UIVisibility,
    ContextType,
    ExecutionEnvironment,
    LEVEL_PRIORITY,
    LOCAL_ONLY_CATEGORIES,
    get_default_visibility,
    get_module_environment,
    is_module_allowed_in_environment,
)
from .connection_rules import (
    can_connect,
    validate_workflow_connections,
    get_connection_rules,
    get_suggested_connections,
    get_acceptable_sources,
    CONNECTION_RULES,
)

# Import atomic modules
from .atomic import browser
from .atomic import data
from .atomic import utility

# Import legacy atomic modules (to be migrated)
from . import atomic

# Import third-party integration modules
from .third_party import ai
from .third_party import communication
from .third_party import database
from .third_party import cloud
from .third_party import productivity
from .third_party import developer

# Composite modules (coming in v1.1)
from . import composite

__all__ = [
    # Core
    'ModuleRegistry',
    'register_module',
    'BaseModule',
    # Express Mode (simplified decorator)
    'module',
    'mod',
    'ParamHelper',
    'create_simple_module',
    # Result & Errors (New)
    'ModuleResult',
    # Item-based execution (ITEM_PIPELINE_SPEC.md)
    'Item',
    'ItemMeta',
    'ItemError',
    'ItemContext',
    'PairedItemInfo',
    'BinaryData',
    'NodeExecutionResult',
    'ExecutionStatus',
    'ExecutionMeta',
    'NodeError',
    'StepInputItems',
    'EdgeType',
    'EdgeInfo',
    'MergeStrategy',
    'wrap_legacy_result',
    'items_to_legacy_context',
    'merge_items',
    'merge_items_append',
    'merge_items_multiplex',
    # Errors
    'ModuleError',
    'ValidationError',
    'InvalidTypeError',
    'InvalidValueError',
    'ParamOutOfRangeError',
    'ConfigMissingError',
    'InvalidConfigError',
    'ExecutionTimeoutError',
    'RetryExhaustedError',
    'CancelledError',
    'NetworkError',
    'APIError',
    'RateLimitedError',
    'AuthenticationError',
    'ForbiddenError',
    'NotFoundError',
    'ElementNotFoundError',
    'ElementNotVisibleError',
    'NavigationError',
    'BrowserError',
    'FileNotFoundError',
    'FileAccessDeniedError',
    'FileReadError',
    'FileWriteError',
    'TypeMismatchError',
    'InvalidConnectionError',
    'DependencyError',
    'ModuleNotFoundError',
    'AIResponseError',
    'AIContextTooLongError',
    'ModelNotAvailableError',
    'UnsupportedError',
    'error_from_code',
    # Runtime (New)
    'execute_module',
    'execute_module_with_retry',
    'wrap_sync_module',
    'check_capabilities',
    # Catalog (New)
    'scrub_catalog_metadata',
    'scrub_all_metadata',
    'get_public_catalog_view',
    'get_public_catalog',
    'PUBLIC_FIELDS',
    'FORBIDDEN_FIELDS',
    # Types
    'ModuleLevel',
    'UIVisibility',
    'ContextType',
    'ExecutionEnvironment',
    'LEVEL_PRIORITY',
    'LOCAL_ONLY_CATEGORIES',
    # Functions
    'get_default_visibility',
    'get_module_environment',
    'is_module_allowed_in_environment',
    # Connection rules
    'can_connect',
    'validate_workflow_connections',
    'get_connection_rules',
    'get_suggested_connections',
    'get_acceptable_sources',
    'CONNECTION_RULES',
    # Atomic
    'browser',
    'data',
    'utility',
    # Third-party
    'ai',
    'communication',
    'database',
    'cloud',
    'productivity',
    'developer',
    # Composite
    'composite',
    # Lint
    'lint_module',
    'lint_all_modules',
    'lint_from_registry',
    'LintResult',
    'LintReport',
    'Severity',
    # Validation (ITEM_PIPELINE_SPEC.md Section 7)
    'ValidationResult',
    'FieldValidationError',
    'ValidationWarning',
    'SchemaValidator',
]
