"""
Random UUID Module
Generate random UUID (Universally Unique Identifier).
"""
from typing import Any, Dict
import uuid as uuid_lib

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup


@register_module(
    module_id='random.uuid',
    version='1.0.0',
    category='random',
    tags=['random', 'uuid', 'unique', 'identifier', 'generate'],
    label='Generate UUID',
    label_key='modules.random.uuid.label',
    description='Generate random UUID (v4)',
    description_key='modules.random.uuid.description',
    icon='Key',
    color='#F59E0B',
    input_types=[],
    output_types=['string'],

    can_receive_from=['*'],
    can_connect_to=['data.*', 'string.*', 'file.*', 'api.*', 'notification.*', 'flow.*'],

    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema=compose(
        field(
            'uppercase',
            type='boolean',
            label='Uppercase',
            label_key='modules.random.uuid.params.uppercase.label',
            description='Return uppercase UUID',
            description_key='modules.random.uuid.params.uppercase.description',
            default=False,
            group=FieldGroup.OPTIONS,
        ),
        field(
            'remove_hyphens',
            type='boolean',
            label='Remove Hyphens',
            label_key='modules.random.uuid.params.remove_hyphens.label',
            description='Remove hyphens from UUID',
            description_key='modules.random.uuid.params.remove_hyphens.description',
            default=False,
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'uuid': {
            'type': 'string',
            'description': 'Generated UUID',
            'description_key': 'modules.random.uuid.output.uuid.description'
        },
        'version': {
            'type': 'number',
            'description': 'UUID version',
            'description_key': 'modules.random.uuid.output.version.description'
        }
    },
    timeout_ms=5000,
)
async def random_uuid(context: Dict[str, Any]) -> Dict[str, Any]:
    """Generate random UUID."""
    params = context['params']
    uppercase = params.get('uppercase', False)
    remove_hyphens = params.get('remove_hyphens', False)

    new_uuid = str(uuid_lib.uuid4())

    if remove_hyphens:
        new_uuid = new_uuid.replace('-', '')

    if uppercase:
        new_uuid = new_uuid.upper()

    return {
        'ok': True,
        'data': {
            'uuid': new_uuid,
            'version': 4
        }
    }
