# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Interact Module — Human-in-the-loop browser interaction

Snapshots the current page, extracts interactive elements with positions,
presents them to the user via a breakpoint dialog, then executes the
user's chosen action (click/select/type) on the actual page.
"""
import base64
import logging
from datetime import datetime
from typing import Any, Dict

from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets
from ...types import NodeType, EdgeType, DataType

logger = logging.getLogger(__name__)


@register_module(
    module_id='browser.interact',
    version='1.0.0',
    category='browser',
    tags=['browser', 'interaction', 'human', 'breakpoint', 'hitl', 'pause'],
    label='Browser Interact',
    label_key='modules.browser.interact.label',
    description='Pause for user to interact with the browser page. Shows page elements in a dialog for the user to choose an action.',
    description_key='modules.browser.interact.description',
    icon='MousePointerClick',
    color='#8B5CF6',

    input_types=['page'],
    output_types=['control'],

    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'flow.*', 'data.*', 'ai.*', 'llm.*'],

    node_type=NodeType.BREAKPOINT,

    input_ports=[
        {
            'id': 'input',
            'label': 'Input',
            'label_key': 'modules.browser.interact.ports.input',
            'max_connections': 1,
            'required': True,
            'data_type': DataType.ANY.value,
            'edge_type': EdgeType.CONTROL.value,
        }
    ],
    output_ports=[
        {
            'id': 'approved',
            'label': 'Action Executed',
            'label_key': 'modules.browser.interact.ports.approved',
            'event': 'approved',
            'color': '#10B981',
            'edge_type': EdgeType.CONTROL.value,
        },
        {
            'id': 'rejected',
            'label': 'Skipped',
            'label_key': 'modules.browser.interact.ports.rejected',
            'event': 'rejected',
            'color': '#EF4444',
            'edge_type': EdgeType.CONTROL.value,
        },
        {
            'id': 'timeout',
            'label': 'Timeout',
            'label_key': 'modules.browser.interact.ports.timeout',
            'event': 'timeout',
            'color': '#F59E0B',
            'edge_type': EdgeType.CONTROL.value,
        },
    ],

    retryable=False,
    concurrent_safe=True,
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['browser.automation'],

    params_schema=compose(
        presets.APPROVAL_TITLE(default='Browser Interaction'),
        presets.DESCRIPTION(multiline=True),
        presets.TIMEOUT_SECONDS(default=0),
    ),
    output_schema={
        'status': {
            'type': 'string',
            'description': 'Operation status',
            'description_key': 'modules.browser.interact.output.status.description',
        },
        'action': {
            'type': 'string',
            'description': 'Action executed (click/select/type/toggle)',
            'description_key': 'modules.browser.interact.output.action.description',
        },
        'selector': {
            'type': 'string',
            'description': 'CSS selector of the interacted element',
            'description_key': 'modules.browser.interact.output.selector.description',
        },
        'value': {
            'type': 'string',
            'description': 'Value used (for select/type actions)',
            'description_key': 'modules.browser.interact.output.value.description',
        },
        'url': {
            'type': 'string',
            'description': 'Page URL at time of interaction',
            'description_key': 'modules.browser.interact.output.url.description',
        },
    },
    examples=[
        {
            'name': 'Interactive page navigation',
            'description': 'Let user choose which link to click',
            'params': {
                'title': 'Choose a department',
                'description': 'Select the department you want to register for',
            },
        },
    ],
    author='Flyto Team',
    license='MIT',
    timeout_ms=0,  # No module-level timeout — waits indefinitely for user interaction
)
class BrowserInteractModule(BaseModule):
    """
    Browser Interact Module

    Human-in-the-loop node that:
    1. Snapshots the page and extracts interactive elements with positions
    2. Takes a screenshot for preview
    3. Pauses execution via breakpoint, sending hints + screenshot to the UI
    4. User selects an element and action in the dialog
    5. Executes the chosen action on the browser page
    6. Returns result and continues workflow
    """

    module_name = "Browser Interact"
    module_description = "Pause for user to interact with browser page"

    def validate_params(self) -> None:
        self.title = self.get_param('title', 'Browser Interaction')
        self.description_text = self.get_param('description', '')
        self.timeout_seconds = self.get_param('timeout_seconds', 0)

    async def execute(self) -> Dict[str, Any]:
        start_time = datetime.utcnow()

        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        page = browser.page

        # 1. Extract hints with positions
        hints = await browser.get_hints(force=True)

        # 2. Take screenshot (JPEG for smaller size)
        screenshot_b64 = ''
        screenshot_url = ''
        screenshot_raw = b''
        try:
            screenshot_raw = await page.screenshot(type='jpeg', quality=60)
            screenshot_b64 = base64.b64encode(screenshot_raw).decode('ascii')
        except Exception as e:
            logger.debug("Failed to take screenshot for interact: %s", e)

        # 2b. Upload screenshot if uploader is configured (cloud mode)
        if screenshot_raw:
            try:
                from ....engine.breakpoints.screenshot import get_screenshot_uploader
                uploader = get_screenshot_uploader()
                if uploader:
                    bp_id = f"interact_{self.context.get('execution_id', 'unknown')}_{self.context.get('step_id', 'unknown')}"
                    screenshot_url = await uploader.upload(screenshot_raw, bp_id)
                    if screenshot_url:
                        # Clear base64 to save bandwidth in cloud mode
                        screenshot_b64 = ''
            except Exception as e:
                logger.debug("Screenshot upload failed, using base64: %s", e)

        # 3. Build context snapshot for the interact dialog
        page_url = page.url
        context_snapshot = {
            '_interact': True,
            'url': page_url,
            'screenshot_base64': screenshot_b64,
            'screenshot_url': screenshot_url,
            'screenshot_media_type': 'image/jpeg',
            'elements': hints.get('elements', []),
            'inputs': hints.get('inputs', []),
            'buttons': hints.get('buttons', []),
            'links': hints.get('links', []),
            'selects': hints.get('selects', []),
            'checkboxes': hints.get('checkboxes', []),
            'radios': hints.get('radios', []),
            'switches': hints.get('switches', []),
        }

        # 4. Create breakpoint and wait for user response
        from ....engine.breakpoints import (
            get_breakpoint_manager,
            ApprovalMode,
        )

        manager = get_breakpoint_manager()

        custom_fields = [
            {'name': 'action', 'type': 'string', 'required': True,
             'label': 'Action', 'description': 'click, type, select, or toggle'},
            {'name': 'selector', 'type': 'string', 'required': True,
             'label': 'Selector', 'description': 'CSS selector of the target element'},
            {'name': 'value', 'type': 'string', 'required': False,
             'label': 'Value', 'description': 'Value for type/select actions'},
        ]

        request = await manager.create_breakpoint(
            execution_id=self.context.get('execution_id', 'unknown'),
            step_id=self.context.get('step_id', 'unknown'),
            workflow_id=self.context.get('workflow_id'),
            title=self.title,
            description=self.description_text,
            required_approvers=[],
            approval_mode=ApprovalMode.FIRST,
            timeout_seconds=self.timeout_seconds if self.timeout_seconds > 0 else None,
            context_snapshot=context_snapshot,
            custom_fields=custom_fields,
            metadata={
                'step_name': self.context.get('step_name'),
                'workflow_name': self.context.get('workflow_name'),
                'interact': True,
            },
        )

        result = await manager.wait_for_resolution(
            request.breakpoint_id,
            check_timeout=True,
        )

        end_time = datetime.utcnow()
        wait_ms = int((end_time - start_time).total_seconds() * 1000)

        # 5. Handle resolution
        from ....engine.breakpoints import BreakpointStatus

        if result.status == BreakpointStatus.APPROVED:
            # Execute the user's chosen action (validated)
            action = result.final_inputs.get('action', 'click')
            selector = result.final_inputs.get('selector', '')
            value = str(result.final_inputs.get('value', ''))[:5000]  # cap length

            _ALLOWED_ACTIONS = {'click', 'type', 'select', 'toggle'}
            if action not in _ALLOWED_ACTIONS:
                raise RuntimeError(f"Invalid action '{action}'. Allowed: {_ALLOWED_ACTIONS}")

            if not selector or len(selector) > 500:
                raise RuntimeError("Invalid selector (empty or too long)")

            # Reject selectors with suspicious patterns (JS injection attempts)
            import re
            if re.search(r'[{}<>]|javascript:|eval\(|Function\(', selector):
                raise RuntimeError("Selector contains disallowed characters")

            try:
                action_result = await self._execute_action(page, browser, action, selector, value)
            except Exception as e:
                logger.warning("browser.interact action failed: %s %s → %s", action, selector, e)
                action_result = {'action_status': 'error', 'error': str(e)}

            output_data = {
                'status': 'success',
                'action': action,
                'selector': selector,
                'value': value,
                'url': page_url,
                'wait_duration_ms': wait_ms,
                **action_result,
            }

            # Refresh hints after action (page may have changed)
            browser._snapshot_since_nav = True
            new_hints = await browser.get_hints(force=True) or {}
            for key in ('inputs', 'checkboxes', 'radios', 'switches', 'buttons', 'links', 'selects', 'elements'):
                if new_hints.get(key):
                    output_data[key] = new_hints[key]

            return {
                '__event__': 'approved',
                'outputs': {'approved': output_data},
                **output_data,
            }

        else:
            # Rejected or timeout
            status_to_event = {
                BreakpointStatus.REJECTED: 'rejected',
                BreakpointStatus.TIMEOUT: 'timeout',
                BreakpointStatus.CANCELLED: 'rejected',
            }
            event = status_to_event.get(result.status, 'rejected')

            output_data = {
                'status': result.status.value,
                'action': '',
                'selector': '',
                'value': '',
                'url': page_url,
                'wait_duration_ms': wait_ms,
            }

            return {
                '__event__': event,
                'outputs': {event: output_data},
                **output_data,
            }

    async def _execute_action(
        self, page, browser, action: str, selector: str, value: str
    ) -> Dict[str, Any]:
        """Execute the user's chosen action on the browser page."""
        if action == 'click':
            await page.click(selector, timeout=10000)
            return {'action_status': 'clicked'}

        elif action == 'type':
            if not value:
                raise RuntimeError("Value is required for type action")
            await page.fill(selector, value, timeout=10000)
            return {'action_status': 'typed', 'typed_value': value}

        elif action == 'select':
            if not value:
                raise RuntimeError("Value is required for select action")
            # Try native select first, fall back to click-based
            try:
                is_native = await page.locator(selector).evaluate(
                    'el => el.tagName === "SELECT"'
                )
            except Exception:
                is_native = False

            if is_native:
                await page.select_option(selector, value=value, timeout=10000)
            else:
                # Custom dropdown: click trigger, then click option
                await page.click(selector, timeout=10000)
                await page.wait_for_timeout(300)
                # value is the option selector for custom dropdowns
                await page.click(value, timeout=5000)
            return {'action_status': 'selected', 'selected_value': value}

        elif action == 'toggle':
            await page.click(selector, timeout=10000)
            return {'action_status': 'toggled'}

        else:
            raise RuntimeError("Unknown action: %s" % action)
