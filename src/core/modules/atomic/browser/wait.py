# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Wait Module - Wait for a duration or until an element appears

A WAIT THAT RETURNS HAS SEEN SOMETHING

This is the one module in the group whose success IS an observation rather than
a report of one. ``BrowserDriver.wait`` polls the real page and returns only
when the state it was asked for holds:

    state='visible'    at least one visible match exists
    state='hidden'     no visible matches exist
    state='attached'   the node is in the DOM
    state='detached'   it is not

Returning is therefore not "the call did not raise" in the way `browser.close`'s
``{'status': 'success'}`` is — Playwright re-evaluated the predicate against the
live DOM until it held. That earns OBSERVED, with the state that held named in
the effect. It does NOT earn VERIFIED: nothing is declared on the decorator, and
what held is a state the module went looking for, not a postcondition a caller
contracted for.

BUT TWO OF THOSE FOUR STATES ARE TRUE OF A SELECTOR THAT MATCHES NOTHING, and
for those, returning is worth nothing on its own. Read the list again as a typo
would: `hidden` means "no visible matches exist", and there are certainly no
visible matches of `#nosuchthign`. `detached` means "the node is not in the
DOM", and a node that was never in the DOM is not in the DOM. Measured against
real Chromium:

    #nosuchthing  state=hidden     returned in 7.3ms    0 matching nodes
    #nosuchthing  state=detached   returned in 0.6ms    0 matching nodes
    #gone         state=hidden     returned in 1.3ms    1 matching node
    #typo-xyz     state=visible    TimeoutError after 1502ms

The first two are the whole defect: a misspelled selector satisfies the wait
faster than a real one and the module called it an observation of the page. It
is the same failure `browser.drag` had — a reading identical whether or not the
effect happened — and it is worse here, because the wait's entire purpose is to
be the step that proves the page got somewhere. A workflow that waits for a
spinner to go `hidden` and moves on would have been told the spinner was gone
by a typo.

`visible` and `attached` cannot be satisfied that way; the fourth line above is
the proof, and it is why they need no extra reading. For the other two the
module counts matching nodes and asks which world it is in:

    hidden      counted AFTER   a node exists and is not visible    OBSERVED
                                nothing matched at all              INDETERMINATE
    detached    counted BEFORE  it was there, and now it is not     OBSERVED
                                it was never there                  INDETERMINATE

The count is read on the opposite side of the wait for each, and that asymmetry
is forced: after a successful `detached` wait the count is 0 whether the node
was removed or never existed, so only the before-reading separates them; for
`hidden` the node is still in the DOM when the state holds, so only the
after-reading does. INDETERMINATE, not FAILED — a caller who waits for an
element that is legitimately absent has not done anything wrong, we simply
cannot say we watched the page do it.

The duration path never touches the browser, so nothing about the page is
claimed for it. What it can measure is its own effect — that time passed — and
it measures it the way `browser.type` measures a field: read before, read after.
``time.monotonic()`` is not derived from the sleep arithmetic, and a sleep that
returned early shows up as a shortfall.

    elapsed >= the duration asked for   OBSERVED (of the clock, not the page)
    elapsed fell short                  INDETERMINATE

THE TIMEOUT PATH IS NOT HERE, AND THAT IS A GAP WORTH NAMING. A wait that times
out is INDETERMINATE by this contract — we do not know whether the thing we were
waiting for happened — but ``BrowserDriver.wait`` raises RuntimeError on
timeout and a raise carries no return value, so there is no envelope to attach
it to. It reaches a consumer as an execution error, which reads as FAILED. The
fix is not in this module: an envelope would have to ride on the exception, and
that is an engine-level channel this module cannot invent.
"""
import time
from typing import Any, Dict, Optional, Tuple

from ....engine.outcome import ClaimBy, Outcome, envelope
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field, presets
from ...schema.constants import FieldGroup


#: The states a selector matching NOTHING satisfies without the page doing
#: anything at all. `visible` and `attached` are absent deliberately: a selector
#: matching no node cannot satisfy either, it times out, and the module docstring
#: has the measurement.
_VACUOUSLY_TRUE_STATES = frozenset({'hidden', 'detached'})

#: Which side of the wait carries the existence witness for each of those. See
#: the docstring: after a `detached` wait the count is 0 either way, and during a
#: `hidden` one the node is still there to be counted.
_WITNESS_SIDE = {'hidden': 'after', 'detached': 'before'}


async def _count_matches(page, selector: str) -> Tuple[Optional[int], Optional[str]]:
    """How many nodes the selector matches, or why we could not count them."""
    try:
        return await page.locator(selector).count(), None
    except Exception as error:  # noqa: BLE001 - any failure means "cannot look"
        return None, f"{type(error).__name__}: {str(error).splitlines()[0][:160]}"


def _element_state_outcome(
    *,
    selector: str,
    state: str,
    count_before: Optional[int] = None,
    count_after: Optional[int] = None,
    count_error: Optional[str] = None,
) -> Dict[str, Any]:
    """The rung a satisfied element wait earned.

    OBSERVED only when the return said something a typo could not have said.
    """
    measured = {
        'kind': 'element_state_observed',
        'selector': selector,
        'state': state,
        'measured_by': (
            'Playwright re-evaluated the state against the live DOM until '
            'it held; the wait returned instead of timing out'
        ),
        'detail': (
            'The page reached the requested state while we were watching. '
            'That the state is the right one to have waited for is the '
            "caller's judgement and is not claimed here."
        ),
    }

    if state not in _VACUOUSLY_TRUE_STATES:
        return envelope(Outcome.OBSERVED, claim_by=ClaimBy.NONE, effects=[measured])

    side = _WITNESS_SIDE[state]
    witness = count_after if side == 'after' else count_before
    measured = {
        **measured,
        'matching_nodes': witness,
        'counted': side,
        'measured_by': (
            f'{measured["measured_by"]}; and locator.count() {side} it, because '
            f'a selector matching nothing satisfies state={state!r} on its own'
        ),
    }

    if witness is None:
        return envelope(
            Outcome.INDETERMINATE,
            claim_by=ClaimBy.INFERRED,
            effects=[{
                **measured,
                'count_error': count_error,
                'detail': (
                    'The wait returned, but the node count could not be read, '
                    'so we cannot tell a page that changed from a selector '
                    'that never matched.'
                ),
            }],
        )

    if witness == 0:
        return envelope(
            Outcome.INDETERMINATE,
            claim_by=ClaimBy.INFERRED,
            effects=[{
                **measured,
                'predicate': f'count({side}) > 0',
                'detail': (
                    f'The selector matched no nodes, and state={state!r} is '
                    'true of every element that was never there, so the wait '
                    'was satisfied without the page doing anything. A '
                    'misspelled selector reaches here, and so does a correct '
                    'one for an element that legitimately never appeared.'
                ),
            }],
        )

    return envelope(
        Outcome.OBSERVED,
        claim_by=ClaimBy.NONE,
        effects=[{
            **measured,
            'detail': (
                f'{witness} node(s) matched, so state={state!r} held of an '
                'element that actually exists in the page rather than of an '
                'empty selector.'
            ),
        }],
    )


def _duration_outcome(*, requested_ms: float, elapsed_ms: float) -> Dict[str, Any]:
    """The rung a plain sleep earned — from a clock, not from the arithmetic.

    Deliberately says nothing about the browser: this path does not touch it.
    The effect being followed is the passage of time, and `time.monotonic()`
    read either side of the sleep is an independent measurement of exactly
    that. If the sleep had not happened the delta would be near zero.
    """
    measured = {
        'kind': 'elapsed_time_observed',
        'requested_ms': requested_ms,
        'elapsed_ms': round(elapsed_ms, 3),
        'measured_by': 'time.monotonic(), read before and after the sleep',
        'detail': (
            'Time, and nothing else. No page was touched on this path, so '
            'nothing about the browser is observed by it.'
        ),
    }
    if elapsed_ms + 0.0 >= requested_ms:
        return envelope(Outcome.OBSERVED, claim_by=ClaimBy.NONE, effects=[measured])
    return envelope(
        Outcome.INDETERMINATE,
        claim_by=ClaimBy.INFERRED,
        effects=[{
            **measured,
            'predicate': 'elapsed_ms >= requested_ms',
            'detail': (
                'The sleep returned before the requested time had passed. A '
                'cancelled sleep, a clock adjustment and a loop that resumed '
                'early read alike, so this is indeterminate rather than failed.'
            ),
        }],
    )


@register_module(
    module_id='browser.wait',
    version='1.1.0',
    category='browser',
    tags=['browser', 'wait', 'delay', 'selector', 'ssrf_protected'],
    label='Wait',
    label_key='modules.browser.wait.label',
    description='Wait for a duration or until an element appears',
    description_key='modules.browser.wait.description',
    icon='Clock',
    color='#95A5A6',

    # Connection types
    input_types=['page'],
    output_types=['browser', 'page'],

    # Connection rules
    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*', 'ai.*', 'llm.*', 'agent.*'],

    # Execution settings
    timeout_ms=30000,
    retryable=True,
    max_retries=2,
    concurrent_safe=True,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['browser.read'],

    # Schema-driven params
    params_schema=compose(
        presets.DURATION_MS(key='duration_ms', default=1000, label='Wait Duration (ms)'),
        presets.SELECTOR(required=False, placeholder='.element-to-wait-for'),
        field(
            'state',
            type='select',
            label='Wait State',
            label_key='modules.browser.wait.params.state.label',
            description='Element state to wait for',
            default='visible',
            options=[
                {'value': 'visible', 'label': 'Visible (element is visible)'},
                {'value': 'hidden', 'label': 'Hidden (element is hidden)'},
                {'value': 'attached', 'label': 'Attached (element exists in DOM)'},
                {'value': 'detached', 'label': 'Detached (element removed from DOM)'},
            ],
            group=FieldGroup.OPTIONS,
            showIf={"selector": {"$ne": ""}},
        ),
        presets.TIMEOUT_MS(key='timeout_ms', default=30000),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.browser.wait.output.status.description'},
        'selector': {'type': 'string', 'optional': True, 'description': 'CSS selector that was waited for',
                'description_key': 'modules.browser.wait.output.selector.description'},
        'duration_ms': {'type': 'number', 'optional': True, 'description': 'Wait duration in milliseconds',
                'description_key': 'modules.browser.wait.output.duration_ms.description'},
        'elapsed_ms': {'type': 'number', 'optional': True, 'description': 'Time that actually passed, from a monotonic clock read either side of the sleep',
                'description_key': 'modules.browser.wait.output.elapsed_ms.description'},
        'outcome': {'type': 'object', 'description': (
            'How far the wait was followed: observed when the element state '
            'held in the live DOM, or when the clock confirmed the requested '
            'time passed; indeterminate when the sleep came up short. A wait '
            'that times out raises and carries no envelope.'
        ),
                'description_key': 'modules.browser.wait.output.outcome.description'}
    },
    examples=[
        {
            'name': 'Wait 2 seconds',
            'params': {'duration_ms': 2000}
        },
        {
            'name': 'Wait for element',
            'params': {'selector': '#loading-complete', 'timeout_ms': 5000}
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class BrowserWaitModule(BaseModule):
    """Wait Module"""

    module_name = "Wait"
    module_description = "Wait for a duration or element to appear"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        # Primary: duration_ms (explicit milliseconds)
        # Fallback: duration (for backwards compatibility - auto-detect unit)
        if 'duration_ms' in self.params:
            self.duration_ms = self.params['duration_ms']
        elif 'duration' in self.params:
            # Backwards compatibility: if duration > 100, assume ms; else assume seconds
            raw = self.params['duration']
            self.duration_ms = raw if raw > 100 else raw * 1000
        else:
            self.duration_ms = 1000  # Default 1 second

        self.selector = self.params.get('selector')
        self.state = self.params.get('state', 'visible')
        self.timeout = self.params.get('timeout_ms', 30000)

    async def execute(self) -> Any:
        import asyncio

        browser = self.context.get('browser')

        if self.selector:
            # Wait for element to reach specified state
            if not browser:
                raise RuntimeError("Browser not launched. Please run browser.launch first")
            # Counted before the wait, because after a satisfied `detached`
            # wait the count is 0 whether the node was removed or never
            # existed. Cheap, and it is the only reading that can tell those
            # apart. Errors are carried, not raised: failing to count is a
            # reason to claim less, never a reason to fail the step.
            needs_witness = self.state in _VACUOUSLY_TRUE_STATES
            count_before = count_after = count_error = None
            if needs_witness:
                count_before, count_error = await _count_matches(browser.page, self.selector)

            # A timeout raises out of here. See the module docstring: that path
            # is INDETERMINATE by this contract and has nowhere to say so.
            await browser.wait(self.selector, state=self.state, timeout_ms=self.timeout)

            if needs_witness:
                count_after, after_error = await _count_matches(browser.page, self.selector)
                count_error = count_error or after_error

            result = {
                "status": "success",
                "selector": self.selector,
                "state": self.state,
                "outcome": _element_state_outcome(
                    selector=self.selector,
                    state=self.state,
                    count_before=count_before,
                    count_after=count_after,
                    count_error=count_error,
                ),
            }
        else:
            # Wait for specified duration. The clock is read either side of the
            # sleep rather than the duration being echoed back.
            started = time.monotonic()
            await asyncio.sleep(self.duration_ms / 1000)
            elapsed_ms = (time.monotonic() - started) * 1000
            result = {
                "status": "success",
                "duration_ms": self.duration_ms,
                "elapsed_ms": round(elapsed_ms, 3),
                "outcome": _duration_outcome(
                    requested_ms=self.duration_ms, elapsed_ms=elapsed_ms
                ),
            }

        # Post-wait: capture element hints for Element Picker UI.
        # This is critical — wait nodes often follow navigation (click "下一步"),
        # so they're the first node to see the NEW page's elements.
        if browser:
            browser._snapshot_since_nav = True
            hints = await browser.get_hints(force=True)
            for key in ('inputs', 'checkboxes', 'radios', 'switches', 'buttons', 'links', 'selects', 'file_inputs'):
                if hints.get(key):
                    result[key] = hints[key]

        return result


