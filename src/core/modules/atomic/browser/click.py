# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

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
    description='Click an element on the page. Run browser.snapshot first to find the correct selector from the real page DOM.',
    description_key='modules.browser.click.description',
    icon='MousePointerClick',
    color='#F0AD4E',

    # Connection types
    input_types=['page'],
    output_types=['browser', 'page'],

    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*'],
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
              showIf={"click_method": {"$in": ["text", "button", "id"]}},
              ui={"widget": "element_picker", "element_types": ["button", "link"],
                  "value_key_from": "click_method",
                  "value_key_map": {
                      "text": "text",
                      "button": "text",
                      "id": "id",
                  }},
              group=FieldGroup.BASIC),
        field("selector", type="string",
              label="CSS/XPath Selector",
              label_key="schema.field.selector",
              description="CSS selector, XPath, or text selector",
              placeholder='#submit-btn, .btn-primary, //button[@type="submit"]',
              showIf={"click_method": {"$in": ["selector"]}},
              ui={"widget": "element_picker", "element_types": ["button", "link"], "value_key": "selector"},
              group=FieldGroup.BASIC),
        field("button", type="select",
              label="Mouse Button",
              label_key="modules.browser.click.param.button.label",
              description="Which mouse button to use for clicking",
              default="left",
              options=[
                  {"value": "left", "label": "Left"},
                  {"value": "right", "label": "Right"},
                  {"value": "middle", "label": "Middle"},
              ],
              group=FieldGroup.OPTIONS),
        field("click_count", type="number",
              label="Click Count",
              label_key="modules.browser.click.param.click_count.label",
              description="Number of clicks (2 for double-click, 3 for triple-click)",
              default=1,
              min=1,
              max=3,
              group=FieldGroup.OPTIONS),
        field("force", type="boolean",
              label="Force Click",
              label_key="modules.browser.click.param.force.label",
              description="Force click even if element is not actionable (covered, invisible)",
              default=False,
              group=FieldGroup.ADVANCED),
        field("modifiers", type="array",
              label="Keyboard Modifiers",
              label_key="modules.browser.click.param.modifiers.label",
              description="Modifier keys to hold during click",
              required=False,
              group=FieldGroup.ADVANCED),
        presets.TIMEOUT_MS(default=30000),
    ),
    output_schema={
        'browser': {'type': 'object', 'description': 'Browser session (pass-through for chaining)',
                'description_key': 'modules.browser.click.output.browser.description'},
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
            self.selector = f':is(button, a, [role="button"]):has-text("{target}")'
        else:  # text (default)
            if not target:
                raise ValueError("Text content is required")
            self.selector = f'text={target}'

        self.method = method
        self.button = self.params.get('button', 'left')
        self.click_count = self.params.get('click_count', 1)
        self.force = self.params.get('force', False)
        self.modifiers = self.params.get('modifiers', [])

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        # Pre-action: refresh element hints to ensure we have current page state
        await browser.get_hints()

        # Wait for element to be visible before clicking (unless force mode)
        if not self.force:
            await browser.wait(self.selector, state='visible', timeout_ms=10000)

        page = browser.page

        click_options = {
            'button': self.button,
            'click_count': self.click_count,
            'force': self.force,
        }
        if self.modifiers:
            click_options['modifiers'] = self.modifiers

        await page.click(self.selector, **click_options)

        # Post-click: capture interactive elements of the NEW page state.
        # This ensures the next step's Element Picker sees the correct elements
        # (especially after click-induced navigation).
        result = {"status": "success", "selector": self.selector, "method": self.method}

        # Wait for page to settle after click.
        # Strategy: try domcontentloaded first (real navigation),
        # then wait for URL change or DOM mutation (SPA navigation).
        pre_url = page.url
        try:
            await page.wait_for_load_state('domcontentloaded', timeout=2000)
        except Exception:
            pass
        # If URL didn't change, this might be an SPA — wait for DOM to stabilize
        if page.url == pre_url:
            try:
                # Wait for any new interactive element to appear (SPA rendered new content)
                await page.wait_for_function(
                    '''() => {
                        const els = document.querySelectorAll(
                            'select, [role="combobox"], [role="listbox"], input:not([type=hidden]), button'
                        );
                        return els.length > 0;
                    }''',
                    timeout=3000,
                )
            except Exception:
                pass
            # Extra brief wait for SPA animations to finish
            await page.wait_for_timeout(500)

        # Post-click: refresh hints on the (potentially new) page
        await browser.invalidate_hints()
        hints = await browser.get_hints()
        browser._snapshot_since_nav = True
        if hints.get('text'):
            result["_page_hint"] = hints["text"][:800]
        for key in ('buttons', 'inputs', 'links', 'selects'):
            if hints.get(key):
                result[key] = hints[key]
        return result


