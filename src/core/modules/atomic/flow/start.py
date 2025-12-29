"""
Start Module - Explicit workflow start node

Workflow Spec v1.1:
- Start node marks explicit workflow beginning
- No input ports
- Single output port
"""
from typing import Any, Dict
from datetime import datetime
from ...base import BaseModule
from ...registry import register_module
from ...types import NodeType, EdgeType, DataType


@register_module(
    module_id='flow.start',
    version='1.0.0',
    category='flow',
    tags=['flow', 'start', 'begin', 'entry', 'control'],
    label='Start',
    label_key='modules.flow.start.label',
    description='Explicit workflow start node',
    description_key='modules.flow.start.description',
    icon='Play',
    color='#10B981',

    # Workflow Spec v1.1
    node_type=NodeType.START,

    # No input ports - this is an entry point
    input_ports=[],

    output_ports=[
        {
            'id': 'start',
            'label': 'Start',
            'label_key': 'modules.flow.start.ports.start',
            'event': 'start',
            'color': '#10B981',
            'edge_type': EdgeType.CONTROL.value
        }
    ],

    retryable=False,
    concurrent_safe=True,
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['flow.control'],

    params_schema={},

    output_schema={
        '__event__': {'type': 'string', 'description': 'Event for routing (start)'},
        'started_at': {'type': 'string', 'description': 'ISO timestamp of start'},
        'workflow_id': {'type': 'string', 'description': 'Workflow ID if available'}
    },

    examples=[
        {
            'name': 'Simple start',
            'description': 'Begin workflow execution',
            'params': {}
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class StartModule(BaseModule):
    """
    Start Module (Spec v1.1)

    Explicit start node for workflows.
    Marks the beginning of workflow execution.
    """

    module_name = "Start"
    module_description = "Explicit workflow start node"
    required_permission = "flow.control"

    def validate_params(self):
        # No required params
        pass

    async def execute(self) -> Dict[str, Any]:
        """
        Mark workflow start.

        Returns:
            Dict with __event__ 'start' for engine routing
        """
        started_at = datetime.utcnow().isoformat()
        workflow_id = self.context.get('workflow_id')
        execution_id = self.context.get('execution_id')

        return {
            '__event__': 'start',
            'outputs': {
                'start': {
                    'started_at': started_at,
                    'workflow_id': workflow_id,
                    'execution_id': execution_id
                }
            },
            'started_at': started_at,
            'workflow_id': workflow_id,
            'execution_id': execution_id
        }
