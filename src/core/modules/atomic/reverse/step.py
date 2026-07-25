# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Reverse Step Module

Step over, into, or out of the current line while paused, then wait for the
next pause internally so the module returns fresh call-frame state in one
round trip.
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field, presets
from ...schema.constants import FieldGroup
from ...types import StabilityLevel

# See reverse.wait_paused for why the registry timeout must exceed the
# largest allowed caller timeout_ms.
_MAX_CALLER_TIMEOUT_MS = 300000
_REGISTRY_TIMEOUT_MS = 310000


@register_module(
    module_id='reverse.step',
    version='1.0.0',
    category='reverse',
    stability=StabilityLevel.BETA,
    tags=['reverse', 'debugger', 'cdp', 'step'],
    label='Step Execution',
    label_key='modules.reverse.step.label',
    description='Step over, into, or out of the current line while paused',
    description_key='modules.reverse.step.description',
    icon='StepForward',
    color='#DC2626',

    input_types=['object'],
    output_types=['object'],

    can_receive_from=['reverse.*', 'flow.*'],
    can_connect_to=['reverse.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*'],

    params_schema=compose(
        field(
            'action',
            type='select',
            label='Action',
            label_key='modules.reverse.step.params.action.label',
            description='Step operation to perform',
            required=True,
            options=[
                {'value': 'over', 'label': 'Step over'},
                {'value': 'into', 'label': 'Step into'},
                {'value': 'out', 'label': 'Step out'},
            ],
            group=FieldGroup.BASIC,
        ),
        presets.TIMEOUT_MS(key='timeout_ms', default=30000, max_ms=_MAX_CALLER_TIMEOUT_MS),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.reverse.step.output.status.description'},
        'paused': {'type': 'boolean', 'description': 'Whether the page re-paused before the timeout',
                'description_key': 'modules.reverse.step.output.paused.description'},
        'callFrames': {'type': 'array', 'description': 'Call frames at the new pause point',
                'description_key': 'modules.reverse.step.output.callFrames.description'},
    },
    examples=[
        {'name': 'Step over the current line', 'params': {'action': 'over'}},
        {'name': 'Step into the current call', 'params': {'action': 'into'}},
        {'name': 'Step out of the current function', 'params': {'action': 'out'}},
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=_REGISTRY_TIMEOUT_MS,
    required_permissions=['browser.debug'],
)
class ReverseStepModule(BaseModule):
    """Step over, into, or out of the current line while paused."""

    module_name = "Step Execution"
    module_description = "Step over, into, or out of the current line while paused"
    required_permission = "browser.debug"

    def validate_params(self) -> None:
        self.action = self.params.get('action')
        if self.action not in ('over', 'into', 'out'):
            raise ValueError(f"Invalid action: {self.action}. Must be over, into, or out")

        timeout_ms = self.params.get('timeout_ms', 30000)
        self.timeout_ms = min(int(timeout_ms), _MAX_CALLER_TIMEOUT_MS)

    async def execute(self) -> Dict[str, Any]:
        session = self.context.get('reverse_session')
        if not session:
            raise RuntimeError("No active debugger session. Please run reverse.attach first")

        step_fn = {
            'over': session.step_over,
            'into': session.step_into,
            'out': session.step_out,
        }[self.action]

        pause = await step_fn(self.timeout_ms / 1000)
        if pause is None:
            return {'status': 'success', 'paused': False}

        return {
            'status': 'success',
            'paused': True,
            'callFrames': pause.get('callFrames', []),
        }
