"""
Env Set Module
Set an environment variable in the current process.
"""
import logging
import os
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError, ModuleError

logger = logging.getLogger(__name__)


@register_module(
    module_id='env.set',
    version='1.0.0',
    category='env',
    tags=['env', 'environment', 'variable', 'config', 'set'],
    label='Set Environment Variable',
    label_key='modules.env.set.label',
    description='Set an environment variable in the current process',
    description_key='modules.env.set.description',
    icon='Settings',
    color='#059669',

    input_types=['string'],
    output_types=['string'],

    can_receive_from=['*'],
    can_connect_to=['*'],

    timeout_ms=5000,
    retryable=False,
    concurrent_safe=False,

    requires_credentials=False,
    handles_sensitive_data=True,
    required_permissions=[],

    params_schema=compose(
        field(
            'name',
            type='string',
            label='Variable Name',
            label_key='modules.env.set.params.name.label',
            description='Name of the environment variable to set',
            description_key='modules.env.set.params.name.description',
            required=True,
            placeholder='MY_APP_KEY',
            group=FieldGroup.BASIC,
        ),
        field(
            'value',
            type='string',
            label='Value',
            label_key='modules.env.set.params.value.label',
            description='Value to assign to the environment variable',
            description_key='modules.env.set.params.value.description',
            required=True,
            placeholder='my-secret-value',
            group=FieldGroup.BASIC,
        ),
    ),
    output_schema={
        'name': {
            'type': 'string',
            'description': 'Variable name',
            'description_key': 'modules.env.set.output.name.description',
        },
        'value': {
            'type': 'string',
            'description': 'New value that was set',
            'description_key': 'modules.env.set.output.value.description',
        },
        'previous_value': {
            'type': 'string',
            'description': 'Previous value (null if not previously set)',
            'description_key': 'modules.env.set.output.previous_value.description',
        },
    },
    examples=[
        {
            'title': 'Set an environment variable',
            'title_key': 'modules.env.set.examples.basic.title',
            'params': {
                'name': 'MY_APP_PORT',
                'value': '3000',
            },
        }
    ],
)
async def env_set(context: Dict[str, Any]) -> Dict[str, Any]:
    """Set an environment variable in the current process."""
    params = context['params']
    name = params.get('name')
    value = params.get('value')

    if not name:
        raise ValidationError("Missing required parameter: name", field="name")
    if value is None:
        raise ValidationError("Missing required parameter: value", field="value")

    # Capture previous value before setting
    previous_value = os.environ.get(name)

    os.environ[name] = str(value)

    return {
        'ok': True,
        'data': {
            'name': name,
            'value': str(value),
            'previous_value': previous_value,
        },
    }
