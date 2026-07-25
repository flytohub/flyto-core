# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Reverse Attach Module

Attach a CDP Debugger session to the current page for interactive
JavaScript debugging: script inspection, breakpoints, pause/resume/step.
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from ...types import StabilityLevel


@register_module(
    module_id='reverse.attach',
    version='1.0.0',
    category='reverse',
    stability=StabilityLevel.BETA,
    tags=['reverse', 'debugger', 'cdp', 'attach'],
    label='Attach Debugger',
    label_key='modules.reverse.attach.label',
    description='Attach a CDP debugger session to the current page',
    description_key='modules.reverse.attach.description',
    icon='Bug',
    color='#DC2626',

    input_types=['browser', 'page'],
    output_types=['object'],

    can_receive_from=['browser.*', 'flow.*'],
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
                'description_key': 'modules.reverse.attach.output.status.description'},
        'url': {'type': 'string', 'description': 'URL of the attached page',
                'description_key': 'modules.reverse.attach.output.url.description'},
    },
    examples=[
        {'name': 'Attach debugger to current page', 'params': {}},
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=30000,
    required_permissions=['browser.debug'],
)
class ReverseAttachModule(BaseModule):
    """Attach a CDP debugger session to the current page."""

    module_name = "Attach Debugger"
    module_description = "Attach a CDP debugger session to the current page"
    required_permission = "browser.debug"

    def validate_params(self) -> None:
        pass

    async def execute(self) -> Dict[str, Any]:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        from core.browser.reverse_session import ReverseSession

        existing = self.context.get('reverse_session')
        if existing:
            try:
                await existing.detach()
            except Exception:
                pass

        session = ReverseSession(browser)
        result = await session.enable()
        self.context['reverse_session'] = session

        return result
