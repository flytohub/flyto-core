"""
Verify Fix Composite Module

Verifies bug fixes with before/after testing.
"""
from ..base import CompositeModule, register_composite


@register_composite(
    module_id='composite.test.verify_fix',
    label='Verify Fix',
    icon='CheckCircle',
    color='#22C55E',

    steps=[
        {
            'id': 'run_repro',
            'module': 'testing.scenario.run',
            'params': {
                'steps': '${params.repro_steps}',
                'expect_fail': False
            }
        },
        {
            'id': 'run_regression',
            'module': 'testing.suite.run',
            'params': {
                'path': '${params.regression_tests}',
                'filter': '${params.test_filter}'
            },
            'on_error': 'continue'
        },
        {
            'id': 'notify',
            'module': 'notification.slack.send_message',
            'params': {
                'webhook_url': '${params.slack_webhook}',
                'text': 'Fix Verification: ${steps.run_repro.status}'
            },
            'on_error': 'continue'
        }
    ],

    params_schema={
        'repro_steps': {
            'type': 'array',
            'label': 'Reproduction Steps',
            'required': True,
            'description': 'Steps to verify the fix works'
        },
        'regression_tests': {
            'type': 'string',
            'label': 'Regression Tests Path',
            'default': './tests/regression'
        },
        'test_filter': {
            'type': 'string',
            'label': 'Test Filter',
            'placeholder': '**/test_*.py'
        },
        'slack_webhook': {
            'type': 'string',
            'label': 'Slack Webhook',
            'placeholder': '${env.SLACK_WEBHOOK_URL}'
        }
    },

    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)'},
        'fix_verified': {'type': 'boolean', 'description': 'The fix verified'},
        'regression_passed': {'type': 'boolean', 'description': 'The regression passed'}
    },

    timeout=300,
    retryable=False,
)
class VerifyFix(CompositeModule):
    """Verify Fix - confirm bug fix with regression tests"""

    def _build_output(self, metadata):
        repro = self.step_results.get('run_repro', {})
        regression = self.step_results.get('run_regression', {})

        fix_verified = repro.get('passed', False)
        regression_passed = regression.get('passed', True)

        return {
            'status': 'verified' if fix_verified and regression_passed else 'failed',
            'fix_verified': fix_verified,
            'regression_passed': regression_passed
        }
