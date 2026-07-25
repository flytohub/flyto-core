# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Reverse Breakpoint Module

Set or remove a CDP breakpoint by URL/line, so a subsequent reverse.wait_paused
call can catch the page pausing when that line executes.
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field
from ...schema.constants import FieldGroup
from ...types import StabilityLevel


@register_module(
    module_id='reverse.breakpoint',
    version='1.0.0',
    category='reverse',
    stability=StabilityLevel.BETA,
    tags=['reverse', 'debugger', 'cdp', 'breakpoint'],
    label='Set/Remove Breakpoint',
    label_key='modules.reverse.breakpoint.label',
    description='Set or remove a breakpoint by script URL and line number',
    description_key='modules.reverse.breakpoint.description',
    icon='CircleDot',
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
            label_key='modules.reverse.breakpoint.params.action.label',
            description='Breakpoint operation to perform',
            required=True,
            options=[
                {'value': 'set', 'label': 'Set breakpoint'},
                {'value': 'remove', 'label': 'Remove breakpoint'},
            ],
            group=FieldGroup.BASIC,
        ),
        field(
            'url',
            type='string',
            label='Script URL',
            label_key='modules.reverse.breakpoint.params.url.label',
            description='Exact script URL to break in (set action; use url or url_regex)',
            placeholder='https://example.com/app.js',
            required=False,
            showIf={"action": {"$in": ["set"]}},
            group=FieldGroup.OPTIONS,
        ),
        field(
            'url_regex',
            type='string',
            label='Script URL Regex',
            label_key='modules.reverse.breakpoint.params.url_regex.label',
            description='Regex matching the script URL to break in (set action; use url or url_regex)',
            placeholder='.*app\\.js$',
            required=False,
            showIf={"action": {"$in": ["set"]}},
            group=FieldGroup.OPTIONS,
        ),
        field(
            'line_number',
            type='number',
            label='Line Number',
            label_key='modules.reverse.breakpoint.params.line_number.label',
            description='Zero-based line number to break at',
            default=0,
            min=0,
            required=False,
            showIf={"action": {"$in": ["set"]}},
            group=FieldGroup.OPTIONS,
        ),
        field(
            'column_number',
            type='number',
            label='Column Number',
            label_key='modules.reverse.breakpoint.params.column_number.label',
            description='Zero-based column number to break at',
            default=0,
            min=0,
            required=False,
            showIf={"action": {"$in": ["set"]}},
            group=FieldGroup.ADVANCED,
        ),
        field(
            'condition',
            type='string',
            label='Condition',
            label_key='modules.reverse.breakpoint.params.condition.label',
            description='JavaScript expression — breakpoint only fires when it evaluates truthy',
            placeholder='userId === 42',
            required=False,
            showIf={"action": {"$in": ["set"]}},
            group=FieldGroup.ADVANCED,
        ),
        field(
            'breakpoint_id',
            type='string',
            label='Breakpoint ID',
            label_key='modules.reverse.breakpoint.params.breakpoint_id.label',
            description='Breakpoint ID returned by a previous "set" call',
            placeholder='1:0:0:https://example.com/app.js',
            required=False,
            showIf={"action": {"$in": ["remove"]}},
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.reverse.breakpoint.output.status.description'},
        'breakpointId': {'type': 'string', 'description': 'Breakpoint ID (set action)',
                'description_key': 'modules.reverse.breakpoint.output.breakpointId.description'},
        'locations': {'type': 'array', 'description': 'Resolved breakpoint locations (set action)',
                'description_key': 'modules.reverse.breakpoint.output.locations.description'},
    },
    examples=[
        {'name': 'Set breakpoint at line 10', 'params': {'action': 'set', 'url': 'https://example.com/app.js', 'line_number': 10}},
        {'name': 'Remove a breakpoint', 'params': {'action': 'remove', 'breakpoint_id': '1:10:0:https://example.com/app.js'}},
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=30000,
    required_permissions=['browser.debug'],
)
class ReverseBreakpointModule(BaseModule):
    """Set or remove a CDP breakpoint by script URL and line number."""

    module_name = "Set/Remove Breakpoint"
    module_description = "Set or remove a breakpoint by script URL and line number"
    required_permission = "browser.debug"

    def validate_params(self) -> None:
        self.action = self.params.get('action')
        if self.action not in ('set', 'remove'):
            raise ValueError(f"Invalid action: {self.action}. Must be set or remove")

        self.url = self.params.get('url')
        self.url_regex = self.params.get('url_regex')
        if self.action == 'set' and not self.url and not self.url_regex:
            raise ValueError("set requires url or url_regex")

        self.line_number = self.params.get('line_number', 0)
        self.column_number = self.params.get('column_number', 0)
        self.condition = self.params.get('condition')

        self.breakpoint_id = self.params.get('breakpoint_id')
        if self.action == 'remove' and not self.breakpoint_id:
            raise ValueError("remove requires breakpoint_id")

    async def execute(self) -> Dict[str, Any]:
        session = self.context.get('reverse_session')
        if not session:
            raise RuntimeError("No active debugger session. Please run reverse.attach first")

        if self.action == 'set':
            entry = await session.set_breakpoint(
                url=self.url,
                url_regex=self.url_regex,
                line_number=self.line_number,
                column_number=self.column_number,
                condition=self.condition,
            )
            return {'status': 'success', **entry}

        return await session.remove_breakpoint(self.breakpoint_id)
