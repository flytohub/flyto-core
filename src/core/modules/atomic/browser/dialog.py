"""
Browser Dialog Module

Handle alert, confirm, and prompt dialogs.
"""
from typing import Any, Dict, Optional
import asyncio
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets


@register_module(
    module_id='browser.dialog',
    version='1.0.0',
    category='browser',
    tags=['browser', 'dialog', 'alert', 'confirm', 'prompt', 'ssrf_protected'],
    label='Handle Dialog',
    label_key='modules.browser.dialog.label',
    description='Handle alert, confirm, and prompt dialogs',
    description_key='modules.browser.dialog.description',
    icon='MessageSquare',
    color='#FD7E14',

    # Connection types
    input_types=['page'],
    output_types=['object'],


    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'page.*', 'screenshot.*', 'flow.*'],    params_schema=compose(
        presets.DIALOG_ACTION(),
        presets.DIALOG_PROMPT_TEXT(),
        presets.TIMEOUT_MS(default=30000),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.browser.dialog.output.status.description'},
        'message': {'type': 'string', 'description': 'Result message describing the outcome',
                'description_key': 'modules.browser.dialog.output.message.description'},
        'type': {'type': 'string', 'description': 'The type',
                'description_key': 'modules.browser.dialog.output.type.description'},
        'default_value': {'type': 'string', 'description': 'The default value',
                'description_key': 'modules.browser.dialog.output.default_value.description'}
    },
    examples=[
        {
            'name': 'Accept alert',
            'params': {'action': 'accept'}
        },
        {
            'name': 'Dismiss confirm dialog',
            'params': {'action': 'dismiss'}
        },
        {
            'name': 'Accept prompt with text',
            'params': {'action': 'accept', 'prompt_text': 'Hello World'}
        },
        {
            'name': 'Listen for dialogs',
            'params': {'action': 'listen', 'timeout': 5000}
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=30000,
    required_permissions=["browser.automation"],
)
class BrowserDialogModule(BaseModule):
    """Handle Dialog Module"""

    module_name = "Handle Dialog"
    module_description = "Handle alert, confirm, and prompt dialogs"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        if 'action' not in self.params:
            raise ValueError("Missing required parameter: action")

        self.action = self.params['action']
        if self.action not in ['accept', 'dismiss', 'listen']:
            raise ValueError(f"Invalid action: {self.action}")

        self.prompt_text = self.params.get('prompt_text')
        self.timeout = self.params.get('timeout', 30000)

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        page = browser.page
        dialog_info = {'appeared': False, 'message': None, 'type': None, 'default_value': None}

        async def handle_dialog(dialog):
            dialog_info['appeared'] = True
            dialog_info['message'] = dialog.message
            dialog_info['type'] = dialog.type
            dialog_info['default_value'] = dialog.default_value

            if self.action == 'accept':
                if self.prompt_text is not None:
                    await dialog.accept(self.prompt_text)
                else:
                    await dialog.accept()
            elif self.action == 'dismiss':
                await dialog.dismiss()
            # For 'listen', just capture info without handling

        page.on('dialog', handle_dialog)

        try:
            if self.action == 'listen':
                # Just wait and capture any dialogs
                await asyncio.sleep(self.timeout / 1000)
            else:
                # Wait for dialog to appear
                try:
                    await asyncio.wait_for(
                        self._wait_for_dialog(dialog_info),
                        timeout=self.timeout / 1000
                    )
                except asyncio.TimeoutError:
                    pass

        finally:
            page.remove_listener('dialog', handle_dialog)

        if dialog_info['appeared']:
            return {
                "status": "success",
                "message": dialog_info['message'],
                "type": dialog_info['type'],
                "default_value": dialog_info['default_value'],
                "action": self.action
            }
        else:
            return {
                "status": "success",
                "message": None,
                "type": None,
                "default_value": None,
                "action": self.action,
                "note": "No dialog appeared within timeout"
            }

    async def _wait_for_dialog(self, dialog_info: dict):
        while not dialog_info['appeared']:
            await asyncio.sleep(0.1)
