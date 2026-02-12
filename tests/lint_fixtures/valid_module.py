"""
LINT FIXTURE: Valid Module (should PASS)

This module follows all best practices and should pass all validation rules.
"""
from typing import Any, Dict

from core.modules.base import BaseModule
from core.modules.registry import register_module
from core.modules.types import NodeType, EdgeType, DataType


@register_module(
    module_id='test.valid_fixture',
    version='1.0.0',
    category='test',
    tags=['test', 'fixture', 'valid'],
    label='Valid Test Module',
    label_key='modules.test.valid_fixture.label',
    description='A valid test module for lint fixture testing',
    description_key='modules.test.valid_fixture.description',
    icon='Check',
    color='#10B981',

    can_receive_from=['*'],
    can_connect_to=['*'],
    node_type=NodeType.STANDARD,

    input_ports=[
        {
            'id': 'input',
            'label': 'Input',
            'label_key': 'modules.test.valid_fixture.ports.input',
            'data_type': DataType.ANY.value,
            'edge_type': EdgeType.CONTROL.value,
            'max_connections': 1,
            'required': True
        }
    ],

    output_ports=[
        {
            'id': 'output',
            'label': 'Output',
            'label_key': 'modules.test.valid_fixture.ports.output',
            'event': 'output',
            'color': '#10B981',
            'edge_type': EdgeType.CONTROL.value
        }
    ],

    retryable=True,
    concurrent_safe=True,
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    output_schema={
        'result': {
            'type': 'string',
            'description': 'The processed result',
            'description_key': 'modules.test.valid_fixture.output.result.description'
        }
    },

    examples=[
        {
            'name': 'Basic usage',
            'description': 'Process input data',
            'params': {'value': 'test'}
        }
    ],
    author='Flyto Team',
    license='MIT',
    timeout_ms=5000,
)
class ValidTestModule(BaseModule):
    """Valid test module for lint fixture testing."""

    module_name = "Valid Test Module"
    module_description = "A valid test module for lint fixture testing"

    def validate_params(self):
        self.value = self.get_param('value', 'default')

    async def execute(self) -> Dict[str, Any]:
        return {
            '__event__': 'output',
            'result': f"Processed: {self.value}"
        }
