"""
Browser Wait Module - Wait for a duration or until an element appears
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets


@register_module(
    module_id='browser.wait',
    version='1.1.0',
    category='browser',
    tags=['browser', 'wait', 'delay', 'selector'],
    label='Wait',
    label_key='modules.browser.wait.label',
    description='Wait for a duration or until an element appears',
    description_key='modules.browser.wait.description',
    icon='Clock',
    color='#95A5A6',

    # Connection types
    input_types=['page'],
    output_types=['page'],

    # Connection rules
    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'page.*', 'screenshot.*', 'flow.*'],

    # Schema-driven params
    params_schema=compose(
        presets.DURATION_MS(key='duration_ms', default=1000, label='Wait Duration (ms)'),
        presets.SELECTOR(required=False, placeholder='.element-to-wait-for'),
        presets.TIMEOUT_MS(default=30000),
    ),
    output_schema={
        'status': {'type': 'string'},
        'selector': {'type': 'string', 'optional': True},
        'duration_ms': {'type': 'number', 'optional': True}
    },
    examples=[
        {
            'name': 'Wait 2 seconds',
            'params': {'duration_ms': 2000}
        },
        {
            'name': 'Wait for element',
            'params': {'selector': '#loading-complete', 'timeout': 5000}
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class BrowserWaitModule(BaseModule):
    """Wait Module"""

    module_name = "Wait"
    module_description = "Wait for a duration or element to appear"
    required_permission = "browser.interact"

    def validate_params(self):
        # Primary: duration_ms (explicit milliseconds)
        # Fallback: duration (for backwards compatibility - auto-detect unit)
        if 'duration_ms' in self.params:
            self.duration_ms = self.params['duration_ms']
        elif 'duration' in self.params:
            # Backwards compatibility: if duration > 100, assume ms; else assume seconds
            raw = self.params['duration']
            self.duration_ms = raw if raw > 100 else raw * 1000
        else:
            self.duration_ms = 1000  # Default 1 second

        self.selector = self.params.get('selector')
        self.timeout = self.params.get('timeout', 30000)

    async def execute(self) -> Any:
        import asyncio

        browser = self.context.get('browser')

        if self.selector:
            # Wait for element to appear
            if not browser:
                raise RuntimeError("Browser not launched. Please run browser.launch first")
            await browser.wait(self.selector, timeout_ms=self.timeout)
            return {"status": "success", "selector": self.selector}
        else:
            # Wait for specified duration
            await asyncio.sleep(self.duration_ms / 1000)
            return {"status": "success", "duration_ms": self.duration_ms}


