"""
Batch Module - Process items in batches

Processes an array of items in batches with configurable batch size.
Useful for:
- Bulk API calls with rate limiting
- Processing large datasets in chunks
- Avoiding memory issues with large arrays

Workflow Spec v1.1:
- Uses __event__ for engine routing
- Supports pause between batches for rate limiting
"""
from typing import Any, Dict, List
from datetime import datetime

from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field
from ...schema.presets import flow as flow_presets
from ...schema.presets import array as array_presets
from ...types import NodeType, EdgeType, DataType


@register_module(
    module_id='flow.batch',
    version='1.0.0',
    category='flow',
    tags=['flow', 'batch', 'chunk', 'bulk', 'control'],
    label='Batch Process',
    label_key='modules.flow.batch.label',
    description='Process items in batches with configurable size',
    description_key='modules.flow.batch.description',
    icon='LayoutGrid',
    color='#06B6D4',

    # Type definitions for connection validation
    input_types=['control', 'array'],
    output_types=['control', 'array'],

    can_receive_from=['*'],
    can_connect_to=['*'],

    node_type=NodeType.STANDARD,

    input_ports=[
        {
            'id': 'input',
            'label': 'Input',
            'label_key': 'modules.flow.batch.ports.input',
            'data_type': DataType.ARRAY.value,
            'edge_type': EdgeType.CONTROL.value,
            'max_connections': 1,
            'required': True
        }
    ],

    output_ports=[
        {
            'id': 'batch',
            'label': 'Batch',
            'label_key': 'modules.flow.batch.ports.batch',
            'event': 'batch',
            'color': '#10B981',
            'edge_type': EdgeType.CONTROL.value,
            'description': 'Emits for each batch'
        },
        {
            'id': 'completed',
            'label': 'Completed',
            'label_key': 'modules.flow.batch.ports.completed',
            'event': 'completed',
            'color': '#3B82F6',
            'edge_type': EdgeType.CONTROL.value,
            'description': 'Emits when all batches are processed'
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

    retryable=False,
    concurrent_safe=True,
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema=compose(
        array_presets.INPUT_ARRAY(key='items', label='Items', label_key='modules.flow.batch.params.items.label'),
        field(
            'batch_size',
            type='integer',
            label='Batch Size',
            label_key='modules.flow.batch.params.batch_size.label',
            description='Number of items per batch',
            description_key='modules.flow.batch.params.batch_size.description',
            default=10,
            min=1,
            max=1000,
            required=True,
        ),
        field(
            'delay_ms',
            type='integer',
            label='Delay Between Batches (ms)',
            label_key='modules.flow.batch.params.delay_ms.label',
            description='Milliseconds to wait between batches (for rate limiting)',
            description_key='modules.flow.batch.params.delay_ms.description',
            default=0,
            min=0,
            max=60000,
        ),
        field(
            'continue_on_error',
            type='boolean',
            label='Continue on Error',
            label_key='modules.flow.batch.params.continue_on_error.label',
            description='Continue processing remaining batches if one fails',
            description_key='modules.flow.batch.params.continue_on_error.description',
            default=False,
        ),
        field(
            'parallel_batches',
            type='integer',
            label='Parallel Batches',
            label_key='modules.flow.batch.params.parallel_batches.label',
            description='Number of batches to process in parallel (1 for sequential)',
            description_key='modules.flow.batch.params.parallel_batches.description',
            default=1,
            min=1,
            max=10,
        ),
    ),

    output_schema={
        '__event__': {
            'type': 'string',
            'description': 'Event for routing (batch/completed/error)',
            'description_key': 'modules.flow.batch.output.__event__.description'
        },
        'batch': {
            'type': 'array',
            'description': 'Current batch items',
            'description_key': 'modules.flow.batch.output.batch.description'
        },
        'batch_index': {
            'type': 'integer',
            'description': 'Current batch index (0-based)',
            'description_key': 'modules.flow.batch.output.batch_index.description'
        },
        'total_batches': {
            'type': 'integer',
            'description': 'Total number of batches',
            'description_key': 'modules.flow.batch.output.total_batches.description'
        },
        'total_items': {
            'type': 'integer',
            'description': 'Total number of items',
            'description_key': 'modules.flow.batch.output.total_items.description'
        },
        'is_last_batch': {
            'type': 'boolean',
            'description': 'Whether this is the last batch',
            'description_key': 'modules.flow.batch.output.is_last_batch.description'
        },
        'progress': {
            'type': 'object',
            'description': 'Progress information',
            'description_key': 'modules.flow.batch.output.progress.description'
        }
    },

    examples=[
        {
            'name': 'Process in batches of 10',
            'description': 'Split array into batches of 10 items each',
            'params': {
                'items': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
                'batch_size': 10
            }
        },
        {
            'name': 'Rate-limited batch processing',
            'description': 'Process batches with 1 second delay between each',
            'params': {
                'items': '${input.records}',
                'batch_size': 100,
                'delay_ms': 1000
            }
        },
        {
            'name': 'Parallel batch processing',
            'description': 'Process 3 batches in parallel',
            'params': {
                'items': '${input.data}',
                'batch_size': 50,
                'parallel_batches': 3,
                'continue_on_error': True
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=300000,
)
class BatchModule(BaseModule):
    """
    Batch processing module.

    Splits an input array into batches and processes them sequentially
    or in parallel. Supports rate limiting via delay between batches.

    The module emits a 'batch' event for each batch, allowing downstream
    nodes to process individual batches. After all batches are processed,
    a 'completed' event is emitted.
    """

    module_name = "Batch Process"
    module_description = "Process items in batches"

    def validate_params(self) -> None:
        self.items = self.params.get('items', [])
        self.batch_size = self.params.get('batch_size', 10)
        self.delay_ms = self.params.get('delay_ms', 0)
        self.continue_on_error = self.params.get('continue_on_error', False)
        self.parallel_batches = self.params.get('parallel_batches', 1)

        if not isinstance(self.items, list):
            raise ValueError("items must be an array")

        if self.batch_size < 1:
            raise ValueError("batch_size must be at least 1")

        if self.parallel_batches < 1:
            raise ValueError("parallel_batches must be at least 1")

    async def execute(self) -> Dict[str, Any]:
        """
        Split items into batches and return batch execution plan.

        The workflow engine will use this plan to:
        1. Split items into batches
        2. Execute each batch (emit 'batch' event)
        3. Apply delay between batches if specified
        4. Emit 'completed' when all batches done
        """
        try:
            # Handle empty array
            if len(self.items) == 0:
                return {
                    '__event__': 'completed',
                    'outputs': {
                        'completed': {
                            'batches': [],
                            'total_batches': 0,
                            'total_items': 0
                        }
                    },
                    'batches': [],
                    'total_batches': 0,
                    'total_items': 0
                }

            # Split into batches
            batches = self._create_batches()
            total_batches = len(batches)

            # Build batch execution plan
            batch_plan = {
                'batches': batches,
                'batch_size': self.batch_size,
                'delay_ms': self.delay_ms,
                'continue_on_error': self.continue_on_error,
                'parallel_batches': self.parallel_batches,
                'total_batches': total_batches,
                'total_items': len(self.items)
            }

            # Return first batch and metadata
            # The engine will iterate through batches
            return {
                '__event__': 'batch',
                '__batch_execution__': batch_plan,
                'outputs': {
                    'batch': {
                        'batch': batches[0] if batches else [],
                        'batch_index': 0,
                        'total_batches': total_batches,
                        'total_items': len(self.items),
                        'is_last_batch': total_batches == 1,
                        'progress': {
                            'current': 1,
                            'total': total_batches,
                            'percentage': (1 / total_batches * 100) if total_batches > 0 else 100
                        }
                    }
                },
                'batch': batches[0] if batches else [],
                'batch_index': 0,
                'total_batches': total_batches,
                'total_items': len(self.items),
                'is_last_batch': total_batches == 1,
                'all_batches': batches,
                'progress': {
                    'current': 1,
                    'total': total_batches,
                    'percentage': (1 / total_batches * 100) if total_batches > 0 else 100
                }
            }

        except Exception as e:
            return {
                '__event__': 'error',
                'outputs': {
                    'error': {'message': str(e)}
                },
                '__error__': {
                    'code': 'BATCH_ERROR',
                    'message': str(e)
                }
            }

    def _create_batches(self) -> List[List[Any]]:
        """Split items into batches of specified size."""
        batches = []
        for i in range(0, len(self.items), self.batch_size):
            batch = self.items[i:i + self.batch_size]
            batches.append(batch)
        return batches
