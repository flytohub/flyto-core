# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Viewport Module - Resize browser viewport

Simple, focused module for viewport resizing.
Uses Playwright's page.set_viewport_size().

Works across all browsers (Chromium, Firefox, WebKit).

THE `viewport` KEY IS THE REQUEST, NOT THE RESULT

``"viewport": {"width": int(self.width), "height": int(self.height)}`` is the
caller's two parameters, cast. It is what was asked for. It is the same object
whether the browser resized, clamped the request, or ignored it.

``page.viewport_size`` is barely better: Playwright answers it from the size it
recorded for the context, so after ``set_viewport_size`` it reports the value we
just handed it. It confirms our own bookkeeping, not the browser's layout.

The reading that is neither is ``window.innerWidth`` / ``window.innerHeight``,
evaluated in the page: the layout viewport as the document itself sees it, taken
once before the resize and once after.

    measured, and the page now reports the requested size    -> OBSERVED
    measured, and it changed, to some other size             -> OBSERVED
    measured, and it neither changed nor matches             -> INDETERMINATE
    the page could not be asked                              -> ACCEPTED

The first case is OBSERVED even when the size did not change, and the ordering
of the branches is the whole argument. A resize is a state-setting operation:
asking for the size a page is already at is a correct no-op, and "the document
reports the requested size" is a measurement of the world whether or not this
call is what put it there. The second case stays on the ladder because that is
what OBSERVED means — we saw the world change, not that the right thing changed;
a device scale factor or a clamp to the window lands a correct resize a few
pixels off the request, and calling that a failure would put a red mark on it.

Only the third case has no evidence in it at all: the page is not where it was
asked to go and did not move. INDETERMINATE rather than FAILED, because no
postcondition was declared, the equality is this module's own inference, and a
mobile-emulated context that refuses the resize is not the same thing as a
broken one.
"""
from typing import Any, Dict, Optional

from ....engine.outcome import ClaimBy, Outcome, envelope
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field


_READ_INNER_SIZE = '() => ({ width: window.innerWidth, height: window.innerHeight })'


async def _read_inner_size(page) -> Optional[Dict[str, Any]]:
    """The layout viewport as the document reports it, or None when unreadable."""
    try:
        return await page.evaluate(_READ_INNER_SIZE)
    except Exception:  # noqa: BLE001 - any failure means "cannot look"
        return None


def _viewport_outcome(
    *,
    requested: Dict[str, int],
    before: Optional[Dict[str, Any]],
    after: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """The rung this resize earned, from what the page reports about itself."""
    requested_effect = {
        'kind': 'viewport_requested',
        'width': requested['width'],
        'height': requested['height'],
        'measured_by': 'the width and height parameters',
        'detail': (
            'What was asked for. No browser call contributes to it; it reads '
            'identically whether the resize was applied, clamped, or ignored.'
        ),
    }

    if before is None or after is None:
        return envelope(
            Outcome.ACCEPTED,
            claim_by=ClaimBy.NONE,
            effects=[
                requested_effect,
                {
                    'kind': 'inner_size_not_observed',
                    'measured_by': None,
                    'detail': (
                        'set_viewport_size() returned without raising. '
                        'window.innerWidth/innerHeight could not be read on both '
                        'sides of it, so nothing followed the resize into the '
                        'page.'
                    ),
                },
            ],
        )

    matches = (
        after.get('width') == requested['width']
        and after.get('height') == requested['height']
    )
    observed_effect = {
        'kind': 'inner_size_observed',
        'before': before,
        'after': after,
        'matches_requested': matches,
        'changed': after != before,
        'measured_by': (
            'window.innerWidth/innerHeight evaluated in the page, before and '
            'after the resize'
        ),
    }

    # Matching first, and deliberately before the changed/unchanged split: a
    # resize is state-setting, so a page already at the requested size is in the
    # requested state and the no-op that left it there is correct.
    if matches:
        return envelope(
            Outcome.OBSERVED,
            claim_by=ClaimBy.INFERRED,
            effects=[requested_effect, observed_effect],
        )

    if after != before:
        return envelope(
            Outcome.OBSERVED,
            claim_by=ClaimBy.INFERRED,
            effects=[
                requested_effect,
                observed_effect,
                {
                    'kind': 'inner_size_differs',
                    'predicate': 'innerWidth/innerHeight == the requested width/height',
                    'detail': (
                        'The viewport changed but the document does not report '
                        'the requested size. A device scale factor, a scrollbar, '
                        'or a clamp to the window all do this to a correct '
                        'resize. The change is observed; that the right thing '
                        'changed is not claimed.'
                    ),
                },
            ],
        )

    return envelope(
        Outcome.INDETERMINATE,
        claim_by=ClaimBy.INFERRED,
        effects=[
            requested_effect,
            observed_effect,
            {
                'kind': 'inner_size_unchanged',
                'predicate': 'innerWidth/innerHeight == the requested width/height',
                'detail': (
                    'The page reports the size it reported before, and it is not '
                    'the size that was asked for. Nothing here can tell a resize '
                    'the context refused from one that has not taken effect yet.'
                ),
            },
        ],
    )


@register_module(
    module_id='browser.viewport',
    version='1.0.0',
    category='browser',
    tags=['browser', 'viewport', 'resize', 'responsive'],
    label='Resize Viewport',
    label_key='modules.browser.viewport.label',
    description='Resize browser viewport to specific dimensions',
    description_key='modules.browser.viewport.description',
    icon='Maximize2',
    color='#6366F1',

    # Connection types
    input_types=['page'],
    output_types=['browser', 'page'],

    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*', 'ai.*', 'llm.*', 'agent.*'],

    params_schema=compose(
        field(
            'width',
            type='number',
            label='Width',
            label_key='modules.browser.viewport.params.width.label',
            description='Viewport width in pixels',
            required=True,
            min=320,
            max=3840,
            default=1280,
        ),
        field(
            'height',
            type='number',
            label='Height',
            label_key='modules.browser.viewport.params.height.label',
            description='Viewport height in pixels',
            required=True,
            min=240,
            max=2160,
            default=720,
        ),
    ),
    output_schema={
        'status': {
            'type': 'string',
            'description': 'Operation status',
            'description_key': 'modules.browser.viewport.output.status.description'
        },
        'viewport': {
            'type': 'object',
            'description': 'Applied viewport dimensions',
            'description_key': 'modules.browser.viewport.output.viewport.description'
        },
        'previous_viewport': {
            'type': 'object',
            'description': 'Previous viewport dimensions',
            'description_key': 'modules.browser.viewport.output.previous_viewport.description'
        },
        'inner_size': {
            'type': 'object',
            'description': (
                'window.innerWidth/innerHeight as the document reports them, '
                'before and after the resize. null when the page could not be '
                'asked'
            ),
            'description_key': 'modules.browser.viewport.output.inner_size.description'
        },
        'outcome': {
            'type': 'object',
            'description': (
                'How far this resize was followed: observed when the document '
                'reports the requested size or a changed one, indeterminate when '
                'it reports neither, accepted when it could not be asked'
            ),
            'description_key': 'modules.browser.viewport.output.outcome.description'
        },
    },
    examples=[
        {
            'name': 'Mobile viewport',
            'params': {'width': 375, 'height': 667}
        },
        {
            'name': 'Tablet viewport',
            'params': {'width': 768, 'height': 1024}
        },
        {
            'name': 'Desktop viewport',
            'params': {'width': 1920, 'height': 1080}
        },
        {
            'name': 'Laptop viewport',
            'params': {'width': 1366, 'height': 768}
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=10000,
    required_permissions=['browser.automation'],
)
class BrowserViewportModule(BaseModule):
    """Resize Viewport Module"""

    module_name = "Resize Viewport"
    module_description = "Resize browser viewport"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        self.width = self.params.get('width')
        self.height = self.params.get('height')

        if not self.width:
            raise ValueError("Missing required parameter: width")
        if not self.height:
            raise ValueError("Missing required parameter: height")

        # Validate ranges
        if not 320 <= self.width <= 3840:
            raise ValueError(f"Width must be between 320 and 3840, got: {self.width}")
        if not 240 <= self.height <= 2160:
            raise ValueError(f"Height must be between 240 and 2160, got: {self.height}")

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        page = browser.page

        # Get current viewport. Playwright answers this from the size it
        # recorded for the context, so it confirms our own bookkeeping; the
        # evaluate below is what asks the document.
        current_viewport = page.viewport_size or {'width': 0, 'height': 0}
        inner_before = await _read_inner_size(page)

        requested = {'width': int(self.width), 'height': int(self.height)}

        # Set new viewport
        await page.set_viewport_size(requested)

        inner_after = await _read_inner_size(page)

        return {
            "status": "success",
            "viewport": dict(requested),
            "previous_viewport": current_viewport,
            "inner_size": (
                None if inner_before is None or inner_after is None
                else {"before": inner_before, "after": inner_after}
            ),
            "outcome": _viewport_outcome(
                requested=requested,
                before=inner_before,
                after=inner_after,
            ),
        }
