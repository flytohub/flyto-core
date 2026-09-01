# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Drag Module

Drag and drop elements.

HOW FAR A DRAG IS FOLLOWED

What this module reported about its own effect was ``from`` and ``to``: the
coordinates it computed from the two bounding boxes and then handed to
``mouse.move``. They are arithmetic on our own inputs. They are pixel-identical
whether the page has a drag handler at all, and this module very often lands on
a page that does not -- synthetic mouse events do not start a native HTML5
drag-and-drop in Chromium, so on any page using the HTML5 DnD API these four
mouse calls do precisely nothing while ``status: "success"`` and a pair of
plausible coordinates come back.

Three readings of the page separate those two worlds, all taken after
``mouse.up`` and each compared against the same reading taken before
``mouse.down``:

    the source element's bounding box moved      the page moved it
    the source element left the layout           the page removed or hid it
    the drop target's childElementCount changed  the page reparented something

Any one of them is a change in the page that our arithmetic cannot produce, so
any one of them earns OBSERVED. None of them earns INDETERMINATE, not FAILED:
a correct drop onto a file dropzone moves nothing and reparents nothing, so an
unchanged page reads the same as a drag that never started. It is claim_by
INFERRED because nobody declared what this drag was supposed to do to the page.

This is the measurement `browser.hover` did not have. ``:hover`` read false for
every hover including the correct ones, so a rung resting on it would have been
a permanent false alarm; these three read TRUE for a working mousedown-based
drag -- pinned against real Chromium in the tests -- and false for a drag that
went nowhere, which is the distinction a rung is for.
"""
from typing import Any, Dict, List, Optional, Tuple

from ....engine.outcome import ClaimBy, Outcome, envelope
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets, field


#: How far a bounding box may move before we call it a move. Sub-pixel drift
#: from a re-layout is not a drop, and comparing floats for equality would make
#: every such wobble look like one.
_MOVED_PX = 0.5


def _box_moved(before: Optional[Dict[str, Any]], after: Optional[Dict[str, Any]]) -> bool:
    if not before or not after:
        return False
    return (
        abs(after['x'] - before['x']) > _MOVED_PX
        or abs(after['y'] - before['y']) > _MOVED_PX
    )


#: The element's position in the LAYOUT, with every scroll that could be hiding
#: under it added back.
#:
#: `getBoundingClientRect()` is viewport-relative, so scrolling anything moves
#: it. The first attempt at this added `window.scrollX/Y`, which fixes exactly
#: one of the three ways a page scrolls and breaks a fourth case outright.
#: Measured on pages containing no script at all, where the truth is always
#: "the element did not move":
#:
#:     page shape                      raw rect   +window.scroll   this
#:     window scrolls (long page)      MOVED      ok               ok
#:     app shell, an overflow:auto     MOVED      MOVED            ok
#:       pane scrolls, window cannot
#:     position:fixed source           ok         MOVED            ok
#:     a drag that really moves it     MOVED      MOVED            MOVED
#:
#: The middle row is the ordinary kanban/app-shell layout, and window.scrollY is
#: 0 throughout it, so the correction adds nothing while the pane scrolls 3920px
#: underneath. The third row is worse: the raw reading was already right --
#: a fixed element does not move when the page scrolls -- and adding the scroll
#: INVENTED a 4280px displacement.
#:
#: So walk every ancestor and add its own scroll offset back. In standards mode
#: `documentElement.scrollTop` IS the window scroll, so the walk covers that case
#: too and must not add it again. A `position:fixed` element is anchored to the
#: viewport and no ancestor's scrolling moves it, so it accumulates nothing --
#: and the walk stops at a fixed ancestor for the same reason.
#:
#: A CSS transform still registers, which is what keeps this honest in the other
#: direction: `getBoundingClientRect()` includes transforms, and a drag
#: implemented as `transform: translate(...)` -- the common one -- moves the rect
#: without changing any layout offset. Reading `offsetTop` instead would have
#: been scroll-proof and blind to those.
_LAYOUT_POSITION_JS = """(el) => {
  const r = el.getBoundingClientRect();
  let x = r.x, y = r.y;
  if (getComputedStyle(el).position !== 'fixed') {
    let n = el.parentElement, anchored = false;
    while (n && !anchored) {
      x += n.scrollLeft;
      y += n.scrollTop;
      if (getComputedStyle(n).position === 'fixed') anchored = true;
      n = n.parentElement;
    }
  }
  return {x: x, y: y};
}"""


async def _read_box(locator) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """``(box, None)`` when the element could be measured, ``(None, why)`` when not.

    The ``x``/``y`` returned are the element's position in the LAYOUT, not in
    the viewport, and that conversion is the whole correctness of the rung above
    it. ``_LAYOUT_POSITION_JS`` carries the measurement that forced its exact
    shape; the short version is that `bounding_box()` is viewport-relative --
    Playwright's own docstring says "Scrolling affects the returned bounding
    box" -- while a synthetic mouse-down-move-up makes Chromium autoscroll on
    its own, so the raw box moves whether or not the drag did, and correcting
    only for `window.scroll` fixes one page shape while breaking another.

    ``width`` and ``height`` come straight from the box. ``viewport_x`` and
    ``viewport_y`` are kept alongside because they are what a person sees in a
    screenshot, and they are deliberately NOT what the rung is computed from.

    A missing box and a raised read are different answers, and neither of them
    is how a deleted element arrives. ``bounding_box()`` returning None means
    the element resolved and has no box -- ``display:none``, still in the DOM.
    A node the page REMOVED does not come back as None at all: the locator no
    longer resolves and the call RAISES, which is why the removal case is read
    by counting nodes in ``_count_nodes`` rather than inferred from a failure
    here. A raise on its own still means only "we could not look".
    """
    try:
        box = await locator.bounding_box(timeout=2000)
        if box is None:
            return None, None
        layout = await locator.evaluate(_LAYOUT_POSITION_JS, timeout=2000)
        return (
            {
                **box,
                'x': layout['x'],
                'y': layout['y'],
                'viewport_x': box['x'],
                'viewport_y': box['y'],
            },
            None,
        )
    except Exception as error:  # noqa: BLE001 - any failure means "cannot look"
        return None, f"{type(error).__name__}: {str(error).splitlines()[0][:160]}"


async def _count_nodes(locator) -> Tuple[Optional[int], Optional[str]]:
    """How many nodes the selector matches, or why we could not count them.

    This exists because `bounding_box()` cannot answer the question. On a node
    the page has REMOVED it does not return None -- it raises TimeoutError,
    because the locator no longer resolves to anything -- and a raise is
    indistinguishable from "we could not look". So the single clearest outcome
    a drag can have, the page deleting what was dragged, arrived as an
    unreadable box and was reported `indeterminate` with an effect named
    `page_unchanged_by_the_drag`. Counting is the reading that separates gone
    from unreadable.
    """
    try:
        return await locator.count(), None
    except Exception as error:  # noqa: BLE001 - any failure means "cannot look"
        return None, f"{type(error).__name__}: {str(error).splitlines()[0][:160]}"


async def _read_child_count(locator) -> Tuple[Optional[int], Optional[str]]:
    """The drop target's child count, or why it could not be read."""
    try:
        count = await locator.evaluate("el => el.childElementCount", timeout=2000)
    except Exception as error:  # noqa: BLE001 - any failure means "cannot look"
        return None, f"{type(error).__name__}: {str(error).splitlines()[0][:160]}"
    return (count, None) if isinstance(count, int) else (None, "childElementCount was not a number")


def _drag_outcome(
    *,
    source_box_before: Optional[Dict[str, Any]],
    source_box_after: Optional[Dict[str, Any]],
    source_read_error: Optional[str],
    source_nodes_after: Optional[int] = None,
    target_children_before: Optional[int],
    target_children_after: Optional[int],
    target_read_error: Optional[str],
) -> Dict[str, Any]:
    """The rung this drag earned, and the readings that earned it."""
    moved = _box_moved(source_box_before, source_box_after)
    # Two ways an element can leave the layout, and only one of them used to
    # count. `source_nodes_after == 0` is the page having REMOVED it -- a
    # drag-to-trash, the least ambiguous effect in this module -- and it is read
    # by counting, because the box read raises for exactly that case. The second
    # is a node still in the DOM with no box at all (`display:none`), where the
    # box read does return None and can be trusted.
    removed_from_dom = source_nodes_after == 0
    left_layout = source_box_before is not None and (
        removed_from_dom
        or (source_box_after is None and not source_read_error)
    )
    reparented = (
        target_children_before is not None
        and target_children_after is not None
        and target_children_before != target_children_after
    )
    read_anything_after = (
        source_box_after is not None
        or left_layout
        or target_children_after is not None
    )

    effects: List[Dict[str, Any]] = [{
        'kind': 'pointer_path_offered',
        'measured_by': 'arithmetic on the two bounding boxes this module read before the drag',
        'detail': (
            'The from/to coordinates are computed from our own inputs. They are '
            'identical whether the page has a drag handler or not, so nothing '
            'in the rung rests on them.'
        ),
    }, {
        'kind': 'source_box_observed' if source_box_after is not None or left_layout else 'source_box_not_observed',
        'moved': moved,
        'left_layout': left_layout,
        'measured_by': (
            None if source_read_error
            else 'locator.bounding_box() on the source, read before mouse.down and after mouse.up'
        ),
        'reason': None if removed_from_dom else source_read_error,
        'source_nodes_after': source_nodes_after,
    }, {
        'kind': 'target_children_observed' if target_children_after is not None else 'target_children_not_observed',
        'before': target_children_before,
        'after': target_children_after,
        'measured_by': (
            None if target_read_error
            else 'element.childElementCount on the drop target, read before mouse.down and after mouse.up'
        ),
        'reason': target_read_error,
    }]

    if moved or left_layout or reparented:
        return envelope(
            Outcome.OBSERVED,
            # INFERRED: that OUR pointer path caused the page to move this is
            # our inference. No caller declared what the drop should do.
            claim_by=ClaimBy.INFERRED,
            effects=effects,
        )

    if read_anything_after:
        return envelope(
            Outcome.INDETERMINATE,
            claim_by=ClaimBy.INFERRED,
            effects=effects + [{
                'kind': 'page_unchanged_by_the_drag',
                'predicate': 'the source box moved, the source left the layout, or the target gained or lost a child',
                'detail': (
                    'Everything we can see about the source and the target is '
                    'where it was. That reads the same whether the page has no '
                    'mouse-drag handler, uses the HTML5 drag-and-drop API that '
                    'synthetic mouse events do not trigger, or accepted the drop '
                    'without moving anything -- a file dropzone does exactly '
                    'that. We cannot say which, so this is indeterminate rather '
                    'than failed.'
                ),
            }],
        )

    return envelope(
        Outcome.ACCEPTED,
        claim_by=ClaimBy.NONE,
        effects=effects + [{
            'kind': 'nothing_could_be_read_back',
            'measured_by': None,
            'detail': (
                'The four mouse calls were acknowledged by the browser and did '
                'not raise. Neither the source nor the target could be read '
                'afterwards, so nothing followed the pointer into the page.'
            ),
        }],
    )


@register_module(
    module_id='browser.drag',
    version='1.0.0',
    category='browser',
    tags=['browser', 'drag', 'drop', 'interaction', 'ssrf_protected'],
    label='Drag and Drop',
    label_key='modules.browser.drag.label',
    description='Drag and drop elements',
    description_key='modules.browser.drag.description',
    icon='Move',
    color='#6F42C1',

    # Connection types
    input_types=['page'],
    output_types=['browser', 'page'],


    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*', 'ai.*', 'llm.*', 'agent.*'],    params_schema=compose(
        presets.SELECTOR(key='source', required=True, placeholder='#draggable', label='Source Selector'),
        presets.SELECTOR(key='target', required=True, placeholder='#dropzone', label='Target Selector'),
        field(
            'source_position',
            type='object',
            label='Source Position',
            label_key='modules.browser.drag.params.source_position.label',
            description='Position within source element {x, y} as percentages',
            required=False,
        ),
        field(
            'target_position',
            type='object',
            label='Target Position',
            label_key='modules.browser.drag.params.target_position.label',
            description='Position within target element {x, y} as percentages',
            required=False,
        ),
        presets.TIMEOUT_MS(default=30000),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.browser.drag.output.status.description'},
        'source': {'type': 'string', 'description': 'The source',
                'description_key': 'modules.browser.drag.output.source.description'},
        'target': {'type': 'string', 'description': 'The target',
                'description_key': 'modules.browser.drag.output.target.description'},
        'outcome': {'type': 'object', 'description': (
            'How far this drag was followed: observed when the source moved, '
            'left the layout, or the target gained or lost a child; '
            'indeterminate when nothing we can see changed; accepted when '
            'neither element could be read back.'
        ), 'description_key': 'modules.browser.drag.output.outcome.description'}
    },
    examples=[
        {
            'name': 'Simple drag and drop',
            'params': {'source': '#item1', 'target': '#dropzone'}
        },
        {
            'name': 'Drag to specific position',
            'params': {
                'source': '.draggable',
                'target': '.container',
                'target_position': {'x': 0.5, 'y': 0.5}
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=30000,
    required_permissions=["browser.automation"],
)
class BrowserDragModule(BaseModule):
    """Drag and Drop Module"""

    module_name = "Drag and Drop"
    module_description = "Drag and drop elements"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        if 'source' not in self.params:
            raise ValueError("Missing required parameter: source")
        if 'target' not in self.params:
            raise ValueError("Missing required parameter: target")

        self.source = self.params['source']
        self.target = self.params['target']
        self.source_position = self.params.get('source_position')
        self.target_position = self.params.get('target_position')
        self.timeout = self.params.get('timeout', 30000)

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        page = browser.page
        # mouse is a Page-only API; use real_page for mouse operations
        real_page = browser.real_page

        # Wait for both elements
        source_locator = page.locator(self.source)
        target_locator = page.locator(self.target)

        await source_locator.wait_for(timeout=self.timeout)
        await target_locator.wait_for(timeout=self.timeout)

        # Get element bounding boxes
        source_box = await source_locator.bounding_box()
        target_box = await target_locator.bounding_box()

        if not source_box:
            raise RuntimeError(f"Could not get bounding box for source: {self.source}")
        if not target_box:
            raise RuntimeError(f"Could not get bounding box for target: {self.target}")

        # Calculate positions
        if self.source_position:
            source_x = source_box['x'] + source_box['width'] * self.source_position.get('x', 0.5)
            source_y = source_box['y'] + source_box['height'] * self.source_position.get('y', 0.5)
        else:
            source_x = source_box['x'] + source_box['width'] / 2
            source_y = source_box['y'] + source_box['height'] / 2

        if self.target_position:
            target_x = target_box['x'] + target_box['width'] * self.target_position.get('x', 0.5)
            target_y = target_box['y'] + target_box['height'] * self.target_position.get('y', 0.5)
        else:
            target_x = target_box['x'] + target_box['width'] / 2
            target_y = target_box['y'] + target_box['height'] / 2

        # The drop target's shape BEFORE the pointer goes anywhere.
        children_before, target_read_error = await _read_child_count(target_locator)

        # The source's position BEFORE, in the same coordinate space the after
        # reading uses. `source_box` above is viewport-relative because that is
        # what the mouse needs; comparing it against a document-space after
        # reading would measure the scroll rather than remove it, which is the
        # same defect in the opposite direction.
        source_box_before, source_read_error_before = await _read_box(source_locator)

        # Perform drag and drop (mouse is Page-only)
        await real_page.mouse.move(source_x, source_y)
        await real_page.mouse.down()
        await real_page.mouse.move(target_x, target_y, steps=10)
        await real_page.mouse.up()

        source_box_after, source_read_error = await _read_box(source_locator)
        source_nodes_after, _source_count_error = await _count_nodes(source_locator)
        children_after, target_read_error_after = await _read_child_count(target_locator)

        return {
            "status": "success",
            "source": self.source,
            "target": self.target,
            "from": {"x": source_x, "y": source_y},
            "to": {"x": target_x, "y": target_y},
            "outcome": _drag_outcome(
                source_box_before=source_box_before,
                source_box_after=source_box_after,
                source_read_error=source_read_error_before or source_read_error,
                source_nodes_after=source_nodes_after,
                target_children_before=children_before,
                target_children_after=children_after,
                target_read_error=target_read_error or target_read_error_after,
            ),
        }
