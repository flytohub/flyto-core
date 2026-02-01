"""
Browser Ensure Module - Smart browser session management

Ensures a browser session exists, either by:
1. Reusing an existing browser from parent context (when called from template.invoke)
2. Launching a new browser if none exists (when run independently)

This enables templates to be both:
- Independently executable (will launch their own browser)
- Composable (will reuse parent's browser when invoked as sub-template)

Design Philosophy:
    browser.ensure = "I need a browser, but I don't care who started it"
    browser.release = "I'm done with the browser, close it if I own it"
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets


@register_module(
    module_id='browser.ensure',
    version='1.0.0',
    category='browser',
    tags=['browser', 'automation', 'setup', 'session', 'composable', 'ssrf_protected'],
    label='Ensure Browser',
    label_key='modules.browser.ensure.label',
    description='Ensure a browser session exists (reuse or launch)',
    description_key='modules.browser.ensure.description',
    icon='MonitorCheck',
    color='#10B981',  # Green - indicates "ready" state

    # Connection types
    input_types=[],
    output_types=['browser', 'page'],

    # Connection rules - same as browser.launch
    can_connect_to=['browser.*', 'element.*', 'page.*', 'flow.*'],
    can_receive_from=['start', 'flow.*', 'browser.*'],  # Can also follow other browser ops

    # Execution settings
    timeout_ms=15000,
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
    ),
    output_schema={
        'status': {
            'type': 'string',
            'enum': ['launched', 'reused'],
            'description': 'Whether browser was launched or reused',
            'description_key': 'modules.browser.ensure.output.status.description'
        },
        'message': {
            'type': 'string',
            'description': 'Result message',
            'description_key': 'modules.browser.ensure.output.message.description'
        },
        'is_owner': {
            'type': 'boolean',
            'description': 'Whether this step owns the browser (responsible for closing)',
            'description_key': 'modules.browser.ensure.output.is_owner.description'
        }
    },
    examples=[
        {
            'name': 'Ensure browser (auto-detect)',
            'description': 'Reuse existing browser or launch new one',
            'params': {'headless': False}
        },
        {
            'name': 'Ensure headless browser',
            'description': 'For background automation',
            'params': {'headless': True}
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class BrowserEnsureModule(BaseModule):
    """
    Ensure Browser Module

    Smart browser session management that enables template composability.

    Behavior:
    - If browser exists in context: reuse it, mark is_owner=False
    - If no browser: launch new one, mark is_owner=True

    This allows templates to:
    1. Run independently (will launch browser)
    2. Be called by other templates (will reuse parent's browser)
    """

    module_name = "Ensure Browser"
    module_description = "Ensure a browser session exists"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        self.headless = self.params.get('headless', False)
        self.viewport = self.params.get('viewport', {'width': 1280, 'height': 800})

    async def execute(self) -> Dict[str, Any]:
        # Check if browser already exists in context
        existing_browser = self.context.get('browser')

        if existing_browser:
            # Browser exists - reuse it
            # Don't change browser_owner - whoever created it owns it
            return {
                "ok": True,
                "status": "reused",
                "message": "Reusing existing browser session",
                "is_owner": False,
                "data": {
                    "status": "reused",
                    "is_owner": False
                }
            }

        # No browser - launch a new one
        from core.browser.driver import BrowserDriver

        driver = BrowserDriver(
            headless=self.headless,
            viewport=self.viewport
        )
        await driver.launch()

        # Store in context
        self.context['browser'] = driver

        # Mark this step as the owner (responsible for cleanup)
        # Use step_id if available, otherwise generate an owner marker
        step_id = self.params.get('$step_id', 'browser_ensure')
        self.context['browser_owner'] = step_id
        self.context['browser_owned_by_ensure'] = True  # Flag for release module

        return {
            "ok": True,
            "status": "launched",
            "message": "Browser launched successfully",
            "is_owner": True,
            "data": {
                "status": "launched",
                "is_owner": True,
                "headless": self.headless
            }
        }
