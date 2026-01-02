"""
UI Review Composite Module

Visual regression testing and UI review workflow.
"""
from ..base import CompositeModule, register_composite


@register_composite(
    module_id='composite.test.ui_review',
    label='UI Review',
    icon='Eye',
    color='#F59E0B',

    steps=[
        {
            'id': 'launch',
            'module': 'browser.launch',
            'params': {'headless': True}
        },
        {
            'id': 'navigate',
            'module': 'browser.goto',
            'params': {'url': '${params.url}'}
        },
        {
            'id': 'screenshot',
            'module': 'browser.screenshot',
            'params': {'path': '${params.screenshot_path}'}
        },
        {
            'id': 'compare',
            'module': 'testing.visual.compare',
            'params': {
                'actual': '${steps.screenshot.path}',
                'expected': '${params.baseline_path}',
                'threshold': '${params.diff_threshold}'
            },
            'on_error': 'continue'
        },
        {
            'id': 'close',
            'module': 'browser.close',
            'params': {}
        }
    ],

    params_schema={
        'url': {
            'type': 'string',
            'label': 'URL to Review',
            'required': True,
            'placeholder': 'http://localhost:3000'
        },
        'screenshot_path': {
            'type': 'string',
            'label': 'Screenshot Path',
            'default': './screenshots/current.png'
        },
        'baseline_path': {
            'type': 'string',
            'label': 'Baseline Path',
            'default': './screenshots/baseline.png'
        },
        'diff_threshold': {
            'type': 'number',
            'label': 'Diff Threshold (%)',
            'default': 0.1
        }
    },

    output_schema={
        'status': {'type': 'string'},
        'diff_percentage': {'type': 'number'},
        'passed': {'type': 'boolean'},
        'screenshot': {'type': 'string'}
    },

    timeout=120,
    retryable=False,
)
class UIReview(CompositeModule):
    """UI Review - visual regression testing"""

    def _build_output(self, metadata):
        screenshot = self.step_results.get('screenshot', {})
        compare = self.step_results.get('compare', {})
        diff = compare.get('diff_percentage', 0)
        threshold = self.params.get('diff_threshold', 0.1)

        return {
            'status': 'passed' if diff <= threshold else 'failed',
            'diff_percentage': diff,
            'passed': diff <= threshold,
            'screenshot': screenshot.get('path', '')
        }
