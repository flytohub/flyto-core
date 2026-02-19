# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Debounce Module - Debounce execution

Prevents repeated execution by waiting for a period of inactivity.
Useful for:
- Preventing duplicate API calls from rapid triggers
- Batching rapid user actions into a single execution
- Search-as-you-type patterns

Workflow Spec v1.1:
- Uses __event__ for engine routing (executed/skipped)
- Supports leading and trailing edge execution
"""
import time
from typing import Any, Dict

from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field
from ...types import NodeType, EdgeType, DataType


@register_module(
    module_id='flow.debounce',
    version='1.0.0',
    category='flow',
    tags=['flow', 'debounce', 'timing', 'control'],
    label='Debounce',
    label_key='modules.flow.debounce.label',
    description='Debounce execution to prevent rapid repeated calls',
    description_key='modules.flow.debounce.description',
    icon='Timer',
    color='#06B6D4',

    input_types=['control', 'any'],
    output_types=['control'],

    can_receive_from=['*'],
    can_connect_to=['*'],

    node_type=NodeType.STANDARD,

    input_ports=[
        {
            'id': 'input',
            'label': 'Input',
            'label_key': 'modules.flow.debounce.ports.input',
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
            'label_key': 'modules.flow.debounce.ports.executed',
            'event': 'executed',
            'color': '#10B981',
            'edge_type': EdgeType.CONTROL.value,
            'description': 'Execution allowed after debounce period'
        },
        {
            'id': 'skipped',
            'label': 'Skipped',
            'label_key': 'modules.flow.debounce.ports.skipped',
            'event': 'skipped',
            'color': '#9CA3AF',
            'edge_type': EdgeType.CONTROL.value,
            'description': 'Execution skipped (within debounce window)'
        }
    ],

    retryable=False,
    concurrent_safe=True,
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema=compose(
        field(
            'delay_ms',
            type='integer',
            label='Delay (ms)',
            label_key='modules.flow.debounce.params.delay_ms.label',
            description='Wait time in milliseconds before allowing execution',
            description_key='modules.flow.debounce.params.delay_ms.description',
            min=0,
            max=300000,
            required=True,
        ),
        field(
            'leading',
            type='boolean',
            label='Leading Edge',
            label_key='modules.flow.debounce.params.leading.label',
            description='Execute on the leading edge (first call immediately)',
            description_key='modules.flow.debounce.params.leading.description',
            default=False,
        ),
        field(
            'trailing',
            type='boolean',
            label='Trailing Edge',
            label_key='modules.flow.debounce.params.trailing.label',
            description='Execute on the trailing edge (after delay of inactivity)',
            description_key='modules.flow.debounce.params.trailing.description',
            default=True,
        ),
    ),

    output_schema={
        '__event__': {
            'type': 'string',
            'description': 'Event for routing (executed/skipped)',
            'description_key': 'modules.flow.debounce.output.__event__.description'
        },
        'last_call_ms': {
            'type': 'integer',
            'description': 'Timestamp of the last call',
            'description_key': 'modules.flow.debounce.output.last_call_ms.description'
        },
        'calls_debounced': {
            'type': 'integer',
            'description': 'Number of calls that were debounced (skipped)',
            'description_key': 'modules.flow.debounce.output.calls_debounced.description'
        },
        'time_since_last_ms': {
            'type': 'integer',
            'description': 'Time since last call in milliseconds',
            'description_key': 'modules.flow.debounce.output.time_since_last_ms.description'
        },
        'edge': {
            'type': 'string',
            'description': 'Which edge triggered execution (leading/trailing)',
            'description_key': 'modules.flow.debounce.output.edge.description'
        }
    },

    examples=[
        {
            'name': 'Basic debounce (500ms)',
            'description': 'Wait 500ms of inactivity before executing',
            'params': {
                'delay_ms': 500
            }
        },
        {
            'name': 'Leading edge debounce',
            'description': 'Execute immediately on first call, then debounce',
            'params': {
                'delay_ms': 1000,
                'leading': True,
                'trailing': False
            }
        },
        {
            'name': 'Both edges',
            'description': 'Execute on first call and after inactivity',
            'params': {
                'delay_ms': 2000,
                'leading': True,
                'trailing': True
            }
        }
    ],
    author='Flyto Team',
    license='MIT',
    timeout_ms=300000,
)
class DebounceModule(BaseModule):
    """
    Debounce module.

    Prevents rapid repeated executions by tracking call timestamps.
    Supports leading edge (execute immediately on first call) and
    trailing edge (execute after a period of inactivity).

    Uses context state to persist debounce timing across executions.
    """

    module_name = "Debounce"
    module_description = "Debounce execution to prevent rapid repeated calls"

    def validate_params(self) -> None:
        self.delay_ms = self.params.get('delay_ms')
        self.leading = self.params.get('leading', False)
        self.trailing = self.params.get('trailing', True)

        if self.delay_ms is None:
            raise ValueError("delay_ms is required")
        if self.delay_ms < 0:
            raise ValueError("delay_ms must be non-negative")
        if not self.leading and not self.trailing:
            raise ValueError("At least one of leading or trailing must be True")

    async def execute(self) -> Dict[str, Any]:
        """
        Check debounce state and determine whether to execute or skip.

        Uses timestamps to track when the last call occurred and
        whether enough time has passed since the last activity.
        """
        try:
            now_ms = int(time.time() * 1000)

            # Get debounce state from context
            db_state = {}
            if self.context:
                db_state = self.context.get('__debounce_state__', {})

            last_call_ms = db_state.get('last_call_ms', 0)
            calls_debounced = db_state.get('calls_debounced', 0)
            leading_executed = db_state.get('leading_executed', False)

            time_since_last = now_ms - last_call_ms if last_call_ms > 0 else self.delay_ms + 1

            # Update state: record this call
            new_state = {
                'last_call_ms': now_ms,
                'calls_debounced': calls_debounced,
                'leading_executed': leading_executed,
            }

            # Leading edge: execute on first call or after delay has elapsed
            if self.leading and (not leading_executed or time_since_last > self.delay_ms):
                new_state['leading_executed'] = True
                new_state['calls_debounced'] = 0

                return {
                    '__event__': 'executed',
                    '__debounce_state__': new_state,
                    'outputs': {
                        'executed': {
                            'last_call_ms': now_ms,
                            'calls_debounced': calls_debounced,
                            'time_since_last_ms': time_since_last,
                            'edge': 'leading',
                        }
                    },
                    'last_call_ms': now_ms,
                    'calls_debounced': calls_debounced,
                    'time_since_last_ms': time_since_last,
                    'edge': 'leading',
                }

            # Trailing edge: execute only if enough time has passed since last call
            if self.trailing and time_since_last >= self.delay_ms and last_call_ms > 0:
                new_state['calls_debounced'] = 0
                new_state['leading_executed'] = False

                return {
                    '__event__': 'executed',
                    '__debounce_state__': new_state,
                    'outputs': {
                        'executed': {
                            'last_call_ms': now_ms,
                            'calls_debounced': calls_debounced,
                            'time_since_last_ms': time_since_last,
                            'edge': 'trailing',
                        }
                    },
                    'last_call_ms': now_ms,
                    'calls_debounced': calls_debounced,
                    'time_since_last_ms': time_since_last,
                    'edge': 'trailing',
                }

            # Within debounce window - skip
            new_state['calls_debounced'] = calls_debounced + 1

            return {
                '__event__': 'skipped',
                '__debounce_state__': new_state,
                'outputs': {
                    'skipped': {
                        'last_call_ms': now_ms,
                        'calls_debounced': calls_debounced + 1,
                        'time_since_last_ms': time_since_last,
                        'remaining_ms': max(0, self.delay_ms - time_since_last),
                    }
                },
                'last_call_ms': now_ms,
                'calls_debounced': calls_debounced + 1,
                'time_since_last_ms': time_since_last,
                'edge': None,
            }

        except Exception as e:
            return {
                '__event__': 'skipped',
                'outputs': {
                    'skipped': {'message': str(e)}
                },
                '__error__': {
                    'code': 'DEBOUNCE_ERROR',
                    'message': str(e)
                }
            }
