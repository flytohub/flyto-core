# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Reverse Resume Module

Resume execution of a page paused at a breakpoint.
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from ...types import StabilityLevel


@register_module(
    module_id='reverse.resume',
    version='1.0.0',
    category='reverse',
    stability=StabilityLevel.BETA,
    tags=['reverse', 'debugger', 'cdp', 'resume'],
    label='Resume Execution',
    label_key='modules.reverse.resume.label',
    description='Resume execution of a page paused at a breakpoint',
    description_key='modules.reverse.resume.description',
    icon='Play',
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
                'description_key': 'modules.reverse.resume.output.status.description'},
    },
    examples=[
        {'name': 'Resume execution', 'params': {}},
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=15000,
    required_permissions=['browser.debug'],
)
class ReverseResumeModule(BaseModule):
    """Resume execution of a page paused at a breakpoint."""

    module_name = "Resume Execution"
    module_description = "Resume execution of a page paused at a breakpoint"
    required_permission = "browser.debug"

    def validate_params(self) -> None:
        pass

    async def execute(self) -> Dict[str, Any]:
        session = self.context.get('reverse_session')
        if not session:
            raise RuntimeError("No active debugger session. Please run reverse.attach first")

        return await session.resume()
