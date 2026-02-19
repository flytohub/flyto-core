# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

"""
Env Get Module
Get the value of an environment variable.
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
    module_id='env.get',
    version='1.0.0',
    category='env',
    tags=['env', 'environment', 'variable', 'config', 'get'],
    label='Get Environment Variable',
    label_key='modules.env.get.label',
    description='Get the value of an environment variable',
    description_key='modules.env.get.description',
    icon='Settings',
    color='#059669',

    input_types=['string'],
    output_types=['string'],

    can_receive_from=['*'],
    can_connect_to=['*'],

    timeout_ms=5000,
    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=True,
    required_permissions=[],

    params_schema=compose(
        field(
            'name',
            type='string',
            label='Variable Name',
            label_key='modules.env.get.params.name.label',
            description='Name of the environment variable',
            description_key='modules.env.get.params.name.description',
            required=True,
            placeholder='HOME',
            group=FieldGroup.BASIC,
        ),
        field(
            'default',
            type='string',
            label='Default Value',
            label_key='modules.env.get.params.default.label',
            description='Default value if the variable is not set',
            description_key='modules.env.get.params.default.description',
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'name': {
            'type': 'string',
            'description': 'Variable name',
            'description_key': 'modules.env.get.output.name.description',
        },
        'value': {
            'type': 'string',
            'description': 'Variable value (or default if not set)',
            'description_key': 'modules.env.get.output.value.description',
        },
        'exists': {
            'type': 'boolean',
            'description': 'Whether the variable exists in the environment',
            'description_key': 'modules.env.get.output.exists.description',
        },
    },
    examples=[
        {
            'title': 'Get HOME variable',
            'title_key': 'modules.env.get.examples.basic.title',
            'params': {
                'name': 'HOME',
            },
        },
        {
            'title': 'Get variable with default',
            'title_key': 'modules.env.get.examples.default.title',
            'params': {
                'name': 'MY_APP_PORT',
                'default': '8080',
            },
        },
    ],
)
async def env_get(context: Dict[str, Any]) -> Dict[str, Any]:
    """Get the value of an environment variable."""
    params = context['params']
    name = params.get('name')
    default = params.get('default')

    if not name:
        raise ValidationError("Missing required parameter: name", field="name")

    exists = name in os.environ
    value = os.environ.get(name, default)

    return {
        'ok': True,
        'data': {
            'name': name,
            'value': value,
            'exists': exists,
        },
    }
