"""
Browser Trace Module - Performance tracing using CDP

Provides Chrome DevTools Protocol-level performance tracing.
Uses Playwright's browser.start_tracing() and browser.stop_tracing().

Note: This module only works with Chromium browsers.
"""
from typing import Any, Dict, List, Optional
from pathlib import Path
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field, presets


@register_module(
    module_id='browser.trace',
    version='1.0.0',
    category='browser',
    tags=['browser', 'performance', 'debug', 'trace', 'cdp', 'chromium'],
    label='Performance Trace',
    label_key='modules.browser.trace.label',
    description='Start/stop Chrome DevTools performance tracing (Chromium only)',
    description_key='modules.browser.trace.description',
    icon='Activity',
    color='#F97316',

    # Connection types
    input_types=['page'],
    output_types=['json', 'file'],

    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'flow.*'],

    params_schema=compose(
        field(
            'action',
            type='string',
            label='Action',
            label_key='modules.browser.trace.params.action.label',
            description='Start or stop tracing',
            required=True,
            options=[
                {'value': 'start', 'label': 'Start Tracing'},
                {'value': 'stop', 'label': 'Stop Tracing'},
            ],
        ),
        field(
            'categories',
            type='array',
            label='Trace Categories',
            label_key='modules.browser.trace.params.categories.label',
            description='CDP trace categories (default: devtools.timeline)',
            required=False,
            default=['devtools.timeline'],
        ),
        field(
            'screenshots',
            type='boolean',
            label='Capture Screenshots',
            label_key='modules.browser.trace.params.screenshots.label',
            description='Include screenshots in trace (increases file size)',
            required=False,
            default=True,
        ),
        presets.OUTPUT_PATH(
            key='path',
            placeholder='/tmp/trace.json',
            label='Output Path',
            required=False,
        ),
    ),
    output_schema={
        'status': {
            'type': 'string',
            'description': 'Operation status (success/error)',
            'description_key': 'modules.browser.trace.output.status.description'
        },
        'tracing': {
            'type': 'boolean',
            'description': 'Whether tracing is active',
            'description_key': 'modules.browser.trace.output.tracing.description'
        },
        'path': {
            'type': 'string',
            'description': 'Path to trace file (when stopped)',
            'description_key': 'modules.browser.trace.output.path.description'
        },
        'size_bytes': {
            'type': 'number',
            'description': 'Trace file size in bytes',
            'description_key': 'modules.browser.trace.output.size_bytes.description'
        },
    },
    examples=[
        {
            'name': 'Start tracing with screenshots',
            'params': {'action': 'start', 'screenshots': True}
        },
        {
            'name': 'Start tracing specific categories',
            'params': {
                'action': 'start',
                'categories': ['devtools.timeline', 'v8.execute'],
                'screenshots': False
            }
        },
        {
            'name': 'Stop tracing and save',
            'params': {'action': 'stop', 'path': '/tmp/performance-trace.json'}
        }
    ],
    author='Flyto Team',
    license='MIT',
    timeout_ms=60000,
    required_permissions=['browser.automation'],
)
class BrowserTraceModule(BaseModule):
    """Performance Trace Module using Chrome DevTools Protocol"""

    module_name = "Performance Trace"
    module_description = "Start/stop Chrome DevTools performance tracing"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        if 'action' not in self.params:
            raise ValueError("Missing required parameter: action")

        self.action = self.params['action']
        if self.action not in ['start', 'stop']:
            raise ValueError(f"Invalid action: {self.action}. Must be 'start' or 'stop'")

        self.categories = self.params.get('categories', ['devtools.timeline'])
        self.screenshots = self.params.get('screenshots', True)
        self.output_path = self.params.get('path', '')

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        # Check if browser is Chromium
        if browser.browser_type != 'chromium':
            return {
                "status": "error",
                "error": f"Tracing only supported on Chromium, got: {browser.browser_type}",
                "error_code": "CHROMIUM_ONLY"
            }

        if self.action == 'start':
            return await self._start_tracing(browser)
        else:
            return await self._stop_tracing(browser)

    async def _start_tracing(self, browser) -> Dict[str, Any]:
        """Start performance tracing"""
        # Check if already tracing
        if self.context.get('_tracing_active'):
            return {
                "status": "error",
                "error": "Tracing already active. Stop current trace before starting new one.",
                "error_code": "TRACING_ACTIVE"
            }

        try:
            # Start tracing on the browser context
            # Note: Playwright's start_tracing is on the browser, not context
            await browser._browser.start_tracing(
                page=browser.page,
                screenshots=self.screenshots,
                categories=self.categories if self.categories else None
            )

            # Mark tracing as active in context
            self.context['_tracing_active'] = True
            self.context['_tracing_categories'] = self.categories
            self.context['_tracing_screenshots'] = self.screenshots

            return {
                "status": "success",
                "tracing": True,
                "categories": self.categories,
                "screenshots": self.screenshots,
                "message": "Performance tracing started"
            }

        except Exception as e:
            error_msg = str(e)
            if 'Target is not attached to CDP' in error_msg or 'Protocol error' in error_msg:
                return {
                    "status": "error",
                    "error": "CDP tracing not available. Ensure browser is Chromium.",
                    "error_code": "CDP_UNAVAILABLE"
                }
            raise

    async def _stop_tracing(self, browser) -> Dict[str, Any]:
        """Stop performance tracing and optionally save to file"""
        # Check if tracing is active
        if not self.context.get('_tracing_active'):
            return {
                "status": "error",
                "error": "No active trace. Start tracing first.",
                "error_code": "NO_ACTIVE_TRACE"
            }

        try:
            # Stop tracing - returns trace data as bytes
            trace_data = await browser._browser.stop_tracing()

            # Clear tracing state
            self.context['_tracing_active'] = False

            result = {
                "status": "success",
                "tracing": False,
                "size_bytes": len(trace_data) if trace_data else 0,
            }

            # Save to file if path provided
            if self.output_path:
                path = Path(self.output_path)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(trace_data)
                result["path"] = str(path.absolute())
                result["message"] = f"Trace saved to {result['path']}"
            else:
                # Return base64 encoded if no path
                import base64
                result["trace_base64"] = base64.b64encode(trace_data).decode('utf-8')
                result["message"] = "Trace data returned as base64"

            return result

        except Exception as e:
            # Reset state on error
            self.context['_tracing_active'] = False
            raise
