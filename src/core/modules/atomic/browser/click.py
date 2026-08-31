# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Click Module - Click an element on the page
"""
import asyncio
import logging
from contextlib import suppress
from typing import Any

from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field, presets
from ...schema.constants import FieldGroup

logger = logging.getLogger(__name__)


# A browser never decides where a click lands from the clicked element's own
# attributes alone. Three shapes carry the decision somewhere else, and all
# three are ordinary page markup:
#   * a submit control inherits its <form>'s target (its own formtarget wins),
#   * an <a href> with no target of its own inherits <base target>,
#   * an inline handler can reach window.open through a named function.
# Reading only the element leaves each of those looking exactly like a click
# that promised nothing, so a tab that never opened cannot be told from one
# that did. This resolves the effective target the way the browser does.
_TAB_DECLARATION_JS = r"""(el) => {
  const isBlank = (value) =>
    typeof value === 'string' && value.trim().toLowerCase() === '_blank';
  const opensWindow = (source) => !!source && (
    /(?:window|self|top|globalThis)\s*\.\s*open\s*\(/.test(source)
    || /(?:^|[^.\w$])open\s*\(/.test(source)
  );

  const tag = (el.tagName || '').toLowerCase();
  // Only these navigate on activation, so only these can inherit a target.
  const navigates = (tag === 'a' || tag === 'area') && el.hasAttribute('href');
  const submits = (tag === 'button' && el.type === 'submit')
    || (tag === 'input' && (el.type === 'submit' || el.type === 'image'));
  const form = submits ? (el.form || (el.closest ? el.closest('form') : null)) : null;
  const owns = (tag === 'a' || tag === 'area' || tag === 'form')
    && el.hasAttribute('target');

  // Effective target, in the browser's own precedence order. Each rung is
  // the answer once it applies: formtarget='_self' on the button beats
  // target='_blank' on the form it submits.
  if (el.hasAttribute('formtarget')) {
    if (isBlank(el.getAttribute('formtarget'))) return true;
  } else if (owns) {
    if (isBlank(el.getAttribute('target'))) return true;
  } else if (form && form.hasAttribute('target')) {
    if (isBlank(form.getAttribute('target'))) return true;
  } else if (navigates || form) {
    const base = el.ownerDocument.querySelector('base[target]');
    if (base && isBlank(base.getAttribute('target'))) return true;
  }

  // A target attribute the browser ignores still declares intent, and 1.2.0
  // reported it; keep saying so rather than silently narrowing.
  if (isBlank(el.getAttribute('target'))) return true;

  const onclick = el.getAttribute('onclick');
  if (!onclick) return false;
  if (opensWindow(onclick)) return true;

  // 'go()' says nothing on its own; what go's body does is the declaration.
  const view = el.ownerDocument.defaultView;
  const called = onclick.match(/[A-Za-z_$][\w$]*(?:\s*\.\s*[A-Za-z_$][\w$]*)*\s*\(/g) || [];
  for (const call of called) {
    const path = call.slice(0, call.lastIndexOf('(')).split('.').map((p) => p.trim());
    let fn = view;
    for (const part of path) {
      try {
        fn = fn == null ? null : fn[part];
      } catch (err) {
        fn = null;
      }
    }
    if (typeof fn !== 'function') continue;
    let source = '';
    try {
      source = Function.prototype.toString.call(fn);
    } catch (err) {
      source = '';
    }
    if (opensWindow(source)) return true;
  }
  return false;
}"""


@register_module(
    module_id='browser.click',
    version='1.3.1',
    category='browser',
    tags=['browser', 'interaction', 'click', 'ssrf_protected'],
    label='Click Element',
    label_key='modules.browser.click.label',
    description='Click a visible element by its button/link name, page text, ID, or an advanced selector.',
    description_key='modules.browser.click.description',
    icon='MousePointerClick',
    color='#F0AD4E',

    # Connection types
    input_types=['page'],
    output_types=['browser', 'page'],

    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*', 'ai.*', 'llm.*', 'agent.*'],
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
              description='Use the visible or accessible name, e.g. "Submit", "Next Page", or "Login"',
              description_key="modules.browser.click.param.target.description",
              placeholder="Submit",
              showIf={"click_method": {"$in": ["text", "button", "id"]}},
              ui={"widget": "element_picker", "element_types": ["button", "link", "checkbox", "radio", "switch"],
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
              ui={"widget": "element_picker", "element_types": ["button", "link", "checkbox", "radio", "switch"], "value_key": "selector"},
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
              items={"type": "string", "enum": ["Alt", "Control", "Meta", "Shift"]},
              group=FieldGroup.ADVANCED),
        field("expected_outcome", type="select",
              label="Expected outcome",
              description=(
                  "Verify what the click must cause. Auto only reports a new tab when "
                  "the element declares one; it never fails the click."
              ),
              default="auto",
              options=[
                  {"value": "auto", "label": "Auto-detect from the element"},
                  {"value": "new_tab", "label": "A new tab opens"},
                  {"value": "url_change", "label": "The page URL changes"},
                  {"value": "url_contains", "label": "The page URL contains text"},
                  {"value": "selector_visible", "label": "An element becomes visible"},
                  {"value": "selector_hidden", "label": "An element becomes hidden"},
                  {"value": "click_only", "label": "Only confirm the click was dispatched"},
              ],
              group=FieldGroup.OPTIONS),
        field("outcome_value", type="string",
              label="Expected value",
              description="URL text or selector used to verify the expected outcome",
              required=False,
              showIf={"expected_outcome": {"$in": ["url_contains", "selector_visible", "selector_hidden"]}},
              group=FieldGroup.OPTIONS),
        field("verification_timeout_ms", type="number",
              label="Outcome timeout (ms)",
              description="Maximum time to wait for the expected outcome",
              default=5000,
              min=1,
              max=120000,
              group=FieldGroup.OPTIONS),
        presets.TIMEOUT_MS(key='timeout_ms', default=30000),
    ),
    # What execute() actually returns. The browser session is a context
    # pass-through, not a result key — ``output_types`` is where chaining is
    # declared — and the element hints harvested after the click are half of
    # what the next step's Element Picker reads, so they belong here too.
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.browser.click.output.status.description'},
        'selector': {'type': 'string', 'description': 'Selector that was used',
                'description_key': 'modules.browser.click.output.selector.description'},
        'method': {'type': 'string', 'description': 'Click method used'},
        'opened_new_tab': {'type': 'boolean', 'description': 'Whether the click opened and adopted a new tab'},
        'tab_count': {'type': 'number', 'description': 'Number of tabs after the click'},
        'current_index': {'type': 'number', 'description': 'Current tab index after the click'},
        'url': {'type': 'string', 'description': 'URL of the page controlled after the click'},
        'expected_outcome': {'type': 'string', 'description': 'Outcome contract applied to the click'},
        'verification_status': {'type': 'string',
                'description': 'What was checked: verified, inferred, unverified, dispatched, not_requested'},
        'effect_observed': {'type': 'boolean', 'description': 'Whether a visible browser effect was observed'},
        'effects': {'type': 'array', 'description': 'Observed browser effects'},
        'pre_url': {'type': 'string', 'description': 'URL controlled before the click'},
        '_page_hint': {'type': 'string', 'description': 'Visible text of the page after the click (truncated)'},
        'inputs': {'type': 'array', 'description': 'Text inputs found on the page after the click'},
        'checkboxes': {'type': 'array', 'description': 'Checkboxes found on the page after the click'},
        'radios': {'type': 'array', 'description': 'Radio groups found on the page after the click'},
        'switches': {'type': 'array', 'description': 'Switch controls found on the page after the click'},
        'selects': {'type': 'array', 'description': 'Dropdowns found on the page after the click'},
        'buttons': {'type': 'array', 'description': 'Buttons found on the page after the click'},
        'links': {'type': 'array', 'description': 'Links found on the page after the click'},
        'file_inputs': {'type': 'array', 'description': 'File upload inputs found on the page after the click'},
    },
    examples=[
        {
            'name': 'Click by button text',
            'params': {'click_method': 'button', 'target': 'Submit'}
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
    author='Flyto2 Team',
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
            escaped = target.replace('"', '\\"')
            self.selector = f':is(button, a, [role="button"]):has-text("{escaped}")'
            self.target = target
        else:  # text (default)
            if not target:
                raise ValueError("Text content is required")
            escaped = target.replace('"', '\\"')
            self.selector = f'text="{escaped}"'

        self.method = method
        self.button = self.params.get('button', 'left')
        self.click_count = self.params.get('click_count', 1)
        self.force = self.params.get('force', False)
        self.modifiers = self.params.get('modifiers', [])
        self.timeout = self.params.get('timeout_ms', 30000)
        self.expected_outcome = self.params.get('expected_outcome', 'auto')
        allowed_outcomes = {
            'auto',
            'new_tab',
            'url_change',
            'url_contains',
            'selector_visible',
            'selector_hidden',
            'click_only',
        }
        if self.expected_outcome not in allowed_outcomes:
            raise ValueError(f"Invalid expected outcome: {self.expected_outcome}")

        raw_outcome_value = self.params.get('outcome_value', '')
        if not isinstance(raw_outcome_value, str):
            raise ValueError("Expected value must be a string")
        self.outcome_value = raw_outcome_value.strip()
        if (
            self.expected_outcome in {'url_contains', 'selector_visible', 'selector_hidden'}
            and not self.outcome_value
        ):
            raise ValueError(
                f"Expected value is required for {self.expected_outcome}"
            )

        self.verification_timeout_ms = self.params.get('verification_timeout_ms', 5000)
        if isinstance(self.verification_timeout_ms, bool) or not isinstance(
            self.verification_timeout_ms,
            (int, float),
        ):
            raise ValueError("Outcome timeout must be a number")
        if not 1 <= self.verification_timeout_ms <= 120000:
            raise ValueError("Outcome timeout must be between 1 and 120000ms")

    async def _resolve_button_or_link(self, page):
        """Resolve a visible action by accessible role and name.

        Element Picker hints use the same accessible-name sources, including
        aria-label and an icon image's alt text. Exact names win; a contains
        match remains as the forgiving fallback used by the old has-text path.
        """
        deadline = asyncio.get_running_loop().time() + (self.timeout / 1000)
        candidates = (
            ('button', True),
            ('link', True),
            ('button', False),
            ('link', False),
        )

        while True:
            for role, exact in candidates:
                locator = page.get_by_role(
                    role,
                    name=self.target,
                    exact=exact,
                    include_hidden=self.force,
                )
                if not self.force:
                    locator = locator.filter(visible=True)
                if await locator.count():
                    match = locator.first
                    return match, f'role={role}[name={self.target!r}]'

            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise RuntimeError(
                    f'No visible button or link named {self.target!r} '
                    f'was found within {self.timeout}ms'
                )
            await asyncio.sleep(min(0.1, remaining))

    async def _expects_new_page(self, locator) -> bool:
        """Best-effort detection for elements that explicitly declare a tab.

        Resolved against the live document, because that is where the answer
        lives: the owning <form>'s target, the document's <base target>, and
        the body of a function an inline handler names are all outside the
        clicked element. Attribute reads remain the fallback for when no DOM
        can be reached, which is all they were ever able to see.
        """
        if locator is None:
            return False

        with suppress(Exception):
            return bool(await locator.evaluate(_TAB_DECLARATION_JS))

        for attribute in ('target', 'formtarget'):
            with suppress(Exception):
                value = await locator.get_attribute(attribute)
                if value and value.lower() == '_blank':
                    return True

        with suppress(Exception):
            onclick = await locator.get_attribute('onclick')
            if onclick and 'window.open' in onclick.lower():
                return True

        return False

    @staticmethod
    def _new_context_page(context, known_pages):
        """Return the newest page that did not exist before the click."""
        return next(
            (candidate for candidate in reversed(context.pages) if candidate not in known_pages),
            None,
        )

    @staticmethod
    def _hint_effect_signature(hints):
        """Return stable, semantic hint content for effect reporting.

        Geometry is deliberately excluded: responsive layout and animation may
        move an unchanged control and must not turn a no-op click into evidence.
        """
        if not isinstance(hints, dict):
            return hints

        def _stable(value):
            if isinstance(value, dict):
                return tuple(
                    (key, _stable(item))
                    for key, item in sorted(value.items())
                    if key != 'rect'
                )
            if isinstance(value, list):
                return tuple(_stable(item) for item in value)
            return value

        return _stable(hints)

    async def _outcome_holds(self, page, outcome, pre_url) -> bool:
        """Return whether ``outcome``'s final state holds on ``page`` right now.

        One derivation serves the pre-click measurement and the post-click
        wait, so the two cannot disagree about the same document.
        """
        if outcome == 'url_change':
            return page.url != pre_url
        if outcome == 'url_contains':
            return self.outcome_value in page.url
        if outcome in {'selector_visible', 'selector_hidden'}:
            visible_count = await page.locator(self.outcome_value).filter(
                visible=True,
            ).count()
            is_visible = visible_count > 0
            return is_visible if outcome == 'selector_visible' else not is_visible
        return False

    async def _verify_current_page_outcome(self, browser, outcome, pre_url):
        """Wait for an explicit non-tab outcome or raise with useful evidence.

        Both branches measure ``browser.page``. The selector branch has to:
        it delegates to ``browser.wait``, which resolves the document from
        ``browser._page`` internally and cannot be pointed at another one. The
        URL branch therefore reads the same attribute rather than a page passed
        in beside it — a parameter only one branch honoured would let the two
        drift apart the moment this call moved relative to tab adoption, with
        the URL branch judging the opener while the selector branch silently
        followed the popup.

        The caller must still invoke this while ``browser.page`` is the
        document ``pre_url`` was read from; the name says which document is
        measured so that requirement is visible at the call site instead of
        being implied by a parameter that was ignored.
        """
        page = browser.page
        if outcome in {'selector_visible', 'selector_hidden'}:
            state = 'visible' if outcome == 'selector_visible' else 'hidden'
            try:
                await browser.wait(
                    self.outcome_value,
                    state=state,
                    timeout_ms=self.verification_timeout_ms,
                )
            except Exception as exc:
                raise RuntimeError(
                    f"Click was dispatched but expected {self.outcome_value!r} to become "
                    f"{state} within {self.verification_timeout_ms}ms"
                ) from exc
            return

        deadline = asyncio.get_running_loop().time() + self.verification_timeout_ms / 1000
        while not await self._outcome_holds(page, outcome, pre_url):
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                expectation = (
                    'the page URL to change'
                    if outcome == 'url_change'
                    else f"the page URL to contain {self.outcome_value!r}"
                )
                raise RuntimeError(
                    f"Click was dispatched but expected {expectation} within "
                    f"{self.verification_timeout_ms}ms; current URL is {page.url!r}"
                )
            await asyncio.sleep(min(0.05, remaining))

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        # Pre-action: refresh element hints to ensure we have current page state
        pre_hints = await browser.get_hints()

        page = browser.page
        context = browser._context
        known_pages = tuple(context.pages)
        loop = asyncio.get_running_loop()
        new_page_future = loop.create_future()

        def _capture_new_page(new_page):
            if new_page not in known_pages and not new_page_future.done():
                new_page_future.set_result(new_page)

        context.on('page', _capture_new_page)

        # Capture before clicking so real navigation is distinguishable from
        # an in-place SPA update after Playwright finishes the click.
        pre_url = page.url

        click_options = {
            'button': self.button,
            'click_count': self.click_count,
            'force': self.force,
        }
        if self.modifiers:
            click_options['modifiers'] = self.modifiers

        locator = None
        new_page = None
        effective_outcome = self.expected_outcome
        try:
            # A state that is already true is not evidence of a click effect;
            # record it and judge the post-state against it, but still click.
            pre_satisfied = await self._outcome_holds(
                page,
                effective_outcome,
                pre_url,
            )

            if self.method == 'button':
                locator, self.selector = await self._resolve_button_or_link(page)
            else:
                # Wait for element to be visible before clicking (unless force mode)
                if not self.force:
                    await browser.wait(
                        self.selector,
                        state='visible',
                        timeout_ms=self.timeout,
                    )
                locator = page.locator(self.selector).first

            expects_new_page = await self._expects_new_page(locator)
            await locator.click(**click_options)

            # Page events raised by a click normally arrive before the click
            # resolves. Yield once so Playwright can dispatch an event already
            # queued on the transport. Explicit target=_blank/window.open
            # actions receive a short bounded wait for slow page creation.
            await asyncio.sleep(0)
            new_page = (
                new_page_future.result()
                if new_page_future.done()
                else self._new_context_page(context, known_pages)
            )
            requires_new_page = effective_outcome == 'new_tab'
            if new_page is None and (expects_new_page or requires_new_page):
                try:
                    # An explicit contract may spend the caller's budget; an
                    # inference keeps 1.2.0's short best-effort re-scan.
                    new_page = await asyncio.wait_for(
                        asyncio.shield(new_page_future),
                        timeout=min(
                            self.verification_timeout_ms / 1000 if requires_new_page else 2.0,
                            self.timeout / 1000,
                        ),
                    )
                except asyncio.TimeoutError:
                    new_page = self._new_context_page(context, known_pages)

            if requires_new_page and new_page is None:
                raise RuntimeError(
                    "Click was dispatched but expected a new tab within "
                    f"{self.verification_timeout_ms}ms; tab count stayed at "
                    f"{len(context.pages)}"
                )
            if effective_outcome == 'auto' and expects_new_page:
                # 'auto' only infers a tab from markup: evidence to report,
                # never a contract. Pre-1.3.0 templates all land here.
                effective_outcome = 'new_tab'
        finally:
            with suppress(Exception):
                context.remove_listener('page', _capture_new_page)
            if not new_page_future.done():
                new_page_future.cancel()

        # Verify before adopting any tab, while ``page`` and ``browser.page``
        # are still the document the contract was measured on.
        if effective_outcome not in {'auto', 'click_only', 'new_tab'}:
            if pre_satisfied:
                raise RuntimeError(
                    f"Expected outcome {effective_outcome!r} was already satisfied "
                    "before the click; no click effect could be verified"
                )
            await self._verify_current_page_outcome(browser, effective_outcome, pre_url)

        origin_page = page
        if new_page is not None:
            # A user click that opens a foreground tab should move both
            # workflow control and live preview to that page. Without this,
            # later browser.* nodes keep operating on the opener.
            browser._page = new_page
            page = new_page

        # Post-click: capture interactive elements of the NEW page state.
        # This ensures the next step's Element Picker sees the correct elements
        # (especially after click-induced navigation).
        pages = context.pages
        current_index = next(
            (index for index, candidate in enumerate(pages) if candidate == page),
            -1,
        )
        # Say exactly what was checked: 'click_only' verifies nothing beyond
        # dispatch, and an inference is weaker than a requested contract.
        if effective_outcome == 'auto':
            verification_status = 'not_requested'
        elif effective_outcome == 'click_only':
            verification_status = 'dispatched'
        elif self.expected_outcome == 'auto':
            verification_status = 'inferred' if new_page is not None else 'unverified'
        else:
            verification_status = 'verified'

        result = {
            "status": "success",
            "selector": self.selector,
            "method": self.method,
            "opened_new_tab": new_page is not None,
            "tab_count": len(pages),
            "current_index": current_index,
            "expected_outcome": effective_outcome,
            "verification_status": verification_status,
            "pre_url": pre_url,
        }

        # Wait for page to settle after click.
        # Strategy: detect real navigation vs SPA, then wait for interactive
        # elements to appear before extracting hints.
        with suppress(Exception):
            await page.wait_for_load_state('domcontentloaded', timeout=2000)

        # A new document (real navigation or an adopted tab) renders its form
        # elements after domcontentloaded, so wait for them; an in-place SPA
        # update only needs the DOM to stabilise, then settle its animations.
        nav_happened = page.url != pre_url
        with suppress(Exception):
            await page.wait_for_function(
                '(sel) => document.querySelectorAll(sel).length > 0',
                arg=(
                    'input:not([type=hidden]), textarea, select, '
                    '[role="combobox"], [role="listbox"], [contenteditable="true"]'
                    if nav_happened
                    else 'select, [role="combobox"], [role="listbox"], '
                         'input:not([type=hidden]), button'
                ),
                timeout=5000 if nav_happened else 3000,
            )
        await page.wait_for_timeout(300 if nav_happened else 500)

        # Post-click: refresh hints on the (potentially new) page
        logger.info("[CLICK] post-action: nav=%s, pre=%s, now=%s", nav_happened, pre_url[:80], page.url[:80])
        await browser.invalidate_hints()
        hints = await browser.get_hints(force=True)
        logger.info("[CLICK] post-hints: inputs=%d, buttons=%d", len(hints.get('inputs', [])), len(hints.get('buttons', [])))
        browser._snapshot_since_nav = True
        if hints.get('text'):
            result["_page_hint"] = hints["text"][:800]
        for key in ('inputs', 'checkboxes', 'radios', 'switches', 'buttons', 'links', 'selects', 'file_inputs'):
            if hints.get(key):
                result[key] = hints[key]
        effects = []
        if new_page is not None:
            effects.append('new_tab')
        # Every effect is measured on the clicked document. An adopted popup
        # is already reported as 'new_tab'; its URL is not the opener's, and
        # neither are the hints just harvested from it.
        if origin_page.url != pre_url:
            effects.append('url_change')
        if new_page is None and (
            self._hint_effect_signature(hints) != self._hint_effect_signature(pre_hints)
        ):
            effects.append('page_content_change')
        if effective_outcome in {'selector_visible', 'selector_hidden'}:
            effects.append(effective_outcome)
        result['effects'] = effects
        result['effect_observed'] = bool(effects)
        result["url"] = page.url
        return result
