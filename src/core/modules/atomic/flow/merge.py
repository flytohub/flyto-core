"""
Merge Module - Combine multiple inputs into single output

Workflow Spec v1.1:
- Merge node with N inputs and single output
- Strategies: first (first input wins), last (last wins), all (collect array)
- Returns __event__ for engine routing
"""
from typing import Any, Dict, List
from ...base import BaseModule
from ...registry import register_module
from ...types import NodeType, EdgeType, DataType


@register_module(
    module_id='flow.merge',
    version='1.0.0',
    category='flow',
    tags=['flow', 'merge', 'combine', 'join', 'control'],
    label='Merge',
    label_key='modules.flow.merge.label',
    description='Merge multiple inputs into a single output',
    description_key='modules.flow.merge.description',
    icon='GitMerge',
    color='#8B5CF6',

    # Workflow Spec v1.1
    node_type=NodeType.MERGE,

    input_ports=[
        {
            'id': 'input_1',
            'label': 'Input 1',
            'label_key': 'modules.flow.merge.ports.input_1',
            'data_type': DataType.ANY.value,
            'edge_type': EdgeType.CONTROL.value,
            'max_connections': 1,
            'required': False
        },
        {
            'id': 'input_2',
            'label': 'Input 2',
            'label_key': 'modules.flow.merge.ports.input_2',
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
            'label_key': 'modules.flow.merge.ports.output',
            'event': 'merged',
            'color': '#10B981',
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
            'label': 'Merge Strategy',
            'label_key': 'modules.flow.merge.params.strategy.label',
            'description': 'How to merge multiple inputs',
            'description_key': 'modules.flow.merge.params.strategy.description',
            'enum': ['first', 'last', 'all'],
            'default': 'all',
            'required': False
        },
        'input_count': {
            'type': 'integer',
            'label': 'Input Count',
            'label_key': 'modules.flow.merge.params.input_count.label',
            'description': 'Number of input ports',
            'description_key': 'modules.flow.merge.params.input_count.description',
            'default': 2,
            'minimum': 2,
            'maximum': 10,
            'required': False
        }
    },

    output_schema={
        '__event__': {'type': 'string', 'description': 'Event for routing (merged/error)'},
        'merged_data': {'type': 'any', 'description': 'Merged data based on strategy'},
        'input_count': {'type': 'integer', 'description': 'Number of inputs received'},
        'strategy': {'type': 'string', 'description': 'Strategy used for merging'}
    },

    examples=[
        {
            'name': 'Merge all inputs',
            'description': 'Collect all inputs into an array',
            'params': {
                'strategy': 'all',
                'input_count': 3
            }
        },
        {
            'name': 'First input wins',
            'description': 'Use the first input that arrives',
            'params': {
                'strategy': 'first',
                'input_count': 2
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class MergeModule(BaseModule):
    """
    Merge Module (Spec v1.1)

    Combines multiple inputs into a single output using configurable strategy.

    Strategies:
    - first: Use the first input received
    - last: Use the last input received
    - all: Collect all inputs into an array
    """

    module_name = "Merge"
    module_description = "Merge multiple inputs into single output"
    required_permission = "flow.control"

    def validate_params(self):
        self.strategy = self.params.get('strategy', 'all')
        self.input_count = self.params.get('input_count', 2)

        if self.strategy not in ('first', 'last', 'all'):
            raise ValueError(f"Invalid strategy: {self.strategy}. Must be first, last, or all")

        if not 2 <= self.input_count <= 10:
            raise ValueError(f"input_count must be between 2 and 10, got {self.input_count}")

    async def execute(self) -> Dict[str, Any]:
        """
        Merge inputs and return merged data.

        Returns:
            Dict with __event__ (merged/error) for engine routing
        """
        try:
            # Collect all inputs from context
            inputs = self._collect_inputs()

            if not inputs:
                return {
                    '__event__': 'error',
                    'outputs': {
                        'error': {'message': 'No inputs received'}
                    },
                    '__error__': {
                        'code': 'NO_INPUTS',
                        'message': 'No inputs received for merge'
                    }
                }

            # Apply merge strategy
            merged_data = self._apply_strategy(inputs)

            return {
                '__event__': 'merged',
                'outputs': {
                    'output': {
                        'merged_data': merged_data,
                        'input_count': len(inputs),
                        'strategy': self.strategy
                    }
                },
                'merged_data': merged_data,
                'input_count': len(inputs),
                'strategy': self.strategy
            }

        except Exception as e:
            return {
                '__event__': 'error',
                'outputs': {
                    'error': {'message': str(e)}
                },
                '__error__': {
                    'code': 'MERGE_ERROR',
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

    def _apply_strategy(self, inputs: List[Any]) -> Any:
        """Apply merge strategy to inputs."""
        if self.strategy == 'first':
            return inputs[0] if inputs else None
        elif self.strategy == 'last':
            return inputs[-1] if inputs else None
        else:  # 'all'
            return inputs
