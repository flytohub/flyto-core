"""
Assert True Module

Assert that a condition is true.
"""

from typing import Any

from ...base import BaseModule
from ...registry import register_module


@register_module(
    module_id='test.assert_true',
    version='1.0.0',
    category='testing',
    tags=['testing', 'assertion', 'validation'],
    label='Assert True',
    label_key='modules.test.assert_true.label',
    description='Assert that a condition is true',
    description_key='modules.test.assert_true.description',
    icon='CheckCircle',
    color='#22C55E',

    # Connection types
    input_types=['boolean'],
    output_types=['boolean'],


    can_receive_from=['*'],
    can_connect_to=['testing.*', 'test.*', 'flow.*', 'notification.*', 'data.*'],    params_schema={
        'condition': {
            'type': 'boolean',
            'required': True,
            'description': 'Condition to check'
        ,
                'description_key': 'modules.test.assert_true.params.condition.description'},
        'message': {
            'type': 'string',
            'required': False,
            'description': 'Custom error message'
        ,
                'description_key': 'modules.test.assert_true.params.message.description'}
    },
    output_schema={
        'passed': {
            'type': 'boolean',
            'description': 'Whether assertion passed'
        ,
                'description_key': 'modules.test.assert_true.output.passed.description'},
        'message': {
            'type': 'string',
            'description': 'Result message'
        ,
                'description_key': 'modules.test.assert_true.output.message.description'}
    }
)
class AssertTrueModule(BaseModule):
    """Assert that a condition is true."""

    module_name = "Assert True"
    module_description = "Assert that a condition is true"

    def validate_params(self):
        if 'condition' not in self.params:
            raise ValueError("Parameter 'condition' is required")

    async def execute(self) -> Any:
        condition = self.params.get('condition')
        custom_message = self.params.get('message')

        passed = bool(condition)

        if passed:
            message = custom_message or "Assertion passed: condition is true"
        else:
            message = custom_message or "Assertion failed: condition is false"

        result = {
            'passed': passed,
            'message': message
        }

        if not passed:
            raise AssertionError(message)

        return result
