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
    description='Assert that a condition is true',
    icon='CheckCircle',
    color='#22C55E',
    params_schema={
        'condition': {
            'type': 'boolean',
            'required': True,
            'description': 'Condition to check'
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
        'message': {
            'type': 'string',
            'description': 'Result message'
        }
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
