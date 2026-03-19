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
              ui={"widget": "element_picker", "element_types": ["input"],
                  "value_key_from": "type_method",
                  "value_key_map": {
                      "placeholder": "placeholder",
                      "label": "label",
                      "name": "name",
                      "id": "id",
                  }},
              group=FieldGroup.BASIC),
        field("selector", type="string",
              label="CSS/XPath Selector",
              label_key="schema.field.selector",
              description="CSS selector, XPath, or text selector",
              placeholder='input[name="email"], #username',
              showIf={"type_method": {"$in": ["selector"]}},
              ui={"widget": "element_picker", "element_types": ["input"], "value_key": "selector"},
              group=FieldGroup.BASIC),
        field("input_type", type="select",
              label="Input type",
              label_key="modules.browser.type.param.input_type.label",
              description="Type of input field — use Password to mask the value in the builder",
              description_key="modules.browser.type.param.input_type.description",
              default="text",
              options=[
                  {"value": "text", "label": "Text",
                   "label_key": "modules.browser.type.param.input_type.option.text"},
                  {"value": "password", "label": "Password",
                   "label_key": "modules.browser.type.param.input_type.option.password"},
                  {"value": "email", "label": "Email",
                   "label_key": "modules.browser.type.param.input_type.option.email"},
              ],
              group=FieldGroup.BASIC),
        field("text", type="string",
              label="Text to type",
              label_key="modules.browser.type.param.text.label",
              placeholder="Text to type",
              required=True,
              showIf={"input_type": {"$in": ["text", "email"]}},
              group=FieldGroup.BASIC),
        field("sensitive_text", type="string",
              label="Text to type",
              label_key="modules.browser.type.param.text.label",
              placeholder="••••••••",
              required=True,
              format="password",
              secret=True,
              showIf={"input_type": {"$in": ["password"]}},
              group=FieldGroup.BASIC),
        field('delay', type='number', label='Typing Delay (ms)',
              label_key='modules.browser.type.param.delay.label',
              description='Delay between keystrokes in milliseconds',
              description_key='modules.browser.type.param.delay.description',
              default=0, min=0, max=5000, step=10,
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
            'name': 'Type password',
            'params': {'type_method': 'placeholder', 'target': 'Password', 'input_type': 'password', 'sensitive_text': '${env.LOGIN_PASSWORD}'}
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
        raw_selector = self.params.get('selector', '').strip()

        # Backward compatibility: selector provided without type_method → selector mode
        if 'type_method' not in self.params and raw_selector:
            method = 'selector'

        target = self.params.get('target', '').strip()

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

        self.input_type = self.params.get('input_type', 'text')
        # Merge text from the visible field (text or sensitive_text based on input_type)
        text = self.params.get('text') or self.params.get('sensitive_text') or ''
        if not text:
            raise ValueError("Missing required parameter: text")

        self.method = method
        self.text = text
        self.delay = int(self.params.get('delay') or 0)
        self.clear = bool(self.params.get('clear'))

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        # Pre-action: refresh element hints to ensure we have current page state
        await browser.get_hints()

        # Wait for element to be visible before interacting
        await browser.wait(self.selector, state='visible', timeout_ms=10000)

        # Clear field first if requested
        if self.clear:
            await browser.page.fill(self.selector, '')

        await browser.type(self.selector, self.text, delay_ms=self.delay)

        # Mask sensitive text in return value
        is_sensitive = self.input_type == 'password' or any(
            kw in self.selector.lower()
            for kw in ['password', 'passwd', 'secret', 'token', 'key', 'credential']
        )
        result = {
            "status": "success",
            "selector": self.selector,
            "method": self.method,
            "input_type": self.input_type,
            "text": '***' if is_sensitive else self.text,
            "text_length": len(self.text),
        }
        # Post-action: refresh hints (typing may trigger dynamic UI changes)
        hints = await browser.get_hints(force=True)
        browser._snapshot_since_nav = True
        if hints.get('text'):
            result["_page_hint"] = hints["text"][:800]
        for key in ('inputs', 'checkboxes', 'radios', 'switches', 'buttons', 'links', 'selects'):
            if hints.get(key):
                result[key] = hints[key]
        return result
