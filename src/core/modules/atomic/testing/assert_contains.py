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
        },
        'value': {
            'type': ['string', 'number', 'boolean'],
            'required': True,
            'description': 'Value to find'
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
        'collection': {
            'type': ['array', 'string'],
            'description': 'Collection searched'
        },
        'value': {
            'type': ['string', 'number', 'boolean'],
            'description': 'Value searched for'
        },
        'message': {
            'type': 'string',
            'description': 'Result message'
        }
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
