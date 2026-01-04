"""
Parameter Resolution Utilities for Loop Module

Resolves variable references like ${var} in loop parameters.
"""
from typing import Any, Dict


def resolve_params(params: Dict, context: Dict) -> Dict:
    """
    Resolve variable references in parameters.

    Supports:
    - String variables: "${item}" -> context['item'] value
    - Nested dicts: Recursively resolve
    - Lists: Resolve dict items within lists

    Args:
        params: Parameter dict with potential ${var} references
        context: Context dict containing variable values

    Returns:
        Resolved parameters with actual values

    Example:
        >>> context = {'item': 'value', 'index': 0}
        >>> resolve_params({'key': '${item}'}, context)
        {'key': 'value'}
    """
    resolved = {}
    for key, value in params.items():
        if isinstance(value, str) and value.startswith('${') and value.endswith('}'):
            var_name = value[2:-1]
            resolved[key] = context.get(var_name, value)
        elif isinstance(value, dict):
            resolved[key] = resolve_params(value, context)
        elif isinstance(value, list):
            resolved[key] = [
                resolve_params(item, context) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            resolved[key] = value
    return resolved


def resolve_variable(value: Any, context: Dict) -> Any:
    """
    Resolve a single variable reference.

    Supports dot notation for nested access (e.g., 'result.items').

    Args:
        value: Value to resolve (may be ${var} string)
        context: Context dict

    Returns:
        Resolved value or original if not a variable reference
    """
    import json

    if not isinstance(value, str):
        return value

    # Try to parse JSON string (e.g., "[1,2,3]" -> [1,2,3])
    if value.startswith('[') and value.endswith(']'):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            pass

    if not (value.startswith('${') and value.endswith('}')):
        return value

    var_name = value[2:-1]

    # Support dot notation for attributes
    if '.' in var_name:
        parts = var_name.split('.')
        result = context.get(parts[0])
        for part in parts[1:]:
            if result is None:
                break
            if isinstance(result, dict):
                result = result.get(part)
            else:
                result = getattr(result, part, None)
        return result if result is not None else []

    # For simple variables, return empty list if not found (for items param)
    resolved = context.get(var_name)
    if resolved is not None:
        return resolved

    # Variable not found - return empty list as default for iteration
    return []
