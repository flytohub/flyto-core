"""
LINT FIXTURE: SQL Injection (should FAIL with SEC006)

This module builds SQL queries using string formatting with user input.
Expected: SEC006 error for SQL injection risk.
"""
from typing import Any, Dict

from core.modules.base import BaseModule
from core.modules.registry import register_module
from core.modules.types import NodeType, EdgeType, DataType


@register_module(
    module_id='test.sql_injection_fixture',
    version='1.0.0',
    category='test',
    tags=['test', 'fixture', 'security'],
    label='SQL Injection Test',
    label_key='modules.test.sql_injection.label',
    description='Test module with SQL injection vulnerability (should fail SEC006)',
    description_key='modules.test.sql_injection.description',
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
            'type': 'object',
            'description': 'Query result',
            'description_key': 'test.output.result'
        }
    },
    author='Flyto Team',
    license='MIT',
    timeout_ms=5000,
)
class SQLInjectionModule(BaseModule):
    """Module with SQL injection vulnerability."""

    module_name = "SQL Injection Test"
    module_description = "Test SQL injection detection"

    def validate_params(self):
        self.user_id = self.get_param('user_id', '1')

    async def execute(self) -> Dict[str, Any]:
        # SECURITY BUG: SQL injection - should be caught by SEC006
        query = f"SELECT * FROM users WHERE id = {self.user_id}"
        # In real code this would execute the query
        return {'result': {'query': query}}
