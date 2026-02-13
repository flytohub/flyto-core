"""
Browser Click Module - Click an element on the page
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field
from ...schema.constants import FieldGroup
from ...schema import presets


@register_module(
    module_id='browser.click',
    version='1.1.0',
    category='browser',
    tags=['browser', 'interaction', 'click', 'ssrf_protected'],
    label='Click Element',
    label_key='modules.browser.click.label',
    description='Click an element on the page',
    description_key='modules.browser.click.description',
    icon='MousePointerClick',
    color='#F0AD4E',

    # Connection types
    input_types=['page'],
    output_types=['page'],

    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'page.*', 'screenshot.*', 'flow.*'],
    params_schema=compose(
        field("click_method", type="select",
              label="How to find the element",
              label_key="modules.browser.click.param.click_method.label",
              description="Choose the easiest way to identify the element you want to click",
              description_key="modules.browser.click.param.click_method.description",
              default="text",
              options=[
                  {"value": "text", "label": "By text on the page",
                   "label_key": "modules.browser.click.param.click_method.option.text"},
                  {"value": "button", "label": "By button / link text",
                   "label_key": "modules.browser.click.param.click_method.option.button"},
                  {"value": "id", "label": "By element ID",
                   "label_key": "modules.browser.click.param.click_method.option.id"},
                  {"value": "selector", "label": "CSS / XPath selector (advanced)",
                   "label_key": "modules.browser.click.param.click_method.option.selector"},
              ],
              group=FieldGroup.BASIC),
        field("target", type="string",
              label="What to click",
              label_key="modules.browser.click.param.target.label",
              description='e.g. "Submit", "Next Page", "Login"',
              description_key="modules.browser.click.param.target.description",
              placeholder="Submit",
              required=True,
              showIf={"click_method": {"$in": ["text", "button", "id"]}},
              group=FieldGroup.BASIC),
        field("selector", type="string",
              label="CSS/XPath Selector",
              label_key="schema.field.selector",
              description="CSS selector, XPath, or text selector",
              placeholder='#submit-btn, .btn-primary, //button[@type="submit"]',
              required=True,
              showIf={"click_method": "selector"},
              group=FieldGroup.BASIC),
        presets.TIMEOUT_MS(default=30000),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.browser.click.output.status.description'},
        'selector': {'type': 'string', 'description': 'Selector that was used',
                'description_key': 'modules.browser.click.output.selector.description'},
        'method': {'type': 'string', 'description': 'Click method used'}
    },
    examples=[
        {
            'name': 'Click by button text',
            'params': {'click_method': 'text', 'target': 'Submit'}
        },
        {
            'name': 'Click by element ID',
            'params': {'click_method': 'id', 'target': 'login-button'}
        },
        {
            'name': 'Click with CSS selector',
            'params': {'click_method': 'selector', 'selector': '#submit-button'}
        }
    ],
    author='Flyto Team',
    license='MIT',
    timeout_ms=30000,
    required_permissions=["browser.automation"],
)
class BrowserClickModule(BaseModule):
    """Click Element Module"""

    module_name = "Click Element"
    module_description = "Click an element on the page"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        method = self.params.get('click_method', 'text')
        target = self.params.get('target', '').strip()
        raw_selector = self.params.get('selector', '').strip()

        # Backward compatibility: selector provided without click_method → selector mode
        if 'click_method' not in self.params and raw_selector and not target:
            method = 'selector'

        if method == 'selector':
            if not raw_selector:
                raise ValueError("CSS/XPath selector is required in advanced mode")
            self.selector = raw_selector
        elif method == 'id':
            if not target:
                raise ValueError("Element ID is required")
            self.selector = f'#{target.lstrip("#")}'
        elif method == 'button':
            if not target:
                raise ValueError("Button or link text is required")
            self.selector = f'text={target}'
        else:  # text (default)
            if not target:
                raise ValueError("Text content is required")
            self.selector = f'text={target}'

        self.method = method

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        await browser.click(self.selector)
        return {"status": "success", "selector": self.selector, "method": self.method}


