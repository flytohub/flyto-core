# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Navigation Module - Go back, forward, or reload the page
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets, field


@register_module(
    module_id='browser.navigation',
    version='1.0.0',
    category='browser',
    tags=['browser', 'navigation', 'back', 'forward', 'reload', 'ssrf_protected'],
    label='Page Navigation',
    label_key='modules.browser.navigation.label',
    description='Navigate back, forward, or reload the page',
    description_key='modules.browser.navigation.description',
    icon='ArrowLeftRight',
    color='#5CB85C',

    # Connection types
    input_types=['page'],
    output_types=['browser', 'page'],

    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*'],

    # Schema-driven params
    params_schema=compose(
        field('action', type='select',
              label='Navigation Action',
              label_key='modules.browser.navigation.param.action.label',
              description='Which navigation action to perform',
              description_key='modules.browser.navigation.param.action.description',
              required=True,
              default='reload',
              options=[
                  {"value": "back", "label": "Go Back",
                   "label_key": "modules.browser.navigation.param.action.option.back"},
                  {"value": "forward", "label": "Go Forward",
                   "label_key": "modules.browser.navigation.param.action.option.forward"},
                  {"value": "reload", "label": "Reload Page",
                   "label_key": "modules.browser.navigation.param.action.option.reload"},
              ]),
        presets.WAIT_CONDITION(default='domcontentloaded'),
        presets.TIMEOUT_MS(key='timeout_ms', default=30000),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.browser.navigation.output.status.description'},
        'action': {'type': 'string', 'description': 'Navigation action performed',
                'description_key': 'modules.browser.navigation.output.action.description'},
        'url': {'type': 'string', 'description': 'Current URL after navigation',
                'description_key': 'modules.browser.navigation.output.url.description'},
    },
    examples=[
        {
            'name': 'Go back to previous page',
            'params': {'action': 'back'}
        },
        {
            'name': 'Go forward',
            'params': {'action': 'forward'}
        },
        {
            'name': 'Reload current page',
            'params': {'action': 'reload', 'wait_until': 'networkidle'}
        }
    ],
    author='Flyto Team',
    license='MIT',
    timeout_ms=30000,
    required_permissions=["browser.automation"],
)
class BrowserNavigationModule(BaseModule):
    """Page Navigation Module"""

    module_name = "Page Navigation"
    module_description = "Navigate back, forward, or reload the page"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        if 'action' not in self.params:
            raise ValueError("Missing required parameter: action")

        self.action = self.params['action']
        if self.action not in ['back', 'forward', 'reload']:
            raise ValueError(f"Invalid action: {self.action}. Must be 'back', 'forward', or 'reload'")

        self.wait_until = self.params.get('wait_until', 'domcontentloaded')
        self.timeout_ms = self.params.get('timeout_ms', 30000)

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        page = browser.page

        if self.action == 'back':
            await page.go_back(wait_until=self.wait_until, timeout=self.timeout_ms)
        elif self.action == 'forward':
            await page.go_forward(wait_until=self.wait_until, timeout=self.timeout_ms)
        elif self.action == 'reload':
            await page.reload(wait_until=self.wait_until, timeout=self.timeout_ms)

        current_url = page.url
        return {
            "status": "success",
            "action": self.action,
            "url": current_url,
        }
