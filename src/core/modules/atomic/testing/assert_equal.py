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
    label_key='modules.test.assert_equal.label',
    description='Assert that two values are equal',
    description_key='modules.test.assert_equal.description',
    icon='CircleCheck',
    color='#22C55E',

    # Connection types
    input_types=['any'],
    output_types=['boolean'],


    can_receive_from=['*'],
    can_connect_to=['testing.*', 'test.*', 'flow.*', 'notification.*', 'data.*'],    params_schema={
        'actual': {
            'type': ['string', 'number', 'boolean', 'object', 'array'],
            'required': True,
            'description': 'Actual value'
        ,
                'description_key': 'modules.test.assert_equal.params.actual.description',
            'placeholder': 'Enter Actual...',
            'label': 'Actual',
        },
        'expected': {
            'type': ['string', 'number', 'boolean', 'object', 'array'],
            'required': True,
            'description': 'Expected value'
        ,
                'description_key': 'modules.test.assert_equal.params.expected.description',
            'placeholder': 'Enter Expected...',
            'label': 'Expected',
        },
        'message': {
            'type': 'string',
            'required': False,
            'description': 'Custom error message'
        ,
                'description_key': 'modules.test.assert_equal.params.message.description',
            'placeholder': 'Your message here',
            'label': 'Message',
        }
    },
    output_schema={
        'passed': {
            'type': 'boolean',
            'description': 'Whether assertion passed'
        ,
                'description_key': 'modules.test.assert_equal.output.passed.description'},
        'actual': {
            'type': ['string', 'number', 'boolean', 'object', 'array'],
            'description': 'Actual value received'
        ,
                'description_key': 'modules.test.assert_equal.output.actual.description'},
        'expected': {
            'type': ['string', 'number', 'boolean', 'object', 'array'],
            'description': 'Expected value'
        ,
                'description_key': 'modules.test.assert_equal.output.expected.description'},
        'message': {
            'type': 'string',
            'description': 'Result message'
        ,
                'description_key': 'modules.test.assert_equal.output.message.description'}
    },
    timeout_ms=5000,
)
class AssertEqualModule(BaseModule):
    """Assert that two values are equal."""

    module_name = "Assert Equal"
    module_description = "Assert that two values are equal"

    def validate_params(self) -> None:
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
