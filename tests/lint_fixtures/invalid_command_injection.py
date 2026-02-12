"""
LINT FIXTURE: Command Injection (should FAIL with SEC005)

This module uses subprocess.run with shell=True and user input.
Expected: SEC005 error for command injection risk.
"""
from typing import Any, Dict
import subprocess

from core.modules.base import BaseModule
from core.modules.registry import register_module
from core.modules.types import NodeType, EdgeType, DataType


@register_module(
    module_id='test.command_injection_fixture',
    version='1.0.0',
    category='test',
    tags=['test', 'fixture', 'security'],
    label='Command Injection Test',
    label_key='modules.test.command_injection.label',
    description='Test module with command injection vulnerability (should fail SEC005)',
    description_key='modules.test.command_injection.description',
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
            'description': 'Command output',
            'description_key': 'test.output.result'
        }
    },
    author='Flyto Team',
    license='MIT',
    timeout_ms=5000,
)
class CommandInjectionModule(BaseModule):
    """Module with command injection vulnerability."""

    module_name = "Command Injection Test"
    module_description = "Test command injection detection"

    def validate_params(self):
        self.user_input = self.get_param('command', 'ls')

    async def execute(self) -> Dict[str, Any]:
        # SECURITY BUG: Command injection - should be caught by SEC005
        cmd = f"echo {self.user_input}"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return {'result': result.stdout}
