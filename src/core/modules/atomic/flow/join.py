"""
Join Module - Wait for parallel branches to complete

Workflow Spec v1.1:
- Join node with N inputs and single output
- Strategies: all (wait for all), any (first one), first (first and cancel others)
- Returns __event__ for engine routing
"""
from typing import Any, Dict, List, Optional
from datetime import datetime
from ...base import BaseModule
from ...registry import register_module
from ...types import NodeType, EdgeType, DataType


@register_module(
    module_id='flow.join',
    version='1.0.0',
    category='flow',
    tags=['flow', 'join', 'wait', 'parallel', 'sync', 'control'],
    label='Join',
    label_key='modules.flow.join.label',
    description='Wait for parallel branches to complete',
    description_key='modules.flow.join.description',
    icon='GitPullRequest',
    color='#F59E0B',

    # Workflow Spec v1.1
    node_type=NodeType.JOIN,

    input_ports=[
        {
            'id': 'input_1',
            'label': 'Input 1',
            'label_key': 'modules.flow.join.ports.input_1',
            'data_type': DataType.ANY.value,
            'edge_type': EdgeType.CONTROL.value,
            'max_connections': 1,
            'required': False
        },
        {
            'id': 'input_2',
            'label': 'Input 2',
            'label_key': 'modules.flow.join.ports.input_2',
            'data_type': DataType.ANY.value,
            'edge_type': EdgeType.CONTROL.value,
            'max_connections': 1,
            'required': False
        }
    ],

    output_ports=[
        {
            'id': 'output',
            'label': 'Output',
            'label_key': 'modules.flow.join.ports.output',
            'event': 'joined',
            'color': '#10B981',
            'edge_type': EdgeType.CONTROL.value
        },
        {
            'id': 'timeout',
            'label': 'Timeout',
            'label_key': 'modules.flow.join.ports.timeout',
            'event': 'timeout',
            'color': '#F59E0B',
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

    # Dynamic ports for additional inputs
    dynamic_ports={
        'input': {
            'from_param': 'input_count',
            'id_template': 'input_{index}',
            'label_template': 'Input {index}',
            'start_index': 1
        }
    },

    retryable=False,
    concurrent_safe=True,
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['flow.control'],

    params_schema={
        'strategy': {
            'type': 'string',
            'label': 'Join Strategy',
            'label_key': 'modules.flow.join.params.strategy.label',
            'description': 'How to handle multiple inputs',
            'description_key': 'modules.flow.join.params.strategy.description',
            'enum': ['all', 'any', 'first'],
            'default': 'all',
            'required': False
        },
        'input_count': {
            'type': 'integer',
            'label': 'Input Count',
            'label_key': 'modules.flow.join.params.input_count.label',
            'description': 'Number of input ports',
            'description_key': 'modules.flow.join.params.input_count.description',
            'default': 2,
            'minimum': 2,
            'maximum': 10,
            'required': False
        },
        'timeout_ms': {
            'type': 'integer',
            'label': 'Timeout (ms)',
            'label_key': 'modules.flow.join.params.timeout_ms.label',
            'description': 'Maximum wait time in milliseconds',
            'description_key': 'modules.flow.join.params.timeout_ms.description',
            'default': 60000,
            'minimum': 1000,
            'maximum': 600000,
            'required': False
        },
        'cancel_pending': {
            'type': 'boolean',
            'label': 'Cancel Pending',
            'label_key': 'modules.flow.join.params.cancel_pending.label',
            'description': 'Cancel pending branches when using first strategy',
            'description_key': 'modules.flow.join.params.cancel_pending.description',
            'default': True,
            'required': False
        }
    },

    output_schema={
        '__event__': {'type': 'string', 'description': 'Event for routing (joined/timeout/error)'},
        'joined_data': {'type': 'array', 'description': 'Data from all completed inputs'},
        'completed_count': {'type': 'integer', 'description': 'Number of inputs completed'},
        'strategy': {'type': 'string', 'description': 'Strategy used for joining'}
    },

    examples=[
        {
            'name': 'Wait for all branches',
            'description': 'Wait until all parallel branches complete',
            'params': {
                'strategy': 'all',
                'input_count': 2,
                'timeout_ms': 30000
            }
        },
        {
            'name': 'First branch wins',
            'description': 'Continue when first branch completes',
            'params': {
                'strategy': 'first',
                'input_count': 3,
                'cancel_pending': True
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class JoinModule(BaseModule):
    """
    Join Module (Spec v1.1)

    Waits for parallel branches to complete based on strategy.

    Strategies:
    - all: Wait for all inputs to complete
    - any: Continue when any input completes
    - first: Continue on first input, optionally cancel others
    """

    module_name = "Join"
    module_description = "Wait for parallel branches to complete"
    required_permission = "flow.control"

    def validate_params(self):
        self.strategy = self.params.get('strategy', 'all')
        self.input_count = self.params.get('input_count', 2)
        self.timeout_ms = self.params.get('timeout_ms', 60000)
        self.cancel_pending = self.params.get('cancel_pending', True)

        if self.strategy not in ('all', 'any', 'first'):
            raise ValueError(f"Invalid strategy: {self.strategy}. Must be all, any, or first")

        if not 2 <= self.input_count <= 10:
            raise ValueError(f"input_count must be between 2 and 10, got {self.input_count}")

    async def execute(self) -> Dict[str, Any]:
        """
        Wait for inputs and join results.

        Note: Actual parallel waiting is handled by the workflow engine.
        This module processes whatever inputs are available in context.

        Returns:
            Dict with __event__ (joined/timeout/error) for engine routing
        """
        try:
            start_time = datetime.utcnow()

            # Collect all available inputs
            inputs = self._collect_inputs()
            completed_count = len(inputs)

            # Apply strategy
            if self.strategy == 'all':
                # Need all inputs
                if completed_count < self.input_count:
                    # Check timeout (in real implementation, engine handles this)
                    return {
                        '__event__': 'timeout',
                        'outputs': {
                            'timeout': {
                                'message': f'Only {completed_count}/{self.input_count} inputs completed',
                                'completed_count': completed_count,
                                'expected_count': self.input_count
                            }
                        },
                        'completed_count': completed_count,
                        'expected_count': self.input_count
                    }
                joined_data = inputs

            elif self.strategy == 'any':
                # Need at least one
                if completed_count == 0:
                    return {
                        '__event__': 'timeout',
                        'outputs': {
                            'timeout': {
                                'message': 'No inputs completed',
                                'completed_count': 0
                            }
                        },
                        'completed_count': 0
                    }
                joined_data = inputs

            else:  # 'first'
                # Use first input only
                if completed_count == 0:
                    return {
                        '__event__': 'timeout',
                        'outputs': {
                            'timeout': {
                                'message': 'No inputs completed',
                                'completed_count': 0
                            }
                        },
                        'completed_count': 0
                    }
                joined_data = [inputs[0]]

            return {
                '__event__': 'joined',
                'outputs': {
                    'output': {
                        'joined_data': joined_data,
                        'completed_count': completed_count,
                        'strategy': self.strategy
                    }
                },
                'joined_data': joined_data,
                'completed_count': completed_count,
                'strategy': self.strategy
            }

        except Exception as e:
            return {
                '__event__': 'error',
                'outputs': {
                    'error': {'message': str(e)}
                },
                '__error__': {
                    'code': 'JOIN_ERROR',
                    'message': str(e)
                }
            }

    def _collect_inputs(self) -> List[Any]:
        """Collect all input values from context."""
        inputs = []

        for i in range(1, self.input_count + 1):
            port_id = f'input_{i}'
            value = self.context.get(port_id)
            if value is not None:
                inputs.append(value)

        # Also check for generic 'input' key
        if 'input' in self.context and self.context['input'] is not None:
            inputs.append(self.context['input'])

        return inputs
