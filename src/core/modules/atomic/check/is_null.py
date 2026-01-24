"""
Check Is Null Module
Check if a value is null/None.
"""
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup


@register_module(
    module_id='check.is_null',
    version='1.0.0',
    category='check',
    tags=['check', 'null', 'none', 'validate', 'condition', 'advanced'],
    label='Is Null',
    label_key='modules.check.is_null.label',
    description='Check if a value is null/None',
    description_key='modules.check.is_null.description',
    icon='CircleSlash',
    color='#F97316',
    input_types=['any'],
    output_types=['boolean'],

    can_receive_from=['*'],
    can_connect_to=['flow.*', 'logic.*', 'data.*'],

    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema=compose(
        field(
            'value',
            type='any',
            label='Value',
            label_key='modules.check.is_null.params.value.label',
            description='Value to check',
            description_key='modules.check.is_null.params.value.description',
            required=False,
            group=FieldGroup.BASIC,
        ),
    ),
    output_schema={
        'is_null': {
            'type': 'boolean',
            'description': 'Whether value is null',
            'description_key': 'modules.check.is_null.output.is_null.description'
        }
    },
    timeout_ms=5000,
)
async def check_is_null(context: Dict[str, Any]) -> Dict[str, Any]:
    """Check if a value is null/None."""
    params = context['params']
    value = params.get('value')

    return {
        'ok': True,
        'data': {
            'is_null': value is None
        }
    }
