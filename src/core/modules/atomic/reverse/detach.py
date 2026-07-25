# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Reverse Detach Module

Detach the CDP debugger session from the current page, removing all
listeners and breakpoints installed by reverse.attach / reverse.breakpoint.
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from ...types import StabilityLevel


@register_module(
    module_id='reverse.detach',
    version='1.0.0',
    category='reverse',
    stability=StabilityLevel.BETA,
    tags=['reverse', 'debugger', 'cdp', 'detach', 'cleanup'],
    label='Detach Debugger',
    label_key='modules.reverse.detach.label',
    description='Detach the CDP debugger session from the current page',
    description_key='modules.reverse.detach.description',
    icon='BugOff',
    color='#DC2626',

    input_types=['object'],
    output_types=[],

    can_receive_from=['reverse.*', 'flow.*'],
    can_connect_to=['*'],

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
                'description_key': 'modules.reverse.detach.output.status.description'},
    },
    examples=[
        {'name': 'Detach debugger', 'params': {}},
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=15000,
    required_permissions=['browser.debug'],
)
class ReverseDetachModule(BaseModule):
    """Detach the CDP debugger session from the current page."""

    module_name = "Detach Debugger"
    module_description = "Detach the CDP debugger session from the current page"
    required_permission = "browser.debug"

    def validate_params(self) -> None:
        pass

    async def execute(self) -> Dict[str, Any]:
        session = self.context.get('reverse_session')
        if not session:
            return {"status": "success", "note": "No active debugger session"}

        result = await session.detach()
        self.context.pop('reverse_session', None)
        return result
