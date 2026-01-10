"""
Express Module Registration - Simplified decorator for quick module creation

The @module decorator provides a minimal-boilerplate way to create modules,
automatically inferring most metadata from the class definition.

Usage:
    @module('math.abs')
    class AbsModule(BaseModule):
        '''Get absolute value of a number.'''

        def validate_params(self):
            self.number = self.params.get('number', 0)

        async def execute(self):
            return self.success(data=abs(self.number))

This is equivalent to the full @register_module with all defaults:
    @register_module(
        module_id='math.abs',
        version='1.0.0',
        category='math',           # from module_id
        ui_label='Abs Module',     # from class name
        ui_description='Get absolute value of a number.',  # from docstring
        can_receive_from=['*'],
        can_connect_to=['*'],
        ...
    )

For more control, use @register_module directly or pass overrides to @module:
    @module('math.abs', version='2.0.0', ui_icon='Calculator')
"""

import re
from typing import Any, Dict, List, Optional, Type

from .registry.decorators import register_module
from .types import (
    ModuleLevel,
    StabilityLevel,
    NodeType,
)


def _class_name_to_label(class_name: str) -> str:
    """
    Convert class name to human-readable label.

    Examples:
        AbsModule -> Abs
        BrowserLaunchModule -> Browser Launch
        HTTPRequestModule -> HTTP Request
        JSONParseModule -> JSON Parse
    """
    # Remove common suffixes
    name = class_name
    for suffix in ('Module', 'Mod', 'Handler', 'Action'):
        if name.endswith(suffix):
            name = name[:-len(suffix)]
            break

    # Insert spaces before capital letters (but handle acronyms)
    # HTTPRequest -> HTTP Request (not H T T P Request)
    result = []
    i = 0
    while i < len(name):
        char = name[i]
        if i > 0 and char.isupper():
            # Check if this is part of an acronym
            prev_upper = name[i-1].isupper()
            next_lower = (i + 1 < len(name) and name[i+1].islower())

            if not prev_upper or next_lower:
                result.append(' ')
        result.append(char)
        i += 1

    return ''.join(result).strip()


def _extract_docstring(cls: Type) -> str:
    """Extract first line of docstring as description."""
    if not cls.__doc__:
        return ""

    doc = cls.__doc__.strip()
    # Get first line only
    first_line = doc.split('\n')[0].strip()
    return first_line


def _infer_output_schema(cls: Type) -> Dict[str, Any]:
    """
    Infer output schema from class.

    Default output schema for modules using self.success():
        {
            "type": "object",
            "properties": {
                "result": {"type": "any", "description": "Module result"}
            }
        }
    """
    # For now, return a generic schema
    # In the future, we could analyze execute() return statements
    return {
        "type": "object",
        "properties": {
            "result": {
                "type": "any",
                "description": "Module result",
            }
        }
    }


def module(
    module_id: str,
    *,
    # Optional overrides (most are auto-inferred)
    version: str = "1.0.0",
    stability: StabilityLevel = StabilityLevel.STABLE,
    level: ModuleLevel = ModuleLevel.ATOMIC,
    category: Optional[str] = None,
    tags: Optional[List[str]] = None,

    # UI overrides (auto-inferred from class)
    ui_label: Optional[str] = None,
    ui_description: Optional[str] = None,
    ui_icon: Optional[str] = None,
    ui_color: Optional[str] = None,

    # Schema overrides (auto-inferred)
    params_schema: Optional[Dict[str, Any]] = None,
    output_schema: Optional[Dict[str, Any]] = None,

    # Connection overrides (default to ['*'])
    can_receive_from: Optional[List[str]] = None,
    can_connect_to: Optional[List[str]] = None,

    # Node type (default STANDARD)
    node_type: NodeType = NodeType.STANDARD,

    # Execution settings
    timeout_ms: Optional[int] = None,
    retryable: bool = False,
    max_retries: int = 3,

    # Security (default: no special requirements)
    requires_credentials: bool = False,

    # Any additional kwargs passed to register_module
    **extra_kwargs: Any,
):
    """
    Express module registration decorator.

    Minimal usage (1 parameter):
        @module('math.abs')
        class AbsModule(BaseModule):
            '''Get absolute value.'''
            ...

    With overrides:
        @module('math.abs', ui_icon='Calculator', timeout_ms=5000)
        class AbsModule(BaseModule):
            ...

    Auto-inferred values:
        - category: First part of module_id (e.g., 'math' from 'math.abs')
        - ui_label: From class name (e.g., 'Abs' from 'AbsModule')
        - ui_description: From class docstring
        - can_receive_from: ['*'] (accepts any predecessor)
        - can_connect_to: ['*'] (can connect to any successor)
        - output_schema: Generic schema with 'result' field

    Args:
        module_id: Module identifier (e.g., 'category.action')
        version: Semantic version (default: '1.0.0')
        stability: Stability level (default: STABLE)
        level: Module level (default: ATOMIC)
        category: Override auto-detected category
        tags: Module tags for filtering
        ui_label: Override auto-detected label
        ui_description: Override auto-detected description
        ui_icon: Lucide icon name
        ui_color: Hex color code
        params_schema: Parameter schema (optional)
        output_schema: Output schema (optional, auto-generated)
        can_receive_from: Connection rules (default: ['*'])
        can_connect_to: Connection rules (default: ['*'])
        node_type: Node type (default: STANDARD)
        timeout_ms: Execution timeout in ms
        retryable: Enable retry on failure
        max_retries: Max retry attempts
        requires_credentials: Needs API keys
        **extra_kwargs: Additional args for register_module

    Returns:
        Decorated module class
    """
    def decorator(cls: Type) -> Type:
        # Auto-infer values from class
        resolved_category = category or module_id.split('.')[0]
        resolved_label = ui_label or _class_name_to_label(cls.__name__)
        resolved_description = ui_description or _extract_docstring(cls)
        resolved_output_schema = output_schema or _infer_output_schema(cls)

        # Default connection rules to ['*'] (accept all)
        resolved_can_receive = can_receive_from if can_receive_from is not None else ['*']
        resolved_can_connect = can_connect_to if can_connect_to is not None else ['*']

        # Build the full register_module call
        return register_module(
            module_id=module_id,
            version=version,
            stability=stability,
            level=level,
            category=resolved_category,
            tags=tags,

            # UI
            ui_label=resolved_label,
            ui_description=resolved_description,
            ui_icon=ui_icon,
            ui_color=ui_color,

            # Schema
            params_schema=params_schema or {},
            output_schema=resolved_output_schema,

            # Connections
            can_receive_from=resolved_can_receive,
            can_connect_to=resolved_can_connect,

            # Node
            node_type=node_type,

            # Execution
            timeout_ms=timeout_ms,
            retryable=retryable,
            max_retries=max_retries,

            # Security
            requires_credentials=requires_credentials,

            # Pass through any extra kwargs
            **extra_kwargs,
        )(cls)

    return decorator


# Alias for even shorter syntax
mod = module


# =============================================================================
# Convenience helpers for validate_params
# =============================================================================

class ParamHelper:
    """
    Mixin or helper for cleaner parameter validation.

    Usage in validate_params():
        self.url = self.require('url', expected_type=str)
        self.timeout = self.optional('timeout', default=30, expected_type=int)
    """

    def require(self, name: str, *, expected_type: type = str, default: Any = None) -> Any:
        """
        Get a required parameter.

        Args:
            name: Parameter name
            expected_type: Expected type (str, int, float, bool, list, dict)
            default: Default value if not provided

        Returns:
            Parameter value

        Raises:
            ValidationError: If parameter is missing or wrong type
        """
        from .errors import ValidationError, InvalidTypeError

        value = self.params.get(name, default)

        if value is None:
            raise ValidationError(f"Missing required parameter: {name}", field=name)

        if not isinstance(value, expected_type):
            raise InvalidTypeError(
                f"Parameter '{name}' must be {expected_type.__name__}",
                expected_type=expected_type.__name__,
                actual_type=type(value).__name__,
                field=name,
            )

        return value

    def optional(self, name: str, *, default: Any = None, expected_type: type = None) -> Any:
        """
        Get an optional parameter.

        Args:
            name: Parameter name
            default: Default value if not provided
            expected_type: Expected type (optional validation)

        Returns:
            Parameter value or default
        """
        from .errors import InvalidTypeError

        value = self.params.get(name, default)

        if value is not None and expected_type is not None and not isinstance(value, expected_type):
            raise InvalidTypeError(
                f"Parameter '{name}' must be {expected_type.__name__}",
                expected_type=expected_type.__name__,
                actual_type=type(value).__name__,
                field=name,
            )

        return value


# =============================================================================
# Quick module template
# =============================================================================

def create_simple_module(
    module_id: str,
    execute_fn,
    *,
    description: str = "",
    params: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> Type:
    """
    Create a simple module from a function.

    Usage:
        async def my_execute(self):
            return self.success(result=42)

        MyModule = create_simple_module(
            'test.answer',
            my_execute,
            description='Return the answer to everything'
        )

    Args:
        module_id: Module identifier
        execute_fn: Async execute function
        description: Module description
        params: Expected parameters
        **kwargs: Additional register_module args

    Returns:
        Module class
    """
    from .base import BaseModule

    @module(module_id, ui_description=description, params_schema=params or {}, **kwargs)
    class SimpleModule(BaseModule):
        __doc__ = description

        def validate_params(self) -> None:
            pass

        async def execute(self):
            return await execute_fn(self)

    return SimpleModule
