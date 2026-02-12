"""
Circuit Breaker Module - Implement circuit breaker pattern

Protects against cascading failures by tracking operation failures
and "opening" the circuit when failure threshold is reached.

Circuit States:
- CLOSED: Normal operation, requests pass through
- OPEN: Circuit tripped, requests fail fast without execution
- HALF_OPEN: Testing if service has recovered

This is a "tool" module - it provides circuit breaker infrastructure
for use by the workflow engine.
"""
from typing import Any, Dict, Optional
from datetime import datetime
from enum import Enum

from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field
from ...types import NodeType, EdgeType, DataType


class CircuitState(str, Enum):
    """Circuit breaker states."""
    CLOSED = 'closed'
    OPEN = 'open'
    HALF_OPEN = 'half_open'


@register_module(
    module_id='error.circuit_breaker',
    version='1.0.0',
    category='error',
    tags=['error', 'circuit-breaker', 'resilience', 'fault-tolerance', 'protection'],
    label='Circuit Breaker',
    label_key='modules.error.circuit_breaker.label',
    description='Protect against cascading failures with circuit breaker pattern',
    description_key='modules.error.circuit_breaker.description',
    icon='Zap',
    color='#EF4444',

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
            'label_key': 'modules.error.circuit_breaker.ports.input',
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
            'label_key': 'modules.error.circuit_breaker.ports.success',
            'event': 'success',
            'color': '#10B981',
            'edge_type': EdgeType.CONTROL.value
        },
        {
            'id': 'circuit_open',
            'label': 'Circuit Open',
            'label_key': 'modules.error.circuit_breaker.ports.circuit_open',
            'event': 'circuit_open',
            'color': '#EF4444',
            'edge_type': EdgeType.CONTROL.value
        },
        {
            'id': 'fallback',
            'label': 'Fallback',
            'label_key': 'modules.error.circuit_breaker.ports.fallback',
            'event': 'fallback',
            'color': '#F59E0B',
            'edge_type': EdgeType.CONTROL.value
        }
    ],

    retryable=False,
    concurrent_safe=False,  # Needs to track state
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema=compose(
        field(
            'action',
            type='object',
            label='Protected Action',
            label_key='modules.error.circuit_breaker.params.action.label',
            description='The action to protect with circuit breaker',
            description_key='modules.error.circuit_breaker.params.action.description',
            required=True,
        ),
        field(
            'circuit_id',
            type='string',
            label='Circuit ID',
            label_key='modules.error.circuit_breaker.params.circuit_id.label',
            description='Unique identifier for this circuit (for state tracking)',
            placeholder='unique-id',
            description_key='modules.error.circuit_breaker.params.circuit_id.description',
            required=True,
        ),
        field(
            'failure_threshold',
            type='integer',
            label='Failure Threshold',
            label_key='modules.error.circuit_breaker.params.failure_threshold.label',
            description='Number of failures before opening circuit',
            description_key='modules.error.circuit_breaker.params.failure_threshold.description',
            default=5,
            min=1,
            max=100,
        ),
        field(
            'failure_window_ms',
            type='integer',
            label='Failure Window (ms)',
            label_key='modules.error.circuit_breaker.params.failure_window_ms.label',
            description='Time window for counting failures',
            description_key='modules.error.circuit_breaker.params.failure_window_ms.description',
            default=60000,
            min=1000,
            max=600000,
        ),
        field(
            'recovery_timeout_ms',
            type='integer',
            label='Recovery Timeout (ms)',
            label_key='modules.error.circuit_breaker.params.recovery_timeout_ms.label',
            description='Time before attempting recovery (half-open state)',
            description_key='modules.error.circuit_breaker.params.recovery_timeout_ms.description',
            default=30000,
            min=1000,
            max=600000,
        ),
        field(
            'success_threshold',
            type='integer',
            label='Success Threshold',
            label_key='modules.error.circuit_breaker.params.success_threshold.label',
            description='Successful requests needed in half-open to close circuit',
            description_key='modules.error.circuit_breaker.params.success_threshold.description',
            default=3,
            min=1,
            max=10,
        ),
        field(
            'fallback',
            type='object',
            label='Fallback Action',
            label_key='modules.error.circuit_breaker.params.fallback.label',
            description='Alternative action when circuit is open',
            description_key='modules.error.circuit_breaker.params.fallback.description',
            required=False,
        ),
        field(
            'fallback_value',
            type='any',
            label='Fallback Value',
            label_key='modules.error.circuit_breaker.params.fallback_value.label',
            description='Static value to return when circuit is open',
            description_key='modules.error.circuit_breaker.params.fallback_value.description',
            required=False,
        ),
        field(
            'track_errors',
            type='array',
            label='Track Error Codes',
            label_key='modules.error.circuit_breaker.params.track_errors.label',
            description='Only count these error codes toward threshold (empty = all)',
            description_key='modules.error.circuit_breaker.params.track_errors.description',
            default=[],
        ),
    ),

    output_schema={
        '__event__': {
            'type': 'string',
            'description': 'Event for routing (success/circuit_open/fallback)',
            'description_key': 'modules.error.circuit_breaker.output.__event__.description'
        },
        'result': {
            'type': 'any',
            'description': 'Result from action or fallback',
            'description_key': 'modules.error.circuit_breaker.output.result.description'
        },
        'circuit_state': {
            'type': 'string',
            'description': 'Current state of circuit (closed/open/half_open)',
            'description_key': 'modules.error.circuit_breaker.output.circuit_state.description'
        },
        'failure_count': {
            'type': 'integer',
            'description': 'Current failure count in window',
            'description_key': 'modules.error.circuit_breaker.output.failure_count.description'
        },
        'last_failure_time': {
            'type': 'string',
            'description': 'Timestamp of last failure',
            'description_key': 'modules.error.circuit_breaker.output.last_failure_time.description'
        },
        'circuit_opened_at': {
            'type': 'string',
            'description': 'When circuit was opened',
            'description_key': 'modules.error.circuit_breaker.output.circuit_opened_at.description'
        }
    },

    examples=[
        {
            'name': 'Basic circuit breaker',
            'description': 'Open circuit after 5 failures in 1 minute',
            'params': {
                'action': {
                    'module': 'http.post',
                    'params': {'url': 'https://api.example.com/submit'}
                },
                'circuit_id': 'example-api',
                'failure_threshold': 5,
                'failure_window_ms': 60000,
                'recovery_timeout_ms': 30000
            }
        },
        {
            'name': 'Circuit breaker with fallback',
            'description': 'Return cached data when circuit opens',
            'params': {
                'action': {
                    'module': 'http.get',
                    'params': {'url': 'https://api.example.com/data'}
                },
                'circuit_id': 'data-api',
                'failure_threshold': 3,
                'fallback': {
                    'module': 'cache.get',
                    'params': {'key': 'data_cache'}
                }
            }
        },
        {
            'name': 'Circuit breaker with static fallback',
            'description': 'Return empty result when circuit opens',
            'params': {
                'action': {
                    'module': 'database.query',
                    'params': {'query': 'SELECT * FROM users'}
                },
                'circuit_id': 'database',
                'failure_threshold': 3,
                'fallback_value': {'users': [], 'from_cache': False}
            }
        }
    ],
    author='Flyto Team',
    license='MIT',
    timeout_ms=60000,
)
class CircuitBreakerModule(BaseModule):
    """
    Circuit Breaker module.

    Implements the circuit breaker pattern to protect against
    cascading failures. Tracks failures within a time window
    and opens the circuit when threshold is exceeded.

    States:
    - CLOSED: Normal operation
    - OPEN: Failing fast, using fallback if available
    - HALF_OPEN: Testing recovery with limited requests
    """

    module_name = "Circuit Breaker"
    module_description = "Protect against cascading failures"

    def validate_params(self) -> None:
        self.action = self.params.get('action', {})
        self.circuit_id = self.params.get('circuit_id', '')
        self.failure_threshold = self.params.get('failure_threshold', 5)
        self.failure_window_ms = self.params.get('failure_window_ms', 60000)
        self.recovery_timeout_ms = self.params.get('recovery_timeout_ms', 30000)
        self.success_threshold = self.params.get('success_threshold', 3)
        self.fallback = self.params.get('fallback')
        self.fallback_value = self.params.get('fallback_value')
        self.track_errors = self.params.get('track_errors', [])

        if not isinstance(self.action, dict):
            raise ValueError("action must be an object with 'module' and 'params'")

        if 'module' not in self.action:
            raise ValueError("action must have a 'module' field")

        if not self.circuit_id:
            raise ValueError("circuit_id is required for state tracking")

        if self.failure_threshold < 1:
            raise ValueError("failure_threshold must be at least 1")

    def _should_count_error(self, error_code: str) -> bool:
        """Determine if error should count toward threshold."""
        if not self.track_errors:
            return True
        return error_code in self.track_errors

    async def execute(self) -> Dict[str, Any]:
        """
        Execute with circuit breaker protection.

        Returns execution plan for workflow engine with circuit
        breaker configuration and current state.
        """
        try:
            # Build circuit breaker execution plan
            circuit_config = {
                'circuit_id': self.circuit_id,
                'action': self.action,
                'failure_threshold': self.failure_threshold,
                'failure_window_ms': self.failure_window_ms,
                'recovery_timeout_ms': self.recovery_timeout_ms,
                'success_threshold': self.success_threshold,
                'fallback': self.fallback,
                'fallback_value': self.fallback_value,
                'track_errors': self.track_errors,
            }

            # Initial state - closed
            # The workflow engine will manage actual state
            current_state = CircuitState.CLOSED.value

            return {
                '__event__': 'success',
                '__circuit_breaker_execution__': circuit_config,
                'outputs': {
                    'success': {
                        'circuit_id': self.circuit_id,
                        'circuit_state': current_state,
                        'action': self.action,
                        'failure_count': 0,
                        'last_failure_time': None,
                        'circuit_opened_at': None
                    }
                },
                'circuit_id': self.circuit_id,
                'circuit_state': current_state,
                'failure_count': 0,
                'last_failure_time': None,
                'circuit_opened_at': None
            }

        except Exception as e:
            # If circuit breaker setup fails, fail fast
            return {
                '__event__': 'circuit_open',
                'outputs': {
                    'circuit_open': {
                        'message': f'Circuit breaker setup failed: {str(e)}',
                        'circuit_id': self.circuit_id
                    }
                },
                '__error__': {
                    'code': 'CIRCUIT_BREAKER_ERROR',
                    'message': str(e)
                }
            }

    def _handle_circuit_open(self) -> Dict[str, Any]:
        """Handle request when circuit is open."""

        # Use fallback value if available
        if self.fallback_value is not None:
            return {
                '__event__': 'fallback',
                'outputs': {
                    'fallback': {
                        'result': self.fallback_value,
                        'circuit_state': CircuitState.OPEN.value,
                        'used_fallback': True,
                        'fallback_type': 'value'
                    }
                },
                'result': self.fallback_value,
                'circuit_state': CircuitState.OPEN.value,
                'used_fallback': True
            }

        # Use fallback action if available
        if self.fallback:
            return {
                '__event__': 'fallback',
                '__execute_fallback__': self.fallback,
                'outputs': {
                    'fallback': {
                        'fallback_action': self.fallback,
                        'circuit_state': CircuitState.OPEN.value,
                        'used_fallback': True,
                        'fallback_type': 'action'
                    }
                },
                'circuit_state': CircuitState.OPEN.value,
                'used_fallback': True
            }

        # No fallback - signal circuit open
        return {
            '__event__': 'circuit_open',
            'outputs': {
                'circuit_open': {
                    'message': 'Circuit is open and no fallback configured',
                    'circuit_id': self.circuit_id,
                    'circuit_state': CircuitState.OPEN.value
                }
            },
            '__error__': {
                'code': 'CIRCUIT_OPEN',
                'message': f'Circuit {self.circuit_id} is open'
            },
            'circuit_state': CircuitState.OPEN.value
        }
