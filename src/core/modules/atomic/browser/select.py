# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Select Module

Select option from dropdown element.
"""
from typing import Any, Dict, List, Optional
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field, presets
from ...schema.constants import FieldGroup


@register_module(
    module_id='browser.select',
    version='1.1.0',
    category='browser',
    tags=['browser', 'interaction', 'select', 'dropdown', 'form', 'ssrf_protected'],
    label='Select Option',
    label_key='modules.browser.select.label',
    description='Select option from dropdown element. Run browser.snapshot first to find the correct selector from the real page DOM.',
    description_key='modules.browser.select.description',
    icon='ChevronDown',
    color='#20C997',

    # Connection types
    input_types=['page'],
    output_types=['browser', 'page'],


    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*', 'ai.*', 'llm.*'],
    params_schema=compose(
        presets.SELECTOR(required=True, placeholder='select#country', element_types=["select"]),
        field("select_method", type="select",
              label="Select by",
              label_key="modules.browser.select.param.select_method.label",
              description="How to identify which option to select",
              description_key="modules.browser.select.param.select_method.description",
              default="value",
              options=[
                  {"value": "value", "label": "By option value",
                   "label_key": "modules.browser.select.param.select_method.option.value"},
                  {"value": "label", "label": "By option text",
                   "label_key": "modules.browser.select.param.select_method.option.label"},
                  {"value": "index", "label": "By index (position)",
                   "label_key": "modules.browser.select.param.select_method.option.index"},
              ],
              group=FieldGroup.BASIC),
        field("target", type="string",
              label="Option",
              label_key="modules.browser.select.param.target.label",
              description="The option value or label text to select",
              placeholder="us",
              showIf={"select_method": {"$in": ["value", "label"]}},
              ui={"widget": "element_picker", "element_types": ["select_option"],
                  "value_key_from": "select_method",
                  "value_key_map": {
                      "value": "value",
                      "label": "text",
                  }},
              group=FieldGroup.BASIC),
        field("index", type="number",
              label="Index",
              label_key="schema.field.select_index",
              description="Option index to select (0-based)",
              placeholder="0",
              min=0, max=1000, step=1,
              showIf={"select_method": {"$in": ["index"]}},
              group=FieldGroup.BASIC),
        presets.TIMEOUT_MS(default=30000),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.browser.select.output.status.description'},
        'selected': {'type': 'array', 'description': 'The selected',
                'description_key': 'modules.browser.select.output.selected.description'},
        'selector': {'type': 'string', 'description': 'CSS selector that was used',
                'description_key': 'modules.browser.select.output.selector.description'}
    },
    examples=[
        {
            'name': 'Select by value',
            'params': {'selector': 'select#country', 'select_method': 'value', 'target': 'us'}
        },
        {
            'name': 'Select by label text',
            'params': {'selector': 'select#country', 'select_method': 'label', 'target': 'United States'}
        },
        {
            'name': 'Select by index',
            'params': {'selector': 'select#country', 'select_method': 'index', 'index': 2}
        }
    ],
    author='Flyto Team',
    license='MIT',
    timeout_ms=30000,
    required_permissions=["browser.automation"],
)
class BrowserSelectModule(BaseModule):
    """Select Option Module"""

    module_name = "Select Option"
    module_description = "Select option from dropdown"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        if 'selector' not in self.params:
            raise ValueError("Missing required parameter: selector")

        self.selector = self.params['selector']
        self.method = self.params.get('select_method', 'value')
        self.timeout = self.params.get('timeout', 30000)

        # Backward compatibility: old params with direct value/label fields
        if 'select_method' not in self.params:
            if self.params.get('value') is not None:
                self.method = 'value'
                self.target = self.params['value']
            elif self.params.get('label') is not None:
                self.method = 'label'
                self.target = self.params['label']
            elif self.params.get('index') is not None:
                self.method = 'index'
                self.target = self.params['index']
            else:
                raise ValueError("Must provide at least one of: target, value, label, or index")
            return

        if self.method == 'index':
            idx = self.params.get('index')
            if idx is None:
                raise ValueError("Index is required when select_method is 'index'")
            self.target = int(idx)
        else:
            target = self.params.get('target', '').strip()
            if not target:
                raise ValueError("Option value or label text is required")
            self.target = target

    async def _select_native(self, page) -> List[str]:
        """Select from a native <select> element using Playwright select_option().

        Auto-fallback: if the configured method (value/label) fails,
        try the other method. This handles the common case where a UI Input
        select passes a value but the node is configured for label, or vice versa.
        """
        if self.method == 'index':
            return await page.select_option(
                self.selector, index=self.target, timeout=self.timeout
            )

        # Try configured method first, fallback to the other
        primary = self.method  # 'value' or 'label'
        fallback = 'label' if primary == 'value' else 'value'

        try:
            return await page.select_option(
                self.selector, **{primary: self.target}, timeout=self.timeout
            )
        except Exception:
            # Fallback: try the other method
            return await page.select_option(
                self.selector, **{fallback: self.target}, timeout=self.timeout
            )

    async def _select_custom(self, page, browser) -> List[str]:
        """Select from a custom (non-native) dropdown via click-based interaction."""
        # Step 1: Click the trigger element to open the dropdown
        await page.click(self.selector, timeout=self.timeout)

        # Step 2: Wait for options to appear
        # First wait for DOM presence, then for visibility (handles animation delays)
        try:
            await page.wait_for_selector(
                '[role="option"], [role="menuitem"]',
                state='attached',
                timeout=3000
            )
            # Extra wait for CSS animations to complete (opacity/transform transitions)
            await page.wait_for_selector(
                '[role="option"], [role="menuitem"]',
                state='visible',
                timeout=2000
            )
        except Exception:
            # Some frameworks keep options invisible until scrolled; proceed anyway
            await page.wait_for_timeout(300)

        # Step 3: Find and click the target option
        # Use Playwright's built-in escaping via get_by_text/get_by_role to avoid CSS injection
        option = None

        async def _find_by_label(target):
            """Find option by label text."""
            loc = page.get_by_role('option', name=target)
            if await loc.count() > 0: return loc
            loc = page.get_by_role('menuitem', name=target)
            if await loc.count() > 0: return loc
            loc = page.locator('[role="option"], [role="menuitem"]').filter(has_text=target)
            if await loc.count() > 0: return loc
            loc = page.locator('[role="listbox"] li, [role="menu"] li').filter(has_text=target)
            if await loc.count() > 0: return loc
            return None

        async def _find_by_value(target):
            """Find option by value attribute."""
            escaped = target.replace('\\', '\\\\').replace('"', '\\"')
            loc = page.locator('[role="option"][data-value="{v}"], [role="menuitem"][data-value="{v}"]'.format(v=escaped))
            if await loc.count() > 0: return loc
            loc = page.locator('[role="option"][value="{v}"], [role="menuitem"][value="{v}"]'.format(v=escaped))
            if await loc.count() > 0: return loc
            loc = page.locator('[role="option"], [role="menuitem"]').filter(has_text=target)
            if await loc.count() > 0: return loc
            return None

        if self.method == 'label':
            option = await _find_by_label(self.target)
            if option is None:
                option = await _find_by_value(self.target)
        elif self.method == 'value':
            option = await _find_by_value(self.target)
            if option is None:
                option = await _find_by_label(self.target)
        elif self.method == 'index':
            option = page.locator('[role="option"]')
            if await option.count() == 0:
                option = page.locator('[role="menuitem"]')
            if await option.count() == 0:
                option = page.locator('[role="listbox"] li, [role="menu"] li')
            option = option.nth(self.target)

        if option is None or await option.count() == 0:
            raise RuntimeError(
                "Could not find option for {m}={t} in custom dropdown".format(
                    m=self.method, t=self.target
                )
            )

        # Step 4: Click the matched option
        # Some frameworks (Google Material) render options with CSS animations/transforms
        # that Playwright considers "not visible". Escalate: normal → force → dispatch_event.
        target_el = option.first
        try:
            await target_el.click(timeout=3000)
        except Exception:
            try:
                await target_el.click(force=True, timeout=3000)
            except Exception:
                # Last resort: fire click event via JS (bypasses all Playwright checks)
                await target_el.dispatch_event('click')

        # Step 5: Brief wait for dropdown to close
        await page.wait_for_timeout(200)

        return [str(self.target)]

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        page = browser.page

        # Pre-action: refresh element hints after page is confirmed ready
        await browser.get_hints(force=True)

        # Auto-detect native <select> vs custom dropdown
        # Use Playwright's own locator to resolve the element (handles CSS, XPath, text= etc.)
        try:
            is_native = await page.locator(self.selector).evaluate(
                'el => el.tagName === "SELECT"'
            )
        except Exception:
            is_native = False

        if is_native:
            selected = await self._select_native(page)
        else:
            selected = await self._select_custom(page, browser)

        kind = "native" if is_native else "custom"

        result = {
            "status": "success",
            "selected": selected,
            "selector": self.selector,
            "method": self.method,
            "kind": kind,
        }
        # Post-action: refresh hints (select may change available options)
        browser._snapshot_since_nav = True
        hints = await browser.get_hints(force=True)
        for key in ('inputs', 'checkboxes', 'radios', 'switches', 'buttons', 'links', 'selects', 'file_inputs'):
            if hints.get(key):
                result[key] = hints[key]
        return result
