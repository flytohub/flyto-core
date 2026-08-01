# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
UI Review Composite Module

Visual regression testing and UI review workflow.
"""
from ..base import CompositeModule, register_composite


@register_composite(
    module_id='composite.test.ui_review',
    label='UI Review',
    label_key='modules.composite.test.ui_review.label',
    description='Visual regression testing and UI review workflow',
    description_key='modules.composite.test.ui_review.description',
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
            # Continue only so the browser.close cleanup step always runs;
            # _build_output treats every missing/failed comparison as failed.
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
            'label': 'Allowed Difference Ratio (0-1)',
            'default': 0.001
        }
    },

    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)'},
        'diff_percentage': {'type': 'number', 'description': 'The diff percentage'},
        'passed': {'type': 'boolean', 'description': 'Number of tests passed'},
        'screenshot': {'type': 'string', 'description': 'Screenshot file path or data'}
    },

    timeout=120,
    retryable=False,
)
class UIReview(CompositeModule):
    """UI Review - visual regression testing"""

    def _build_output(self, metadata):
        screenshot = self.step_results.get('screenshot', {})
        compare = self.step_results.get('compare', {})
        compare_ok = compare.get('ok') is True
        diff = compare.get('difference')
        threshold = self.params.get('diff_threshold', 0.001)
        passed = compare_ok and isinstance(diff, (int, float)) and diff <= threshold

        return {
            'status': 'passed' if passed else 'failed',
            'diff_percentage': compare.get('diff_percentage'),
            'passed': passed,
            'screenshot': screenshot.get('path', ''),
            'comparison': compare,
        }
