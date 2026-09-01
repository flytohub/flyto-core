# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Frame Module

Switch to iframe or frame context.

After entering a frame, all subsequent browser modules (click, type, extract,
evaluate, etc.) automatically operate within the frame because browser._page
is set to the Frame object (Playwright Frame shares the same API as Page).

Use action="exit" to return to the main page context.

WHAT ENTERING A FRAME CHANGES, AND WHAT IT DOES NOT

Nothing outside this process. ``browser._page = frame`` rebinds an attribute;
the page is untouched. So the rung here is not about a change to the world — it
is the extraction rule: this module went looking for a frame in the live page
and either found one or did not.

    the frame was located and reports itself attached   OBSERVED
    the frame was located and reports itself DETACHED   INDETERMINATE
    no frame matched                                    raises; no envelope

What was located is real in all three lookup modes: ``page.frames`` is the frame
tree Playwright maintains from the browser's own frame lifecycle events, and the
selector mode additionally waits for the element in the DOM and resolves
``content_frame()`` through it. ``frame.url`` and ``frame.name`` come back from
that tree, not from the parameters — ask for ``name='inner'`` and the URL that
comes back is the document the browser actually has in it.

The detached case is INDETERMINATE and not FAILED because the lookup did
succeed: a frame that was in the tree when we asked and has since been removed
reads the same as one that is about to be re-attached by the page's own script.
Subsequent modules will act on it and may well be fine.

`exit` writes no envelope. It restores an attribute this module saved and
touches nothing else — no instruction is issued, and the ladder has no rung that
means "nothing was dispatched". `list` is the same extraction as the `enter`
lookup and says so.
"""
from typing import Any, Dict, Optional

from ....engine.outcome import ClaimBy, Outcome, envelope
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets, field


def _frames_listed_outcome(count: int) -> Dict[str, Any]:
    """Listing frames is an extraction. A page always has at least its main
    frame, so the empty case is unreachable in practice and still handled."""
    if count <= 0:
        return envelope(
            Outcome.ACCEPTED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'no_frames_listed',
                'measured_by': None,
                'detail': (
                    'The page reports no frames at all, not even a main frame. '
                    'An empty listing is not an observation of the page.'
                ),
            }],
        )
    return envelope(
        Outcome.OBSERVED,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'frames_listed',
            'count': count,
            'measured_by': (
                "page.frames — the frame tree Playwright maintains from the "
                "browser's frame lifecycle events, with each frame's url and "
                'name read from it'
            ),
        }],
    )


def _frame_entered_outcome(
    *, how: str, frame_url: str, frame_name: str, detached: Optional[bool]
) -> Dict[str, Any]:
    """The rung entering a frame earned, from the frame the browser handed back."""
    located = {
        'kind': 'frame_located',
        'found_by': how,
        'frame_url': frame_url,
        'frame_name': frame_name,
        'measured_by': (
            'the frame object the browser reported, with its url and name read '
            'from it'
            if how != 'selector' else
            'page.wait_for_selector() then ElementHandle.content_frame(), with '
            "the frame's url and name read from the frame it returned"
        ),
    }

    if detached:
        return envelope(
            Outcome.INDETERMINATE,
            claim_by=ClaimBy.INFERRED,
            effects=[{
                **located,
                'predicate': 'not Frame.is_detached()',
                'detail': (
                    'The frame was found in the tree and reports itself '
                    'detached. Every module after this one will act inside it. '
                    'A frame torn down after the lookup and one about to be '
                    're-attached by the page read alike, so this is '
                    'indeterminate rather than failed.'
                ),
            }],
        )

    return envelope(
        Outcome.OBSERVED,
        claim_by=ClaimBy.NONE,
        effects=[{
            **located,
            'detail': (
                'A frame matching the request exists in the page and is '
                'attached. What changed is only which object subsequent modules '
                'address — nothing on the page moved, and nothing here claims '
                'it did.'
            ),
        }],
    )


@register_module(
    module_id='browser.frame',
    version='1.1.0',
    category='browser',
    tags=['browser', 'frame', 'iframe', 'ssrf_protected'],
    label='Switch Frame',
    label_key='modules.browser.frame.label',
    description='Switch to iframe or frame context',
    description_key='modules.browser.frame.description',
    icon='LayoutGrid',
    color='#0D6EFD',

    # Connection types
    input_types=['page'],
    output_types=['browser', 'page'],


    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*', 'ai.*', 'llm.*', 'agent.*'],
    params_schema=compose(
        presets.SELECTOR(required=False, placeholder='iframe#content'),
        field(
            'name',
            type='string',
            label='Frame Name',
            label_key='modules.browser.frame.params.name.label',
            description='Name attribute of the frame (alternative to selector)',
            placeholder='my-name',
            required=False,
        ),
        field(
            'url',
            type='string',
            label='Frame URL',
            label_key='modules.browser.frame.params.url.label',
            description='URL pattern to match frame (alternative to selector)',
            placeholder='https://example.com',
            required=False,
        ),
        field(
            'action',
            type='string',
            label='Action',
            label_key='modules.browser.frame.params.action.label',
            description='Frame action to perform',
            default='enter',
            options=[
                {'value': 'enter', 'label': 'Enter Frame (switch context)'},
                {'value': 'exit', 'label': 'Exit Frame (return to main page)'},
                {'value': 'list', 'label': 'List All Frames'},
            ],
        ),
        presets.TIMEOUT_MS(default=30000),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.browser.frame.output.status.description'},
        'frame_url': {'type': 'string', 'description': 'Frame URL',
                'description_key': 'modules.browser.frame.output.frame_url.description'},
        'frame_name': {'type': 'string', 'description': 'The frame name',
                'description_key': 'modules.browser.frame.output.frame_name.description'},
        'frames': {'type': 'array', 'description': 'List of frames',
                'description_key': 'modules.browser.frame.output.frames.description'},
        'outcome': {'type': 'object', 'description': (
            'How far the lookup went: observed when a frame was located in the '
            'live page and reports itself attached, indeterminate when it '
            'reports itself detached. Absent on exit, which dispatches nothing.'
        ),
                'description_key': 'modules.browser.frame.output.outcome.description'}
    },
    examples=[
        {
            'name': 'Switch to iframe by selector',
            'params': {'selector': 'iframe#content-frame'}
        },
        {
            'name': 'Switch to frame by name',
            'params': {'name': 'main-content'}
        },
        {
            'name': 'Exit frame (back to main page)',
            'params': {'action': 'exit'}
        },
        {
            'name': 'List all frames',
            'params': {'action': 'list'}
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=30000,
    required_permissions=["browser.automation"],
)
class BrowserFrameModule(BaseModule):
    """Switch Frame Module"""

    module_name = "Switch Frame"
    module_description = "Switch to iframe or frame context"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        self.selector = self.params.get('selector')
        self.name = self.params.get('name')
        self.url = self.params.get('url')
        self.action = self.params.get('action', 'enter')
        self.timeout = self.params.get('timeout', 30000)

        if self.action == 'enter' and not any([self.selector, self.name, self.url]):
            raise ValueError("enter action requires selector, name, or url")

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        # Exit frame: restore original page context. No envelope on either
        # branch — this restores an attribute and issues no instruction, and no
        # rung on the ladder means "nothing was dispatched".
        if self.action == 'exit':
            original_page = self.context.get('_original_page')
            if original_page:
                browser._page = original_page
                self.context.pop('_original_page', None)
                self.context.pop('current_frame', None)
                return {
                    "status": "success",
                    "message": "Returned to main page context"
                }
            else:
                return {
                    "status": "success",
                    "message": "Already in main page context"
                }

        # Use the original page for listing/finding frames (not a frame object)
        original_page = self.context.get('_original_page')
        page = original_page if original_page else browser.page

        if self.action == 'list':
            # List all frames (always from the main page)
            frames = []
            for frame in page.frames:
                frames.append({
                    'name': frame.name,
                    'url': frame.url,
                    'is_main': frame == page.main_frame
                })
            return {
                "status": "success",
                "frames": frames,
                "count": len(frames),
                "outcome": _frames_listed_outcome(len(frames)),
            }

        # Find and switch to frame
        frame = None
        how = 'selector' if self.selector else ('name' if self.name else 'url')

        if self.selector:
            # Get frame by selector
            frame_element = await page.wait_for_selector(
                self.selector,
                timeout=self.timeout
            )
            frame = await frame_element.content_frame()

        elif self.name:
            # Get frame by name
            frame = page.frame(name=self.name)

        elif self.url:
            # Get frame by URL pattern
            import re
            pattern = re.compile(self.url)
            for f in page.frames:
                if pattern.search(f.url):
                    frame = f
                    break

        if not frame:
            raise RuntimeError(f"Frame not found")

        # Save original page for restoration (only if not already inside a frame)
        if not original_page:
            self.context['_original_page'] = browser._page

        # Set browser._page to the frame so all subsequent modules
        # (click, type, extract, evaluate, etc.) operate within the frame.
        # Playwright Frame has the same API as Page for these operations.
        browser._page = frame

        # Also keep in context for backward compatibility
        self.context['current_frame'] = frame

        try:
            detached = frame.is_detached()
        except Exception:  # noqa: BLE001 - any failure means "cannot look"
            detached = None

        return {
            "status": "success",
            "frame_url": frame.url,
            "frame_name": frame.name or "(unnamed)",
            "outcome": _frame_entered_outcome(
                how=how,
                frame_url=frame.url,
                frame_name=frame.name or "(unnamed)",
                detached=detached,
            ),
        }
