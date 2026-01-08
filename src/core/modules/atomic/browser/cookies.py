"""
Browser Cookies Module

Get, set, or clear browser cookies.
"""
from typing import Any, Dict, List, Optional
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets


@register_module(
    module_id='browser.cookies',
    version='1.0.0',
    category='browser',
    tags=['browser', 'cookies', 'session', 'storage', 'ssrf_protected', 'path_restricted'],
    label='Manage Cookies',
    label_key='modules.browser.cookies.label',
    description='Get, set, or clear browser cookies',
    description_key='modules.browser.cookies.description',
    icon='Cookie',
    color='#D4A373',

    # Connection types
    input_types=['browser'],
    output_types=['array', 'json'],


    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'page.*', 'screenshot.*', 'flow.*'],    params_schema=compose(
        presets.BROWSER_ACTION(options=['get', 'set', 'clear', 'delete']),
        presets.COOKIE_NAME(),
        presets.COOKIE_VALUE(),
        presets.COOKIE_DOMAIN(),
        presets.COOKIE_PATH(),
        presets.COOKIE_SECURE(),
        presets.COOKIE_HTTP_ONLY(),
        presets.COOKIE_EXPIRES(),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.browser.cookies.output.status.description'},
        'cookies': {'type': 'array', 'description': 'Browser cookies',
                'description_key': 'modules.browser.cookies.output.cookies.description'},
        'count': {'type': 'number', 'description': 'Number of items',
                'description_key': 'modules.browser.cookies.output.count.description'}
    },
    examples=[
        {
            'name': 'Get all cookies',
            'params': {'action': 'get'}
        },
        {
            'name': 'Get specific cookie',
            'params': {'action': 'get', 'name': 'session_id'}
        },
        {
            'name': 'Set a cookie',
            'params': {
                'action': 'set',
                'name': 'user_pref',
                'value': 'dark_mode',
                'domain': 'example.com'
            }
        },
        {
            'name': 'Clear all cookies',
            'params': {'action': 'clear'}
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=30000,
    required_permissions=["browser.automation"],
)
class BrowserCookiesModule(BaseModule):
    """Manage Cookies Module"""

    module_name = "Manage Cookies"
    module_description = "Get, set, or clear browser cookies"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        if 'action' not in self.params:
            raise ValueError("Missing required parameter: action")

        self.action = self.params['action']
        if self.action not in ['get', 'set', 'clear', 'delete']:
            raise ValueError(f"Invalid action: {self.action}")

        self.name = self.params.get('name')
        self.value = self.params.get('value')
        self.domain = self.params.get('domain')
        self.path = self.params.get('path', '/')
        self.secure = self.params.get('secure', False)
        self.http_only = self.params.get('httpOnly', False)
        self.expires = self.params.get('expires')

        if self.action == 'set':
            if not self.name or not self.value:
                raise ValueError("set action requires name and value")
            if not self.domain:
                raise ValueError("set action requires domain")

        if self.action == 'delete' and not self.name:
            raise ValueError("delete action requires name")

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        context = browser._context

        if self.action == 'get':
            cookies = await context.cookies()
            if self.name:
                cookies = [c for c in cookies if c.get('name') == self.name]
            return {
                "status": "success",
                "cookies": cookies,
                "count": len(cookies)
            }

        elif self.action == 'set':
            cookie = {
                'name': self.name,
                'value': self.value,
                'domain': self.domain,
                'path': self.path,
                'secure': self.secure,
                'httpOnly': self.http_only
            }
            if self.expires:
                cookie['expires'] = self.expires

            await context.add_cookies([cookie])
            return {
                "status": "success",
                "cookies": [cookie],
                "count": 1
            }

        elif self.action == 'clear':
            await context.clear_cookies()
            return {
                "status": "success",
                "cookies": [],
                "count": 0
            }

        elif self.action == 'delete':
            # Get all cookies, filter out the one to delete, then clear and re-add
            all_cookies = await context.cookies()
            remaining = [c for c in all_cookies if c.get('name') != self.name]
            await context.clear_cookies()
            if remaining:
                await context.add_cookies(remaining)
            return {
                "status": "success",
                "deleted": self.name,
                "count": len(all_cookies) - len(remaining)
            }
