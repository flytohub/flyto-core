"""
Logic Contains Module
Check if a value contains another value
"""
from typing import Any, Dict

from ...registry import register_module
from ...errors import ValidationError


@register_module(
    module_id='logic.contains',
    version='1.0.0',
    category='logic',
    tags=['logic', 'contains', 'include', 'search', 'condition'],
    label='Logic Contains',
    label_key='modules.logic.contains.label',
    description='Check if a value contains another value',
    description_key='modules.logic.contains.description',
    icon='Search',
    color='#14B8A6',
    input_types=['string', 'array', 'object'],
    output_types=['boolean'],

    can_receive_from=['*'],
    can_connect_to=['flow.*', 'data.*'],

    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema={
        'haystack': {
            'type': 'text',
            'label': 'Haystack',
            'label_key': 'modules.logic.contains.params.haystack.label',
            'description': 'Value to search in (string, array, or object)',
            'description_key': 'modules.logic.contains.params.haystack.description',
            'placeholder': 'The container value',
            'required': True
        },
        'needle': {
            'type': 'text',
            'label': 'Needle',
            'label_key': 'modules.logic.contains.params.needle.label',
            'description': 'Value to search for',
            'description_key': 'modules.logic.contains.params.needle.description',
            'placeholder': 'The value to find',
            'required': True
        },
        'case_sensitive': {
            'type': 'boolean',
            'label': 'Case Sensitive',
            'label_key': 'modules.logic.contains.params.case_sensitive.label',
            'description': 'Case sensitive search for strings',
            'description_key': 'modules.logic.contains.params.case_sensitive.description',
            'default': True,
            'required': False
        }
    },
    output_schema={
        'result': {
            'type': 'boolean',
            'description': 'Whether haystack contains needle',
            'description_key': 'modules.logic.contains.output.result.description'
        },
        'position': {
            'type': 'number',
            'description': 'Position/index where found (-1 if not found)',
            'description_key': 'modules.logic.contains.output.position.description'
        },
        'count': {
            'type': 'number',
            'description': 'Number of occurrences',
            'description_key': 'modules.logic.contains.output.count.description'
        }
    },
    timeout_ms=5000,
)
async def logic_contains(context: Dict[str, Any]) -> Dict[str, Any]:
    """Check if a value contains another value."""
    params = context['params']
    haystack = params.get('haystack')
    needle = params.get('needle')
    case_sensitive = params.get('case_sensitive', True)

    if haystack is None:
        raise ValidationError("Missing required parameter: haystack", field="haystack")
    if needle is None:
        raise ValidationError("Missing required parameter: needle", field="needle")

    result = False
    position = -1
    count = 0

    if isinstance(haystack, str):
        search_haystack = haystack if case_sensitive else haystack.lower()
        search_needle = str(needle) if case_sensitive else str(needle).lower()
        result = search_needle in search_haystack
        if result:
            position = search_haystack.find(search_needle)
            count = search_haystack.count(search_needle)

    elif isinstance(haystack, list):
        for i, item in enumerate(haystack):
            if item == needle:
                if position == -1:
                    position = i
                count += 1
                result = True

    elif isinstance(haystack, dict):
        if needle in haystack:
            result = True
            position = list(haystack.keys()).index(needle)
            count = 1

    return {
        'ok': True,
        'data': {
            'result': result,
            'position': position,
            'count': count
        }
    }
