"""
Assert Equal Module

Assert that two values are equal.
"""

from typing import Any

from ...base import BaseModule
from ...registry import register_module


@register_module(
    module_id='test.assert_equal',
    version='1.0.0',
    category='testing',
    tags=['testing', 'assertion', 'validation'],
    label='Assert Equal',
    description='Assert that two values are equal',
    icon='CheckCircle',
    color='#22C55E',
    params_schema={
        'actual': {
            'type': ['string', 'number', 'boolean', 'object', 'array'],
            'required': True,
            'description': 'Actual value'
        },
        'expected': {
            'type': ['string', 'number', 'boolean', 'object', 'array'],
            'required': True,
            'description': 'Expected value'
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
            'type': ['string', 'number', 'boolean', 'object', 'array'],
            'description': 'Actual value received'
        },
        'expected': {
            'type': ['string', 'number', 'boolean', 'object', 'array'],
            'description': 'Expected value'
        },
        'message': {
            'type': 'string',
            'description': 'Result message'
        }
    }
)
class AssertEqualModule(BaseModule):
    """Assert that two values are equal."""

    module_name = "Assert Equal"
    module_description = "Assert that two values are equal"

    def validate_params(self):
        if 'actual' not in self.params:
            raise ValueError("Parameter 'actual' is required")
        if 'expected' not in self.params:
            raise ValueError("Parameter 'expected' is required")

    async def execute(self) -> Any:
        actual = self.params.get('actual')
        expected = self.params.get('expected')
        custom_message = self.params.get('message')

        passed = actual == expected

        if passed:
            message = custom_message or f"Assertion passed: {actual} == {expected}"
        else:
            message = custom_message or f"Assertion failed: expected {expected}, got {actual}"

        result = {
            'passed': passed,
            'actual': actual,
            'expected': expected,
            'message': message
        }

        if not passed:
            raise AssertionError(message)

        return result
