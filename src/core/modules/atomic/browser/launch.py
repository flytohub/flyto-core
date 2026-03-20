# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Launch Module - Launch a single browser instance

Single responsibility: launch ONE browser with its configuration.
For proxy rotation → browser.proxy_rotate
For multiple browsers → browser.pool
For rate limiting → browser.throttle
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field, presets
from ...schema.constants import FieldGroup, Visibility


@register_module(
    module_id='browser.launch',
    version='2.0.0',
    category='browser',
    tags=['browser', 'automation', 'setup', 'ssrf_protected'],
    label='Launch Browser',
    label_key='modules.browser.launch.label',
    description='Launch a new browser instance with Playwright',
    description_key='modules.browser.launch.description',
    icon='Monitor',
    color='#4A90E2',

    input_types=[],
    output_types=['browser', 'page'],

    can_connect_to=['browser.*', 'element.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*'],
    can_receive_from=['start', 'flow.*'],

    timeout_ms=30000,
    retryable=True,
    max_retries=2,
    concurrent_safe=False,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['browser.read', 'browser.write'],

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
            'channel',
            type='select',
            label='Browser Channel',
            description='Use system Chrome instead of bundled Chromium for better anti-detection bypass',
            default='',
            options=[
                {'value': '', 'label': 'Default (Playwright Chromium)'},
                {'value': 'chrome', 'label': 'System Chrome'},
                {'value': 'msedge', 'label': 'Microsoft Edge'},
            ],
            required=False,
            group=FieldGroup.ADVANCED,
            visibility=Visibility.EXPERT,
        ),
        field(
            'behavior',
            type='select',
            label='Behavior Profile',
            description='How the browser interacts: fast (no delays), normal, careful (mouse movement), human_like (full simulation)',
            default='fast',
            options=[
                {'value': 'fast', 'label': 'Fast (no delays)'},
                {'value': 'normal', 'label': 'Normal (small delays)'},
                {'value': 'careful', 'label': 'Careful (mouse movement, random scrolls)'},
                {'value': 'human_like', 'label': 'Human-like (full simulation)'},
            ],
            group=FieldGroup.OPTIONS,
        ),
        field(
            'stealth',
            type='boolean',
            label='Stealth Mode',
            description='Anti-detection patches: WebGL fingerprint, canvas noise, navigator fixes. Always recommended.',
            default=True,
            required=False,
            group=FieldGroup.OPTIONS,
        ),
        field(
            'proxy',
            type='string',
            label='Proxy',
            label_key='modules.browser.launch.params.proxy.label',
            description='HTTP/SOCKS proxy server URL. For rotation use browser.proxy_rotate.',
            placeholder='http://proxy:8080 or socks5://proxy:1080',
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
            'locale',
            type='string',
            label='Locale',
            label_key='modules.browser.launch.params.locale.label',
            description='Browser locale (e.g. en-US, zh-TW, ja-JP)',
            default='en-US',
            required=False,
            group=FieldGroup.ADVANCED,
            visibility=Visibility.EXPERT,
        ),
        field(
            'slow_mo',
            type='number',
            label='Slow Motion (ms)',
            label_key='modules.browser.launch.params.slow_mo.label',
            description='Delay between Playwright actions in ms (low-level, prefer Behavior Profile)',
            default=0,
            min=0,
            max=5000,
            group=FieldGroup.ADVANCED,
            visibility=Visibility.EXPERT,
        ),
        field(
            'record_video_dir',
            type='string',
            label='Record Video Directory',
            label_key='modules.browser.launch.params.record_video_dir.label',
            description='Directory to save recorded videos (enables Playwright video recording)',
            required=False,
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
        'behavior': {'type': 'string', 'description': 'Active behavior profile',
                'description_key': 'modules.browser.launch.output.behavior.description'},
    },
    examples=[
        {'name': 'Launch headless browser', 'params': {'headless': True}},
        {'name': 'Launch visible browser', 'params': {'headless': False}},
        {'name': 'Human-like with stealth', 'params': {'headless': True, 'behavior': 'human_like', 'stealth': True}},
    ],
    author='Flyto Team',
    license='MIT'
)
class BrowserLaunchModule(BaseModule):
    """Launch Browser Module — single browser, single responsibility."""

    module_name = "Launch Browser"
    module_description = "Launch a new browser instance"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        # HEADLESS env var forces headless mode (set by cloud workers)
        import os
        env_headless = os.environ.get('HEADLESS', '').lower() in ('true', '1', 'yes')
        self.headless = env_headless or self.params.get('headless', False)
        self.browser_type = self.params.get('browser_type', 'chromium')
        self.channel = self.params.get('channel', '')
        self.stealth = self.params.get('stealth', True)
        self.behavior = self.params.get('behavior', 'fast')
        self.proxy = self.params.get('proxy')
        self.user_agent = self.params.get('user_agent')
        self.locale = self.params.get('locale', 'en-US')
        self.slow_mo = self.params.get('slow_mo', 0)
        self.record_video_dir = self.params.get('record_video_dir')
        self.viewport = {
            'width': self.params.get('width', 1280),
            'height': self.params.get('height', 720),
        }

        valid_behaviors = ['fast', 'normal', 'careful', 'human_like']
        if self.behavior not in valid_behaviors:
            raise ValueError(f"behavior must be one of: {valid_behaviors}")

    async def execute(self) -> Any:
        from core.browser.driver import BrowserDriver
        from core.browser.humanize import HumanBehavior

        # Close existing browser before launching a new one
        existing = self.context.get('browser')
        if existing:
            try:
                await existing.close()
            except Exception:
                pass
            self.context.pop('browser', None)

        driver = BrowserDriver(
            headless=self.headless,
            viewport=self.viewport,
            browser_type=self.browser_type,
        )
        await driver.launch(
            proxy=self.proxy,
            user_agent=self.user_agent,
            locale=self.locale,
            slow_mo=self.slow_mo,
            record_video_dir=self.record_video_dir,
            channel=self.channel or None,
            stealth=self.stealth,
        )

        # Set behavior profile
        if self.behavior != 'fast':
            driver._human = HumanBehavior(self.behavior)

        self.context['browser'] = driver
        self.context['browser_headless'] = self.headless

        return {
            "status": "success",
            "message": "Browser launched successfully",
            "browser_type": self.browser_type,
            "headless": self.headless,
            "viewport": self.viewport,
            "behavior": self.behavior,
        }
