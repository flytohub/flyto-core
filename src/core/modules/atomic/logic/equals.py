"""
Logic Equals Module
Check if two values are equal (deep comparison)
"""
from typing import Any, Dict
import json

from ...registry import register_module


def deep_equals(a: Any, b: Any) -> bool:
    """Deep equality comparison."""
    if type(a) != type(b):
        try:
            if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                return float(a) == float(b)
        except (ValueError, TypeError):
            pass
        return False

    if isinstance(a, dict):
        if set(a.keys()) != set(b.keys()):
            return False
        return all(deep_equals(a[k], b[k]) for k in a)

    if isinstance(a, (list, tuple)):
        if len(a) != len(b):
            return False
        return all(deep_equals(x, y) for x, y in zip(a, b))

    return a == b


@register_module(
    module_id='logic.equals',
    version='1.0.0',
    category='logic',
    tags=['logic', 'equals', 'compare', 'condition'],
    label='Logic Equals',
    label_key='modules.logic.equals.label',
    description='Check if two values are equal',
    description_key='modules.logic.equals.description',
    icon='Equal',
    color='#14B8A6',
    input_types=['any'],
    output_types=['boolean'],

    can_receive_from=['*'],
    can_connect_to=['flow.*', 'data.*'],

    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema={
        'a': {
            'type': 'text',
            'label': 'Value A',
            'label_key': 'modules.logic.equals.params.a.label',
            'description': 'First value to compare',
            'description_key': 'modules.logic.equals.params.a.description',
            'placeholder': 'First value',
            'required': True
        },
        'b': {
            'type': 'text',
            'label': 'Value B',
            'label_key': 'modules.logic.equals.params.b.label',
            'description': 'Second value to compare',
            'description_key': 'modules.logic.equals.params.b.description',
            'placeholder': 'Second value',
            'required': True
        },
        'strict': {
            'type': 'boolean',
            'label': 'Strict',
            'label_key': 'modules.logic.equals.params.strict.label',
            'description': 'Require same type (no type coercion)',
            'description_key': 'modules.logic.equals.params.strict.description',
            'default': False,
            'required': False
        },
        'case_sensitive': {
            'type': 'boolean',
            'label': 'Case Sensitive',
            'label_key': 'modules.logic.equals.params.case_sensitive.label',
            'description': 'Case sensitive string comparison',
            'description_key': 'modules.logic.equals.params.case_sensitive.description',
            'default': True,
            'required': False
        }
    },
    output_schema={
        'result': {
            'type': 'boolean',
            'description': 'Whether values are equal',
            'description_key': 'modules.logic.equals.output.result.description'
        },
        'type_a': {
            'type': 'string',
            'description': 'Type of first value',
            'description_key': 'modules.logic.equals.output.type_a.description'
        },
        'type_b': {
            'type': 'string',
            'description': 'Type of second value',
            'description_key': 'modules.logic.equals.output.type_b.description'
        }
    },
    timeout_ms=5000,
)
async def logic_equals(context: Dict[str, Any]) -> Dict[str, Any]:
    """Check if two values are equal."""
    params = context['params']
    a = params.get('a')
    b = params.get('b')
    strict = params.get('strict', False)
    case_sensitive = params.get('case_sensitive', True)

    type_a = type(a).__name__
    type_b = type(b).__name__

    if not case_sensitive and isinstance(a, str) and isinstance(b, str):
        a = a.lower()
        b = b.lower()

    if strict:
        result = a == b and type(a) == type(b)
    else:
        result = deep_equals(a, b)

    return {
        'ok': True,
        'data': {
            'result': result,
            'type_a': type_a,
            'type_b': type_b
        }
    }
