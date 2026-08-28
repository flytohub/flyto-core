# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Click Module - Click an element on the page
"""
import asyncio
from contextlib import suppress
from typing import Any

from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field, presets
from ...schema.constants import FieldGroup


@register_module(
    module_id='browser.click',
    version='1.2.0',
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
        presets.TIMEOUT_MS(default=30000),
    ),
    output_schema={
        'browser': {'type': 'object', 'description': 'Browser session (pass-through for chaining)',
                'description_key': 'modules.browser.click.output.browser.description'},
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.browser.click.output.status.description'},
        'selector': {'type': 'string', 'description': 'Selector that was used',
                'description_key': 'modules.browser.click.output.selector.description'},
        'method': {'type': 'string', 'description': 'Click method used'},
        'opened_new_tab': {'type': 'boolean', 'description': 'Whether the click opened and adopted a new tab'},
        'tab_count': {'type': 'number', 'description': 'Number of tabs after the click'},
        'current_index': {'type': 'number', 'description': 'Current tab index after the click'},
        'url': {'type': 'string', 'description': 'URL of the page controlled after the click'},
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
        """Best-effort detection for links/forms that explicitly open a tab."""
        if locator is None:
            return False

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

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        # Pre-action: refresh element hints to ensure we have current page state
        await browser.get_hints()

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
        try:
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
                with suppress(Exception):
                    locator = page.locator(self.selector).first

            expects_new_page = await self._expects_new_page(locator)

            if self.method == 'button':
                await locator.click(**click_options)
            else:
                await page.click(self.selector, **click_options)

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
            if new_page is None and expects_new_page:
                try:
                    new_page = await asyncio.wait_for(
                        asyncio.shield(new_page_future),
                        timeout=min(2.0, self.timeout / 1000),
                    )
                except asyncio.TimeoutError:
                    new_page = self._new_context_page(context, known_pages)
        finally:
            with suppress(Exception):
                context.remove_listener('page', _capture_new_page)
            if not new_page_future.done():
                new_page_future.cancel()

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
        result = {
            "status": "success",
            "selector": self.selector,
            "method": self.method,
            "opened_new_tab": new_page is not None,
            "tab_count": len(pages),
            "current_index": current_index,
            "url": page.url,
        }

        # Wait for page to settle after click.
        # Strategy: detect real navigation vs SPA, then wait for interactive
        # elements to appear before extracting hints.
        with suppress(Exception):
            await page.wait_for_load_state('domcontentloaded', timeout=2000)

        if page.url != pre_url:
            # Real navigation: page URL changed.
            # domcontentloaded fires before JS frameworks render form elements
            # (e.g. Google Signup, React apps). Wait for interactive elements.
            with suppress(Exception):
                await page.wait_for_function(
                    '''() => {
                        const els = document.querySelectorAll(
                            'input:not([type=hidden]), textarea, select, '
                            + '[role="combobox"], [role="listbox"], '
                            + '[contenteditable="true"]'
                        );
                        return els.length > 0;
                    }''',
                    timeout=5000,
                )
            # Brief extra wait for late-rendering elements (animations, lazy fields)
            await page.wait_for_timeout(300)
        else:
            # SPA navigation: URL didn't change, wait for DOM to stabilize
            with suppress(Exception):
                await page.wait_for_function(
                    '''() => {
                        const els = document.querySelectorAll(
                            'select, [role="combobox"], [role="listbox"], input:not([type=hidden]), button'
                        );
                        return els.length > 0;
                    }''',
                    timeout=3000,
                )
            # Extra brief wait for SPA animations to finish
            await page.wait_for_timeout(500)

        # Post-click: refresh hints on the (potentially new) page
        import logging as _logging
        _click_log = _logging.getLogger(__name__)
        nav_happened = page.url != pre_url
        _click_log.info("[CLICK] post-action: nav=%s, pre=%s, now=%s", nav_happened, pre_url[:80], page.url[:80])
        await browser.invalidate_hints()
        hints = await browser.get_hints(force=True)
        _click_log.info("[CLICK] post-hints: inputs=%d, buttons=%d", len(hints.get('inputs', [])), len(hints.get('buttons', [])))
        browser._snapshot_since_nav = True
        if hints.get('text'):
            result["_page_hint"] = hints["text"][:800]
        for key in ('inputs', 'checkboxes', 'radios', 'switches', 'buttons', 'links', 'selects', 'file_inputs'):
            if hints.get(key):
                result[key] = hints[key]
        result["url"] = page.url
        return result
