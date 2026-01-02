"""
Quality Gate Composite Module

Runs quality checks and gates deployments.
"""
from ..base import CompositeModule, register_composite


@register_composite(
    module_id='composite.test.quality_gate',
    label='Quality Gate',
    icon='Shield',
    color='#10B981',

    steps=[
        {
            'id': 'lint',
            'module': 'testing.lint.run',
            'params': {
                'path': '${params.source_path}',
                'config': '${params.lint_config}'
            },
            'on_error': 'continue'
        },
        {
            'id': 'test',
            'module': 'testing.unit.run',
            'params': {
                'path': '${params.test_path}',
                'coverage': '${params.check_coverage}'
            },
            'on_error': 'continue'
        },
        {
            'id': 'security',
            'module': 'testing.security.scan',
            'params': {'path': '${params.source_path}'},
            'on_error': 'continue'
        },
        {
            'id': 'evaluate',
            'module': 'testing.gate.evaluate',
            'params': {
                'lint_result': '${steps.lint}',
                'test_result': '${steps.test}',
                'security_result': '${steps.security}',
                'thresholds': '${params.thresholds}'
            }
        }
    ],

    params_schema={
        'source_path': {
            'type': 'string',
            'label': 'Source Path',
            'required': True,
            'default': './src'
        },
        'test_path': {
            'type': 'string',
            'label': 'Test Path',
            'default': './tests'
        },
        'lint_config': {
            'type': 'string',
            'label': 'Lint Config',
            'placeholder': '.eslintrc.json'
        },
        'check_coverage': {
            'type': 'boolean',
            'label': 'Check Coverage',
            'default': True
        },
        'thresholds': {
            'type': 'object',
            'label': 'Quality Thresholds',
            'default': {
                'coverage': 80,
                'lint_errors': 0,
                'security_high': 0
            }
        }
    },

    output_schema={
        'status': {'type': 'string'},
        'passed': {'type': 'boolean'},
        'checks': {'type': 'object'}
    },

    timeout=300,
    retryable=False,
)
class QualityGate(CompositeModule):
    """Quality Gate - lint, test, security checks before deploy"""

    def _build_output(self, metadata):
        lint = self.step_results.get('lint', {})
        test = self.step_results.get('test', {})
        security = self.step_results.get('security', {})
        evaluate = self.step_results.get('evaluate', {})

        return {
            'status': 'passed' if evaluate.get('passed') else 'failed',
            'passed': evaluate.get('passed', False),
            'checks': {
                'lint': lint.get('passed', False),
                'test': test.get('passed', False),
                'security': security.get('passed', False)
            }
        }
