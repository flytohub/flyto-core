"""
Browser Evaluate Module

Execute JavaScript in page context.
"""
from typing import Any, Dict, List, Optional
from ...base import BaseModule
from ...registry import register_module


@register_module(
    module_id='core.browser.evaluate',
    version='1.0.0',
    category='browser',
    tags=['browser', 'javascript', 'execute', 'script'],
    label='Execute JavaScript',
    label_key='modules.browser.evaluate.label',
    description='Execute JavaScript code in page context',
    description_key='modules.browser.evaluate.description',
    icon='Code',
    color='#FFC107',

    # Connection types
    input_types=['page'],
    output_types=['any'],

    params_schema={
        'script': {
            'type': 'string',
            'label': 'JavaScript Code',
            'label_key': 'modules.browser.evaluate.params.script.label',
            'placeholder': 'return document.title',
            'description': 'JavaScript code to execute (can use return statement)',
            'description_key': 'modules.browser.evaluate.params.script.description',
            'required': True,
            'multiline': True
        },
        'args': {
            'type': 'array',
            'label': 'Arguments',
            'label_key': 'modules.browser.evaluate.params.args.label',
            'description': 'Arguments to pass to the script function',
            'description_key': 'modules.browser.evaluate.params.args.description',
            'required': False
        }
    },
    output_schema={
        'status': {'type': 'string'},
        'result': {'type': 'any'}
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
    license='MIT'
)
class BrowserEvaluateModule(BaseModule):
    """Execute JavaScript Module"""

    module_name = "Execute JavaScript"
    module_description = "Execute JavaScript in page context"
    required_permission = "browser.interact"

    def validate_params(self):
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
