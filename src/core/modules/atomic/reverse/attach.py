# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Reverse Attach Module

Attach a CDP Debugger session to the current page for interactive
JavaScript debugging: script inspection, breakpoints, pause/resume/step.

If a session is already attached to the same page, reuses it (keeping its
script cache, breakpoints, request breakpoints, and hooks) instead of
detaching and re-enabling the Debugger domain from scratch — pass
`force_new` to opt out and always get a fresh session.
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field
from ...types import StabilityLevel


@register_module(
    module_id='reverse.attach',
    version='1.1.0',
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

    params_schema=compose(
        field(
            'force_new',
            type='boolean',
            label='Force New Session',
            label_key='modules.reverse.attach.params.force_new.label',
            description=(
                'Detach and recreate the debugger session even if one is already '
                'attached to this page. Default reuses the existing session, '
                'keeping its script cache, breakpoints, request breakpoints, and hooks.'
            ),
            description_key='modules.reverse.attach.params.force_new.description',
            default=False,
            required=False,
        ),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.reverse.attach.output.status.description'},
        'url': {'type': 'string', 'description': 'URL of the attached page',
                'description_key': 'modules.reverse.attach.output.url.description'},
        'reused': {'type': 'boolean', 'description': 'True if an existing session on the same page was reused',
                'description_key': 'modules.reverse.attach.output.reused.description'},
        'scriptCount': {'type': 'number', 'description': 'Loaded script count (present when reused)',
                'description_key': 'modules.reverse.attach.output.scriptCount.description'},
        'breakpointCount': {'type': 'number', 'description': 'Active script breakpoint count (present when reused)',
                'description_key': 'modules.reverse.attach.output.breakpointCount.description'},
        'requestBreakpointCount': {'type': 'number', 'description': 'Active request breakpoint count (present when reused)',
                'description_key': 'modules.reverse.attach.output.requestBreakpointCount.description'},
        'hookCount': {'type': 'number', 'description': 'Installed function hook count (present when reused)',
                'description_key': 'modules.reverse.attach.output.hookCount.description'},
        'isPaused': {'type': 'boolean', 'description': 'Whether the reused session is currently paused',
                'description_key': 'modules.reverse.attach.output.isPaused.description'},
        'networkEnabled': {'type': 'boolean', 'description': 'Whether Network domain tracing is active on the reused session',
                'description_key': 'modules.reverse.attach.output.networkEnabled.description'},
    },
    examples=[
        {'name': 'Attach debugger to current page', 'params': {}},
        {'name': 'Force a fresh session', 'params': {'force_new': True}},
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
        self.force_new = bool(self.params.get('force_new', False))

    async def execute(self) -> Dict[str, Any]:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        from core.browser.reverse_session import ReverseSession

        existing = self.context.get('reverse_session')
        if existing is not None:
            same_page = (
                not self.force_new
                and existing.is_enabled
                and browser.real_page is not None
                and existing.page is browser.real_page
            )
            if same_page:
                return {'status': 'success', 'reused': True, **existing.snapshot()}

            try:
                await existing.detach()
            except Exception:
                pass

        session = ReverseSession(browser)
        result = await session.enable()
        self.context['reverse_session'] = session

        return {**result, 'reused': False}
