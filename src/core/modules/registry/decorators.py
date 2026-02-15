"""
Module registration decorators
"""
from typing import Dict, Type, Any, Optional, List

from ..base import BaseModule
from ..types import (
    ModuleLevel,
    ModuleTier,
    UIVisibility,
    ExecutionEnvironment,
    NodeType,
    StabilityLevel,
    DEFAULT_CONTEXT_REQUIREMENTS,
    DEFAULT_CONTEXT_PROVISIONS,
    get_default_visibility,
    get_module_environment,
    get_default_ports,
)
from ..connection_rules import get_default_connection_rules
from .core import ModuleRegistry


def _resolve_tier(
    tier: Optional[ModuleTier],
    level: ModuleLevel,
    tags: Optional[List[str]],
    category: str,
    subcategory: Optional[str] = None,
    module_id: Optional[str] = None,
) -> ModuleTier:
    """
    Resolve module tier based on explicit value or auto-detection.

    Priority:
    1. Explicit tier parameter (if provided)
    2. INTERNAL for system/internal categories
    3. TOOLKIT for low-level utility categories (string, array, object, math, etc.)
       - Checks category, subcategory, and module_id prefix
    4. TOOLKIT for 'advanced' tag
    5. FEATURED for template level
    6. STANDARD for user-facing categories (browser, api, ai, etc.)
    """
    if tier is not None:
        return tier

    # Internal categories are always INTERNAL
    internal_categories = {'meta', 'testing', 'debug', 'training'}
    if category in internal_categories:
        return ModuleTier.INTERNAL

    # Low-level utility categories -> TOOLKIT (collapsed by default)
    # These are building blocks that power users need
    toolkit_categories = {
        # Data manipulation
        'string', 'array', 'object', 'math', 'datetime',
        # Type operations
        'validate', 'encode', 'convert', 'check', 'logic',
        # Text processing
        'text', 'regex', 'format', 'hash',
        # Collections
        'set', 'stats',
        # Low-level utilities
        'utility', 'random', 'crypto', 'path',
        # Development/testing tools
        'shell', 'process', 'port',
        # Vector/embedding utilities
        'vector',
    }

    # Check category directly
    if category in toolkit_categories:
        return ModuleTier.TOOLKIT

    # Check subcategory (for modules with category='atomic')
    if subcategory and subcategory in toolkit_categories:
        return ModuleTier.TOOLKIT

    # Check module_id prefix (e.g., 'array' from 'array.filter')
    if module_id:
        id_prefix = module_id.split('.')[0]
        if id_prefix in toolkit_categories:
            return ModuleTier.TOOLKIT

    # 'advanced' tag also goes to TOOLKIT
    if tags and 'advanced' in tags:
        return ModuleTier.TOOLKIT

    # Template modules -> FEATURED
    if level == ModuleLevel.TEMPLATE:
        return ModuleTier.FEATURED

    # User-facing categories -> STANDARD (visible by default)
    # These are what most users interact with
    # browser, api, ai, llm, vision, http, file, image, document, etc.
    return ModuleTier.STANDARD


def _enrich_port_handle_metadata(port: dict, port_type: str, node_type: NodeType) -> dict:
    """Auto-fill handle_id and position if not explicitly set."""
    if 'handle_id' in port:
        return port

    enriched = dict(port)
    pid = port['id']

    if port_type == 'input':
        enriched.setdefault('position', 'left')
        if pid == 'input':
            enriched['handle_id'] = 'in' if node_type == NodeType.LOOP else 'target'
        else:
            enriched['handle_id'] = 'target-%s' % pid
    else:  # output
        enriched.setdefault('position', 'right')
        if pid in ('success', 'trigger', 'start', 'output'):
            enriched['handle_id'] = 'output'
        elif pid == 'iterate':
            enriched['handle_id'] = 'body_out'
        elif pid == 'done':
            enriched['handle_id'] = 'done_out'
        else:
            enriched['handle_id'] = 'source-%s' % pid

    return enriched


def _validate_module_registration(
    module_id: str,
    category: str,
    node_type: NodeType,
    input_ports: Optional[List[Dict[str, Any]]],
    output_ports: Optional[List[Dict[str, Any]]],
    can_receive_from: Optional[List[str]],
    can_connect_to: Optional[List[str]],
    params_schema: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Validate module registration at import time.
    Raises ValueError if validation fails (hard fail).
    """
    errors = []

    # P1: All modules must have explicit connection rules
    if can_receive_from is None:
        errors.append("Missing 'can_receive_from' - connection rules are required")
    if can_connect_to is None:
        errors.append("Missing 'can_connect_to' - connection rules are required")

    # P0: Flow modules must have ports defined
    if category == 'flow':
        # START and TRIGGER don't need input_ports (they're entry points)
        if not input_ports and node_type not in (NodeType.START, NodeType.TRIGGER):
            errors.append("Flow module missing 'input_ports' - port definitions required")
        # END doesn't need output_ports (it's a terminal)
        if not output_ports and node_type != NodeType.END:
            errors.append("Flow module missing 'output_ports' - port definitions required")

    # Reserved keyword check: __event__ cannot be used as a param name
    if params_schema and '__event__' in params_schema:
        errors.append("'__event__' is a reserved keyword and cannot be used in params_schema")

    if errors:
        error_msg = f"Module '{module_id}' registration failed (import-time validation):\n"
        error_msg += "\n".join(f"  - {e}" for e in errors)
        raise ValueError(error_msg)


def register_module(
    module_id: str,
    version: str = "1.0.0",
    stability: StabilityLevel = StabilityLevel.STABLE,
    level: ModuleLevel = ModuleLevel.ATOMIC,
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    tags: Optional[List[str]] = None,

    # Context requirements (for connection validation)
    requires_context: Optional[List[str]] = None,
    provides_context: Optional[List[str]] = None,

    # UI visibility and metadata
    # None = auto-detect based on category (see types.DEFAULT_VISIBILITY_CATEGORIES)
    ui_visibility: Optional[UIVisibility] = None,
    ui_label: Optional[Any] = None,
    ui_label_key: Optional[str] = None,
    ui_description: Optional[Any] = None,
    ui_description_key: Optional[str] = None,
    ui_group: Optional[str] = None,
    ui_icon: Optional[str] = None,
    ui_color: Optional[str] = None,

    # Extended UI help (detailed explanation)
    ui_help: Optional[str] = None,
    ui_help_key: Optional[str] = None,

    # Legacy label fields (deprecated, use ui_label instead)
    label: Optional[Any] = None,
    label_key: Optional[str] = None,
    description: Optional[Any] = None,
    description_key: Optional[str] = None,

    # Legacy visual fields (deprecated, use ui_icon instead)
    icon: Optional[str] = None,
    color: Optional[str] = None,

    # Connection types (for UI compatibility)
    input_types: Optional[List[str]] = None,
    output_types: Optional[List[str]] = None,
    can_receive_from: Optional[List[str]] = None,
    can_connect_to: Optional[List[str]] = None,

    # Type labels and descriptions (for UI display)
    input_type_labels: Optional[Dict[str, str]] = None,
    input_type_descriptions: Optional[Dict[str, str]] = None,
    output_type_labels: Optional[Dict[str, str]] = None,
    output_type_descriptions: Optional[Dict[str, str]] = None,

    # Connection suggestions (for UI guidance)
    suggested_predecessors: Optional[List[str]] = None,
    suggested_successors: Optional[List[str]] = None,

    # Connection error messages (custom messages)
    connection_error_messages: Optional[Dict[str, str]] = None,

    # Schema
    params_schema: Optional[Dict[str, Any]] = None,
    output_schema: Optional[Dict[str, Any]] = None,

    # Execution settings
    timeout_ms: Optional[int] = None,  # Timeout in milliseconds (preferred)
    timeout: Optional[int] = None,     # DEPRECATED: Use timeout_ms instead (seconds)
    retryable: bool = False,
    max_retries: int = 3,
    concurrent_safe: bool = True,

    # Security settings
    requires_credentials: bool = False,
    handles_sensitive_data: bool = False,
    required_permissions: Optional[List[str]] = None,
    credential_keys: Optional[List[str]] = None,  # e.g., ['OPENAI_API_KEY']
    required_secrets: Optional[List[str]] = None,  # Alternative to credential_keys
    env_vars: Optional[List[str]] = None,  # Environment variable names

    # Execution environment (LOCAL/CLOUD/ALL)
    # None = auto-detect based on category (see types.LOCAL_ONLY_CATEGORIES)
    execution_environment: Optional[ExecutionEnvironment] = None,

    # ==========================================================================
    # Workflow Spec v1.1 - Node & Port Configuration
    # ==========================================================================

    # Node type (determines default ports and execution behavior)
    node_type: NodeType = NodeType.STANDARD,

    # Input ports (if not specified, uses defaults from node_type)
    # Each port: {id, label, label_key?, data_type?, edge_type?, max_connections?, required?, ui?}
    input_ports: Optional[List[Dict[str, Any]]] = None,

    # Output ports (if not specified, uses defaults from node_type)
    # Each port: {id, label, label_key?, data_type?, edge_type?, event, color?, ui?}
    output_ports: Optional[List[Dict[str, Any]]] = None,

    # Dynamic ports configuration (for Switch/Case nodes)
    # {
    #   'output': {
    #     'from_param': 'cases',
    #     'stable_key_field': 'id',
    #     'id_field': 'value',
    #     'label_field': 'label',
    #     'event_prefix': 'case:',
    #     'include_default': True
    #   }
    # }
    dynamic_ports: Optional[Dict[str, Dict[str, Any]]] = None,

    # Container configuration (for container/sandbox nodes)
    container_config: Optional[Dict[str, Any]] = None,

    # Start node configuration
    # None = auto-derive from node_type and input_types
    can_be_start: Optional[bool] = None,
    # Parameters required if this node is used as start (e.g., ['url'] for http.request)
    start_requires_params: Optional[List[str]] = None,

    # Advanced
    requires: Optional[List[str]] = None,
    permissions: Optional[List[str]] = None,
    examples: Optional[List[Dict[str, Any]]] = None,
    docs_url: Optional[str] = None,
    author: Optional[str] = None,
    license: str = "MIT",

    # License tier requirement (for feature gating)
    # "free" = available in all tiers
    # "pro" = requires PRO or ENTERPRISE tier
    # "enterprise" = requires ENTERPRISE tier only
    required_tier: Optional[str] = None,
    # Specific feature flag requirement (e.g., "DESKTOP_AUTOMATION")
    required_feature: Optional[str] = None,

    # ==========================================================================
    # UI Display Tier (for node picker dialog grouping)
    # ==========================================================================
    # None = auto-detect based on level/tags/category
    # FEATURED: Prominent display, recommended modules
    # STANDARD: Normal display in category sections
    # TOOLKIT: Collapsed section for atomic/advanced modules
    # INTERNAL: Hidden from UI, system use only
    tier: Optional[ModuleTier] = None,
):
    """
    Module registration decorator

    UI Visibility Auto-Detection:
        When ui_visibility is not specified (None), it will be automatically
        determined based on the module's category:
        - DEFAULT (shown to all users): ai, agent, notification, api, browser, cloud, database, productivity, payment, image
        - EXPERT (advanced users only): string, array, object, math, datetime, file, element, flow, data, utility, meta, test

        See types.DEFAULT_VISIBILITY_CATEGORIES for the full mapping.

    Example:
        @register_module(
            module_id="browser.goto",
            level=ModuleLevel.ATOMIC,
            category="browser",

            # Context for connection validation
            requires_context=["browser"],
            provides_context=["browser", "page"],

            # UI metadata (ui_visibility auto-detected from category "browser" -> DEFAULT)
            ui_label="Open URL",
            ui_description="Navigate browser to a URL",
            ui_group="Browser / Navigation",
            ui_icon="Globe",
            ui_color="#8B5CF6",

            params_schema={
                "url": {
                    "type": "string",
                    "required": True,
                    "label": "URL"
                }
            }
        )
        class BrowserGotoModule(BaseModule):
            async def execute(self):
                pass

    Args:
        module_id: Unique identifier (e.g., "browser.goto")
        version: Semantic version (default: "1.0.0")
        stability: Stability level (STABLE/BETA/ALPHA/DEPRECATED)
                   - STABLE: Production ready, shown everywhere
                   - BETA: Testing, shown in development/staging
                   - ALPHA: Early dev, shown only in local dev
                   - DEPRECATED: Hidden but functional
        level: Module level classification
        category: Primary category (default: extracted from module_id)
        subcategory: Optional subcategory
        tags: List of tags for filtering

        requires_context: List of context types this module requires (e.g., ["browser"])
        provides_context: List of context types this module provides (e.g., ["browser", "page"])

        ui_visibility: UI visibility level (DEFAULT/EXPERT/HIDDEN), or None for auto-detection
        ui_label: Display name for UI
        ui_label_key: i18n translation key for label
        ui_description: Description for UI
        ui_description_key: i18n translation key for description
        ui_group: UI grouping category
        ui_icon: Lucide icon name
        ui_color: Hex color code

        params_schema: Parameter definitions
        output_schema: Output structure definition

        timeout_ms: Execution timeout in milliseconds (preferred)
        timeout: DEPRECATED - Execution timeout in seconds (use timeout_ms instead)
        retryable: Whether module can be retried on failure
        max_retries: Maximum retry attempts
        concurrent_safe: Whether module can run concurrently

        requires_credentials: Whether module needs API keys
        handles_sensitive_data: Whether module processes sensitive data
        required_permissions: List of required permissions

        execution_environment: Where module can run (LOCAL/CLOUD/ALL), or None for auto-detection

        examples: Usage examples
        docs_url: Documentation URL
        author: Module author
        license: License identifier
    """
    def decorator(module_class_or_func):
        # Check if it's a function or a class
        import inspect
        is_function = inspect.isfunction(module_class_or_func) or inspect.iscoroutinefunction(module_class_or_func)

        if is_function:
            # Wrap function in a class
            class FunctionModuleWrapper(BaseModule):
                """Wrapper to make function-based modules work with class-based engine"""

                def __init__(self, params: Dict[str, Any], context: Dict[str, Any]):
                    self.params = params
                    self.context = context

                def validate_params(self) -> None:
                    """Validation handled by function"""
                    pass

                async def execute(self) -> Any:
                    """Execute the wrapped function"""
                    # Build context dict for function
                    func_context = {
                        'params': self.params,
                        **self.context
                    }
                    return await module_class_or_func(func_context)

            FunctionModuleWrapper.module_id = module_id
            FunctionModuleWrapper.__name__ = f"{module_class_or_func.__name__}_Wrapper"
            FunctionModuleWrapper.__doc__ = module_class_or_func.__doc__
            module_class = FunctionModuleWrapper
        else:
            # It's already a class
            module_class = module_class_or_func
            module_class.module_id = module_id

        # Determine category from module_id if not provided
        resolved_category = category or module_id.split('.')[0]

        # Auto-resolve UI visibility from category if not explicitly provided
        resolved_visibility = ui_visibility
        if resolved_visibility is None:
            resolved_visibility = get_default_visibility(resolved_category)

        # Auto-resolve context from category defaults if not explicitly provided
        resolved_requires_context = requires_context
        resolved_provides_context = provides_context

        if resolved_requires_context is None:
            resolved_requires_context = DEFAULT_CONTEXT_REQUIREMENTS.get(resolved_category, [])

        if resolved_provides_context is None:
            resolved_provides_context = DEFAULT_CONTEXT_PROVISIONS.get(resolved_category, [])

        # Auto-resolve execution environment from category if not explicitly provided
        resolved_execution_env = execution_environment
        if resolved_execution_env is None:
            resolved_execution_env = get_module_environment(module_id, resolved_category)

        # Resolve ports from node_type defaults if not explicitly provided
        default_ports = get_default_ports(node_type)
        resolved_input_ports = input_ports if input_ports is not None else default_ports.get("input", [])
        resolved_output_ports = output_ports if output_ports is not None else default_ports.get("output", [])

        # Enrich ports with handle_id/position if not set (for custom ports)
        resolved_input_ports = [
            _enrich_port_handle_metadata(p, 'input', node_type) for p in resolved_input_ports
        ]
        resolved_output_ports = [
            _enrich_port_handle_metadata(p, 'output', node_type) for p in resolved_output_ports
        ]

        # Resolve connection rules from category defaults if not explicitly provided
        default_can_connect, default_can_receive = get_default_connection_rules(resolved_category)
        resolved_can_connect_to = can_connect_to if can_connect_to is not None else default_can_connect
        resolved_can_receive_from = can_receive_from if can_receive_from is not None else default_can_receive

        # Resolve can_be_start: explicit > node_type > can_receive_from > input_types > requires_context
        resolved_can_be_start = can_be_start
        if resolved_can_be_start is None:
            # START and TRIGGER node types can always be start
            if node_type in (NodeType.START, NodeType.TRIGGER):
                resolved_can_be_start = True
            # Flow control nodes that need input cannot be start
            elif node_type in (NodeType.SWITCH, NodeType.MERGE, NodeType.LOOP, NodeType.JOIN, NodeType.END, NodeType.BRANCH, NodeType.FORK):
                resolved_can_be_start = False
            # If input_types requires specific data types, cannot be start
            elif input_types and input_types != ['*']:
                # Has specific input requirements (e.g., ['browser'], ['page'])
                resolved_can_be_start = False
            # If requires_context is set, cannot be start
            elif resolved_requires_context:
                resolved_can_be_start = False
            # Check can_receive_from: must EXPLICITLY include 'start' to be a starter
            # Note: ['*'] means "accepts any INPUT" not "doesn't need input"
            elif resolved_can_receive_from:
                # Check if 'start' is explicitly allowed
                allows_start = any(
                    pattern == 'start' or pattern.startswith('start.')
                    for pattern in resolved_can_receive_from
                )
                resolved_can_be_start = allows_start
            # Empty can_receive_from means no input needed - can be starter
            else:
                resolved_can_be_start = True

        # Resolve tier from level/tags/category/subcategory/module_id
        resolved_tier = _resolve_tier(
            tier=tier,
            level=level,
            tags=tags,
            category=resolved_category,
            subcategory=subcategory,
            module_id=module_id,
        )

        # Resolve timeout_ms from timeout (deprecated) if not set
        resolved_timeout_ms = timeout_ms
        if resolved_timeout_ms is None and timeout is not None:
            # Convert seconds to milliseconds with deprecation warning
            import logging
            import warnings
            logger = logging.getLogger(__name__)
            resolved_timeout_ms = timeout * 1000
            warnings.warn(
                f"[{module_id}] 'timeout' (seconds) is deprecated. "
                f"Use 'timeout_ms={resolved_timeout_ms}' instead.",
                DeprecationWarning,
                stacklevel=3
            )
            logger.warning(
                f"[{module_id}] 'timeout' is deprecated. "
                f"Use 'timeout_ms={resolved_timeout_ms}' instead."
            )

        # Import-time validation (P0/P1 - hard fail)
        # Check ORIGINAL values to enforce explicit definition
        _validate_module_registration(
            module_id=module_id,
            category=resolved_category,
            node_type=node_type,
            input_ports=input_ports,  # Original, not resolved
            output_ports=output_ports,  # Original, not resolved
            can_receive_from=can_receive_from,  # Original, not resolved
            can_connect_to=can_connect_to,  # Original, not resolved
            params_schema=params_schema,  # Check for reserved keywords
        )

        # Build metadata
        metadata = {
            "module_id": module_id,
            "version": version,
            "stability": stability.value if isinstance(stability, StabilityLevel) else stability,
            "level": level.value if isinstance(level, ModuleLevel) else level,
            "category": resolved_category,
            "subcategory": subcategory,
            "tags": tags or [],
            "tier": resolved_tier.value if isinstance(resolved_tier, ModuleTier) else resolved_tier,

            # Context for connection validation
            "requires_context": resolved_requires_context,
            "provides_context": resolved_provides_context,

            # UI metadata (prefer new ui_* fields, fallback to legacy)
            "ui_visibility": resolved_visibility.value if isinstance(resolved_visibility, UIVisibility) else resolved_visibility,
            "ui_label": ui_label or label or module_id,
            "ui_label_key": ui_label_key or label_key,
            "ui_description": ui_description or description or "",
            "ui_description_key": ui_description_key or description_key,
            "ui_group": ui_group,
            "ui_icon": ui_icon or icon,
            "ui_color": ui_color or color,

            # Extended UI help
            "ui_help": ui_help,
            "ui_help_key": ui_help_key,

            # Legacy fields (for backward compatibility)
            "label": ui_label or label or module_id,
            "description": ui_description or description or "",
            "icon": ui_icon or icon,
            "color": ui_color or color,

            # Connection types
            "input_types": input_types or [],
            "output_types": output_types or [],
            "can_receive_from": resolved_can_receive_from,
            "can_connect_to": resolved_can_connect_to,

            # Type labels and descriptions (for UI display)
            "input_type_labels": input_type_labels or {},
            "input_type_descriptions": input_type_descriptions or {},
            "output_type_labels": output_type_labels or {},
            "output_type_descriptions": output_type_descriptions or {},

            # Connection suggestions
            "suggested_predecessors": suggested_predecessors or [],
            "suggested_successors": suggested_successors or [],

            # Connection error messages
            "connection_error_messages": connection_error_messages or {},

            # Schema
            "params_schema": params_schema or {},
            "output_schema": output_schema or {},

            # Execution settings
            "timeout_ms": resolved_timeout_ms,
            "timeout": resolved_timeout_ms / 1000.0 if resolved_timeout_ms else None,  # Legacy (seconds)
            "retryable": retryable,
            # If retryable=False, max_retries should be 0 (consistency fix)
            "max_retries": max_retries if retryable else 0,
            "concurrent_safe": concurrent_safe,

            # Security settings
            "requires_credentials": requires_credentials,
            "handles_sensitive_data": handles_sensitive_data,
            "required_permissions": required_permissions or [],
            "credential_keys": credential_keys or [],
            "required_secrets": required_secrets or [],
            "env_vars": env_vars or [],

            # Execution environment
            "execution_environment": resolved_execution_env.value if isinstance(resolved_execution_env, ExecutionEnvironment) else resolved_execution_env,

            # Workflow Spec v1.1 - Node & Port Configuration
            "node_type": node_type.value if isinstance(node_type, NodeType) else node_type,
            "input_ports": resolved_input_ports,
            "output_ports": resolved_output_ports,
            "dynamic_ports": dynamic_ports,
            "container_config": container_config,

            # Start node configuration
            "can_be_start": resolved_can_be_start,
            "start_requires_params": start_requires_params or [],

            # Advanced
            "requires": requires or [],
            "permissions": permissions or [],
            "examples": examples or [],
            "docs_url": docs_url,
            "author": author,
            "license": license,

            # License tier requirement
            "required_tier": required_tier,
            "required_feature": required_feature,
        }

        # ======================================================================
        # Quality Validation (P0 - hard fail on errors)
        # ======================================================================
        # Import here to avoid circular imports
        from .quality_validator import validate_module_quality

        # Validate module code quality before registration
        # This ensures "good decorator != bad code" - the code must meet standards
        # For function-based modules, we validate the original function, not the wrapper
        validate_module_quality(
            module_class=module_class,
            module_id=module_id,
            metadata=metadata,
            original_func=module_class_or_func if is_function else None,
        )

        ModuleRegistry.register(module_id, module_class, metadata)
        return module_class

    return decorator
