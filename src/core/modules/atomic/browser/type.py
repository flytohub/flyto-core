# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Type Module - Type text into an input field
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets, field
from ...schema.constants import FieldGroup


@register_module(
    module_id='browser.type',
    version='1.1.0',
    category='browser',
    tags=['browser', 'interaction', 'input', 'keyboard', 'ssrf_protected'],
    label='Type Text',
    label_key='modules.browser.type.label',
    description='Type text into an input field. Run browser.snapshot first to find the correct selector from the real page DOM.',
    description_key='modules.browser.type.description',
    icon='Keyboard',
    color='#5BC0DE',

    # Connection types
    input_types=['page'],
    output_types=['browser', 'page'],

    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*'],
    params_schema=compose(
        field("type_method", type="select",
              label="How to find the input field",
              label_key="modules.browser.type.param.type_method.label",
              description="Choose the easiest way to identify the input field",
              description_key="modules.browser.type.param.type_method.description",
              default="placeholder",
              options=[
                  {"value": "placeholder", "label": "By placeholder text",
                   "label_key": "modules.browser.type.param.type_method.option.placeholder"},
                  {"value": "label", "label": "By label text",
                   "label_key": "modules.browser.type.param.type_method.option.label"},
                  {"value": "name", "label": "By input name",
                   "label_key": "modules.browser.type.param.type_method.option.name"},
                  {"value": "id", "label": "By element ID",
                   "label_key": "modules.browser.type.param.type_method.option.id"},
                  {"value": "selector", "label": "CSS / XPath selector (advanced)",
                   "label_key": "modules.browser.type.param.type_method.option.selector"},
              ],
              group=FieldGroup.BASIC),
        field("target", type="string",
              label="Input field identifier",
              label_key="modules.browser.type.param.target.label",
              description='e.g. "Enter your email", "Email", "username"',
              description_key="modules.browser.type.param.target.description",
              placeholder="Enter your email",
              showIf={"type_method": {"$in": ["placeholder", "label", "name", "id"]}},
              group=FieldGroup.BASIC),
        field("selector", type="string",
              label="CSS/XPath Selector",
              label_key="schema.field.selector",
              description="CSS selector, XPath, or text selector",
              placeholder='input[name="email"], #username',
              showIf={"type_method": "selector"},
              ui={"widget": "selector"},
              group=FieldGroup.BASIC),
        presets.TEXT(key='text', required=True, label='Text to type', placeholder='Text to type'),
        field('delay', type='number', label='Typing Delay (ms)',
              label_key='modules.browser.type.param.delay.label',
              description='Delay between keystrokes in milliseconds',
              description_key='modules.browser.type.param.delay.description',
              default=0, min=0,
              group=FieldGroup.OPTIONS),
        field('clear', type='boolean', label='Clear Field First',
              label_key='modules.browser.type.param.clear.label',
              description='Clear the input field before typing',
              description_key='modules.browser.type.param.clear.description',
              default=False,
              group=FieldGroup.OPTIONS),
        presets.TIMEOUT_MS(default=30000),
    ),
    output_schema={
        'browser': {'type': 'object', 'description': 'Browser session (pass-through for chaining)',
                'description_key': 'modules.browser.type.output.browser.description'},
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.browser.type.output.status.description'},
        'selector': {'type': 'string', 'description': 'CSS selector that was used',
                'description_key': 'modules.browser.type.output.selector.description'},
        'method': {'type': 'string', 'description': 'Type method used'}
    },
    examples=[
        {
            'name': 'Type by placeholder',
            'params': {'type_method': 'placeholder', 'target': 'Enter your email', 'text': 'user@example.com'}
        },
        {
            'name': 'Type by label',
            'params': {'type_method': 'label', 'target': 'Email', 'text': 'user@example.com'}
        },
        {
            'name': 'Type with selector',
            'params': {'type_method': 'selector', 'selector': '#email', 'text': 'user@example.com'}
        },
    ],
    author='Flyto Team',
    license='MIT',
    timeout_ms=30000,
    required_permissions=["browser.automation"],
)
class BrowserTypeModule(BaseModule):
    """Type Text Module"""

    module_name = "Type Text"
    module_description = "Type text into an input field"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        method = self.params.get('type_method', 'placeholder')
        target = self.params.get('target', '').strip()
        raw_selector = self.params.get('selector', '').strip()

        # Backward compatibility: selector provided without type_method → selector mode
        if 'type_method' not in self.params and raw_selector:
            method = 'selector'

        if method == 'selector':
            if not raw_selector:
                raise ValueError("CSS/XPath selector is required in advanced mode")
            self.selector = raw_selector
        elif method == 'id':
            if not target:
                raise ValueError("Element ID is required")
            self.selector = f'#{target.lstrip("#")}'
        elif method == 'name':
            if not target:
                raise ValueError("Input name is required")
            self.selector = f'input[name="{target}"]'
        elif method == 'label':
            if not target:
                raise ValueError("Label text is required")
            self.selector = f'label:has-text("{target}") >> input, input[aria-label="{target}"]'
        else:  # placeholder (default)
            if not target:
                raise ValueError("Placeholder text is required")
            self.selector = f'input[placeholder="{target}"], textarea[placeholder="{target}"]'

        if 'text' not in self.params:
            raise ValueError("Missing required parameter: text")

        self.method = method
        self.text = self.params['text']
        self.delay = int(self.params.get('delay') or 0)
        self.clear = bool(self.params.get('clear'))

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        # Auto-snapshot if the AI skipped it — selectors should come from
        # real DOM, not from guessing.  The snapshot text is returned so the
        # LLM can see page structure for subsequent calls.
        if not getattr(browser, '_snapshot_since_nav', True):
            try:
                page = browser.page
                body = await page.evaluate('document.body ? document.body.innerText.substring(0, 2000) : ""')
                browser._snapshot_since_nav = True
                self._auto_snapshot_text = body
            except Exception:
                self._auto_snapshot_text = None
        else:
            self._auto_snapshot_text = None

        # Wait for element to be visible before interacting
        await browser.wait(self.selector, state='visible', timeout_ms=10000)

        # Clear field first if requested
        if self.clear:
            await browser.page.fill(self.selector, '')

        await browser.type(self.selector, self.text, delay_ms=self.delay)

        # Mask sensitive text in return value
        is_sensitive = any(kw in self.selector.lower() for kw in ['password', 'passwd', 'secret', 'token', 'key', 'credential'])
        result = {
            "status": "success",
            "selector": self.selector,
            "method": self.method,
            "text": '***' if is_sensitive else self.text,
            "text_length": len(self.text),
        }
        if self._auto_snapshot_text:
            result["_page_hint"] = self._auto_snapshot_text[:800]
        return result
