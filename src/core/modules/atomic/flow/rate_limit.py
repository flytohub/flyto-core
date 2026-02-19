"""
Rate Limit Module - Token bucket rate limiter

Controls the rate of execution using configurable strategies.
Useful for:
- API rate limiting compliance
- Preventing resource exhaustion
- Throttling downstream services

Workflow Spec v1.1:
- Uses __event__ for engine routing (allowed/throttled/error)
- Supports fixed window, sliding window, and token bucket strategies
"""
import time
from typing import Any, Dict, List

from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field
from ...types import NodeType, EdgeType, DataType


@register_module(
    module_id='flow.rate_limit',
    version='1.0.0',
    category='flow',
    tags=['flow', 'rate-limit', 'throttle', 'token-bucket', 'control'],
    label='Rate Limit',
    label_key='modules.flow.rate_limit.label',
    description='Rate limiter with token bucket strategy',
    description_key='modules.flow.rate_limit.description',
    icon='Gauge',
    color='#8B5CF6',

    input_types=['control', 'any'],
    output_types=['control'],

    can_receive_from=['*'],
    can_connect_to=['*'],

    node_type=NodeType.STANDARD,

    input_ports=[
        {
            'id': 'input',
            'label': 'Input',
            'label_key': 'modules.flow.rate_limit.ports.input',
            'data_type': DataType.ANY.value,
            'edge_type': EdgeType.CONTROL.value,
            'max_connections': 1,
            'required': True
        }
    ],

    output_ports=[
        {
            'id': 'allowed',
            'label': 'Allowed',
            'label_key': 'modules.flow.rate_limit.ports.allowed',
            'event': 'allowed',
            'color': '#10B981',
            'edge_type': EdgeType.CONTROL.value,
            'description': 'Request is within rate limit'
        },
        {
            'id': 'throttled',
            'label': 'Throttled',
            'label_key': 'modules.flow.rate_limit.ports.throttled',
            'event': 'throttled',
            'color': '#F59E0B',
            'edge_type': EdgeType.CONTROL.value,
            'description': 'Request exceeds rate limit'
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
            'max_requests',
            type='integer',
            label='Max Requests',
            label_key='modules.flow.rate_limit.params.max_requests.label',
            description='Maximum number of requests allowed per window',
            description_key='modules.flow.rate_limit.params.max_requests.description',
            min=1,
            max=10000,
            required=True,
        ),
        field(
            'window_ms',
            type='integer',
            label='Window (ms)',
            label_key='modules.flow.rate_limit.params.window_ms.label',
            description='Time window in milliseconds',
            description_key='modules.flow.rate_limit.params.window_ms.description',
            default=60000,
            min=100,
            max=3600000,
        ),
        field(
            'strategy',
            type='string',
            label='Strategy',
            label_key='modules.flow.rate_limit.params.strategy.label',
            description='Rate limiting strategy',
            description_key='modules.flow.rate_limit.params.strategy.description',
            default='token_bucket',
            options=[
                {'value': 'fixed_window', 'label': 'Fixed Window'},
                {'value': 'sliding_window', 'label': 'Sliding Window'},
                {'value': 'token_bucket', 'label': 'Token Bucket'},
            ],
        ),
        field(
            'queue_overflow',
            type='string',
            label='Queue Overflow',
            label_key='modules.flow.rate_limit.params.queue_overflow.label',
            description='Behavior when rate limit is exceeded',
            description_key='modules.flow.rate_limit.params.queue_overflow.description',
            default='wait',
            options=[
                {'value': 'drop', 'label': 'Drop (discard request)'},
                {'value': 'wait', 'label': 'Wait (queue until available)'},
                {'value': 'error', 'label': 'Error (raise error)'},
            ],
        ),
    ),

    output_schema={
        '__event__': {
            'type': 'string',
            'description': 'Event for routing (allowed/throttled/error)',
            'description_key': 'modules.flow.rate_limit.output.__event__.description'
        },
        'tokens_remaining': {
            'type': 'integer',
            'description': 'Number of tokens remaining in the bucket',
            'description_key': 'modules.flow.rate_limit.output.tokens_remaining.description'
        },
        'window_reset_ms': {
            'type': 'integer',
            'description': 'Milliseconds until the window resets',
            'description_key': 'modules.flow.rate_limit.output.window_reset_ms.description'
        },
        'requests_in_window': {
            'type': 'integer',
            'description': 'Number of requests made in current window',
            'description_key': 'modules.flow.rate_limit.output.requests_in_window.description'
        },
        'wait_ms': {
            'type': 'integer',
            'description': 'Milliseconds to wait before retry (if throttled)',
            'description_key': 'modules.flow.rate_limit.output.wait_ms.description'
        }
    },

    examples=[
        {
            'name': 'API rate limiting',
            'description': 'Limit to 100 requests per minute',
            'params': {
                'max_requests': 100,
                'window_ms': 60000,
                'strategy': 'token_bucket'
            }
        },
        {
            'name': 'Strict fixed window',
            'description': '10 requests per second with error on overflow',
            'params': {
                'max_requests': 10,
                'window_ms': 1000,
                'strategy': 'fixed_window',
                'queue_overflow': 'error'
            }
        },
        {
            'name': 'Sliding window with wait',
            'description': '50 requests per 30 seconds, queue excess',
            'params': {
                'max_requests': 50,
                'window_ms': 30000,
                'strategy': 'sliding_window',
                'queue_overflow': 'wait'
            }
        }
    ],
    author='Flyto Team',
    license='MIT',
    timeout_ms=300000,
)
class RateLimitModule(BaseModule):
    """
    Rate limiter module using token bucket algorithm.

    Implements three strategies:
    - fixed_window: Simple counter reset at window boundary
    - sliding_window: Rolling window with timestamp tracking
    - token_bucket: Tokens refill continuously over time

    The module tracks request timestamps in context state to
    determine whether to allow or throttle the current request.
    """

    module_name = "Rate Limit"
    module_description = "Rate limiter with token bucket strategy"

    def validate_params(self) -> None:
        self.max_requests = self.params.get('max_requests')
        self.window_ms = self.params.get('window_ms', 60000)
        self.strategy = self.params.get('strategy', 'token_bucket')
        self.queue_overflow = self.params.get('queue_overflow', 'wait')

        if self.max_requests is None:
            raise ValueError("max_requests is required")
        if self.max_requests < 1:
            raise ValueError("max_requests must be at least 1")
        if self.strategy not in ('fixed_window', 'sliding_window', 'token_bucket'):
            raise ValueError(
                "strategy must be one of: fixed_window, sliding_window, token_bucket"
            )
        if self.queue_overflow not in ('drop', 'wait', 'error'):
            raise ValueError("queue_overflow must be one of: drop, wait, error")

    async def execute(self) -> Dict[str, Any]:
        """
        Check rate limit and return allowed or throttled event.

        Uses context state to track request history across executions.
        """
        try:
            now_ms = int(time.time() * 1000)

            # Get rate limit state from context
            rl_state = {}
            if self.context:
                rl_state = self.context.get('__rate_limit_state__', {})

            if self.strategy == 'token_bucket':
                return self._token_bucket(now_ms, rl_state)
            elif self.strategy == 'sliding_window':
                return self._sliding_window(now_ms, rl_state)
            else:
                return self._fixed_window(now_ms, rl_state)

        except Exception as e:
            return {
                '__event__': 'error',
                'outputs': {
                    'error': {'message': str(e)}
                },
                '__error__': {
                    'code': 'RATE_LIMIT_ERROR',
                    'message': str(e)
                }
            }

    def _token_bucket(
        self, now_ms: int, state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Token bucket algorithm.

        Tokens refill at a constant rate. Each request consumes one token.
        If no tokens available, the request is throttled.
        """
        # Initialize or restore bucket state
        tokens = state.get('tokens', float(self.max_requests))
        last_refill_ms = state.get('last_refill_ms', now_ms)

        # Calculate tokens to add based on elapsed time
        elapsed_ms = now_ms - last_refill_ms
        refill_rate = self.max_requests / self.window_ms  # tokens per ms
        tokens_to_add = elapsed_ms * refill_rate
        tokens = min(tokens + tokens_to_add, float(self.max_requests))

        # Try to consume a token
        if tokens >= 1.0:
            tokens -= 1.0
            requests_in_window = self.max_requests - int(tokens)

            # Update state
            new_state = {
                'tokens': tokens,
                'last_refill_ms': now_ms,
            }

            return {
                '__event__': 'allowed',
                '__rate_limit_state__': new_state,
                'outputs': {
                    'allowed': {
                        'tokens_remaining': int(tokens),
                        'requests_in_window': requests_in_window,
                    }
                },
                'tokens_remaining': int(tokens),
                'window_reset_ms': 0,
                'requests_in_window': requests_in_window,
                'wait_ms': 0,
            }
        else:
            # Calculate wait time until next token
            tokens_needed = 1.0 - tokens
            wait_ms = int(tokens_needed / refill_rate) if refill_rate > 0 else self.window_ms

            return self._build_throttled_response(
                tokens_remaining=0,
                requests_in_window=self.max_requests,
                window_reset_ms=wait_ms,
                wait_ms=wait_ms,
                state={'tokens': tokens, 'last_refill_ms': now_ms},
            )

    def _sliding_window(
        self, now_ms: int, state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Sliding window algorithm.

        Tracks individual request timestamps. Counts requests within
        the rolling window. Expired timestamps are pruned.
        """
        timestamps: List[int] = state.get('timestamps', [])

        # Prune expired timestamps
        window_start = now_ms - self.window_ms
        timestamps = [ts for ts in timestamps if ts > window_start]

        requests_in_window = len(timestamps)

        if requests_in_window < self.max_requests:
            timestamps.append(now_ms)
            tokens_remaining = self.max_requests - requests_in_window - 1

            new_state = {'timestamps': timestamps}

            return {
                '__event__': 'allowed',
                '__rate_limit_state__': new_state,
                'outputs': {
                    'allowed': {
                        'tokens_remaining': tokens_remaining,
                        'requests_in_window': requests_in_window + 1,
                    }
                },
                'tokens_remaining': tokens_remaining,
                'window_reset_ms': (timestamps[0] + self.window_ms - now_ms) if timestamps else self.window_ms,
                'requests_in_window': requests_in_window + 1,
                'wait_ms': 0,
            }
        else:
            # Oldest request determines when a slot opens
            oldest_ts = timestamps[0] if timestamps else now_ms
            wait_ms = max(0, oldest_ts + self.window_ms - now_ms)

            return self._build_throttled_response(
                tokens_remaining=0,
                requests_in_window=requests_in_window,
                window_reset_ms=wait_ms,
                wait_ms=wait_ms,
                state={'timestamps': timestamps},
            )

    def _fixed_window(
        self, now_ms: int, state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Fixed window algorithm.

        Counter resets at fixed window boundaries.
        Simple but can allow bursts at window edges.
        """
        window_start = state.get('window_start', now_ms)
        count = state.get('count', 0)

        # Check if window has expired
        if now_ms - window_start >= self.window_ms:
            window_start = now_ms
            count = 0

        if count < self.max_requests:
            count += 1
            tokens_remaining = self.max_requests - count
            window_reset_ms = max(0, window_start + self.window_ms - now_ms)

            new_state = {
                'window_start': window_start,
                'count': count,
            }

            return {
                '__event__': 'allowed',
                '__rate_limit_state__': new_state,
                'outputs': {
                    'allowed': {
                        'tokens_remaining': tokens_remaining,
                        'requests_in_window': count,
                    }
                },
                'tokens_remaining': tokens_remaining,
                'window_reset_ms': window_reset_ms,
                'requests_in_window': count,
                'wait_ms': 0,
            }
        else:
            window_reset_ms = max(0, window_start + self.window_ms - now_ms)

            return self._build_throttled_response(
                tokens_remaining=0,
                requests_in_window=count,
                window_reset_ms=window_reset_ms,
                wait_ms=window_reset_ms,
                state={'window_start': window_start, 'count': count},
            )

    def _build_throttled_response(
        self,
        tokens_remaining: int,
        requests_in_window: int,
        window_reset_ms: int,
        wait_ms: int,
        state: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build response when request is throttled."""
        event = 'throttled'

        # If queue_overflow is 'error', return error event instead
        if self.queue_overflow == 'error':
            return {
                '__event__': 'error',
                '__rate_limit_state__': state,
                'outputs': {
                    'error': {
                        'message': 'Rate limit exceeded',
                        'wait_ms': wait_ms,
                    }
                },
                '__error__': {
                    'code': 'RATE_LIMIT_EXCEEDED',
                    'message': f'Rate limit exceeded. Retry after {wait_ms}ms',
                },
                'tokens_remaining': tokens_remaining,
                'window_reset_ms': window_reset_ms,
                'requests_in_window': requests_in_window,
                'wait_ms': wait_ms,
            }

        return {
            '__event__': event,
            '__rate_limit_state__': state,
            'outputs': {
                'throttled': {
                    'tokens_remaining': tokens_remaining,
                    'requests_in_window': requests_in_window,
                    'wait_ms': wait_ms,
                    'queue_overflow': self.queue_overflow,
                }
            },
            'tokens_remaining': tokens_remaining,
            'window_reset_ms': window_reset_ms,
            'requests_in_window': requests_in_window,
            'wait_ms': wait_ms,
        }
