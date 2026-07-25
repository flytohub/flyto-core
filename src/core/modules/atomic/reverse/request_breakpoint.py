# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Reverse Request Breakpoint Module

Pause execution whenever an XHR/fetch request whose URL contains a given
substring is sent, via CDP's DOMDebugger domain (the same mechanism behind
Chrome DevTools' Sources > XHR/Fetch Breakpoints panel). Complements
reverse.breakpoint (script-line breakpoints): this one triggers on network
activity instead of a specific line of code, so it catches a request from
anywhere in the page's code without knowing which script/line issues it.

A hit surfaces through the same Debugger.paused event as a script breakpoint
— reverse.wait_paused/resume/get_call_frames/evaluate_on_call_frame all work
unchanged; the pause result's `reason` is `"XHR"` and `data` carries the
matched URL.
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field
from ...schema.constants import FieldGroup
from ...types import StabilityLevel


@register_module(
    module_id='reverse.request_breakpoint',
    version='1.0.0',
    category='reverse',
    stability=StabilityLevel.BETA,
    tags=['reverse', 'debugger', 'cdp', 'breakpoint', 'network', 'xhr', 'fetch'],
    label='Set/Remove Request Breakpoint',
    label_key='modules.reverse.request_breakpoint.label',
    description='Pause execution when a matching XHR/fetch request is sent',
    description_key='modules.reverse.request_breakpoint.description',
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
            label_key='modules.reverse.request_breakpoint.params.action.label',
            description='Request breakpoint operation to perform',
            required=True,
            options=[
                {'value': 'set', 'label': 'Set request breakpoint'},
                {'value': 'remove', 'label': 'Remove request breakpoint'},
                {'value': 'list', 'label': 'List active request breakpoints'},
            ],
            group=FieldGroup.BASIC,
        ),
        field(
            'url',
            type='string',
            label='URL Substring',
            label_key='modules.reverse.request_breakpoint.params.url.label',
            description='Pause when a request URL contains this substring (set/remove action; empty string matches every XHR/fetch request)',
            placeholder='/api/checkout',
            required=False,
            showIf={"action": {"$in": ["set", "remove"]}},
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.reverse.request_breakpoint.output.status.description'},
        'url': {'type': 'string', 'description': 'URL substring the breakpoint matches (set/remove action)',
                'description_key': 'modules.reverse.request_breakpoint.output.url.description'},
        'breakpoints': {'type': 'array', 'description': 'Active request breakpoints (list action)',
                'description_key': 'modules.reverse.request_breakpoint.output.breakpoints.description'},
        'count': {'type': 'number', 'description': 'Number of active request breakpoints (list action)',
                'description_key': 'modules.reverse.request_breakpoint.output.count.description'},
    },
    examples=[
        {'name': 'Break on any request to /api/checkout', 'params': {'action': 'set', 'url': '/api/checkout'}},
        {'name': 'Break on every XHR/fetch request', 'params': {'action': 'set', 'url': ''}},
        {'name': 'Remove a request breakpoint', 'params': {'action': 'remove', 'url': '/api/checkout'}},
        {'name': 'List active request breakpoints', 'params': {'action': 'list'}},
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=30000,
    required_permissions=['browser.debug'],
)
class ReverseRequestBreakpointModule(BaseModule):
    """Set, remove, or list request-level (XHR/fetch) breakpoints."""

    module_name = "Set/Remove Request Breakpoint"
    module_description = "Pause execution when a matching XHR/fetch request is sent"
    required_permission = "browser.debug"

    def validate_params(self) -> None:
        self.action = self.params.get('action')
        if self.action not in ('set', 'remove', 'list'):
            raise ValueError(f"Invalid action: {self.action}. Must be set, remove, or list")

        self.url = self.params.get('url')
        if self.action in ('set', 'remove') and self.url is None:
            raise ValueError(f"{self.action} requires url (use an empty string to match every request)")

    async def execute(self) -> Dict[str, Any]:
        session = self.context.get('reverse_session')
        if not session:
            raise RuntimeError("No active debugger session. Please run reverse.attach first")

        if self.action == 'set':
            entry = await session.set_request_breakpoint(self.url)
            return {'status': 'success', **entry}

        if self.action == 'remove':
            return await session.remove_request_breakpoint(self.url)

        breakpoints = session.list_request_breakpoints()
        return {'status': 'success', 'breakpoints': breakpoints, 'count': len(breakpoints)}
