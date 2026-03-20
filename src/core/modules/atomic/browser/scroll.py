# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Scroll Module

Scroll page to element, position, or direction.
"""
from typing import Any, Dict, Optional
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets


@register_module(
    module_id='browser.scroll',
    version='1.0.0',
    category='browser',
    tags=['browser', 'scroll', 'navigation', 'ssrf_protected'],
    label='Scroll Page',
    label_key='modules.browser.scroll.label',
    description='Scroll page to element, position, or direction. Run browser.snapshot first to find the correct selector from the real page DOM.',
    description_key='modules.browser.scroll.description',
    icon='ArrowDownUp',
    color='#17A2B8',

    # Connection types
    input_types=['page'],
    output_types=['browser', 'page'],


    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*'],    params_schema=compose(
        presets.SELECTOR(required=False, placeholder='#element-id'),
        presets.SCROLL_DIRECTION(),
        presets.SCROLL_AMOUNT(),
        presets.SCROLL_BEHAVIOR(),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.browser.scroll.output.status.description'},
        'scrolled_to': {'type': 'object', 'description': 'The scrolled to',
                'description_key': 'modules.browser.scroll.output.scrolled_to.description'}
    },
    examples=[
        {
            'name': 'Scroll to element',
            'params': {'selector': '#footer'}
        },
        {
            'name': 'Scroll down 500 pixels',
            'params': {'direction': 'down', 'amount': 500}
        },
        {
            'name': 'Smooth scroll to top',
            'params': {'direction': 'up', 'amount': 10000, 'behavior': 'smooth'}
        }
    ],
    author='Flyto Team',
    license='MIT',
    timeout_ms=30000,
    required_permissions=["browser.automation"],
)
class BrowserScrollModule(BaseModule):
    """Scroll Page Module"""

    module_name = "Scroll Page"
    module_description = "Scroll page to element or position"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        self.selector = self.params.get('selector')
        self.direction = self.params.get('direction', 'down')
        self.amount = self.params.get('amount', 500)
        self.behavior = self.params.get('behavior', 'smooth')

        if self.direction not in ['up', 'down', 'left', 'right']:
            raise ValueError(f"Invalid direction: {self.direction}")
        if self.behavior not in ['smooth', 'instant']:
            raise ValueError(f"Invalid behavior: {self.behavior}")

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        page = browser.page

        if self.selector:
            # Scroll to element
            await page.locator(self.selector).scroll_into_view_if_needed()
            # Get element position
            position = await page.evaluate('''
                (selector) => {
                    const el = document.querySelector(selector);
                    if (el) {
                        const rect = el.getBoundingClientRect();
                        return { x: rect.left + window.scrollX, y: rect.top + window.scrollY };
                    }
                    return { x: 0, y: 0 };
                }
            ''', self.selector)
            result = {
                "status": "success",
                "scrolled_to": position,
                "selector": self.selector
            }
        else:
            # Scroll by direction and amount
            scroll_x = 0
            scroll_y = 0

            if self.direction == 'down':
                scroll_y = self.amount
            elif self.direction == 'up':
                scroll_y = -self.amount
            elif self.direction == 'right':
                scroll_x = self.amount
            elif self.direction == 'left':
                scroll_x = -self.amount

            behavior = 'smooth' if self.behavior == 'smooth' else 'auto'

            await page.evaluate('''
                ([scrollX, scrollY, behavior]) => {
                    window.scrollBy({
                        left: scrollX,
                        top: scrollY,
                        behavior: behavior
                    });
                }
            ''', [scroll_x, scroll_y, behavior])

            # Get current scroll position
            position = await page.evaluate('''
                () => ({ x: window.scrollX, y: window.scrollY })
            ''')

            result = {
                "status": "success",
                "scrolled_to": position,
                "direction": self.direction,
                "amount": self.amount
            }

        # Post-scroll: refresh hints — scrolling may reveal new elements
        # (infinite scroll, lazy-loaded content, viewport-dependent visibility)
        hints = await browser.get_hints(force=True)
        for key in ('inputs', 'checkboxes', 'radios', 'switches', 'buttons', 'links', 'selects'):
            if hints.get(key):
                result[key] = hints[key]
        return result
