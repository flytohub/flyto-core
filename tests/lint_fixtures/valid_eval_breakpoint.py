"""
LINT FIXTURE: Safe eval() Usage in Breakpoint (should PASS)

This module uses eval() but is tagged as 'breakpoint' which is allowed.
Expected: Should PASS - breakpoint modules can use controlled eval.
"""
from typing import Any, Dict

from core.modules.base import BaseModule
from core.modules.registry import register_module
from core.modules.types import NodeType, EdgeType, DataType


@register_module(
    module_id='test.eval_breakpoint_fixture',
    version='1.0.0',
    category='test',
    tags=['test', 'fixture', 'breakpoint', 'hitl'],  # Exempt tags present
    label='Eval Breakpoint Test',
    label_key='modules.test.eval_breakpoint.label',
    description='Test module with eval in breakpoint context (should pass)',
    description_key='modules.test.eval_breakpoint.description',
    icon='Hand',
    color='#8B5CF6',

    can_receive_from=['*'],
    can_connect_to=['*'],
    node_type=NodeType.BREAKPOINT,

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
            'id': 'approved',
            'label': 'Approved',
            'label_key': 'modules.test.eval_breakpoint.ports.approved',
            'event': 'approved',
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
            'description': 'Evaluation result',
            'description_key': 'test.output.result'
        }
    },
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=5000,
)
class EvalBreakpointModule(BaseModule):
    """Module with eval in breakpoint context - allowed."""

    module_name = "Eval Breakpoint Test"
    module_description = "Test eval exemption for breakpoint modules"

    def validate_params(self):
        self.condition = self.get_param('condition', 'True')

    async def execute(self) -> Dict[str, Any]:
        # OK: eval in breakpoint module with controlled context
        safe_context = {
            'True': True,
            'False': False,
            '__builtins__': {'len': len, 'str': str}
        }
        result = eval(self.condition, safe_context)
        return {'__event__': 'approved' if result else 'rejected', 'result': result}
