"""
Parallel Module - Execute multiple tasks in parallel

Provides parallel execution with different strategies:
- all: Wait for all tasks to complete (like Promise.all)
- race: Return first completed task (like Promise.race)
- settle: Wait for all, return results with status (like Promise.allSettled)

This is a flow control module that enables concurrent execution
within workflows. The actual parallel execution is handled by
the workflow engine.

Workflow Spec v1.1:
- Uses __event__ for engine routing
- Returns structured results based on mode
"""
import asyncio
from typing import Any, Dict, List, Optional
from datetime import datetime

from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field
from ...schema.presets import flow as flow_presets
from ...types import NodeType, EdgeType, DataType


@register_module(
    module_id='flow.parallel',
    version='1.0.0',
    category='flow',
    tags=['flow', 'parallel', 'concurrent', 'async', 'control'],
    label='Parallel',
    label_key='modules.flow.parallel.label',
    description='Execute multiple tasks in parallel with different strategies',
    description_key='modules.flow.parallel.description',
    icon='Layers',
    color='#8B5CF6',

    can_receive_from=['*'],
    can_connect_to=['*'],

    node_type=NodeType.STANDARD,

    input_ports=[
        {
            'id': 'input',
            'label': 'Input',
            'label_key': 'modules.flow.parallel.ports.input',
            'data_type': DataType.ANY.value,
            'edge_type': EdgeType.CONTROL.value,
            'max_connections': 1,
            'required': True
        }
    ],

    output_ports=[
        {
            'id': 'completed',
            'label': 'Completed',
            'label_key': 'modules.flow.parallel.ports.completed',
            'event': 'completed',
            'color': '#10B981',
            'edge_type': EdgeType.CONTROL.value
        },
        {
            'id': 'partial',
            'label': 'Partial',
            'label_key': 'modules.flow.parallel.ports.partial',
            'event': 'partial',
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

    retryable=False,
    concurrent_safe=True,
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema=compose(
        field(
            'tasks',
            type='array',
            label='Tasks',
            label_key='modules.flow.parallel.params.tasks.label',
            description='Array of task definitions to execute in parallel',
            description_key='modules.flow.parallel.params.tasks.description',
            required=True,
        ),
        field(
            'mode',
            type='string',
            label='Mode',
            label_key='modules.flow.parallel.params.mode.label',
            description='Parallel execution mode',
            description_key='modules.flow.parallel.params.mode.description',
            default='all',
            enum=['all', 'race', 'settle'],
        ),
        flow_presets.TIMEOUT_MS(default=60000),
        field(
            'fail_fast',
            type='boolean',
            label='Fail Fast',
            label_key='modules.flow.parallel.params.fail_fast.label',
            description='Stop all tasks on first failure (only for mode=all)',
            description_key='modules.flow.parallel.params.fail_fast.description',
            default=True,
        ),
        field(
            'concurrency_limit',
            type='integer',
            label='Concurrency Limit',
            label_key='modules.flow.parallel.params.concurrency_limit.label',
            description='Maximum number of concurrent tasks (0 for unlimited)',
            description_key='modules.flow.parallel.params.concurrency_limit.description',
            default=0,
            min=0,
            max=100,
        ),
    ),

    output_schema={
        '__event__': {
            'type': 'string',
            'description': 'Event for routing (completed/partial/error)',
            'description_key': 'modules.flow.parallel.output.__event__.description'
        },
        'results': {
            'type': 'array',
            'description': 'Results from all tasks',
            'description_key': 'modules.flow.parallel.output.results.description'
        },
        'completed_count': {
            'type': 'integer',
            'description': 'Number of successfully completed tasks',
            'description_key': 'modules.flow.parallel.output.completed_count.description'
        },
        'failed_count': {
            'type': 'integer',
            'description': 'Number of failed tasks',
            'description_key': 'modules.flow.parallel.output.failed_count.description'
        },
        'total_count': {
            'type': 'integer',
            'description': 'Total number of tasks',
            'description_key': 'modules.flow.parallel.output.total_count.description'
        },
        'mode': {
            'type': 'string',
            'description': 'Execution mode used',
            'description_key': 'modules.flow.parallel.output.mode.description'
        },
        'duration_ms': {
            'type': 'number',
            'description': 'Total execution time in milliseconds',
            'description_key': 'modules.flow.parallel.output.duration_ms.description'
        }
    },

    examples=[
        {
            'name': 'Wait for all tasks',
            'description': 'Execute all tasks and wait for completion',
            'params': {
                'tasks': [
                    {'module': 'http.get', 'params': {'url': 'https://api1.example.com'}},
                    {'module': 'http.get', 'params': {'url': 'https://api2.example.com'}}
                ],
                'mode': 'all',
                'timeout_ms': 30000
            }
        },
        {
            'name': 'Race to first result',
            'description': 'Return as soon as first task completes',
            'params': {
                'tasks': [
                    {'module': 'http.get', 'params': {'url': 'https://mirror1.example.com'}},
                    {'module': 'http.get', 'params': {'url': 'https://mirror2.example.com'}}
                ],
                'mode': 'race'
            }
        },
        {
            'name': 'Settle all tasks',
            'description': 'Wait for all tasks, collect both successes and failures',
            'params': {
                'tasks': [
                    {'module': 'http.get', 'params': {'url': 'https://api1.example.com'}},
                    {'module': 'http.get', 'params': {'url': 'https://might-fail.example.com'}}
                ],
                'mode': 'settle'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=120000,
)
class ParallelModule(BaseModule):
    """
    Parallel execution module.

    Executes multiple tasks concurrently with configurable strategies:
    - all: Wait for all tasks, fail if any fails (unless fail_fast=False)
    - race: Return first successful result
    - settle: Wait for all, return all results with status

    Note: The actual task execution is handled by the workflow engine.
    This module provides the coordination logic and result aggregation.
    """

    module_name = "Parallel"
    module_description = "Execute multiple tasks in parallel"

    def validate_params(self) -> None:
        self.tasks = self.params.get('tasks', [])
        self.mode = self.params.get('mode', 'all')
        self.timeout_ms = self.params.get('timeout_ms', 60000)
        self.fail_fast = self.params.get('fail_fast', True)
        self.concurrency_limit = self.params.get('concurrency_limit', 0)

        if not isinstance(self.tasks, list):
            raise ValueError("tasks must be an array")

        if len(self.tasks) == 0:
            raise ValueError("tasks array cannot be empty")

        if self.mode not in ('all', 'race', 'settle'):
            raise ValueError(f"Invalid mode: {self.mode}. Must be all, race, or settle")

        if self.concurrency_limit < 0:
            raise ValueError("concurrency_limit cannot be negative")

    async def execute(self) -> Dict[str, Any]:
        """
        Execute tasks in parallel based on mode.

        The workflow engine will interpret the task definitions and
        execute them. This module handles the coordination.
        """
        start_time = datetime.utcnow()

        try:
            # Build task execution plan
            task_plan = {
                'tasks': self.tasks,
                'mode': self.mode,
                'timeout_ms': self.timeout_ms,
                'fail_fast': self.fail_fast,
                'concurrency_limit': self.concurrency_limit,
            }

            # For now, simulate execution results
            # In actual workflow execution, the engine will:
            # 1. Parse task definitions
            # 2. Execute them in parallel
            # 3. Return results based on mode

            # Pass input data to all tasks
            input_data = self.context.get('input', {})

            results = []
            for i, task in enumerate(self.tasks):
                results.append({
                    'index': i,
                    'task': task,
                    'status': 'pending',
                    'input': input_data
                })

            end_time = datetime.utcnow()
            duration_ms = (end_time - start_time).total_seconds() * 1000

            return {
                '__event__': 'completed',
                '__parallel_execution__': task_plan,
                'outputs': {
                    'completed': {
                        'results': results,
                        'completed_count': 0,
                        'failed_count': 0,
                        'total_count': len(self.tasks),
                        'mode': self.mode,
                        'duration_ms': duration_ms
                    }
                },
                'results': results,
                'completed_count': 0,
                'failed_count': 0,
                'total_count': len(self.tasks),
                'mode': self.mode,
                'duration_ms': duration_ms
            }

        except asyncio.TimeoutError:
            return {
                '__event__': 'partial',
                'outputs': {
                    'partial': {
                        'message': f'Timeout after {self.timeout_ms}ms',
                        'timeout': True
                    }
                },
                '__error__': {
                    'code': 'PARALLEL_TIMEOUT',
                    'message': f'Parallel execution timed out after {self.timeout_ms}ms'
                }
            }

        except Exception as e:
            return {
                '__event__': 'error',
                'outputs': {
                    'error': {'message': str(e)}
                },
                '__error__': {
                    'code': 'PARALLEL_ERROR',
                    'message': str(e)
                }
            }
