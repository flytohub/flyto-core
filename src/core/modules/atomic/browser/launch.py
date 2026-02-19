# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

"""
Browser Launch Module - Launch a new browser instance with Playwright
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field, presets
from ...schema.constants import FieldGroup, Visibility


@register_module(
    module_id='browser.launch',
    version='1.0.0',
    category='browser',
    tags=['browser', 'automation', 'setup', 'ssrf_protected'],
    label='Launch Browser',
    label_key='modules.browser.launch.label',
    description='Launch a new browser instance with Playwright',
    description_key='modules.browser.launch.description',
    icon='Monitor',
    color='#4A90E2',

    # Connection types
    input_types=[],
    output_types=['browser', 'page'],  # Browser launch also creates a default page

    # Connection rules
    can_connect_to=['browser.*', 'element.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*'],  # Can connect to browser and flow modules
    can_receive_from=['start', 'flow.*'],

    # Execution settings
    timeout_ms=10000,
    retryable=True,
    max_retries=2,
    concurrent_safe=False,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['browser.read', 'browser.write'],

    # Schema-driven params
    params_schema=compose(
        presets.BROWSER_HEADLESS(default=False),
        presets.VIEWPORT(),
        field(
            'browser_type',
            type='select',
            label='Browser Type',
            label_key='modules.browser.launch.params.browser_type.label',
            description='Browser engine to use',
            default='chromium',
            options=[
                {'value': 'chromium', 'label': 'Chromium'},
                {'value': 'firefox', 'label': 'Firefox'},
                {'value': 'webkit', 'label': 'WebKit (Safari)'},
            ],
            group=FieldGroup.OPTIONS,
        ),
        field(
            'proxy',
            type='string',
            label='Proxy',
            label_key='modules.browser.launch.params.proxy.label',
            description='HTTP/SOCKS proxy server URL',
            placeholder='http://proxy:8080',
            required=False,
            group=FieldGroup.ADVANCED,
            visibility=Visibility.EXPERT,
        ),
        field(
            'user_agent',
            type='string',
            label='User Agent',
            label_key='modules.browser.launch.params.user_agent.label',
            description='Custom user agent string',
            required=False,
            group=FieldGroup.ADVANCED,
            visibility=Visibility.EXPERT,
        ),
        field(
            'slow_mo',
            type='integer',
            label='Slow Motion (ms)',
            label_key='modules.browser.launch.params.slow_mo.label',
            description='Delay between actions in ms',
            default=0,
            min=0,
            max=5000,
            group=FieldGroup.ADVANCED,
            visibility=Visibility.EXPERT,
        ),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.browser.launch.output.status.description'},
        'message': {'type': 'string', 'description': 'Result message describing the outcome',
                'description_key': 'modules.browser.launch.output.message.description'},
        'browser_type': {'type': 'string', 'description': 'Browser engine used',
                'description_key': 'modules.browser.launch.output.browser_type.description'},
        'headless': {'type': 'boolean', 'description': 'Whether browser is in headless mode',
                'description_key': 'modules.browser.launch.output.headless.description'},
        'viewport': {'type': 'object', 'description': 'Browser viewport dimensions',
                'description_key': 'modules.browser.launch.output.viewport.description'},
    },
    examples=[
        {
            'name': 'Launch headless browser',
            'params': {'headless': True}
        },
        {
            'name': 'Launch visible browser',
            'params': {'headless': False}
        }
    ],
    author='Flyto Team',
    license='MIT'
)
class BrowserLaunchModule(BaseModule):
    """Launch Browser Module"""

    module_name = "Launch Browser"
    module_description = "Launch a new browser instance"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        self.headless = self.params.get('headless', False)
        self.browser_type = self.params.get('browser_type', 'chromium')
        self.proxy = self.params.get('proxy')
        self.user_agent = self.params.get('user_agent')
        self.slow_mo = self.params.get('slow_mo', 0)
        self.viewport = {
            'width': self.params.get('width', 1280),
            'height': self.params.get('height', 720),
        }

    async def execute(self) -> Any:
        from core.browser.driver import BrowserDriver

        driver = BrowserDriver(
            headless=self.headless,
            viewport=self.viewport,
            browser_type=self.browser_type,
        )
        await driver.launch(
            proxy=self.proxy,
            user_agent=self.user_agent,
            slow_mo=self.slow_mo,
        )

        # Store in context for later use
        self.context['browser'] = driver
        self.context['browser_headless'] = self.headless

        return {
            "status": "success",
            "message": "Browser launched successfully",
            "browser_type": self.browser_type,
            "headless": self.headless,
            "viewport": self.viewport,
        }


