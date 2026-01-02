"""
E2E Flow Test Composite Module

End-to-end workflow testing with browser automation.
"""
from ..base import CompositeModule, register_composite


@register_composite(
    module_id='composite.test.e2e_flow',
    label='E2E Flow Test',
    icon='Monitor',
    color='#8B5CF6',

    steps=[
        {
            'id': 'launch',
            'module': 'browser.launch',
            'params': {'headless': '${params.headless}'}
        },
        {
            'id': 'navigate',
            'module': 'browser.goto',
            'params': {'url': '${params.start_url}'}
        },
        {
            'id': 'run_flow',
            'module': 'testing.e2e.run_steps',
            'params': {
                'steps': '${params.test_steps}',
                'timeout': '${params.step_timeout}'
            }
        },
        {
            'id': 'screenshot',
            'module': 'browser.screenshot',
            'params': {'path': '${params.screenshot_path}'},
            'on_error': 'continue'
        },
        {
            'id': 'close',
            'module': 'browser.close',
            'params': {}
        }
    ],

    params_schema={
        'start_url': {
            'type': 'string',
            'label': 'Start URL',
            'required': True,
            'placeholder': 'http://localhost:3000'
        },
        'test_steps': {
            'type': 'array',
            'label': 'Test Steps',
            'required': True,
            'description': 'Array of E2E test steps'
        },
        'headless': {
            'type': 'boolean',
            'label': 'Headless Mode',
            'default': True
        },
        'step_timeout': {
            'type': 'number',
            'label': 'Step Timeout (ms)',
            'default': 10000
        },
        'screenshot_path': {
            'type': 'string',
            'label': 'Screenshot Path',
            'default': './screenshots/e2e-result.png'
        }
    },

    output_schema={
        'status': {'type': 'string'},
        'steps_passed': {'type': 'number'},
        'steps_failed': {'type': 'number'},
        'screenshot': {'type': 'string'}
    },

    timeout=300,
    retryable=False,
)
class E2EFlowTest(CompositeModule):
    """E2E Flow Test - browser-based end-to-end testing"""

    def _build_output(self, metadata):
        flow_result = self.step_results.get('run_flow', {})
        screenshot_result = self.step_results.get('screenshot', {})
        steps = flow_result.get('steps', [])
        passed = sum(1 for s in steps if s.get('passed'))

        return {
            'status': 'success' if passed == len(steps) else 'failed',
            'steps_passed': passed,
            'steps_failed': len(steps) - passed,
            'screenshot': screenshot_result.get('path', '')
        }
