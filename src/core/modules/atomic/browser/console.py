"""
Browser Console Module

Captures browser console logs (errors, warnings, info, etc.)
"""
from typing import Any, Dict, List
import asyncio
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets


@register_module(
    module_id='browser.console',
    version='1.0.0',
    category='browser',
    tags=['browser', 'console', 'debug', 'logs'],
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
    can_connect_to=['browser.*', 'element.*', 'page.*', 'screenshot.*', 'flow.*'],    params_schema=compose(
        presets.CONSOLE_LEVEL(),
        presets.TIMEOUT_MS(default=5000),
        presets.CONSOLE_CLEAR_EXISTING(),
    ),
    output_schema={
        'status': {'type': 'string'},
        'messages': {'type': 'array'},
        'count': {'type': 'number'}
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
    license='MIT'
)
class BrowserConsoleModule(BaseModule):
    """Capture Console Module"""

    module_name = "Capture Console"
    module_description = "Capture browser console logs"
    required_permission = "browser.interact"

    def validate_params(self):
        self.level = self.params.get('level', 'all')
        self.timeout = self.params.get('timeout', 5000)
        self.clear_existing = self.params.get('clear_existing', False)

        if self.level not in ['all', 'error', 'warning', 'info', 'log']:
            raise ValueError(f"Invalid level: {self.level}. Must be one of: all, error, warning, info, log")

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        page = browser.page
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
            "count": len(messages)
        }
