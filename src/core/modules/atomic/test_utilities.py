from typing import Any
from ..base import BaseModule
from ..registry import register_module


@register_module(
    module_id='test.assert_equal',
    version='1.0.0',
    category='atomic',
    description='Assert that two values are equal',
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
    def validate_params(self):
        """Validate parameters"""
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


@register_module(
    module_id='test.assert_true',
    version='1.0.0',
    category='atomic',
    description='Assert that a condition is true',
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
    def validate_params(self):
        """Validate parameters"""
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


@register_module(
    module_id='test.assert_contains',
    version='1.0.0',
    category='atomic',
    description='Assert that a collection contains a value',
    params_schema={
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
    def validate_params(self):
        """Validate parameters"""
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


@register_module(
    module_id='test.assert_greater_than',
    version='1.0.0',
    category='atomic',
    description='Assert that a value is greater than another',
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
    def validate_params(self):
        """Validate parameters"""
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


@register_module(
    module_id='test.assert_length',
    version='1.0.0',
    category='atomic',
    description='Assert that a collection has expected length',
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
    def validate_params(self):
        """Validate parameters"""
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


@register_module(
    module_id='test.assert_not_null',
    version='1.0.0',
    category='atomic',
    description='Assert that a value is not null or undefined',
    params_schema={
        'value': {
            'type': ['string', 'number', 'boolean', 'object', 'array', 'null'],
            'required': True,
            'description': 'Value to check'
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
class AssertNotNullModule(BaseModule):
    def validate_params(self):
        """Validate parameters"""
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
