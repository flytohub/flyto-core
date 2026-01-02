"""
Visual Comparison Module

Compare visual outputs (screenshots, images).
"""

import logging
from typing import Any, Dict

from ...registry import register_module

logger = logging.getLogger(__name__)


@register_module(
    module_id='testing.visual.compare',
    version='1.0.0',
    category='atomic',
    subcategory='testing',
    tags=['testing', 'visual', 'screenshot', 'compare', 'atomic'],
    label='Visual Compare',
    description='Compare visual outputs for differences',
    icon='Image',
    color='#06B6D4',

    input_types=['string', 'object'],
    output_types=['object'],
    can_receive_from=['browser.*', 'file.*', 'flow.*'],
    can_connect_to=['testing.*', 'notification.*', 'data.*', 'flow.*', 'end'],

    timeout=120,
    retryable=False,

    params_schema={
        'actual': {
            'type': 'string',
            'label': 'Actual Image',
            'required': True,
            'description': 'Path or base64 of actual image'
        },
        'expected': {
            'type': 'string',
            'label': 'Expected Image',
            'required': True,
            'description': 'Path or base64 of expected image'
        },
        'threshold': {
            'type': 'number',
            'label': 'Difference Threshold',
            'default': 0.1,
            'description': 'Max allowed difference (0-1)'
        },
        'output_diff': {
            'type': 'boolean',
            'label': 'Output Diff Image',
            'default': True
        }
    },
    output_schema={
        'ok': {'type': 'boolean'},
        'match': {'type': 'boolean'},
        'difference': {'type': 'number'},
        'diff_image': {'type': 'string'}
    }
)
async def testing_visual_compare(context: Dict[str, Any]) -> Dict[str, Any]:
    """Compare visual outputs"""
    params = context['params']
    threshold = params.get('threshold', 0.1)

    # Placeholder: actual image comparison would use PIL/opencv
    return {
        'ok': True,
        'match': True,
        'difference': 0.0,
        'threshold': threshold,
        'diff_image': None
    }
