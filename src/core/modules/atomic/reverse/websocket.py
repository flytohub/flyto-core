# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Reverse WebSocket Module

Capture WebSocket connections and frames on the debugged page via CDP's
Network domain (webSocketCreated / webSocketFrameSent / webSocketFrameReceived
/ webSocketClosed events).
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field
from ...schema.constants import FieldGroup
from ...types import StabilityLevel


@register_module(
    module_id='reverse.websocket',
    version='1.0.0',
    category='reverse',
    stability=StabilityLevel.BETA,
    tags=['reverse', 'debugger', 'cdp', 'websocket'],
    label='WebSocket Capture',
    label_key='modules.reverse.websocket.label',
    description='Capture WebSocket connections and frames on the debugged page',
    description_key='modules.reverse.websocket.description',
    icon='Radio',
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
            label_key='modules.reverse.websocket.params.action.label',
            description='WebSocket capture operation to perform',
            required=True,
            options=[
                {'value': 'start', 'label': 'Start capture'},
                {'value': 'stop', 'label': 'Stop capture'},
                {'value': 'list', 'label': 'List captured connections'},
                {'value': 'get_frames', 'label': 'Get frames for a connection'},
            ],
            group=FieldGroup.BASIC,
        ),
        field(
            'request_id',
            type='string',
            label='Request ID',
            label_key='modules.reverse.websocket.params.request_id.label',
            description='WebSocket request ID from a previous "list" call',
            placeholder='12345.7',
            required=False,
            showIf={"action": {"$in": ["get_frames"]}},
            group=FieldGroup.OPTIONS,
        ),
        field(
            'direction',
            type='select',
            label='Direction',
            label_key='modules.reverse.websocket.params.direction.label',
            description='Filter frames by direction',
            default='both',
            options=[
                {'value': 'both', 'label': 'Both'},
                {'value': 'sent', 'label': 'Sent'},
                {'value': 'received', 'label': 'Received'},
            ],
            required=False,
            showIf={"action": {"$in": ["get_frames"]}},
            group=FieldGroup.OPTIONS,
        ),
        field(
            'limit',
            type='number',
            label='Limit',
            label_key='modules.reverse.websocket.params.limit.label',
            description='Return only the most recent N frames',
            required=False,
            min=1,
            showIf={"action": {"$in": ["get_frames"]}},
            group=FieldGroup.ADVANCED,
        ),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.reverse.websocket.output.status.description'},
        'connections': {'type': 'array', 'description': 'Captured WebSocket connections (list action)',
                'description_key': 'modules.reverse.websocket.output.connections.description'},
        'frames': {'type': 'array', 'description': 'Captured frames for a connection (get_frames action)',
                'description_key': 'modules.reverse.websocket.output.frames.description'},
    },
    examples=[
        {'name': 'Start capture', 'params': {'action': 'start'}},
        {'name': 'List connections', 'params': {'action': 'list'}},
        {'name': 'Get received frames', 'params': {'action': 'get_frames', 'request_id': '12345.7', 'direction': 'received'}},
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=30000,
    required_permissions=['browser.debug'],
)
class ReverseWebSocketModule(BaseModule):
    """Capture WebSocket connections and frames on the debugged page."""

    module_name = "WebSocket Capture"
    module_description = "Capture WebSocket connections and frames on the debugged page"
    required_permission = "browser.debug"

    def validate_params(self) -> None:
        self.action = self.params.get('action')
        if self.action not in ('start', 'stop', 'list', 'get_frames'):
            raise ValueError(f"Invalid action: {self.action}. Must be start, stop, list, or get_frames")

        self.request_id = self.params.get('request_id')
        if self.action == 'get_frames' and not self.request_id:
            raise ValueError("get_frames requires request_id")

        self.direction = self.params.get('direction', 'both')
        self.limit = self.params.get('limit')

    async def execute(self) -> Dict[str, Any]:
        session = self.context.get('reverse_session')
        if not session:
            raise RuntimeError("No active debugger session. Please run reverse.attach first")

        if self.action == 'start':
            await session.enable_network()
            return {'status': 'success'}

        if self.action == 'stop':
            await session.disable_network()
            return {'status': 'success'}

        if self.action == 'list':
            connections = session.list_websockets()
            return {'status': 'success', 'connections': connections, 'count': len(connections)}

        frames = session.get_websocket_frames(self.request_id, direction=self.direction, limit=self.limit)
        return {'status': 'success', 'frames': frames, 'count': len(frames)}
