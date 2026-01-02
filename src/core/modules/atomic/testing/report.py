"""
Test Report Generator Module

Generate test execution reports.
"""

import logging
from typing import Any, Dict

from ...registry import register_module

logger = logging.getLogger(__name__)


@register_module(
    module_id='testing.report.generate',
    version='1.0.0',
    category='atomic',
    subcategory='testing',
    tags=['testing', 'report', 'documentation', 'atomic'],
    label='Generate Report',
    description='Generate test execution report',
    icon='FileText',
    color='#6366F1',

    input_types=['object', 'array'],
    output_types=['object', 'string'],
    can_receive_from=['testing.*', 'data.*', 'flow.*'],
    can_connect_to=['notification.*', 'file.*', 'data.*', 'flow.*', 'end'],

    timeout=60,
    retryable=False,

    params_schema={
        'results': {
            'type': 'object',
            'label': 'Test Results',
            'required': True
        },
        'format': {
            'type': 'string',
            'label': 'Report Format',
            'default': 'json',
            'options': ['json', 'html', 'markdown', 'junit']
        },
        'title': {
            'type': 'string',
            'label': 'Report Title',
            'default': 'Test Report'
        }
    },
    output_schema={
        'ok': {'type': 'boolean'},
        'report': {'type': 'string'},
        'format': {'type': 'string'},
        'summary': {'type': 'object'}
    }
)
async def testing_report_generate(context: Dict[str, Any]) -> Dict[str, Any]:
    """Generate test report"""
    import json

    params = context['params']
    results = params.get('results', {})
    format_type = params.get('format', 'json')
    title = params.get('title', 'Test Report')

    summary = {
        'title': title,
        'total': results.get('total', 0),
        'passed': results.get('passed', 0),
        'failed': results.get('failed', 0)
    }

    if format_type == 'json':
        report = json.dumps({'title': title, 'results': results}, indent=2)
    elif format_type == 'markdown':
        report = f"# {title}\n\n"
        report += f"- Total: {summary['total']}\n"
        report += f"- Passed: {summary['passed']}\n"
        report += f"- Failed: {summary['failed']}\n"
    else:
        report = json.dumps(results)

    return {
        'ok': True,
        'report': report,
        'format': format_type,
        'summary': summary
    }
