"""
Browser Evaluate Module

Execute JavaScript in page context.
"""
from typing import Any, Dict, List, Optional
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets


@register_module(
    module_id='browser.evaluate',
    version='1.0.0',
    category='browser',
    tags=['browser', 'javascript', 'execute', 'script', 'ssrf_protected'],
    label='Execute JavaScript',
    label_key='modules.browser.evaluate.label',
    description='Execute JavaScript code in page context',
    description_key='modules.browser.evaluate.description',
    icon='Code',
    color='#FFC107',

    # Connection types
    input_types=['page'],
    output_types=['any'],


    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'page.*', 'screenshot.*', 'flow.*'],    params_schema=compose(
        presets.JS_SCRIPT(),
        presets.JS_ARGS(),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.browser.evaluate.output.status.description'},
        'result': {'type': 'any', 'description': 'The operation result',
                'description_key': 'modules.browser.evaluate.output.result.description'}
    },
    examples=[
        {
            'name': 'Get page title',
            'params': {'script': 'return document.title'}
        },
        {
            'name': 'Get element count',
            'params': {'script': 'return document.querySelectorAll("a").length'}
        },
        {
            'name': 'Execute with arguments',
            'params': {
                'script': '(selector) => document.querySelector(selector)?.textContent',
                'args': ['#header']
            }
        },
        {
            'name': 'Modify page',
            'params': {'script': 'document.body.style.backgroundColor = "red"; return "done"'}
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=30000,
    required_permissions=["browser.automation"],
)
class BrowserEvaluateModule(BaseModule):
    """Execute JavaScript Module"""

    module_name = "Execute JavaScript"
    module_description = "Execute JavaScript in page context"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        if 'script' not in self.params:
            raise ValueError("Missing required parameter: script")
        self.script = self.params['script']
        self.args = self.params.get('args', [])

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        page = browser.page

        # Wrap script if it doesn't look like a function
        script = self.script.strip()
        if not script.startswith('(') and not script.startswith('function'):
            # Wrap in arrow function
            script = f'() => {{ {script} }}'

        if self.args:
            result = await page.evaluate(script, *self.args)
        else:
            result = await page.evaluate(script)

        return {
            "status": "success",
            "result": result
        }
