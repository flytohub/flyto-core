"""
Assert Contains Module

Assert that a collection contains a value.
"""

from typing import Any

from ...base import BaseModule
from ...registry import register_module


@register_module(
    module_id='test.assert_contains',
    version='1.0.0',
    category='testing',
    tags=['testing', 'assertion', 'validation'],
    label='Assert Contains',
    label_key='modules.test.assert_contains.label',
    description='Assert that a collection contains a value',
    description_key='modules.test.assert_contains.description',
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
            'description': 'Collection to search in'
        ,
                'description_key': 'modules.test.assert_contains.params.collection.description'},
        'value': {
            'type': ['string', 'number', 'boolean'],
            'required': True,
            'description': 'Value to find'
        ,
                'description_key': 'modules.test.assert_contains.params.value.description'},
        'message': {
            'type': 'string',
            'required': False,
            'description': 'Custom error message'
        ,
                'description_key': 'modules.test.assert_contains.params.message.description'}
    },
    output_schema={
        'passed': {
            'type': 'boolean',
            'description': 'Whether assertion passed'
        ,
                'description_key': 'modules.test.assert_contains.output.passed.description'},
        'collection': {
            'type': ['array', 'string'],
            'description': 'Collection searched'
        ,
                'description_key': 'modules.test.assert_contains.output.collection.description'},
        'value': {
            'type': ['string', 'number', 'boolean'],
            'description': 'Value searched for'
        ,
                'description_key': 'modules.test.assert_contains.output.value.description'},
        'message': {
            'type': 'string',
            'description': 'Result message'
        ,
                'description_key': 'modules.test.assert_contains.output.message.description'}
    }
)
class AssertContainsModule(BaseModule):
    """Assert that a collection contains a value."""

    module_name = "Assert Contains"
    module_description = "Assert that a collection contains a value"

    def validate_params(self):
        if 'collection' not in self.params:
            raise ValueError("Parameter 'collection' is required")
        if 'value' not in self.params:
            raise ValueError("Parameter 'value' is required")

    async def execute(self) -> Any:
        collection = self.params.get('collection')
        value = self.params.get('value')
        custom_message = self.params.get('message')

        passed = value in collection

        if passed:
            message = custom_message or f"Assertion passed: {value} found in collection"
        else:
            message = custom_message or f"Assertion failed: {value} not found in collection"

        result = {
            'passed': passed,
            'collection': collection,
            'value': value,
            'message': message
        }

        if not passed:
            raise AssertionError(message)

        return result
