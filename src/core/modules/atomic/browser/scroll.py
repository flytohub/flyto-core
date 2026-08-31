# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Scroll Module

Scroll page to element, position, or direction.

`scrolled_to` IS NOT EVIDENCE OF A SCROLL — IN EITHER BRANCH

The selector branch returns ``rect.left + window.scrollX, rect.top +
window.scrollY``. Add the viewport-relative position of an element to the
scroll offset and you get the element's position in the DOCUMENT, which is a
property of the layout and is the same number before and after any scroll. It
answers "where is this element on the page", not "did the page move".

The direction branch returns ``window.scrollX/scrollY`` after the call, with
nothing to compare it against. On a page already at its limit — and, more
often, on ``behavior: 'smooth'``, which is the DEFAULT here and returns
immediately while the browser animates — that reading is the position the page
was already at. It is the same number the module would have produced with the
``scrollBy`` deleted.

What separates them is a baseline. The scroll offset is read once before the
scroll and once after, and only the DIFFERENCE is evidence:

    offsets read, and they differ        the page moved      -> OBSERVED
    offsets read, and they are equal     nothing we can see  -> ACCEPTED
    offsets unreadable                   nothing followed    -> ACCEPTED

Equal offsets are ACCEPTED and deliberately not FAILED or INDETERMINATE-with-
alarm: scrolling down at the bottom of a document is a correct no-op, and a
smooth scroll that has not finished animating is a correct scroll measured too
early. The number cannot tell those from a scroll that did nothing, so it claims
only that the browser took the call — and the effect says which of the two
reasons applies, because the smooth case is knowable from the parameters.
"""
from typing import Any, Dict, Optional

from ....engine.outcome import ClaimBy, Outcome, envelope
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets


_READ_SCROLL_OFFSET = '() => ({ x: window.scrollX, y: window.scrollY })'


async def _read_scroll_offset(page) -> Optional[Dict[str, Any]]:
    """The document's scroll offset, or None when the page cannot be asked."""
    try:
        return await page.evaluate(_READ_SCROLL_OFFSET)
    except Exception:  # noqa: BLE001 - any failure means "cannot look"
        return None


def _scroll_outcome(
    *,
    before: Optional[Dict[str, Any]],
    after: Optional[Dict[str, Any]],
    smooth: bool,
    target: str,
) -> Dict[str, Any]:
    """The rung this scroll earned, from the offset before and the offset after."""
    if before is None or after is None:
        return envelope(
            Outcome.ACCEPTED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'scroll_offset_not_observed',
                'target': target,
                'measured_by': None,
                'detail': (
                    'The scroll call returned without raising. window.scrollX/Y '
                    'could not be read on both sides of it, so no change was '
                    'measured.'
                ),
            }],
        )

    moved_x = after.get('x', 0) - before.get('x', 0)
    moved_y = after.get('y', 0) - before.get('y', 0)

    if moved_x == 0 and moved_y == 0:
        return envelope(
            Outcome.ACCEPTED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'scroll_offset_unchanged',
                'target': target,
                'offset': after,
                'measured_by': 'window.scrollX/scrollY, read before and after the scroll',
                'detail': (
                    'The scroll animation had not moved the page when it was '
                    'measured: behavior="smooth" returns immediately and the '
                    'browser scrolls afterwards.'
                    if smooth else
                    'The page is where it was. That reads the same whether it '
                    'was already at the requested position, could not scroll '
                    'further, or did not scroll at all.'
                ),
            }],
        )

    return envelope(
        Outcome.OBSERVED,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'scroll_offset_changed',
            'target': target,
            'offset_before': before,
            'offset_after': after,
            'moved': {'x': moved_x, 'y': moved_y},
            'measured_by': 'window.scrollX/scrollY, read before and after the scroll',
            'detail': (
                'The document scroll offset changed. That the page moved is '
                'observed; that it moved to the right place is not claimed.'
            ),
        }],
    )


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
    can_connect_to=['browser.*', 'element.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*', 'ai.*', 'llm.*', 'agent.*'],    params_schema=compose(
        presets.SELECTOR(required=False, placeholder='#element-id'),
        presets.SCROLL_DIRECTION(),
        presets.SCROLL_AMOUNT(),
        presets.SCROLL_BEHAVIOR(),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.browser.scroll.output.status.description'},
        'scrolled_to': {'type': 'object', 'description': (
                    'For the direction form, the scroll offset after the call. '
                    'For the selector form, the target element\'s position in '
                    'the document -- a layout property that does not change when '
                    'the page scrolls'
                ),
                'description_key': 'modules.browser.scroll.output.scrolled_to.description'},
        'scroll_offset': {
            'type': 'object',
            'description': (
                'The document scroll offset before and after the scroll, and the '
                'difference between them. null when it could not be read'
            ),
            'description_key': 'modules.browser.scroll.output.scroll_offset.description'},
        'outcome': {
            'type': 'object',
            'description': (
                'How far this scroll was followed: observed when the document '
                'scroll offset changed, accepted when it did not or could not be '
                'read'
            ),
            'description_key': 'modules.browser.scroll.output.outcome.description'}
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
    author='Flyto2 Team',
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

        # The baseline. Without it, every position this module reports is a
        # number that would read the same with the scroll deleted.
        offset_before = await _read_scroll_offset(page)

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

        offset_after = await _read_scroll_offset(page)
        result["scroll_offset"] = (
            None if offset_before is None or offset_after is None
            else {
                "before": offset_before,
                "after": offset_after,
                "moved": {
                    "x": offset_after.get('x', 0) - offset_before.get('x', 0),
                    "y": offset_after.get('y', 0) - offset_before.get('y', 0),
                },
            }
        )
        result["outcome"] = _scroll_outcome(
            before=offset_before,
            after=offset_after,
            # `behavior` only reaches the browser on the direction branch;
            # scroll_into_view_if_needed() is synchronous and instant, so
            # blaming an animation there would be a wrong explanation.
            smooth=not self.selector and self.behavior == 'smooth',
            target=self.selector if self.selector else self.direction,
        )

        # Post-scroll: refresh hints — scrolling may reveal new elements
        # (infinite scroll, lazy-loaded content, viewport-dependent visibility)
        hints = await browser.get_hints(force=True)
        for key in ('inputs', 'checkboxes', 'radios', 'switches', 'buttons', 'links', 'selects', 'file_inputs'):
            if hints.get(key):
                result[key] = hints[key]
        return result
