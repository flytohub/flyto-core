"""
Circuit Breaker Module - Circuit breaker pattern for fault tolerance

Implements the circuit breaker pattern to prevent cascading failures.
Useful for:
- Protecting against failing downstream services
- Allowing systems to recover gracefully
- Preventing resource exhaustion from repeated failures

Workflow Spec v1.1:
- Uses __event__ for engine routing (closed/open/half_open)
- State transitions: closed -> open -> half_open -> closed
"""
import time
from typing import Any, Dict, Optional

from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field
from ...types import NodeType, EdgeType, DataType


@register_module(
    module_id='flow.circuit_breaker',
    version='1.0.0',
    category='flow',
    tags=['flow', 'circuit-breaker', 'resilience', 'fault-tolerance', 'control'],
    label='Circuit Breaker',
    label_key='modules.flow.circuit_breaker.label',
    description='Circuit breaker pattern for fault tolerance',
    description_key='modules.flow.circuit_breaker.description',
    icon='Zap',
    color='#EF4444',

    input_types=['control', 'any'],
    output_types=['control'],

    can_receive_from=['*'],
    can_connect_to=['*'],

    node_type=NodeType.STANDARD,

    input_ports=[
        {
            'id': 'input',
            'label': 'Input',
            'label_key': 'modules.flow.circuit_breaker.ports.input',
            'data_type': DataType.ANY.value,
            'edge_type': EdgeType.CONTROL.value,
            'max_connections': 1,
            'required': True
        }
    ],

    output_ports=[
        {
            'id': 'closed',
            'label': 'Closed',
            'label_key': 'modules.flow.circuit_breaker.ports.closed',
            'event': 'closed',
            'color': '#10B981',
            'edge_type': EdgeType.CONTROL.value,
            'description': 'Circuit is closed (normal operation, requests pass through)'
        },
        {
            'id': 'open',
            'label': 'Open',
            'label_key': 'modules.flow.circuit_breaker.ports.open',
            'event': 'open',
            'color': '#EF4444',
            'edge_type': EdgeType.CONTROL.value,
            'description': 'Circuit is open (requests are blocked)'
        },
        {
            'id': 'half_open',
            'label': 'Half Open',
            'label_key': 'modules.flow.circuit_breaker.ports.half_open',
            'event': 'half_open',
            'color': '#F59E0B',
            'edge_type': EdgeType.CONTROL.value,
            'description': 'Circuit is testing (limited requests allowed)'
        }
    ],

    retryable=False,
    concurrent_safe=True,
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema=compose(
        field(
            'failure_threshold',
            type='integer',
            label='Failure Threshold',
            label_key='modules.flow.circuit_breaker.params.failure_threshold.label',
            description='Number of failures before opening the circuit',
            description_key='modules.flow.circuit_breaker.params.failure_threshold.description',
            default=5,
            min=1,
            max=100,
            required=True,
        ),
        field(
            'reset_timeout_ms',
            type='integer',
            label='Reset Timeout (ms)',
            label_key='modules.flow.circuit_breaker.params.reset_timeout_ms.label',
            description='Time to wait before transitioning from open to half-open',
            description_key='modules.flow.circuit_breaker.params.reset_timeout_ms.description',
            default=60000,
            min=1000,
            max=600000,
        ),
        field(
            'half_open_max',
            type='integer',
            label='Half-Open Max Requests',
            label_key='modules.flow.circuit_breaker.params.half_open_max.label',
            description='Maximum test requests allowed in half-open state',
            description_key='modules.flow.circuit_breaker.params.half_open_max.description',
            default=1,
            min=1,
            max=10,
        ),
    ),

    output_schema={
        '__event__': {
            'type': 'string',
            'description': 'Event for routing (closed/open/half_open)',
            'description_key': 'modules.flow.circuit_breaker.output.__event__.description'
        },
        'state': {
            'type': 'string',
            'description': 'Current circuit breaker state',
            'description_key': 'modules.flow.circuit_breaker.output.state.description'
        },
        'failure_count': {
            'type': 'integer',
            'description': 'Current number of consecutive failures',
            'description_key': 'modules.flow.circuit_breaker.output.failure_count.description'
        },
        'last_failure_time_ms': {
            'type': 'integer',
            'description': 'Timestamp of last failure',
            'description_key': 'modules.flow.circuit_breaker.output.last_failure_time_ms.description'
        },
        'time_until_half_open_ms': {
            'type': 'integer',
            'description': 'Milliseconds until circuit transitions to half-open',
            'description_key': 'modules.flow.circuit_breaker.output.time_until_half_open_ms.description'
        }
    },

    examples=[
        {
            'name': 'Default circuit breaker',
            'description': 'Open after 5 failures, reset after 60 seconds',
            'params': {
                'failure_threshold': 5,
                'reset_timeout_ms': 60000
            }
        },
        {
            'name': 'Sensitive circuit breaker',
            'description': 'Open after 2 failures, fast recovery',
            'params': {
                'failure_threshold': 2,
                'reset_timeout_ms': 10000,
                'half_open_max': 1
            }
        },
        {
            'name': 'Tolerant circuit breaker',
            'description': 'Open after 20 failures, slow recovery with 3 test requests',
            'params': {
                'failure_threshold': 20,
                'reset_timeout_ms': 120000,
                'half_open_max': 3
            }
        }
    ],
    author='Flyto Team',
    license='MIT',
    timeout_ms=300000,
)
class CircuitBreakerModule(BaseModule):
    """
    Circuit breaker module for fault tolerance.

    Implements three states:
    - CLOSED: Normal operation, requests pass through. Failures are counted.
    - OPEN: Circuit tripped, all requests are blocked. Waiting for reset timeout.
    - HALF_OPEN: Testing state, limited requests allowed to check recovery.

    State transitions:
    - closed -> open: When failure_count >= failure_threshold
    - open -> half_open: After reset_timeout_ms has elapsed
    - half_open -> closed: If test request succeeds
    - half_open -> open: If test request fails
    """

    module_name = "Circuit Breaker"
    module_description = "Circuit breaker pattern for fault tolerance"

    # State constants
    STATE_CLOSED = 'closed'
    STATE_OPEN = 'open'
    STATE_HALF_OPEN = 'half_open'

    def validate_params(self) -> None:
        self.failure_threshold = self.params.get('failure_threshold', 5)
        self.reset_timeout_ms = self.params.get('reset_timeout_ms', 60000)
        self.half_open_max = self.params.get('half_open_max', 1)

        if self.failure_threshold < 1:
            raise ValueError("failure_threshold must be at least 1")
        if self.reset_timeout_ms < 1000:
            raise ValueError("reset_timeout_ms must be at least 1000")
        if self.half_open_max < 1:
            raise ValueError("half_open_max must be at least 1")

    async def execute(self) -> Dict[str, Any]:
        """
        Evaluate circuit breaker state and route accordingly.

        Reads circuit state from context and determines whether to
        allow (closed/half_open) or block (open) the request.
        """
        try:
            now_ms = int(time.time() * 1000)

            # Get circuit breaker state from context
            cb_state = {}
            if self.context:
                cb_state = self.context.get('__circuit_breaker_state__', {})

            current_state = cb_state.get('state', self.STATE_CLOSED)
            failure_count = cb_state.get('failure_count', 0)
            last_failure_time_ms = cb_state.get('last_failure_time_ms', 0)
            half_open_count = cb_state.get('half_open_count', 0)

            # Check for incoming error signal (from previous node)
            incoming_error = None
            if self.context:
                incoming_error = self.context.get('__error__')

            # --- State machine logic ---

            if current_state == self.STATE_CLOSED:
                if incoming_error:
                    # Record failure
                    failure_count += 1
                    last_failure_time_ms = now_ms

                    if failure_count >= self.failure_threshold:
                        # Trip the circuit
                        return self._build_response(
                            state=self.STATE_OPEN,
                            failure_count=failure_count,
                            last_failure_time_ms=last_failure_time_ms,
                            now_ms=now_ms,
                        )
                    else:
                        # Stay closed, but record failure
                        return self._build_response(
                            state=self.STATE_CLOSED,
                            failure_count=failure_count,
                            last_failure_time_ms=last_failure_time_ms,
                            now_ms=now_ms,
                        )
                else:
                    # Success - reset failure count
                    return self._build_response(
                        state=self.STATE_CLOSED,
                        failure_count=0,
                        last_failure_time_ms=last_failure_time_ms,
                        now_ms=now_ms,
                    )

            elif current_state == self.STATE_OPEN:
                # Check if reset timeout has elapsed
                elapsed = now_ms - last_failure_time_ms
                if elapsed >= self.reset_timeout_ms:
                    # Transition to half-open
                    return self._build_response(
                        state=self.STATE_HALF_OPEN,
                        failure_count=failure_count,
                        last_failure_time_ms=last_failure_time_ms,
                        now_ms=now_ms,
                        half_open_count=0,
                    )
                else:
                    # Still open, block request
                    time_until_half_open = self.reset_timeout_ms - elapsed
                    return self._build_response(
                        state=self.STATE_OPEN,
                        failure_count=failure_count,
                        last_failure_time_ms=last_failure_time_ms,
                        now_ms=now_ms,
                        time_until_half_open_ms=time_until_half_open,
                    )

            elif current_state == self.STATE_HALF_OPEN:
                if incoming_error:
                    # Test failed, reopen circuit
                    return self._build_response(
                        state=self.STATE_OPEN,
                        failure_count=failure_count,
                        last_failure_time_ms=now_ms,
                        now_ms=now_ms,
                    )
                else:
                    half_open_count += 1
                    if half_open_count >= self.half_open_max:
                        # All test requests succeeded, close circuit
                        return self._build_response(
                            state=self.STATE_CLOSED,
                            failure_count=0,
                            last_failure_time_ms=last_failure_time_ms,
                            now_ms=now_ms,
                        )
                    else:
                        # More test requests needed
                        return self._build_response(
                            state=self.STATE_HALF_OPEN,
                            failure_count=failure_count,
                            last_failure_time_ms=last_failure_time_ms,
                            now_ms=now_ms,
                            half_open_count=half_open_count,
                        )

            # Fallback (should not reach here)
            return self._build_response(
                state=self.STATE_CLOSED,
                failure_count=0,
                last_failure_time_ms=0,
                now_ms=now_ms,
            )

        except Exception as e:
            return {
                '__event__': 'open',
                'outputs': {
                    'open': {'message': str(e)}
                },
                '__error__': {
                    'code': 'CIRCUIT_BREAKER_ERROR',
                    'message': str(e)
                }
            }

    def _build_response(
        self,
        state: str,
        failure_count: int,
        last_failure_time_ms: int,
        now_ms: int,
        half_open_count: int = 0,
        time_until_half_open_ms: int = 0,
    ) -> Dict[str, Any]:
        """Build circuit breaker response with state update."""
        # Calculate time_until_half_open for open state
        if state == self.STATE_OPEN and time_until_half_open_ms == 0:
            elapsed = now_ms - last_failure_time_ms
            time_until_half_open_ms = max(0, self.reset_timeout_ms - elapsed)

        # Persist state for next execution
        new_state = {
            'state': state,
            'failure_count': failure_count,
            'last_failure_time_ms': last_failure_time_ms,
            'half_open_count': half_open_count,
        }

        output_data = {
            'state': state,
            'failure_count': failure_count,
            'last_failure_time_ms': last_failure_time_ms,
            'time_until_half_open_ms': time_until_half_open_ms,
        }

        return {
            '__event__': state,
            '__circuit_breaker_state__': new_state,
            'outputs': {
                state: output_data
            },
            **output_data,
        }
