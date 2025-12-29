"""
Assert Length Module

Assert that a collection has expected length.
"""

from typing import Any

from ...base import BaseModule
from ...registry import register_module


@register_module(
    module_id='test.assert_length',
    version='1.0.0',
    category='testing',
    tags=['testing', 'assertion', 'validation'],
    label='Assert Length',
    description='Assert that a collection has expected length',
    icon='CheckCircle',
    color='#22C55E',
    params_schema={
        'collection': {
            'type': ['array', 'string'],
            'required': True,
            'description': 'Collection to check'
        },
        'expected_length': {
            'type': 'number',
            'required': True,
            'description': 'Expected length'
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
        'actual_length': {
            'type': 'number',
            'description': 'Actual length'
        },
        'expected_length': {
            'type': 'number',
            'description': 'Expected length'
        },
        'message': {
            'type': 'string',
            'description': 'Result message'
        }
    }
)
class AssertLengthModule(BaseModule):
    """Assert that a collection has expected length."""

    module_name = "Assert Length"
    module_description = "Assert that a collection has expected length"

    def validate_params(self):
        if 'collection' not in self.params:
            raise ValueError("Parameter 'collection' is required")
        if 'expected_length' not in self.params:
            raise ValueError("Parameter 'expected_length' is required")

    async def execute(self) -> Any:
        collection = self.params.get('collection')
        expected_length = self.params.get('expected_length')
        custom_message = self.params.get('message')

        actual_length = len(collection)
        passed = actual_length == expected_length

        if passed:
            message = custom_message or f"Assertion passed: length is {actual_length}"
        else:
            message = custom_message or f"Assertion failed: expected length {expected_length}, got {actual_length}"

        result = {
            'passed': passed,
            'actual_length': actual_length,
            'expected_length': expected_length,
            'message': message
        }

        if not passed:
            raise AssertionError(message)

        return result
