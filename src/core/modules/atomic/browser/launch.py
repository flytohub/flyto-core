# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Launch Module - Launch a single browser instance

Single responsibility: launch ONE browser with its configuration.
For proxy rotation → browser.proxy_rotate
For multiple browsers → browser.pool
For rate limiting → browser.throttle

WHAT "BROWSER LAUNCHED SUCCESSFULLY" WAS MADE OF

Every field this module returned came back out of its own parameters:
``browser_type`` is the string the caller selected, ``headless`` is the boolean
it was handed (or the env var), ``viewport`` is the dict it built in
``validate_params``, ``behavior`` is the profile name it validated, and the
message is a literal. A step that started nothing and a step that started
Chromium produce byte-identical output as long as ``driver.launch()`` returns.

The value that is not that is ``Browser.version``: a string the launched process
sent us through the DevTools handshake. See ``_session_outcome`` for why that
one is evidence and ``Browser.is_connected()`` is not.

    the process reported its version   OBSERVED
    no Browser object to ask           ACCEPTED

There is one thing this module knows and still throws away, and it is worth
naming because the version string is what makes it visible.
``BrowserDriver._launch_chromium`` RETURNS the channel it actually started —
``"chromium"``, ``"chrome"`` or ``"msedge"``, falling through
``(None, "chrome", "msedge")`` when the caller pinned none — and
``BrowserDriver.launch`` discards it, testing the value only for ``is False``.
So a workflow that asked for the bundled build and got system Chrome is told
``browser_type: 'chromium'`` by this module and ``browser_type: 'chromium'`` by
the driver. Nothing here can fix that without changing the driver, which this
pass does not touch; what it can do is report the version the process gave,
which is the one field that differs between those two binaries.
"""
from typing import Any

from ....engine.outcome import envelope
from ....utils import enforce_outbound_service_url, validate_path_with_env_config
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field, presets
from ...schema.constants import FieldGroup, Visibility
from ._session_outcome import read_engine, started_claim


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

    can_connect_to=['browser.*', 'element.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*', 'ai.*', 'llm.*', 'agent.*'],
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
        'engine_version': {'type': 'string', 'description': 'Version string the launched browser process reported, or null when it could not be read',
                'description_key': 'modules.browser.launch.output.engine_version.description'},
        'outcome': {
            'type': 'object',
            'description': (
                'How far this launch was followed: observed when the browser '
                'process reported its own version, accepted when there was no '
                'Browser object to ask'
            ),
            'description_key': 'modules.browser.launch.output.outcome.description'},
    },
    examples=[
        {'name': 'Launch headless browser', 'params': {'headless': True}},
        {'name': 'Launch visible browser', 'params': {'headless': False}},
        {'name': 'Human-like with stealth', 'params': {'headless': True, 'behavior': 'human_like', 'stealth': True}},
    ],
    author='Flyto2 Team',
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
        # SECURITY: every request the browser makes is routed through this
        # proxy, so a caller-supplied internal address turns the browser into a
        # relay into the private network — and the egress guard, which inspects
        # the request URL, does not see where the proxy itself points.
        raw_proxy = self.params.get('proxy')
        self.proxy = (
            enforce_outbound_service_url(raw_proxy, purpose='browser proxy')
            if raw_proxy else raw_proxy
        )
        self.user_agent = self.params.get('user_agent')
        self.locale = self.params.get('locale', 'en-US')
        self.slow_mo = self.params.get('slow_mo', 0)
        # SECURITY: confine recorded video to FLYTO_SANDBOX_DIR. The driver
        # mkdir()s this directory and Playwright drops .webm files into it —
        # an unvalidated caller-controlled path is an arbitrary directory
        # create/write outside the sandbox the file.* modules enforce.
        raw_video_dir = self.params.get('record_video_dir')
        self.record_video_dir = (
            validate_path_with_env_config(raw_video_dir) if raw_video_dir else None
        )
        self.viewport = {
            'width': self.params.get('width', 1280),
            'height': self.params.get('height', 720),
        }

        valid_behaviors = ['fast', 'normal', 'careful', 'human_like']
        if self.behavior not in valid_behaviors:
            raise ValueError(f"behavior must be one of: {valid_behaviors}")

    async def execute(self) -> Any:
        from core.browser.driver import BrowserDriver, browser_profile_scope_from_context
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
            profile_scope=browser_profile_scope_from_context(self.context),
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

        # Read out of the process this step started, not out of its parameters.
        engine, version, reason = read_engine(driver)
        rung, claim_by, reading = started_claim(
            engine=engine,
            version=version,
            requested_engine=self.browser_type,
            reason=reason,
        )

        return {
            "status": "success",
            "message": "Browser launched successfully",
            "browser_type": self.browser_type,
            "headless": self.headless,
            "viewport": self.viewport,
            "behavior": self.behavior,
            "engine_version": version,
            "outcome": envelope(rung, claim_by=claim_by, effects=[reading]),
        }
