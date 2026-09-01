# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Hover Module - Hover mouse over an element

WHY THIS MODULE REPORTS NO OUTCOME

It was given one and the measurement had to be taken back out. The candidate was
``el.matches(':hover')`` -- the CSS hover state, which the engine computes from
its own hit-testing rather than from what Playwright asked for, and which would
have been a genuine observation of the browser rather than a restatement of the
request.

Measured on the Chromium this repository drives (headless, via
``page.hover()`` and again via a bare ``page.mouse.move()``, on a real
navigation rather than ``set_content``):

    document.querySelectorAll(':hover')  ->  []

Empty. Not "the wrong element" -- nothing at all, not even ``html``. Headless
Chromium does not enter the hover state for a synthesised pointer move here, so
the predicate reads false for every hover, including the ones that worked
perfectly.

Shipping it would have produced INDETERMINATE on every successful hover in this
product: a permanent false alarm, on a signal that says nothing about the hover.
A rung the code cannot support is worse than no rung, and this is the case the
rule is about -- so `browser.hover` keeps the engine's default `dispatched`
until there is a measurement that answers.

What would earn one: an assertion the CALLER supplies about the page after the
hover ("this menu is now visible"), evaluated here as a declared postcondition.
That is a contract someone asked for, not an inference of ours, and it is a
change to this module's parameters rather than to its reporting.
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets


@register_module(
    module_id='browser.hover',
    version='1.0.0',
    category='browser',
    tags=['browser', 'interaction', 'hover', 'mouse', 'ssrf_protected'],
    label='Hover Element',
    label_key='modules.browser.hover.label',
    description='Hover mouse over an element',
    description_key='modules.browser.hover.description',
    icon='MousePointer',
    color='#6F42C1',

    # Connection types
    input_types=['page'],
    output_types=['browser', 'page'],


    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*', 'ai.*', 'llm.*', 'agent.*'],    # Schema-driven params
    params_schema=compose(
        presets.SELECTOR(required=True, placeholder='#element-id or .element-class'),
        presets.TIMEOUT_MS(key='timeout_ms', default=30000),
        presets.POSITION(),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.browser.hover.output.status.description'},
        'selector': {'type': 'string', 'description': 'CSS selector that was used',
                'description_key': 'modules.browser.hover.output.selector.description'}
    },
    examples=[
        {
            'name': 'Hover over menu item',
            'params': {'selector': '.menu-item'}
        },
        {
            'name': 'Hover with timeout',
            'params': {'selector': '#dropdown-trigger', 'timeout_ms': 5000}
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=30000,
    required_permissions=["browser.automation"],
)
class BrowserHoverModule(BaseModule):
    """Hover Element Module"""

    module_name = "Hover Element"
    module_description = "Hover mouse over an element"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        if 'selector' not in self.params:
            raise ValueError("Missing required parameter: selector")
        self.selector = self.params['selector']
        self.timeout = self.params.get('timeout_ms', 30000)
        self.position = self.params.get('position')

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        page = browser.page

        hover_options = {'timeout': self.timeout}
        if self.position:
            hover_options['position'] = {
                'x': self.position.get('x', 0.5),
                'y': self.position.get('y', 0.5)
            }

        await page.hover(self.selector, **hover_options)

        # Post-hover: refresh hints — hover may trigger dropdown menus,
        # tooltips, or popover content that reveals new interactive elements.
        result = {"status": "success", "selector": self.selector}
        hints = await browser.get_hints(force=True)
        for key in ('inputs', 'checkboxes', 'radios', 'switches', 'buttons', 'links', 'selects', 'file_inputs'):
            if hints.get(key):
                result[key] = hints[key]
        return result
