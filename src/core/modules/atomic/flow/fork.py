"""
Fork Module - Split execution into parallel branches

Workflow Spec v1.1:
- Fork node with single input and N outputs
- All output ports fire simultaneously
- Returns __event__ for engine routing
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from ...types import NodeType, EdgeType, DataType


@register_module(
    module_id='flow.fork',
    version='1.0.0',
    category='flow',
    tags=['flow', 'fork', 'parallel', 'split', 'control'],
    label='Fork',
    label_key='modules.flow.fork.label',
    description='Split execution into parallel branches',
    description_key='modules.flow.fork.description',
    icon='GitFork',
    color='#06B6D4',

    # Workflow Spec v1.1
    node_type=NodeType.FORK,

    input_ports=[
        {
            'id': 'input',
            'label': 'Input',
            'label_key': 'modules.flow.fork.ports.input',
            'data_type': DataType.ANY.value,
            'edge_type': EdgeType.CONTROL.value,
            'max_connections': 1,
            'required': True
        }
    ],

    output_ports=[
        {
            'id': 'branch_1',
            'label': 'Branch 1',
            'label_key': 'modules.flow.fork.ports.branch_1',
            'event': 'fork',
            'color': '#10B981',
            'edge_type': EdgeType.CONTROL.value
        },
        {
            'id': 'branch_2',
            'label': 'Branch 2',
            'label_key': 'modules.flow.fork.ports.branch_2',
            'event': 'fork',
            'color': '#3B82F6',
            'edge_type': EdgeType.CONTROL.value
        },
        {
            'id': 'error',
            'label': 'Error',
            'label_key': 'common.ports.error',
            'event': 'error',
            'color': '#EF4444',
            'edge_type': EdgeType.CONTROL.value
        }
    ],

    # Dynamic ports for additional branches
    dynamic_ports={
        'output': {
            'from_param': 'branch_count',
            'id_template': 'branch_{index}',
            'label_template': 'Branch {index}',
            'event': 'fork',
            'start_index': 1
        }
    },

    retryable=False,
    concurrent_safe=True,
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['flow.control'],

    params_schema={
        'branch_count': {
            'type': 'integer',
            'label': 'Branch Count',
            'label_key': 'modules.flow.fork.params.branch_count.label',
            'description': 'Number of parallel branches',
            'description_key': 'modules.flow.fork.params.branch_count.description',
            'default': 2,
            'minimum': 2,
            'maximum': 10,
            'required': False
        }
    },

    output_schema={
        '__event__': {'type': 'string', 'description': 'Event for routing (fork/error)'},
        'input_data': {'type': 'any', 'description': 'Input data passed to all branches'},
        'branch_count': {'type': 'integer', 'description': 'Number of branches created'}
    },

    examples=[
        {
            'name': 'Two parallel branches',
            'description': 'Split into two parallel execution paths',
            'params': {
                'branch_count': 2
            }
        },
        {
            'name': 'Three parallel branches',
            'description': 'Split into three parallel execution paths',
            'params': {
                'branch_count': 3
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class ForkModule(BaseModule):
    """
    Fork Module (Spec v1.1)

    Splits a single input into multiple parallel branches.
    All branches receive the same input data and execute simultaneously.

    Note: The workflow engine handles parallel execution.
    This module just signals that all branch ports should fire.
    """

    module_name = "Fork"
    module_description = "Split execution into parallel branches"
    required_permission = "flow.control"

    def validate_params(self):
        self.branch_count = self.params.get('branch_count', 2)

        if not 2 <= self.branch_count <= 10:
            raise ValueError(f"branch_count must be between 2 and 10, got {self.branch_count}")

    async def execute(self) -> Dict[str, Any]:
        """
        Fork execution into parallel branches.

        All branch output ports emit the 'fork' event simultaneously.
        The workflow engine handles parallel execution of connected nodes.

        Returns:
            Dict with __event__ 'fork' for engine routing
        """
        try:
            # Get input data
            input_data = self.context.get('input')

            # Build outputs for each branch
            outputs = {}
            for i in range(1, self.branch_count + 1):
                branch_id = f'branch_{i}'
                outputs[branch_id] = {
                    'input_data': input_data,
                    'branch_index': i
                }

            return {
                # All branches fire on 'fork' event
                '__event__': 'fork',
                'outputs': outputs,
                'input_data': input_data,
                'branch_count': self.branch_count
            }

        except Exception as e:
            return {
                '__event__': 'error',
                'outputs': {
                    'error': {'message': str(e)}
                },
                '__error__': {
                    'code': 'FORK_ERROR',
                    'message': str(e)
                }
            }
