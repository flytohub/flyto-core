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
    label_key='modules.test.assert_length.label',
    description='Assert that a collection has expected length',
    description_key='modules.test.assert_length.description',
    icon='CheckCircle',
    color='#22C55E',

    # Connection types
    input_types=['string', 'array'],
    output_types=['boolean'],


    can_receive_from=['*'],
    can_connect_to=['testing.*', 'test.*', 'flow.*', 'notification.*', 'data.*'],    params_schema={
        'collection': {
            'type': ['array', 'string'],
            'required': True,
            'description': 'Collection to check'
        ,
                'description_key': 'modules.test.assert_length.params.collection.description'},
        'expected_length': {
            'type': 'number',
            'required': True,
            'description': 'Expected length'
        ,
                'description_key': 'modules.test.assert_length.params.expected_length.description'},
        'message': {
            'type': 'string',
            'required': False,
            'description': 'Custom error message'
        ,
                'description_key': 'modules.test.assert_length.params.message.description'}
    },
    output_schema={
        'passed': {
            'type': 'boolean',
            'description': 'Whether assertion passed'
        ,
                'description_key': 'modules.test.assert_length.output.passed.description'},
        'actual_length': {
            'type': 'number',
            'description': 'Actual length'
        ,
                'description_key': 'modules.test.assert_length.output.actual_length.description'},
        'expected_length': {
            'type': 'number',
            'description': 'Expected length'
        ,
                'description_key': 'modules.test.assert_length.output.expected_length.description'},
        'message': {
            'type': 'string',
            'description': 'Result message'
        ,
                'description_key': 'modules.test.assert_length.output.message.description'}
    },
    timeout_ms=5000,
)
class AssertLengthModule(BaseModule):
    """Assert that a collection has expected length."""

    module_name = "Assert Length"
    module_description = "Assert that a collection has expected length"

    def validate_params(self) -> None:
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
