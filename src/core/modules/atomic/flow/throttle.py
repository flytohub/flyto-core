# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Throttle Module - Throttle execution rate

Limits execution frequency by enforcing a minimum interval between calls.
Unlike debounce (which waits for inactivity), throttle guarantees a
maximum execution rate.

Useful for:
- Enforcing API call frequency limits
- Preventing UI update storms
- Steady-rate processing pipelines

Workflow Spec v1.1:
- Uses __event__ for engine routing (executed/throttled)
- Tracks last execution timestamp in context state
"""
import time
from typing import Any, Dict

from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field
from ...types import NodeType, EdgeType, DataType


@register_module(
    module_id='flow.throttle',
    version='1.0.0',
    category='flow',
    tags=['flow', 'throttle', 'rate', 'timing', 'control'],
    label='Throttle',
    label_key='modules.flow.throttle.label',
    description='Throttle execution rate with minimum interval',
    description_key='modules.flow.throttle.description',
    icon='Activity',
    color='#10B981',

    input_types=['control', 'any'],
    output_types=['control'],

    can_receive_from=['*'],
    can_connect_to=['*'],

    node_type=NodeType.STANDARD,

    input_ports=[
        {
            'id': 'input',
            'label': 'Input',
            'label_key': 'modules.flow.throttle.ports.input',
            'data_type': DataType.ANY.value,
            'edge_type': EdgeType.CONTROL.value,
            'max_connections': 1,
            'required': True
        }
    ],

    output_ports=[
        {
            'id': 'executed',
            'label': 'Executed',
            'label_key': 'modules.flow.throttle.ports.executed',
            'event': 'executed',
            'color': '#10B981',
            'edge_type': EdgeType.CONTROL.value,
            'description': 'Execution allowed (interval has passed)'
        },
        {
            'id': 'throttled',
            'label': 'Throttled',
            'label_key': 'modules.flow.throttle.ports.throttled',
            'event': 'throttled',
            'color': '#F59E0B',
            'edge_type': EdgeType.CONTROL.value,
            'description': 'Execution throttled (too soon since last execution)'
        }
    ],

    retryable=False,
    concurrent_safe=True,
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema=compose(
        field(
            'interval_ms',
            type='integer',
            label='Interval (ms)',
            label_key='modules.flow.throttle.params.interval_ms.label',
            description='Minimum time between executions in milliseconds',
            description_key='modules.flow.throttle.params.interval_ms.description',
            min=0,
            max=300000,
            required=True,
        ),
        field(
            'leading',
            type='boolean',
            label='Leading Edge',
            label_key='modules.flow.throttle.params.leading.label',
            description='Execute on the leading edge (first call passes immediately)',
            description_key='modules.flow.throttle.params.leading.description',
            default=True,
        ),
    ),

    output_schema={
        '__event__': {
            'type': 'string',
            'description': 'Event for routing (executed/throttled)',
            'description_key': 'modules.flow.throttle.output.__event__.description'
        },
        'last_execution_ms': {
            'type': 'integer',
            'description': 'Timestamp of last allowed execution',
            'description_key': 'modules.flow.throttle.output.last_execution_ms.description'
        },
        'calls_throttled': {
            'type': 'integer',
            'description': 'Number of calls throttled since last execution',
            'description_key': 'modules.flow.throttle.output.calls_throttled.description'
        },
        'time_since_last_ms': {
            'type': 'integer',
            'description': 'Time elapsed since last execution in milliseconds',
            'description_key': 'modules.flow.throttle.output.time_since_last_ms.description'
        },
        'remaining_ms': {
            'type': 'integer',
            'description': 'Milliseconds remaining until next execution is allowed',
            'description_key': 'modules.flow.throttle.output.remaining_ms.description'
        }
    },

    examples=[
        {
            'name': 'Throttle to 1 per second',
            'description': 'Allow at most one execution per second',
            'params': {
                'interval_ms': 1000
            }
        },
        {
            'name': 'API rate compliance',
            'description': 'Enforce 200ms minimum between API calls',
            'params': {
                'interval_ms': 200,
                'leading': True
            }
        },
        {
            'name': 'Delayed start throttle',
            'description': 'Skip first call, then allow every 5 seconds',
            'params': {
                'interval_ms': 5000,
                'leading': False
            }
        }
    ],
    author='Flyto Team',
    license='MIT',
    timeout_ms=300000,
)
class ThrottleModule(BaseModule):
    """
    Throttle module.

    Enforces a minimum interval between executions. Unlike debounce
    which waits for inactivity, throttle provides a steady maximum
    execution rate.

    With leading=True (default), the first call in a burst passes
    immediately and subsequent calls within the interval are throttled.
    With leading=False, the first call is also throttled.
    """

    module_name = "Throttle"
    module_description = "Throttle execution rate with minimum interval"

    def validate_params(self) -> None:
        self.interval_ms = self.params.get('interval_ms')
        self.leading = self.params.get('leading', True)

        if self.interval_ms is None:
            raise ValueError("interval_ms is required")
        if self.interval_ms < 0:
            raise ValueError("interval_ms must be non-negative")

    async def execute(self) -> Dict[str, Any]:
        """
        Check throttle state and determine whether to execute or throttle.

        Compares current time against the last execution timestamp.
        Only allows execution if the configured interval has passed.
        """
        try:
            now_ms = int(time.time() * 1000)

            th_state = {}
            if self.context:
                th_state = self.context.get('__throttle_state__', {})

            last_execution_ms = th_state.get('last_execution_ms', 0)
            calls_throttled = th_state.get('calls_throttled', 0)
            time_since_last = now_ms - last_execution_ms if last_execution_ms > 0 else 0
            is_first_call = last_execution_ms == 0

            should_execute = (is_first_call and self.leading) or (
                not is_first_call and time_since_last >= self.interval_ms
            )

            if should_execute:
                return self._build_executed_response(
                    now_ms, calls_throttled, time_since_last
                )
            return self._build_throttled_response(
                last_execution_ms, calls_throttled, time_since_last
            )

        except Exception as e:
            return {
                '__event__': 'throttled',
                'outputs': {
                    'throttled': {'message': str(e)}
                },
                '__error__': {
                    'code': 'THROTTLE_ERROR',
                    'message': str(e)
                }
            }

    def _build_executed_response(
        self, now_ms, calls_throttled, time_since_last
    ) -> Dict[str, Any]:
        new_state = {'last_execution_ms': now_ms, 'calls_throttled': 0}
        return {
            '__event__': 'executed',
            '__throttle_state__': new_state,
            'outputs': {
                'executed': {
                    'last_execution_ms': now_ms,
                    'calls_throttled': calls_throttled,
                    'time_since_last_ms': time_since_last,
                    'remaining_ms': 0,
                }
            },
            'last_execution_ms': now_ms,
            'calls_throttled': calls_throttled,
            'time_since_last_ms': time_since_last,
            'remaining_ms': 0,
        }

    def _build_throttled_response(
        self, last_execution_ms, calls_throttled, time_since_last
    ) -> Dict[str, Any]:
        remaining_ms = max(0, self.interval_ms - time_since_last)
        new_state = {
            'last_execution_ms': last_execution_ms,
            'calls_throttled': calls_throttled + 1,
        }
        return {
            '__event__': 'throttled',
            '__throttle_state__': new_state,
            'outputs': {
                'throttled': {
                    'last_execution_ms': last_execution_ms,
                    'calls_throttled': calls_throttled + 1,
                    'time_since_last_ms': time_since_last,
                    'remaining_ms': remaining_ms,
                }
            },
            'last_execution_ms': last_execution_ms,
            'calls_throttled': calls_throttled + 1,
            'time_since_last_ms': time_since_last,
            'remaining_ms': remaining_ms,
        }
