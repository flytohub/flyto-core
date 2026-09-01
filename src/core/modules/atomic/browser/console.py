# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Console Module

Captures browser console logs (errors, warnings, info, etc.)

AN EMPTY CAPTURE AND A SUCCESSFUL ONE LOOKED THE SAME

``{"status": "success", "messages": [], "count": 0}`` is what this module
returns after listening to a page that logged nothing -- and it is also what it
returns after listening to the wrong page object, after the level filter
excluded every message, and after a listener that was attached to a page that
navigated out from under it. Four different facts, one payload, and a green
tick on all of them.

The rung splits them the way `database.query` splits an empty result set:

    messages arrived   OBSERVED. Each entry is a `console` event the browser
                       delivered from the page, with the text and source
                       location the renderer supplied. It cannot exist without
                       the page having logged it.
    none arrived       ACCEPTED. The listener was attached and the wait ran to
                       completion; the zero is not a measurement of the page.

The full-duration sleep is NOT a timeout and the result is not indeterminate
because of it. ``timeout`` here names the listening window this module is asked
to hold open -- reaching the end of it is the module working, not an answer
going missing.
"""
from typing import Any, Dict, List
import asyncio

from ....engine.outcome import ClaimBy, Outcome, envelope
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets


def _console_outcome(*, count: int, level: str, listened_ms: int) -> Dict[str, Any]:
    """OBSERVED for messages that arrived, ACCEPTED for a window that stayed quiet."""
    if count:
        return envelope(
            Outcome.OBSERVED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'console_messages_captured',
                'count': count,
                'level': level,
                'listened_ms': listened_ms,
                'measured_by': (
                    'len() over Playwright `console` events the browser '
                    'delivered from the page'
                ),
                'detail': (
                    'Each entry carries text and a source location the renderer '
                    'supplied. It says the page logged these; it says nothing '
                    'about anything the page did not log.'
                ),
            }],
        )
    return envelope(
        Outcome.ACCEPTED,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'no_console_messages',
            'level': level,
            'listened_ms': listened_ms,
            'measured_by': None,
            'detail': (
                'The listener was attached for the whole window and nothing '
                'arrived. A zero here reads identically whether the page logged '
                'nothing, the level filter excluded everything, or the listener '
                'was on a different page object than the one being driven -- so '
                'it is not an observation of the page.'
            ),
        }],
    )


@register_module(
    module_id='browser.console',
    version='1.0.0',
    category='browser',
    tags=['browser', 'console', 'debug', 'logs', 'ssrf_protected'],
    label='Capture Console',
    label_key='modules.browser.console.label',
    description='Capture browser console logs (errors, warnings, info)',
    description_key='modules.browser.console.description',
    icon='Terminal',
    color='#6C757D',

    # Connection types
    input_types=['page'],
    output_types=['array', 'json'],


    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*', 'ai.*', 'llm.*', 'agent.*'],    params_schema=compose(
        presets.CONSOLE_LEVEL(),
        presets.TIMEOUT_MS(default=5000),
        presets.CONSOLE_CLEAR_EXISTING(),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.browser.console.output.status.description'},
        'messages': {'type': 'array', 'description': 'The messages',
                'description_key': 'modules.browser.console.output.messages.description'},
        'count': {'type': 'number', 'description': 'Number of items',
                'description_key': 'modules.browser.console.output.count.description'},
        'outcome': {'type': 'object', 'description': (
            'How far the capture was followed: "observed" when console messages '
            'arrived from the page, "accepted" when the window stayed quiet'
        ),
                'description_key': 'modules.browser.console.output.outcome.description'}
    },
    examples=[
        {
            'name': 'Capture all console messages',
            'params': {'timeout': 3000}
        },
        {
            'name': 'Capture only errors',
            'params': {'level': 'error', 'timeout': 5000}
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=30000,
    required_permissions=["browser.automation"],
)
class BrowserConsoleModule(BaseModule):
    """Capture Console Module"""

    module_name = "Capture Console"
    module_description = "Capture browser console logs"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        self.level = self.params.get('level', 'all')
        self.timeout = self.params.get('timeout', 5000)
        self.clear_existing = self.params.get('clear_existing', False)

        if self.level not in ['all', 'error', 'warning', 'info', 'log']:
            raise ValueError(f"Invalid level: {self.level}. Must be one of: all, error, warning, info, log")

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        page = browser.real_page
        messages: List[Dict[str, Any]] = []

        def handle_console(msg):
            msg_type = msg.type
            if self.level == 'all' or msg_type == self.level:
                messages.append({
                    'level': msg_type,
                    'text': msg.text,
                    'location': {
                        'url': msg.location.get('url', ''),
                        'line': msg.location.get('lineNumber', 0),
                        'column': msg.location.get('columnNumber', 0)
                    }
                })

        page.on('console', handle_console)

        try:
            await asyncio.sleep(self.timeout / 1000)
        finally:
            page.remove_listener('console', handle_console)

        return {
            "status": "success",
            "messages": messages,
            "count": len(messages),
            "outcome": _console_outcome(
                count=len(messages), level=self.level, listened_ms=self.timeout,
            ),
        }
