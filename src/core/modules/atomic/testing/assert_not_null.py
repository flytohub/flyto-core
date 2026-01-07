"""
Assert Not Null Module

Assert that a value is not null or undefined.
"""

from typing import Any

from ...base import BaseModule
from ...registry import register_module


@register_module(
    module_id='test.assert_not_null',
    version='1.0.0',
    category='testing',
    tags=['testing', 'assertion', 'validation'],
    label='Assert Not Null',
    label_key='modules.test.assert_not_null.label',
    description='Assert that a value is not null or undefined',
    description_key='modules.test.assert_not_null.description',
    icon='CheckCircle',
    color='#22C55E',

    # Connection types
    input_types=['any'],
    output_types=['boolean'],


    can_receive_from=['*'],
    can_connect_to=['testing.*', 'test.*', 'flow.*', 'notification.*', 'data.*'],    params_schema={
        'value': {
            'type': ['string', 'number', 'boolean', 'object', 'array', 'null'],
            'required': True,
            'description': 'Value to check'
        ,
                'description_key': 'modules.test.assert_not_null.params.value.description'},
        'message': {
            'type': 'string',
            'required': False,
            'description': 'Custom error message'
        ,
                'description_key': 'modules.test.assert_not_null.params.message.description'}
    },
    output_schema={
        'passed': {
            'type': 'boolean',
            'description': 'Whether assertion passed'
        ,
                'description_key': 'modules.test.assert_not_null.output.passed.description'},
        'message': {
            'type': 'string',
            'description': 'Result message'
        ,
                'description_key': 'modules.test.assert_not_null.output.message.description'}
    }
)
class AssertNotNullModule(BaseModule):
    """Assert that a value is not null or undefined."""

    module_name = "Assert Not Null"
    module_description = "Assert that a value is not null or undefined"

    def validate_params(self):
        # value can be None, so we check if it's in params dict instead
        pass

    async def execute(self) -> Any:
        value = self.params.get('value')
        custom_message = self.params.get('message')

        passed = value is not None

        if passed:
            message = custom_message or "Assertion passed: value is not null"
        else:
            message = custom_message or "Assertion failed: value is null"

        result = {
            'passed': passed,
            'message': message
        }

        if not passed:
            raise AssertionError(message)

        return result
