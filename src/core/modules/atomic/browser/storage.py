"""
Browser Storage Module

Access localStorage and sessionStorage.
"""
from typing import Any, Dict, List, Optional
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets


@register_module(
    module_id='browser.storage',
    version='1.0.0',
    category='browser',
    tags=['browser', 'storage', 'localStorage', 'sessionStorage', 'ssrf_protected', 'path_restricted'],
    label='Browser Storage',
    label_key='modules.browser.storage.label',
    description='Access localStorage and sessionStorage',
    description_key='modules.browser.storage.description',
    icon='Database',
    color='#6610F2',

    # Connection types
    input_types=['page'],
    output_types=['string', 'json'],


    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'page.*', 'screenshot.*', 'flow.*'],    params_schema=compose(
        presets.BROWSER_ACTION(options=['get', 'set', 'remove', 'clear', 'keys', 'length']),
        presets.STORAGE_TYPE(),
        presets.STORAGE_KEY(),
        presets.STORAGE_VALUE(),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.browser.storage.output.status.description'},
        'value': {'type': 'any', 'description': 'The returned value',
                'description_key': 'modules.browser.storage.output.value.description'},
        'keys': {'type': 'array', 'description': 'List of keys',
                'description_key': 'modules.browser.storage.output.keys.description'},
        'length': {'type': 'number', 'description': 'Length of data',
                'description_key': 'modules.browser.storage.output.length.description'}
    },
    examples=[
        {
            'name': 'Get value from localStorage',
            'params': {'action': 'get', 'type': 'local', 'key': 'user_token'}
        },
        {
            'name': 'Set value in sessionStorage',
            'params': {'action': 'set', 'type': 'session', 'key': 'temp_data', 'value': '{"id": 123}'}
        },
        {
            'name': 'Clear localStorage',
            'params': {'action': 'clear', 'type': 'local'}
        },
        {
            'name': 'Get all keys',
            'params': {'action': 'keys', 'type': 'local'}
        }
    ],
    author='Flyto Team',
    license='MIT',
    timeout_ms=30000,
    required_permissions=["browser.automation"],
)
class BrowserStorageModule(BaseModule):
    """Browser Storage Module"""

    module_name = "Browser Storage"
    module_description = "Access localStorage and sessionStorage"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        if 'action' not in self.params:
            raise ValueError("Missing required parameter: action")

        self.action = self.params['action']
        if self.action not in ['get', 'set', 'remove', 'clear', 'keys', 'length']:
            raise ValueError(f"Invalid action: {self.action}")

        self.storage_type = self.params.get('type', 'local')
        if self.storage_type not in ['local', 'session']:
            raise ValueError(f"Invalid storage type: {self.storage_type}")

        self.key = self.params.get('key')
        self.value = self.params.get('value')

        if self.action in ['get', 'remove'] and not self.key:
            raise ValueError(f"{self.action} action requires key")
        if self.action == 'set' and (not self.key or self.value is None):
            raise ValueError("set action requires key and value")

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        page = browser.page
        storage_name = 'localStorage' if self.storage_type == 'local' else 'sessionStorage'

        if self.action == 'get':
            value = await page.evaluate(f'{storage_name}.getItem("{self.key}")')
            return {
                "status": "success",
                "key": self.key,
                "value": value
            }

        elif self.action == 'set':
            # Escape value for JavaScript string
            escaped_value = self.value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
            await page.evaluate(f'{storage_name}.setItem("{self.key}", "{escaped_value}")')
            return {
                "status": "success",
                "key": self.key,
                "value": self.value
            }

        elif self.action == 'remove':
            await page.evaluate(f'{storage_name}.removeItem("{self.key}")')
            return {
                "status": "success",
                "key": self.key,
                "removed": True
            }

        elif self.action == 'clear':
            await page.evaluate(f'{storage_name}.clear()')
            return {
                "status": "success",
                "cleared": True
            }

        elif self.action == 'keys':
            keys = await page.evaluate(f'''
                () => {{
                    const keys = [];
                    for (let i = 0; i < {storage_name}.length; i++) {{
                        keys.push({storage_name}.key(i));
                    }}
                    return keys;
                }}
            ''')
            return {
                "status": "success",
                "keys": keys,
                "count": len(keys)
            }

        elif self.action == 'length':
            length = await page.evaluate(f'{storage_name}.length')
            return {
                "status": "success",
                "length": length
            }
