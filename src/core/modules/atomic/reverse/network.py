# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Reverse Network Module

Trace which JavaScript call stack triggered a given HTTP request, via CDP's
Network domain. Complements browser.network (which sees requests/responses
via Playwright's high-level API but not the JS initiator stack).
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field
from ...schema.constants import FieldGroup
from ...types import StabilityLevel


@register_module(
    module_id='reverse.network',
    version='1.0.0',
    category='reverse',
    stability=StabilityLevel.BETA,
    tags=['reverse', 'debugger', 'cdp', 'network', 'initiator'],
    label='Network Initiator Tracing',
    label_key='modules.reverse.network.label',
    description='Trace which JavaScript call triggered an HTTP request',
    description_key='modules.reverse.network.description',
    icon='Network',
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
            label_key='modules.reverse.network.params.action.label',
            description='Network tracing operation to perform',
            required=True,
            options=[
                {'value': 'start', 'label': 'Start tracing'},
                {'value': 'stop', 'label': 'Stop tracing'},
                {'value': 'list', 'label': 'List captured requests'},
                {'value': 'get_initiator', 'label': 'Get request initiator'},
            ],
            group=FieldGroup.BASIC,
        ),
        field(
            'request_id',
            type='string',
            label='Request ID',
            label_key='modules.reverse.network.params.request_id.label',
            description='Request ID from a previous "list" call',
            placeholder='12345.6',
            required=False,
            showIf={"action": {"$in": ["get_initiator"]}},
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.reverse.network.output.status.description'},
        'requests': {'type': 'array', 'description': 'Captured requests (list action)',
                'description_key': 'modules.reverse.network.output.requests.description'},
        'type': {'type': 'string', 'description': 'Initiator type: parser, script, preload, or other (get_initiator action)',
                'description_key': 'modules.reverse.network.output.type.description'},
        'stack': {'type': 'array', 'description': 'JS call frames that triggered the request (get_initiator action)',
                'description_key': 'modules.reverse.network.output.stack.description'},
    },
    examples=[
        {'name': 'Start tracing', 'params': {'action': 'start'}},
        {'name': 'List captured requests', 'params': {'action': 'list'}},
        {'name': 'Get initiator for a request', 'params': {'action': 'get_initiator', 'request_id': '12345.6'}},
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=30000,
    required_permissions=['browser.debug'],
)
class ReverseNetworkModule(BaseModule):
    """Trace which JavaScript call stack triggered an HTTP request."""

    module_name = "Network Initiator Tracing"
    module_description = "Trace which JavaScript call triggered an HTTP request"
    required_permission = "browser.debug"

    def validate_params(self) -> None:
        self.action = self.params.get('action')
        if self.action not in ('start', 'stop', 'list', 'get_initiator'):
            raise ValueError(f"Invalid action: {self.action}. Must be start, stop, list, or get_initiator")

        self.request_id = self.params.get('request_id')
        if self.action == 'get_initiator' and not self.request_id:
            raise ValueError("get_initiator requires request_id")

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
            requests = session.list_requests()
            return {'status': 'success', 'requests': requests, 'count': len(requests)}

        return {'status': 'success', **session.get_request_initiator(self.request_id)}
