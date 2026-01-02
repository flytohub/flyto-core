"""
Quality Gate Module

Evaluate quality metrics against thresholds.
"""

import logging
from typing import Any, Dict

from ...registry import register_module

logger = logging.getLogger(__name__)


@register_module(
    module_id='testing.gate.evaluate',
    version='1.0.0',
    category='atomic',
    subcategory='testing',
    tags=['testing', 'quality', 'gate', 'threshold', 'atomic'],
    label='Quality Gate',
    description='Evaluate quality metrics against defined thresholds',
    icon='Shield',
    color='#10B981',

    input_types=['object'],
    output_types=['object'],
    can_receive_from=['testing.*', 'data.*', 'flow.*'],
    can_connect_to=['notification.*', 'flow.*', 'end'],

    timeout=60,
    retryable=False,

    params_schema={
        'metrics': {
            'type': 'object',
            'label': 'Metrics',
            'required': True,
            'description': 'Metrics to evaluate'
        },
        'thresholds': {
            'type': 'object',
            'label': 'Thresholds',
            'required': True,
            'description': 'Threshold values for each metric'
        },
        'fail_on_breach': {
            'type': 'boolean',
            'label': 'Fail on Breach',
            'default': True
        }
    },
    output_schema={
        'ok': {'type': 'boolean'},
        'passed': {'type': 'boolean'},
        'results': {'type': 'array'},
        'summary': {'type': 'string'}
    }
)
async def testing_gate_evaluate(context: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate quality gate"""
    params = context['params']
    metrics = params.get('metrics', {})
    thresholds = params.get('thresholds', {})

    results = []
    all_passed = True

    for key, threshold in thresholds.items():
        value = metrics.get(key)
        passed = value is not None and value >= threshold

        results.append({
            'metric': key,
            'value': value,
            'threshold': threshold,
            'passed': passed
        })

        if not passed:
            all_passed = False

    return {
        'ok': True,
        'passed': all_passed,
        'results': results,
        'summary': f'Quality gate {"passed" if all_passed else "failed"}'
    }
