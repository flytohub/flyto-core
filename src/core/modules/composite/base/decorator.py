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

    # Connection types
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
            ui_help='This module launches a browser, performs a search, and captures a screenshot.',
            ui_group='Browser / Common Tasks',
            ui_icon='Search',
            ui_color='#4285F4',

            # Connection type labels for UI display
            input_types=['string'],
            input_type_labels={'string': 'Search Query'},
            input_type_descriptions={'string': 'The search term to look for'},

            output_types=['image', 'file'],
            output_type_labels={'image': 'Screenshot', 'file': 'Image File'},
            output_type_descriptions={'image': 'Screenshot of search results'},

            # Connection suggestions for UI guidance
            suggested_predecessors=['file.read', 'string.template'],
            suggested_successors=['file.write', 'notification.send'],

            ui_params_schema={
                'query': {
                    'type': 'string',
                    'label': 'Search Query',
                    'description': 'What to search for',
                    'help': 'Enter keywords separated by spaces',
                    'hint': 'Tip: Use quotes for exact matches',
                    'examples': ['python tutorial', 'latest news'],
                    'required': True,
                    'ui_component': 'input',
                    'validation': {
                        'min_length': 1,
                        'max_length': 200,
                    },
                    'error_messages': {
                        'required': 'Please enter a search query',
                        'min_length': 'Query is too short',
                    },
                },
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
        ui_description: Short description for UI
        ui_description_key: i18n key for description
        ui_help: Detailed help text (expandable in UI)
        ui_help_key: i18n key for help text
        ui_group: UI grouping category
        ui_icon: Lucide icon name
        ui_color: Hex color code
        ui_params_schema: Schema for UI form generation with enhanced fields:
            - help: Detailed field explanation
            - hint: Inline tip displayed below field
            - warning: Warning message (non-blocking)
            - examples: List of example values
            - validation: {pattern, pattern_error, min_length, max_length, min, max}
            - error_messages: Custom error messages for validation types
            - visible_when: Conditional display rules
            - depends_on: Field dependencies

        input_types: List of accepted input data types
        input_type_labels: Human-readable labels for input types
        input_type_descriptions: Detailed descriptions for input types
        output_types: List of produced output data types
        output_type_labels: Human-readable labels for output types
        output_type_descriptions: Detailed descriptions for output types

        suggested_predecessors: Recommended modules to connect before this one
        suggested_successors: Recommended modules to connect after this one
        connection_error_messages: Custom error messages for connection validation

        can_connect_to: Module patterns this can connect to
        can_receive_from: Module patterns this can receive from

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

            # Connection types
            "input_types": input_types or [],
            "output_types": output_types or [],

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
