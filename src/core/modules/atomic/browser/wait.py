# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Wait Module - Wait for a duration or until an element appears
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field, presets
from ...schema.constants import FieldGroup


@register_module(
    module_id='browser.wait',
    version='1.1.0',
    category='browser',
    tags=['browser', 'wait', 'delay', 'selector', 'ssrf_protected'],
    label='Wait',
    label_key='modules.browser.wait.label',
    description='Wait for a duration or until an element appears',
    description_key='modules.browser.wait.description',
    icon='Clock',
    color='#95A5A6',

    # Connection types
    input_types=['page'],
    output_types=['browser', 'page'],

    # Connection rules
    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*'],

    # Execution settings
    timeout_ms=30000,
    retryable=True,
    max_retries=2,
    concurrent_safe=True,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['browser.read'],

    # Schema-driven params
    params_schema=compose(
        presets.DURATION_MS(key='duration_ms', default=1000, label='Wait Duration (ms)'),
        presets.SELECTOR(required=False, placeholder='.element-to-wait-for'),
        field(
            'state',
            type='select',
            label='Wait State',
            label_key='modules.browser.wait.params.state.label',
            description='Element state to wait for',
            default='visible',
            options=[
                {'value': 'visible', 'label': 'Visible (element is visible)'},
                {'value': 'hidden', 'label': 'Hidden (element is hidden)'},
                {'value': 'attached', 'label': 'Attached (element exists in DOM)'},
                {'value': 'detached', 'label': 'Detached (element removed from DOM)'},
            ],
            group=FieldGroup.OPTIONS,
            showIf={"selector": {"$ne": ""}},
        ),
        presets.TIMEOUT_MS(key='timeout_ms', default=30000),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.browser.wait.output.status.description'},
        'selector': {'type': 'string', 'optional': True, 'description': 'CSS selector that was waited for',
                'description_key': 'modules.browser.wait.output.selector.description'},
        'duration_ms': {'type': 'number', 'optional': True, 'description': 'Wait duration in milliseconds',
                'description_key': 'modules.browser.wait.output.duration_ms.description'}
    },
    examples=[
        {
            'name': 'Wait 2 seconds',
            'params': {'duration_ms': 2000}
        },
        {
            'name': 'Wait for element',
            'params': {'selector': '#loading-complete', 'timeout_ms': 5000}
        }
    ],
    author='Flyto Team',
    license='MIT'
)
class BrowserWaitModule(BaseModule):
    """Wait Module"""

    module_name = "Wait"
    module_description = "Wait for a duration or element to appear"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
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
        self.state = self.params.get('state', 'visible')
        self.timeout = self.params.get('timeout_ms', 30000)

    async def execute(self) -> Any:
        import asyncio

        browser = self.context.get('browser')

        if self.selector:
            # Wait for element to reach specified state
            if not browser:
                raise RuntimeError("Browser not launched. Please run browser.launch first")
            await browser.wait(self.selector, state=self.state, timeout_ms=self.timeout)
            result = {"status": "success", "selector": self.selector, "state": self.state}
        else:
            # Wait for specified duration
            await asyncio.sleep(self.duration_ms / 1000)
            result = {"status": "success", "duration_ms": self.duration_ms}

        # Post-wait: capture element hints for Element Picker UI.
        # This is critical — wait nodes often follow navigation (click "下一步"),
        # so they're the first node to see the NEW page's elements.
        if browser:
            browser._snapshot_since_nav = True
            hints = await browser.get_hints(force=True)
            for key in ('inputs', 'checkboxes', 'radios', 'switches', 'buttons', 'links', 'selects'):
                if hints.get(key):
                    result[key] = hints[key]

        return result


