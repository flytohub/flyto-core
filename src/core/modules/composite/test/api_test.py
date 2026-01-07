"""
API Test Suite Composite Module

Runs API tests with HTTP requests and assertions.
"""
from ..base import CompositeModule, register_composite


@register_composite(
    module_id='composite.test.api_test',
    label='API Test Suite',
    icon='Zap',
    color='#3B82F6',

    steps=[
        {
            'id': 'run_tests',
            'module': 'testing.http.run_suite',
            'params': {
                'base_url': '${params.base_url}',
                'test_cases': '${params.test_cases}',
                'timeout': '${params.timeout}',
                'headers': '${params.default_headers}'
            }
        },
        {
            'id': 'generate_report',
            'module': 'testing.report.generate',
            'params': {
                'results': '${steps.run_tests.results}',
                'format': '${params.report_format}'
            }
        },
        {
            'id': 'notify',
            'module': 'notification.slack.send_message',
            'params': {
                'webhook_url': '${params.slack_webhook}',
                'text': '${steps.generate_report.summary}'
            },
            'on_error': 'continue'
        }
    ],

    params_schema={
        'base_url': {
            'type': 'string',
            'label': 'Base URL',
            'required': True,
            'placeholder': 'http://localhost:3000/api'
        },
        'test_cases': {
            'type': 'array',
            'label': 'Test Cases',
            'required': True,
            'description': 'Array of test case definitions'
        },
        'timeout': {
            'type': 'number',
            'label': 'Timeout (ms)',
            'default': 5000
        },
        'default_headers': {
            'type': 'object',
            'label': 'Default Headers',
            'default': {}
        },
        'report_format': {
            'type': 'string',
            'label': 'Report Format',
            'default': 'markdown',
            'options': ['markdown', 'json', 'html']
        },
        'slack_webhook': {
            'type': 'string',
            'label': 'Slack Webhook',
            'placeholder': '${env.SLACK_WEBHOOK_URL}'
        }
    },

    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)'},
        'passed': {'type': 'number', 'description': 'Number of tests passed'},
        'failed': {'type': 'number', 'description': 'Number of tests failed'},
        'total': {'type': 'number', 'description': 'Total count'},
        'results': {'type': 'array', 'description': 'List of results'}
    },

    timeout=300,
    retryable=False,
)
class ApiTestSuite(CompositeModule):
    """API Test Suite - run HTTP tests with assertions"""

    def _build_output(self, metadata):
        test_results = self.step_results.get('run_tests', {})
        results = test_results.get('results', [])
        passed = sum(1 for r in results if r.get('passed'))
        failed = len(results) - passed

        return {
            'status': 'success' if failed == 0 else 'failed',
            'passed': passed,
            'failed': failed,
            'total': len(results),
            'results': results
        }
