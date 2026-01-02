"""
Composite Module Registration Decorator

Features:
- Auto-derivation: input_types, output_types, can_receive_from, can_connect_to
  are automatically inferred from the first/last steps
- Import-time validation: steps must be defined, each step must have 'module'
- Simplified API: only need module_id, label, icon, color, steps, params_schema
"""
from typing import Any, Dict, List, Optional

from ...types import UIVisibility
from ....constants import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT_SECONDS,
)
from .registry import CompositeRegistry
from .module import CompositeModule


def _validate_composite_registration(
    module_id: str,
    steps: Optional[List[Dict[str, Any]]],
) -> None:
    """
    Validate composite module registration at import time.
    Raises ValueError if validation fails.
    """
    errors = []

    # P1: steps must be defined
    if not steps:
        errors.append("Missing 'steps' - composite must define workflow steps")

    # P0: each step must have 'module' reference
    for i, step in enumerate(steps or []):
        if 'module' not in step:
            step_id = step.get('id', f'step_{i}')
            errors.append(f"Step '{step_id}' missing 'module' reference")

    if errors:
        raise ValueError(
            f"Composite '{module_id}' registration failed:\n  - " +
            "\n  - ".join(errors)
        )


def _infer_from_steps(steps: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Auto-derive input/output types and connection rules from steps.

    Rules:
    - input_types: from first step's input_types
    - output_types: from last step's output_types
    - can_receive_from: from first step's can_receive_from
    - can_connect_to: from last step's can_connect_to
    """
    if not steps:
        return {}

    # Lazy import to avoid circular dependency
    from ...registry import ModuleRegistry

    first_step = steps[0]
    last_step = steps[-1]

    first_module_id = first_step.get('module', '')
    last_module_id = last_step.get('module', '')

    # Get metadata from atomic module registry
    first_meta = ModuleRegistry.get_metadata(first_module_id) or {}
    last_meta = ModuleRegistry.get_metadata(last_module_id) or {}

    return {
        'input_types': first_meta.get('input_types', []),
        'output_types': last_meta.get('output_types', []),
        'can_receive_from': first_meta.get('can_receive_from', ['*']),
        'can_connect_to': last_meta.get('can_connect_to', ['*']),
    }


def register_composite(
    module_id: str,
    version: str = "1.0.0",
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    tags: Optional[List[str]] = None,

    # Context requirements (for connection validation)
    requires_context: Optional[List[str]] = None,
    provides_context: Optional[List[str]] = None,

    # UI visibility and metadata
    ui_visibility: UIVisibility = UIVisibility.DEFAULT,
    ui_label: Optional[str] = None,
    ui_label_key: Optional[str] = None,
    ui_description: Optional[str] = None,
    ui_description_key: Optional[str] = None,
    ui_group: Optional[str] = None,
    ui_icon: Optional[str] = None,
    ui_color: Optional[str] = None,

    # Extended UI help (detailed explanation)
    ui_help: Optional[str] = None,
    ui_help_key: Optional[str] = None,

    # UI form generation
    ui_params_schema: Optional[Dict[str, Any]] = None,

    # Legacy display fields (deprecated, use ui_* instead)
    label: Optional[str] = None,
    label_key: Optional[str] = None,
    description: Optional[str] = None,
    description_key: Optional[str] = None,
    icon: Optional[str] = None,
    color: Optional[str] = None,

    # Connection types (auto-derived from steps if not provided)
    input_types: Optional[List[str]] = None,
    output_types: Optional[List[str]] = None,

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

    # Connection rules (auto-derived from steps if not provided)
    can_connect_to: Optional[List[str]] = None,
    can_receive_from: Optional[List[str]] = None,

    # Steps definition (REQUIRED)
    steps: Optional[List[Dict[str, Any]]] = None,

    # Schema
    params_schema: Optional[Dict[str, Any]] = None,
    output_schema: Optional[Dict[str, Any]] = None,

    # Execution settings
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    retryable: bool = False,
    max_retries: int = DEFAULT_MAX_RETRIES,

    # Documentation
    examples: Optional[List[Dict[str, Any]]] = None,
    author: Optional[str] = None,
    license: str = "MIT"
):
    """
    Decorator to register a Composite Module (Level 3)

    Composite modules combine multiple atomic modules into a single action.
    Connection types and rules are auto-derived from steps unless explicitly provided.

    Simplified Example:
        @register_composite(
            module_id='composite.browser.scrape_to_json',
            label='Scrape Web to JSON',
            icon='FileJson',
            color='#10B981',

            steps=[
                {'id': 'launch', 'module': 'browser.launch', 'params': {'headless': True}},
                {'id': 'goto', 'module': 'browser.goto', 'params': {'url': '${params.url}'}},
                {'id': 'extract', 'module': 'browser.extract', 'params': {'selector': '${params.selector}'}},
            ],

            params_schema={
                'url': {'type': 'string', 'required': True, 'label': 'URL'},
                'selector': {'type': 'string', 'required': True, 'label': 'CSS Selector'},
            },
            # input_types, output_types, can_receive_from, can_connect_to
            # are automatically derived from steps!
        )
        class WebScrapeToJson(CompositeModule):
            pass

    Auto-Derivation Rules:
        - input_types: from first step's input_types
        - output_types: from last step's output_types
        - can_receive_from: from first step's can_receive_from
        - can_connect_to: from last step's can_connect_to
        - category: from module_id (e.g., composite.browser.x → browser)

    Priority: Manual override > Auto-derived > Default

    Args:
        module_id: Unique identifier (e.g., "composite.browser.scrape_to_json")
        label/ui_label: Display name for UI
        icon/ui_icon: Lucide icon name
        color/ui_color: Hex color code
        steps: List of atomic steps to execute (REQUIRED)
        params_schema: Parameter definitions for UI form

        # Auto-derived (override only if needed):
        input_types: List of accepted input data types
        output_types: List of produced output data types
        can_connect_to: Module patterns this can connect to
        can_receive_from: Module patterns this can receive from
    """
    def decorator(cls):
        # Ensure class inherits from CompositeModule
        if not issubclass(cls, CompositeModule):
            raise TypeError(f"{cls.__name__} must inherit from CompositeModule")

        # Step 1: Validate (import-time hard fail)
        _validate_composite_registration(module_id, steps)

        # Step 2: Auto-derive from steps
        inferred = _infer_from_steps(steps or [])

        # Step 3: Resolve values (manual > inferred > default)
        final_input_types = input_types if input_types is not None else inferred.get('input_types', [])
        final_output_types = output_types if output_types is not None else inferred.get('output_types', [])
        final_can_receive = can_receive_from if can_receive_from is not None else inferred.get('can_receive_from', ['*'])
        final_can_connect = can_connect_to if can_connect_to is not None else inferred.get('can_connect_to', ['*'])

        cls.module_id = module_id
        cls.steps = steps or []

        # Determine category from module_id if not provided
        resolved_category = category or (module_id.split('.')[1] if '.' in module_id else 'composite')

        # Build metadata
        metadata = {
            "module_id": module_id,
            "version": version,
            "level": "composite",
            "category": resolved_category,
            "subcategory": subcategory,
            "tags": tags or [],

            # Context for connection validation
            "requires_context": requires_context or [],
            "provides_context": provides_context or [],

            # UI metadata (prefer new ui_* fields, fallback to legacy)
            "ui_visibility": ui_visibility.value if isinstance(ui_visibility, UIVisibility) else ui_visibility,
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

            # UI form generation schema
            "ui_params_schema": ui_params_schema or params_schema or {},

            # Legacy fields (for backward compatibility)
            "label": ui_label or label or module_id,
            "description": ui_description or description or "",
            "icon": ui_icon or icon,
            "color": ui_color or color,

            # Connection types (auto-derived or manual)
            "input_types": final_input_types,
            "output_types": final_output_types,

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

            # Connection rules (auto-derived or manual)
            "can_connect_to": final_can_connect,
            "can_receive_from": final_can_receive,

            # Steps definition
            "steps": steps or [],

            # Schema
            "params_schema": params_schema or {},
            "output_schema": output_schema or {},

            # Execution settings
            "timeout": timeout,
            "retryable": retryable,
            "max_retries": max_retries,

            # Documentation
            "examples": examples or [],
            "author": author,
            "license": license
        }

        CompositeRegistry.register(module_id, cls, metadata)
        return cls

    return decorator
