# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Reverse Hook Module

Wrap a JavaScript function so every call, its arguments, its return value
(or thrown error), and a timestamp are recorded — without needing a paused
breakpoint. Useful for observing how a page calls a function (e.g. a token
generator, a fetch wrapper, a WebSocket constructor) across many invocations.
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field
from ...schema.constants import FieldGroup
from ...types import StabilityLevel


@register_module(
    module_id='reverse.hook',
    version='1.0.0',
    category='reverse',
    stability=StabilityLevel.BETA,
    tags=['reverse', 'debugger', 'cdp', 'hook', 'function'],
    label='Hook Function',
    label_key='modules.reverse.hook.label',
    description='Install or remove a call/return recorder on a JavaScript function',
    description_key='modules.reverse.hook.description',
    icon='Zap',
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
            label_key='modules.reverse.hook.params.action.label',
            description='Hook operation to perform',
            required=True,
            options=[
                {'value': 'install', 'label': 'Install hook'},
                {'value': 'remove', 'label': 'Remove hook'},
                {'value': 'list', 'label': 'List installed hooks'},
                {'value': 'get_records', 'label': 'Get recorded calls'},
            ],
            group=FieldGroup.BASIC,
        ),
        field(
            'function_path',
            type='string',
            label='Function Path',
            label_key='modules.reverse.hook.params.function_path.label',
            description='Dot-path to the function on window, e.g. "window.fetch" or "window.generateToken"',
            placeholder='window.fetch',
            required=False,
            showIf={"action": {"$in": ["install"]}},
            group=FieldGroup.OPTIONS,
        ),
        field(
            'capture_args',
            type='boolean',
            label='Capture Arguments',
            label_key='modules.reverse.hook.params.capture_args.label',
            description='Record each call\'s arguments (JSON-serialized best-effort)',
            default=True,
            required=False,
            showIf={"action": {"$in": ["install"]}},
            group=FieldGroup.OPTIONS,
        ),
        field(
            'capture_result',
            type='boolean',
            label='Capture Result',
            label_key='modules.reverse.hook.params.capture_result.label',
            description='Record each call\'s return value (or resolved Promise value)',
            default=True,
            required=False,
            showIf={"action": {"$in": ["install"]}},
            group=FieldGroup.OPTIONS,
        ),
        field(
            'max_records',
            type='number',
            label='Max Records',
            label_key='modules.reverse.hook.params.max_records.label',
            description='Ring-buffer size — oldest call records are dropped past this count',
            default=500,
            min=1,
            max=10000,
            required=False,
            showIf={"action": {"$in": ["install"]}},
            group=FieldGroup.ADVANCED,
        ),
        field(
            'hook_id',
            type='string',
            label='Hook ID',
            label_key='modules.reverse.hook.params.hook_id.label',
            description='Hook ID returned by a previous "install" call',
            placeholder='hook_1a2b3c4d',
            required=False,
            showIf={"action": {"$in": ["remove", "get_records"]}},
            group=FieldGroup.OPTIONS,
        ),
        field(
            'clear',
            type='boolean',
            label='Clear After Read',
            label_key='modules.reverse.hook.params.clear.label',
            description='Clear the recorded-call buffer after reading it',
            default=False,
            required=False,
            showIf={"action": {"$in": ["get_records"]}},
            group=FieldGroup.ADVANCED,
        ),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.reverse.hook.output.status.description'},
        'hookId': {'type': 'string', 'description': 'Hook ID (install action)',
                'description_key': 'modules.reverse.hook.output.hookId.description'},
        'hooks': {'type': 'array', 'description': 'Installed hooks (list action)',
                'description_key': 'modules.reverse.hook.output.hooks.description'},
        'records': {'type': 'array', 'description': 'Recorded calls (get_records action)',
                'description_key': 'modules.reverse.hook.output.records.description'},
    },
    examples=[
        {'name': 'Hook window.fetch', 'params': {'action': 'install', 'function_path': 'window.fetch'}},
        {'name': 'Read recorded calls', 'params': {'action': 'get_records', 'hook_id': 'hook_1a2b3c4d'}},
        {'name': 'Remove a hook', 'params': {'action': 'remove', 'hook_id': 'hook_1a2b3c4d'}},
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=30000,
    required_permissions=['browser.debug'],
)
class ReverseHookModule(BaseModule):
    """Install or remove a call/return recorder on a JavaScript function."""

    module_name = "Hook Function"
    module_description = "Install or remove a call/return recorder on a JavaScript function"
    required_permission = "browser.debug"

    def validate_params(self) -> None:
        self.action = self.params.get('action')
        if self.action not in ('install', 'remove', 'list', 'get_records'):
            raise ValueError(f"Invalid action: {self.action}. Must be install, remove, list, or get_records")

        self.function_path = self.params.get('function_path')
        if self.action == 'install' and not self.function_path:
            raise ValueError("install requires function_path")

        self.capture_args = self.params.get('capture_args', True)
        self.capture_result = self.params.get('capture_result', True)
        self.max_records = self.params.get('max_records', 500)

        self.hook_id = self.params.get('hook_id')
        if self.action in ('remove', 'get_records') and not self.hook_id:
            raise ValueError(f"{self.action} requires hook_id")

        self.clear = self.params.get('clear', False)

    async def execute(self) -> Dict[str, Any]:
        session = self.context.get('reverse_session')
        if not session:
            raise RuntimeError("No active debugger session. Please run reverse.attach first")

        if self.action == 'install':
            entry = await session.install_hook(
                function_path=self.function_path,
                capture_args=self.capture_args,
                capture_result=self.capture_result,
                max_records=self.max_records,
            )
            return {'status': 'success', **entry}

        if self.action == 'remove':
            return await session.remove_hook(self.hook_id)

        if self.action == 'list':
            return {'status': 'success', 'hooks': session.list_hooks()}

        records = await session.get_hook_records(self.hook_id, clear=self.clear)
        return {'status': 'success', 'hookId': self.hook_id, 'records': records, 'count': len(records)}
