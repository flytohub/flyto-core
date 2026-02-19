"""
LINT FIXTURE: Hardcoded Secret (should FAIL with SEC004)

This module contains a hardcoded API key which is a security vulnerability.
Expected: SEC004 error for hardcoded secret.
"""
from typing import Any, Dict

from core.modules.base import BaseModule
from core.modules.registry import register_module
from core.modules.types import NodeType, EdgeType, DataType


@register_module(
    module_id='test.hardcoded_secret_fixture',
    version='1.0.0',
    category='test',
    tags=['test', 'fixture', 'security'],
    label='Hardcoded Secret Test',
    label_key='modules.test.hardcoded_secret.label',
    description='Test module with hardcoded secret (should fail SEC004)',
    description_key='modules.test.hardcoded_secret.description',
    icon='Warning',
    color='#EF4444',

    can_receive_from=['*'],
    can_connect_to=['*'],
    node_type=NodeType.STANDARD,

    input_ports=[
        {
            'id': 'input',
            'label': 'Input',
            'label_key': 'common.ports.input',
            'data_type': DataType.ANY.value,
            'edge_type': EdgeType.CONTROL.value,
        }
    ],

    output_ports=[
        {
            'id': 'output',
            'label': 'Output',
            'label_key': 'common.ports.output',
            'event': 'output',
            'edge_type': EdgeType.CONTROL.value
        }
    ],

    retryable=False,
    concurrent_safe=True,
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    output_schema={
        'result': {
            'type': 'string',
            'description': 'Result',
            'description_key': 'test.output.result'
        }
    },
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=5000,
)
class HardcodedSecretModule(BaseModule):
    """Module with hardcoded secret - security vulnerability."""

    module_name = "Hardcoded Secret Test"
    module_description = "Test hardcoded secret detection"

    # SECURITY BUG: Hardcoded API key - should be caught by SEC004
    API_KEY = "sk-proj-1234567890abcdefghijklmnopqrstuvwxyz"

    def validate_params(self):
        pass

    async def execute(self) -> Dict[str, Any]:
        # Using hardcoded key
        return {'result': 'test', 'key': self.API_KEY[:8] + '...'}
