# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Retry Module - Retry with exponential backoff

Retries a failed operation with configurable exponential backoff.
Useful for:
- Transient API failures
- Network timeouts
- Rate-limited services

Workflow Spec v1.1:
- Uses __event__ for engine routing (success/retry/exhausted)
- Uses __retry_execution__ plan for engine retry orchestration
- Supports jitter to prevent thundering herd
"""
import random
import time
from typing import Any, Dict, List, Optional

from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field
from ...types import NodeType, EdgeType, DataType


@register_module(
    module_id='flow.retry',
    version='1.0.0',
    category='flow',
    tags=['flow', 'retry', 'backoff', 'resilience', 'control'],
    label='Retry',
    label_key='modules.flow.retry.label',
    description='Retry with exponential backoff',
    description_key='modules.flow.retry.description',
    icon='RefreshCw',
    color='#F59E0B',

    input_types=['control', 'any'],
    output_types=['control'],

    can_receive_from=['*'],
    can_connect_to=['*'],

    node_type=NodeType.STANDARD,

    input_ports=[
        {
            'id': 'input',
            'label': 'Input',
            'label_key': 'modules.flow.retry.ports.input',
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
            'label_key': 'modules.flow.retry.ports.success',
            'event': 'success',
            'color': '#10B981',
            'edge_type': EdgeType.CONTROL.value,
            'description': 'Operation succeeded'
        },
        {
            'id': 'retry',
            'label': 'Retry',
            'label_key': 'modules.flow.retry.ports.retry',
            'event': 'retry',
            'color': '#F59E0B',
            'edge_type': EdgeType.CONTROL.value,
            'description': 'Emits for each retry attempt'
        },
        {
            'id': 'exhausted',
            'label': 'Exhausted',
            'label_key': 'modules.flow.retry.ports.exhausted',
            'event': 'exhausted',
            'color': '#EF4444',
            'edge_type': EdgeType.CONTROL.value,
            'description': 'All retries failed'
        }
    ],

    retryable=False,
    concurrent_safe=True,
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema=compose(
        field(
            'max_retries',
            type='number',
            label='Max Retries',
            label_key='modules.flow.retry.params.max_retries.label',
            description='Maximum number of retry attempts',
            description_key='modules.flow.retry.params.max_retries.description',
            default=3,
            min=1,
            max=20,
            required=True,
        ),
        field(
            'initial_delay_ms',
            type='number',
            label='Initial Delay (ms)',
            label_key='modules.flow.retry.params.initial_delay_ms.label',
            description='Initial delay before first retry in milliseconds',
            description_key='modules.flow.retry.params.initial_delay_ms.description',
            default=1000,
            min=0,
            max=60000,
        ),
        field(
            'backoff_multiplier',
            type='number',
            label='Backoff Multiplier',
            label_key='modules.flow.retry.params.backoff_multiplier.label',
            description='Multiplier for exponential backoff (e.g. 2.0 doubles delay each retry)',
            description_key='modules.flow.retry.params.backoff_multiplier.description',
            default=2.0,
            min=1.0,
            max=10.0,
        ),
        field(
            'max_delay_ms',
            type='number',
            label='Max Delay (ms)',
            label_key='modules.flow.retry.params.max_delay_ms.label',
            description='Maximum delay cap in milliseconds',
            description_key='modules.flow.retry.params.max_delay_ms.description',
            default=30000,
            min=1000,
            max=300000,
        ),
        field(
            'retry_on_errors',
            type='array',
            label='Retry on Error Codes',
            label_key='modules.flow.retry.params.retry_on_errors.label',
            description='Optional list of error codes to retry on (empty = retry on all errors)',
            description_key='modules.flow.retry.params.retry_on_errors.description',
            default=[],
            required=False,
        ),
    ),

    output_schema={
        '__event__': {
            'type': 'string',
            'description': 'Event for routing (success/retry/exhausted)',
            'description_key': 'modules.flow.retry.output.__event__.description'
        },
        'attempt': {
            'type': 'number',
            'description': 'Current attempt number (1-based)',
            'description_key': 'modules.flow.retry.output.attempt.description'
        },
        'max_retries': {
            'type': 'number',
            'description': 'Maximum retry attempts configured',
            'description_key': 'modules.flow.retry.output.max_retries.description'
        },
        'delay_ms': {
            'type': 'number',
            'description': 'Delay before this attempt in milliseconds',
            'description_key': 'modules.flow.retry.output.delay_ms.description'
        },
        'total_elapsed_ms': {
            'type': 'number',
            'description': 'Total time elapsed across all attempts',
            'description_key': 'modules.flow.retry.output.total_elapsed_ms.description'
        },
        'last_error': {
            'type': 'object',
            'description': 'Last error that triggered a retry',
            'description_key': 'modules.flow.retry.output.last_error.description'
        }
    },

    examples=[
        {
            'name': 'Basic retry with defaults',
            'description': 'Retry up to 3 times with exponential backoff',
            'params': {
                'max_retries': 3
            }
        },
        {
            'name': 'Aggressive retry for critical operations',
            'description': 'Retry up to 10 times with short initial delay',
            'params': {
                'max_retries': 10,
                'initial_delay_ms': 500,
                'backoff_multiplier': 1.5,
                'max_delay_ms': 10000
            }
        },
        {
            'name': 'Retry only on specific errors',
            'description': 'Retry only on timeout and rate limit errors',
            'params': {
                'max_retries': 5,
                'initial_delay_ms': 2000,
                'retry_on_errors': ['TIMEOUT', 'RATE_LIMIT', '429', '503']
            }
        }
    ],
    author='Flyto Team',
    license='MIT',
    timeout_ms=300000,
)
class RetryModule(BaseModule):
    """
    Retry module with exponential backoff.

    Manages retry state for failed operations. Calculates delay with
    jitter using exponential backoff strategy. The engine uses the
    __retry_execution__ plan to orchestrate retry attempts.

    Events:
    - success: Operation succeeded (no retry needed or passed through)
    - retry: A retry attempt is being made
    - exhausted: All retry attempts have been exhausted
    """

    module_name = "Retry"
    module_description = "Retry with exponential backoff"

    def validate_params(self) -> None:
        self.max_retries = self.params.get('max_retries', 3)
        self.initial_delay_ms = self.params.get('initial_delay_ms', 1000)
        self.backoff_multiplier = self.params.get('backoff_multiplier', 2.0)
        self.max_delay_ms = self.params.get('max_delay_ms', 30000)
        self.retry_on_errors = self.params.get('retry_on_errors', [])

        if self.max_retries < 1:
            raise ValueError("max_retries must be at least 1")
        if self.initial_delay_ms < 0:
            raise ValueError("initial_delay_ms must be non-negative")
        if self.backoff_multiplier < 1.0:
            raise ValueError("backoff_multiplier must be at least 1.0")
        if self.max_delay_ms < self.initial_delay_ms:
            raise ValueError("max_delay_ms must be >= initial_delay_ms")

    async def execute(self) -> Dict[str, Any]:
        """
        Evaluate retry state and return appropriate event.

        Reads retry context from input to determine current attempt.
        Calculates next delay with exponential backoff + jitter.
        Returns __retry_execution__ plan for the engine.
        """
        try:
            retry_state = self.context.get('__retry_state__', {}) if self.context else {}
            current_attempt = retry_state.get('attempt', 0)
            last_error = retry_state.get('last_error', None)
            start_time_ms = retry_state.get('start_time_ms', int(time.time() * 1000))

            if self._should_skip_retry(last_error):
                return self._build_exhausted_response(
                    current_attempt, last_error, start_time_ms
                )

            if current_attempt == 0 and last_error is None:
                return self._build_success_response(current_attempt, start_time_ms)

            if current_attempt >= self.max_retries:
                return self._build_exhausted_response(
                    current_attempt, last_error, start_time_ms
                )

            return self._build_retry_response(
                current_attempt, last_error, start_time_ms
            )

        except Exception as e:
            return {
                '__event__': 'exhausted',
                'outputs': {
                    'exhausted': {'message': str(e)}
                },
                '__error__': {
                    'code': 'RETRY_ERROR',
                    'message': str(e)
                }
            }

    def _should_skip_retry(self, last_error) -> bool:
        if last_error and self.retry_on_errors:
            error_code = str(last_error.get('code', ''))
            return error_code not in self.retry_on_errors
        return False

    def _build_retry_response(
        self, current_attempt: int, last_error, start_time_ms: int
    ) -> Dict[str, Any]:
        delay_ms = self._calculate_delay(current_attempt)
        retry_plan = {
            'max_retries': self.max_retries,
            'current_attempt': current_attempt + 1,
            'delay_ms': delay_ms,
            'backoff_multiplier': self.backoff_multiplier,
            'max_delay_ms': self.max_delay_ms,
            'retry_on_errors': self.retry_on_errors,
            'start_time_ms': start_time_ms,
        }
        now_ms = int(time.time() * 1000)
        total_elapsed_ms = now_ms - start_time_ms

        return {
            '__event__': 'retry',
            '__retry_execution__': retry_plan,
            'outputs': {
                'retry': {
                    'attempt': current_attempt + 1,
                    'max_retries': self.max_retries,
                    'delay_ms': delay_ms,
                    'last_error': last_error,
                    'total_elapsed_ms': total_elapsed_ms,
                }
            },
            'attempt': current_attempt + 1,
            'max_retries': self.max_retries,
            'delay_ms': delay_ms,
            'total_elapsed_ms': total_elapsed_ms,
            'last_error': last_error,
        }

    def _calculate_delay(self, attempt: int) -> int:
        """
        Calculate delay with exponential backoff and jitter.

        Formula: min(initial_delay * multiplier^attempt + jitter, max_delay)
        Jitter is ±25% of the calculated delay to prevent thundering herd.
        """
        base_delay = self.initial_delay_ms * (self.backoff_multiplier ** attempt)

        # Add jitter: ±25%
        jitter_range = base_delay * 0.25
        jitter = random.uniform(-jitter_range, jitter_range)
        delay = base_delay + jitter

        # Cap at max delay
        delay = min(delay, self.max_delay_ms)
        delay = max(delay, 0)

        return int(delay)

    def _build_success_response(
        self, attempt: int, start_time_ms: int
    ) -> Dict[str, Any]:
        """Build response for successful execution (no retry needed)."""
        now_ms = int(time.time() * 1000)
        total_elapsed_ms = now_ms - start_time_ms

        return {
            '__event__': 'success',
            'outputs': {
                'success': {
                    'attempt': attempt,
                    'max_retries': self.max_retries,
                    'total_elapsed_ms': total_elapsed_ms,
                }
            },
            'attempt': attempt,
            'max_retries': self.max_retries,
            'delay_ms': 0,
            'total_elapsed_ms': total_elapsed_ms,
            'last_error': None,
        }

    def _build_exhausted_response(
        self, attempt: int, last_error: Optional[Dict], start_time_ms: int
    ) -> Dict[str, Any]:
        """Build response when all retries are exhausted."""
        now_ms = int(time.time() * 1000)
        total_elapsed_ms = now_ms - start_time_ms

        return {
            '__event__': 'exhausted',
            'outputs': {
                'exhausted': {
                    'attempt': attempt,
                    'max_retries': self.max_retries,
                    'last_error': last_error,
                    'total_elapsed_ms': total_elapsed_ms,
                }
            },
            'attempt': attempt,
            'max_retries': self.max_retries,
            'delay_ms': 0,
            'total_elapsed_ms': total_elapsed_ms,
            'last_error': last_error,
        }
