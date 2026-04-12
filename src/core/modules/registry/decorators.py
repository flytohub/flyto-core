# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Module registration decorators

The @register_module decorator is the entry point for all module registration.
Resolution logic lives in resolve.py, metadata construction in metadata.py.
"""

import inspect
from typing import Dict, Type, Any, Optional, List

from ..base import BaseModule
from ..types import (
    ModuleLevel,
    ModuleTier,
    UIVisibility,
    ExecutionEnvironment,
    NodeType,
    StabilityLevel,
)
from .core import ModuleRegistry
from .resolve import resolve_module_config
from .metadata import build_module_metadata

# Re-export for backward compatibility (internal callers that imported _resolve_tier etc.)
from .resolve import (  # noqa: F401
    resolve_tier as _resolve_tier,
    enrich_port_handle_metadata as _enrich_port_handle_metadata,
    resolve_can_be_start as _resolve_can_be_start,
    resolve_timeout_ms as _resolve_timeout_ms,
    resolve_module_config as _resolve_module_config,
)
from .metadata import build_module_metadata as _build_module_metadata  # noqa: F401


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


def _wrap_function_as_module(func, module_id: str):
    """Wrap a function-based module into a BaseModule subclass."""
    is_function = inspect.isfunction(func) or inspect.iscoroutinefunction(func)

    if not is_function:
        func.module_id = module_id
        return func, False

    class FunctionModuleWrapper(BaseModule):
        """Wrapper to make function-based modules work with class-based engine"""

        def __init__(self, params: Dict[str, Any], context: Dict[str, Any]):
            self.params = params
            self.context = context

        def validate_params(self) -> None:
            pass

        async def execute(self) -> Any:
            func_context = {
                'params': self.params,
                **self.context
            }
            return await func(func_context)

    FunctionModuleWrapper.module_id = module_id
    FunctionModuleWrapper.__name__ = f"{func.__name__}_Wrapper"
    FunctionModuleWrapper.__doc__ = func.__doc__
    return FunctionModuleWrapper, True


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
    timeout_ms: Optional[int] = None,
    timeout: Optional[int] = None,     # DEPRECATED: Use timeout_ms instead (seconds)
    retryable: bool = False,
    max_retries: int = 3,
    concurrent_safe: bool = True,

    # Security settings
    requires_credentials: bool = False,
    handles_sensitive_data: bool = False,
    required_permissions: Optional[List[str]] = None,
    credential_keys: Optional[List[str]] = None,
    required_secrets: Optional[List[str]] = None,
    env_vars: Optional[List[str]] = None,

    # Execution environment (LOCAL/CLOUD/ALL)
    execution_environment: Optional[ExecutionEnvironment] = None,

    # Workflow Spec v1.1 - Node & Port Configuration
    node_type: NodeType = NodeType.STANDARD,
    input_ports: Optional[List[Dict[str, Any]]] = None,
    output_ports: Optional[List[Dict[str, Any]]] = None,
    dynamic_ports: Optional[Dict[str, Dict[str, Any]]] = None,
    container_config: Optional[Dict[str, Any]] = None,

    # Start node configuration
    can_be_start: Optional[bool] = None,
    start_requires_params: Optional[List[str]] = None,

    # Advanced
    requires: Optional[List[str]] = None,
    permissions: Optional[List[str]] = None,
    examples: Optional[List[Dict[str, Any]]] = None,
    docs_url: Optional[str] = None,
    author: Optional[str] = None,
    license: str = "MIT",

    # License tier requirement
    required_tier: Optional[str] = None,
    required_feature: Optional[str] = None,

    # UI Display Tier
    tier: Optional[ModuleTier] = None,
):
    """
    Module registration decorator.

    Registers a module class or async function with the ModuleRegistry.
    Auto-detects configuration values (visibility, tier, ports, connection rules)
    based on category and module_id when not explicitly provided.

    Example:
        @register_module(
            module_id="browser.goto",
            ui_label="Open URL",
            params_schema={"url": {"type": "string", "required": True}},
            can_receive_from=["browser.*"],
            can_connect_to=["browser.*"],
        )
        class BrowserGotoModule(BaseModule):
            async def execute(self):
                pass
    """
    def decorator(module_class_or_func):
        module_class, is_function = _wrap_function_as_module(module_class_or_func, module_id)

        # Resolve all auto-detected config values
        resolved = resolve_module_config(
            module_id=module_id,
            level=level,
            category=category,
            subcategory=subcategory,
            tags=tags,
            ui_visibility=ui_visibility,
            requires_context=requires_context,
            provides_context=provides_context,
            execution_environment=execution_environment,
            node_type=node_type,
            input_ports=input_ports,
            output_ports=output_ports,
            input_types=input_types,
            can_receive_from=can_receive_from,
            can_connect_to=can_connect_to,
            can_be_start=can_be_start,
            tier=tier,
            timeout_ms=timeout_ms,
            timeout=timeout,
        )

        # Import-time validation (P0/P1 - hard fail)
        _validate_module_registration(
            module_id=module_id,
            category=resolved["category"],
            node_type=node_type,
            input_ports=input_ports,
            output_ports=output_ports,
            can_receive_from=can_receive_from,
            can_connect_to=can_connect_to,
            params_schema=params_schema,
        )

        # Build metadata
        metadata = build_module_metadata(
            module_id=module_id,
            version=version,
            stability=stability,
            level=level,
            resolved=resolved,
            subcategory=subcategory,
            tags=tags,
            ui_label=ui_label,
            ui_label_key=ui_label_key,
            ui_description=ui_description,
            ui_description_key=ui_description_key,
            ui_group=ui_group,
            ui_icon=ui_icon,
            ui_color=ui_color,
            ui_help=ui_help,
            ui_help_key=ui_help_key,
            label=label,
            label_key=label_key,
            description=description,
            description_key=description_key,
            icon=icon,
            color=color,
            input_types=input_types,
            output_types=output_types,
            input_type_labels=input_type_labels,
            input_type_descriptions=input_type_descriptions,
            output_type_labels=output_type_labels,
            output_type_descriptions=output_type_descriptions,
            suggested_predecessors=suggested_predecessors,
            suggested_successors=suggested_successors,
            connection_error_messages=connection_error_messages,
            params_schema=params_schema,
            output_schema=output_schema,
            retryable=retryable,
            max_retries=max_retries,
            concurrent_safe=concurrent_safe,
            requires_credentials=requires_credentials,
            handles_sensitive_data=handles_sensitive_data,
            required_permissions=required_permissions,
            credential_keys=credential_keys,
            required_secrets=required_secrets,
            env_vars=env_vars,
            node_type=node_type,
            dynamic_ports=dynamic_ports,
            container_config=container_config,
            start_requires_params=start_requires_params,
            requires=requires,
            permissions=permissions,
            examples=examples,
            docs_url=docs_url,
            author=author,
            license_str=license,
            required_tier=required_tier,
            required_feature=required_feature,
        )

        # Quality Validation (P0 - hard fail on errors)
        from .quality_validator import validate_module_quality

        validate_module_quality(
            module_class=module_class,
            module_id=module_id,
            metadata=metadata,
            original_func=module_class_or_func if is_function else None,
        )

        ModuleRegistry.register(module_id, module_class, metadata)
        return module_class

    return decorator
