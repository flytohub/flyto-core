# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Reverse Evaluate On Call Frame Module

Evaluate a JavaScript expression in the scope of a paused call frame,
resolving locals and closures — this is the primary tool for inspecting
in-memory state while paused at a breakpoint.
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field
from ...schema.constants import FieldGroup
from ...types import StabilityLevel


@register_module(
    module_id='reverse.evaluate_on_call_frame',
    version='1.0.0',
    category='reverse',
    stability=StabilityLevel.BETA,
    tags=['reverse', 'debugger', 'cdp', 'evaluate'],
    label='Evaluate On Call Frame',
    label_key='modules.reverse.evaluate_on_call_frame.label',
    description='Evaluate a JavaScript expression in a paused call frame scope',
    description_key='modules.reverse.evaluate_on_call_frame.description',
    icon='Terminal',
    color='#DC2626',

    input_types=['object'],
    output_types=['object'],

    can_receive_from=['reverse.*', 'flow.*'],
    can_connect_to=['reverse.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*'],

    params_schema=compose(
        field(
            'call_frame_id',
            type='string',
            label='Call Frame ID',
            label_key='modules.reverse.evaluate_on_call_frame.params.call_frame_id.label',
            description='Call frame ID from reverse.wait_paused or reverse.get_call_frames',
            placeholder='{"ordinal":0,"callFrameId":"1"}',
            required=True,
            group=FieldGroup.BASIC,
        ),
        field(
            'expression',
            type='string',
            label='Expression',
            label_key='modules.reverse.evaluate_on_call_frame.params.expression.label',
            description='JavaScript expression to evaluate in the call frame scope',
            placeholder='userId + JSON.stringify(localVar)',
            required=True,
            format='multiline',
            group=FieldGroup.BASIC,
        ),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.reverse.evaluate_on_call_frame.output.status.description'},
        'result': {'type': 'object', 'description': 'Evaluation result (Runtime.RemoteObject)',
                'description_key': 'modules.reverse.evaluate_on_call_frame.output.result.description'},
        'error': {'type': 'string', 'description': 'Error message if the expression threw',
                'description_key': 'modules.reverse.evaluate_on_call_frame.output.error.description'},
    },
    examples=[
        {'name': 'Read a local variable', 'params': {'call_frame_id': '1', 'expression': 'userId'}},
        {'name': 'Inspect a closure value as JSON', 'params': {'call_frame_id': '1', 'expression': 'JSON.stringify(token)'}},
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=30000,
    required_permissions=['browser.debug'],
)
class ReverseEvaluateOnCallFrameModule(BaseModule):
    """Evaluate a JavaScript expression in the scope of a paused call frame."""

    module_name = "Evaluate On Call Frame"
    module_description = "Evaluate a JavaScript expression in a paused call frame scope"
    required_permission = "browser.debug"

    def validate_params(self) -> None:
        self.call_frame_id = self.params.get('call_frame_id')
        if not self.call_frame_id:
            raise ValueError("Missing required parameter: call_frame_id")

        self.expression = self.params.get('expression')
        if not self.expression:
            raise ValueError("Missing required parameter: expression")

    async def execute(self) -> Dict[str, Any]:
        session = self.context.get('reverse_session')
        if not session:
            raise RuntimeError("No active debugger session. Please run reverse.attach first")

        return await session.evaluate_on_call_frame(self.call_frame_id, self.expression)
