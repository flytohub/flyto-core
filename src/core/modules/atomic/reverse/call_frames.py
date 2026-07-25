# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Reverse Get Call Frames Module

Return the call stack captured at the current pause point.
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from ...types import StabilityLevel


@register_module(
    module_id='reverse.get_call_frames',
    version='1.0.0',
    category='reverse',
    stability=StabilityLevel.BETA,
    tags=['reverse', 'debugger', 'cdp', 'call-stack'],
    label='Get Call Frames',
    label_key='modules.reverse.get_call_frames.label',
    description='Get the call stack at the current pause point',
    description_key='modules.reverse.get_call_frames.description',
    icon='Layers',
    color='#DC2626',

    input_types=['object'],
    output_types=['object'],

    can_receive_from=['reverse.*', 'flow.*'],
    can_connect_to=['reverse.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*'],

    params_schema={
        '_no_params': {
            'type': 'boolean',
            'label': 'No Parameters',
            'description': 'This module requires no parameters',
            'default': True,
            'hidden': True,
        }
    },
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.reverse.get_call_frames.output.status.description'},
        'callFrames': {'type': 'array', 'description': 'Call frames at the current pause point (empty if not paused)',
                'description_key': 'modules.reverse.get_call_frames.output.callFrames.description'},
    },
    examples=[
        {'name': 'Get current call stack', 'params': {}},
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=15000,
    required_permissions=['browser.debug'],
)
class ReverseGetCallFramesModule(BaseModule):
    """Get the call stack captured at the current pause point."""

    module_name = "Get Call Frames"
    module_description = "Get the call stack at the current pause point"
    required_permission = "browser.debug"

    def validate_params(self) -> None:
        pass

    async def execute(self) -> Dict[str, Any]:
        session = self.context.get('reverse_session')
        if not session:
            raise RuntimeError("No active debugger session. Please run reverse.attach first")

        return {'status': 'success', 'callFrames': session.get_call_frames()}
