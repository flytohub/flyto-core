"""
Assert Greater Than Module

Assert that a value is greater than another.
"""

from typing import Any

from ...base import BaseModule
from ...registry import register_module


@register_module(
    module_id='test.assert_greater_than',
    version='1.0.0',
    category='testing',
    tags=['testing', 'assertion', 'validation'],
    label='Assert Greater Than',
    description='Assert that a value is greater than another',
    icon='CheckCircle',
    color='#22C55E',
    params_schema={
        'actual': {
            'type': 'number',
            'required': True,
            'description': 'Actual value'
        },
        'threshold': {
            'type': 'number',
            'required': True,
            'description': 'Threshold value'
        },
        'message': {
            'type': 'string',
            'required': False,
            'description': 'Custom error message'
        }
    },
    output_schema={
        'passed': {
            'type': 'boolean',
            'description': 'Whether assertion passed'
        },
        'actual': {
            'type': 'number',
            'description': 'Actual value'
        },
        'threshold': {
            'type': 'number',
            'description': 'Threshold value'
        },
        'message': {
            'type': 'string',
            'description': 'Result message'
        }
    }
)
class AssertGreaterThanModule(BaseModule):
    """Assert that a value is greater than another."""

    module_name = "Assert Greater Than"
    module_description = "Assert that a value is greater than another"

    def validate_params(self):
        if 'actual' not in self.params:
            raise ValueError("Parameter 'actual' is required")
        if 'threshold' not in self.params:
            raise ValueError("Parameter 'threshold' is required")

    async def execute(self) -> Any:
        actual = self.params.get('actual')
        threshold = self.params.get('threshold')
        custom_message = self.params.get('message')

        passed = actual > threshold

        if passed:
            message = custom_message or f"Assertion passed: {actual} > {threshold}"
        else:
            message = custom_message or f"Assertion failed: {actual} <= {threshold}"

        result = {
            'passed': passed,
            'actual': actual,
            'threshold': threshold,
            'message': message
        }

        if not passed:
            raise AssertionError(message)

        return result
