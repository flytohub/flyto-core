"""
LINT FIXTURE: Unsafe eval() Usage (should FAIL with SEC007)

This module uses eval() which is dangerous without proper sandboxing.
Expected: SEC007 error for dangerous eval usage.

Note: Modules tagged with 'breakpoint', 'debugger', or 'hitl' are exempt.
"""
from typing import Any, Dict

from core.modules.base import BaseModule
from core.modules.registry import register_module
from core.modules.types import NodeType, EdgeType, DataType


@register_module(
    module_id='test.eval_usage_fixture',
    version='1.0.0',
    category='test',
    tags=['test', 'fixture', 'security'],  # No exemption tags
    label='Eval Usage Test',
    label_key='modules.test.eval_usage.label',
    description='Test module with unsafe eval usage (should fail SEC007)',
    description_key='modules.test.eval_usage.description',
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
            'type': 'any',
            'description': 'Eval result',
            'description_key': 'test.output.result'
        }
    },
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=5000,
)
class EvalUsageModule(BaseModule):
    """Module with unsafe eval usage."""

    module_name = "Eval Usage Test"
    module_description = "Test eval detection"

    def validate_params(self):
        self.expression = self.get_param('expression', '1+1')

    async def execute(self) -> Dict[str, Any]:
        # SECURITY BUG: Unsafe eval - should be caught by SEC007
        result = eval(self.expression)
        return {'result': result}
