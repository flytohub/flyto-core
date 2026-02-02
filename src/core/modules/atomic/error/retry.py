"""
Retry Module - Wrap operations with retry logic

Provides configurable retry behavior for operations that may fail
transiently, such as network requests or API calls.

Features:
- Configurable max retries
- Exponential backoff with jitter
- Retry conditions (which errors to retry)
- Delay customization
- Timeout per attempt

This is a "tool" module - it wraps another operation with retry
logic rather than containing intelligence about when to retry.
"""
import asyncio
import random
from typing import Any, Dict, List, Optional
from datetime import datetime

from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field
from ...types import NodeType, EdgeType, DataType


@register_module(
    module_id='error.retry',
    version='1.0.0',
    category='error',
    tags=['error', 'retry', 'resilience', 'fault-tolerance'],
    label='Retry',
    label_key='modules.error.retry.label',
    description='Wrap operations with configurable retry logic',
    description_key='modules.error.retry.description',
    icon='RefreshCw',
    color='#F59E0B',

    # Type definitions for connection validation
    input_types=['any'],
    output_types=['any'],

    can_receive_from=['*'],
    can_connect_to=['*'],

    node_type=NodeType.STANDARD,

    input_ports=[
        {
            'id': 'input',
            'label': 'Input',
            'label_key': 'modules.error.retry.ports.input',
            'data_type': DataType.ANY.value,
            'edge_type': EdgeType.CONTROL.value,
            'max_connections': 1,
            'required': True
        }
    ],

    output_ports=[
        {
            'id': 'success',
            'label': 'Success',
            'label_key': 'modules.error.retry.ports.success',
            'event': 'success',
            'color': '#10B981',
            'edge_type': EdgeType.CONTROL.value
        },
        {
            'id': 'exhausted',
            'label': 'Retries Exhausted',
            'label_key': 'modules.error.retry.ports.exhausted',
            'event': 'exhausted',
            'color': '#EF4444',
            'edge_type': EdgeType.CONTROL.value
        }
    ],

    retryable=False,  # This module handles retry itself
    concurrent_safe=True,
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema=compose(
        field(
            'operation',
            type='object',
            label='Operation',
            label_key='modules.error.retry.params.operation.label',
            description='The operation to retry (module ID and params)',
            description_key='modules.error.retry.params.operation.description',
            required=True,
        ),
        field(
            'max_retries',
            type='integer',
            label='Max Retries',
            label_key='modules.error.retry.params.max_retries.label',
            description='Maximum number of retry attempts',
            description_key='modules.error.retry.params.max_retries.description',
            default=3,
            min=1,
            max=10,
        ),
        field(
            'initial_delay_ms',
            type='integer',
            label='Initial Delay (ms)',
            label_key='modules.error.retry.params.initial_delay_ms.label',
            description='Initial delay before first retry',
            description_key='modules.error.retry.params.initial_delay_ms.description',
            default=1000,
            min=0,
            max=60000,
        ),
        field(
            'max_delay_ms',
            type='integer',
            label='Max Delay (ms)',
            label_key='modules.error.retry.params.max_delay_ms.label',
            description='Maximum delay between retries',
            description_key='modules.error.retry.params.max_delay_ms.description',
            default=30000,
            min=1000,
            max=300000,
        ),
        field(
            'backoff_multiplier',
            type='number',
            label='Backoff Multiplier',
            label_key='modules.error.retry.params.backoff_multiplier.label',
            description='Multiplier for exponential backoff (e.g., 2 doubles delay each retry)',
            description_key='modules.error.retry.params.backoff_multiplier.description',
            default=2.0,
            min=1.0,
            max=5.0,
        ),
        field(
            'jitter',
            type='boolean',
            label='Add Jitter',
            label_key='modules.error.retry.params.jitter.label',
            description='Add random jitter to delay to prevent thundering herd',
            description_key='modules.error.retry.params.jitter.description',
            default=True,
        ),
        field(
            'retry_on',
            type='array',
            label='Retry On Error Codes',
            label_key='modules.error.retry.params.retry_on.label',
            description='List of error codes to retry on (empty = retry all)',
            description_key='modules.error.retry.params.retry_on.description',
            default=[],
        ),
        field(
            'timeout_per_attempt_ms',
            type='integer',
            label='Timeout Per Attempt (ms)',
            label_key='modules.error.retry.params.timeout_per_attempt_ms.label',
            description='Timeout for each attempt (0 for no timeout)',
            description_key='modules.error.retry.params.timeout_per_attempt_ms.description',
            default=0,
            min=0,
            max=300000,
        ),
    ),

    output_schema={
        '__event__': {
            'type': 'string',
            'description': 'Event for routing (success/exhausted)',
            'description_key': 'modules.error.retry.output.__event__.description'
        },
        'result': {
            'type': 'any',
            'description': 'Result from successful attempt',
            'description_key': 'modules.error.retry.output.result.description'
        },
        'attempts': {
            'type': 'integer',
            'description': 'Number of attempts made',
            'description_key': 'modules.error.retry.output.attempts.description'
        },
        'total_delay_ms': {
            'type': 'number',
            'description': 'Total time spent in delays',
            'description_key': 'modules.error.retry.output.total_delay_ms.description'
        },
        'errors': {
            'type': 'array',
            'description': 'Errors from each failed attempt',
            'description_key': 'modules.error.retry.output.errors.description'
        }
    },

    examples=[
        {
            'name': 'Simple retry with defaults',
            'description': 'Retry an HTTP request up to 3 times',
            'params': {
                'operation': {
                    'module': 'http.get',
                    'params': {'url': 'https://api.example.com/data'}
                },
                'max_retries': 3
            }
        },
        {
            'name': 'Exponential backoff',
            'description': 'Retry with exponential backoff starting at 2 seconds',
            'params': {
                'operation': {
                    'module': 'database.query',
                    'params': {'query': 'SELECT * FROM users'}
                },
                'max_retries': 5,
                'initial_delay_ms': 2000,
                'backoff_multiplier': 2.0,
                'jitter': True
            }
        },
        {
            'name': 'Retry specific errors',
            'description': 'Only retry on network and timeout errors',
            'params': {
                'operation': {
                    'module': 'api.call',
                    'params': {'endpoint': '/submit'}
                },
                'max_retries': 3,
                'retry_on': ['NETWORK_ERROR', 'TIMEOUT_ERROR', 'SERVICE_UNAVAILABLE']
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=600000,  # 10 minutes to allow for retries
)
class RetryModule(BaseModule):
    """
    Retry module.

    Wraps an operation with retry logic including:
    - Configurable max retries
    - Exponential backoff with optional jitter
    - Selective retry based on error codes
    - Per-attempt timeout

    The module signals the workflow engine to execute the wrapped
    operation with retry behavior.
    """

    module_name = "Retry"
    module_description = "Wrap operations with retry logic"

    def validate_params(self) -> None:
        self.operation = self.params.get('operation', {})
        self.max_retries = self.params.get('max_retries', 3)
        self.initial_delay_ms = self.params.get('initial_delay_ms', 1000)
        self.max_delay_ms = self.params.get('max_delay_ms', 30000)
        self.backoff_multiplier = self.params.get('backoff_multiplier', 2.0)
        self.jitter = self.params.get('jitter', True)
        self.retry_on = self.params.get('retry_on', [])
        self.timeout_per_attempt_ms = self.params.get('timeout_per_attempt_ms', 0)

        if not isinstance(self.operation, dict):
            raise ValueError("operation must be an object with 'module' and 'params'")

        if 'module' not in self.operation:
            raise ValueError("operation must have a 'module' field")

        if self.max_retries < 1:
            raise ValueError("max_retries must be at least 1")

        if self.backoff_multiplier < 1.0:
            raise ValueError("backoff_multiplier must be at least 1.0")

    def _calculate_delay(self, attempt: int) -> int:
        """Calculate delay for given attempt number using exponential backoff."""
        delay = self.initial_delay_ms * (self.backoff_multiplier ** attempt)

        # Add jitter if enabled (up to 25% of delay)
        if self.jitter:
            jitter_amount = delay * 0.25 * random.random()
            delay += jitter_amount

        # Cap at max delay
        delay = min(delay, self.max_delay_ms)

        return int(delay)

    def _should_retry(self, error_code: str) -> bool:
        """Determine if we should retry based on error code."""
        # If no specific codes configured, retry all errors
        if not self.retry_on:
            return True

        return error_code in self.retry_on

    async def execute(self) -> Dict[str, Any]:
        """
        Execute with retry logic.

        Returns a retry execution plan for the workflow engine.
        The engine will handle actual execution and retry.
        """
        try:
            # Build retry execution plan
            retry_plan = {
                'operation': self.operation,
                'max_retries': self.max_retries,
                'delays': [self._calculate_delay(i) for i in range(self.max_retries)],
                'retry_on': self.retry_on,
                'timeout_per_attempt_ms': self.timeout_per_attempt_ms,
            }

            # Track timing
            start_time = datetime.utcnow()

            # For direct execution simulation, return the plan
            # The workflow engine will interpret this and execute with retries

            return {
                '__event__': 'success',
                '__retry_execution__': retry_plan,
                'outputs': {
                    'success': {
                        'operation': self.operation,
                        'max_retries': self.max_retries,
                        'retry_plan': retry_plan,
                        'attempts': 0,
                        'total_delay_ms': 0,
                        'errors': []
                    }
                },
                'operation': self.operation,
                'max_retries': self.max_retries,
                'retry_plan': retry_plan,
                'attempts': 0,
                'total_delay_ms': 0,
                'errors': []
            }

        except Exception as e:
            return {
                '__event__': 'exhausted',
                'outputs': {
                    'exhausted': {
                        'message': str(e),
                        'attempts': 0,
                        'errors': [{'message': str(e)}]
                    }
                },
                '__error__': {
                    'code': 'RETRY_SETUP_ERROR',
                    'message': str(e)
                }
            }
