"""
Composite Module Registration Decorator
"""
from typing import Any, Dict, List, Optional

from ...types import UIVisibility
from ....constants import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT_SECONDS,
)
from .registry import CompositeRegistry
from .module import CompositeModule


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

    # UI form generation
    ui_params_schema: Optional[Dict[str, Any]] = None,

    # Legacy display fields (deprecated, use ui_* instead)
    label: Optional[str] = None,
    label_key: Optional[str] = None,
    description: Optional[str] = None,
    description_key: Optional[str] = None,
    icon: Optional[str] = None,
    color: Optional[str] = None,

    # Connection types
    input_types: Optional[List[str]] = None,
    output_types: Optional[List[str]] = None,

    # Connection rules (which modules can connect to/from this composite)
    can_connect_to: Optional[List[str]] = None,
    can_receive_from: Optional[List[str]] = None,

    # Steps definition
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

    Composite modules are the primary interface for normal users.
    They combine multiple atomic modules into a single, easy-to-use action.

    Example:
        @register_composite(
            module_id='composite.browser.search_and_screenshot',
            category='browser',
            tags=['search', 'screenshot'],

            requires_context=None,
            provides_context=['file'],

            ui_visibility=UIVisibility.DEFAULT,
            ui_label='Search and Screenshot',
            ui_description='Search the web and capture screenshot',
            ui_group='Browser / Common Tasks',
            ui_icon='Search',
            ui_color='#4285F4',

            ui_params_schema={
                'query': {
                    'type': 'string',
                    'label': 'Search Query',
                    'required': True,
                    'ui_component': 'input',
                },
                'engine': {
                    'type': 'string',
                    'label': 'Search Engine',
                    'options': ['google', 'bing'],
                    'default': 'google',
                    'ui_component': 'select',
                }
            },

            steps=[
                {'id': 'launch', 'module': 'browser.launch'},
                {'id': 'search', 'module': 'browser.goto', 'params': {...}},
            ]
        )
        class SearchAndScreenshot(CompositeModule):
            pass

    Args:
        module_id: Unique identifier (e.g., "composite.browser.search_and_screenshot")
        version: Semantic version
        category: Primary category
        subcategory: Subcategory
        tags: List of tags for filtering

        requires_context: List of context types this composite requires
        provides_context: List of context types this composite provides

        ui_visibility: UI visibility level (DEFAULT/EXPERT/HIDDEN)
        ui_label: Display name for UI
        ui_label_key: i18n key for label
        ui_description: Description for UI
        ui_description_key: i18n key for description
        ui_group: UI grouping category
        ui_icon: Lucide icon name
        ui_color: Hex color code
        ui_params_schema: Schema for UI form generation

        steps: List of atomic steps to execute
        params_schema: Parameter definitions
        output_schema: Output structure definition

        timeout: Execution timeout in seconds
        retryable: Whether module can be retried
        max_retries: Maximum retry attempts
        examples: Usage examples
        author: Module author
        license: License identifier
    """
    def decorator(cls):
        # Ensure class inherits from CompositeModule
        if not issubclass(cls, CompositeModule):
            raise TypeError(f"{cls.__name__} must inherit from CompositeModule")

        cls.module_id = module_id
        cls.steps = steps or []

        # Determine category from module_id if not provided
        resolved_category = category or module_id.split('.')[1] if '.' in module_id else 'composite'

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

            # UI form generation schema
            "ui_params_schema": ui_params_schema or params_schema or {},

            # Legacy fields (for backward compatibility)
            "label": ui_label or label or module_id,
            "description": ui_description or description or "",
            "icon": ui_icon or icon,
            "color": ui_color or color,

            # Connection types
            "input_types": input_types or [],
            "output_types": output_types or [],

            # Connection rules
            "can_connect_to": can_connect_to or ["*"],
            "can_receive_from": can_receive_from or ["*"],

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
