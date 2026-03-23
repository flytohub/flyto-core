# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
JSON Schema Validation Module
Validate JSON data against a JSON Schema
"""
import json
from typing import Any, Dict

from ...errors import ValidationError
from ...registry import register_module


def _check_bool_excluded(value, types):
    """Check isinstance but exclude bool (bool is a subclass of int)."""
    return isinstance(value, types) and not isinstance(value, bool)


# Dispatch table: type name → (checker_fn, allowed_types_for_error_msg)
# checker_fn(value) → bool
_TYPE_CHECKERS = {
    "string":  lambda v: isinstance(v, str),
    "number":  lambda v: _check_bool_excluded(v, (int, float)),
    "integer": lambda v: _check_bool_excluded(v, int),
    "boolean": lambda v: isinstance(v, bool),
    "array":   lambda v: isinstance(v, list),
    "object":  lambda v: isinstance(v, dict),
    "null":    lambda v: v is None,
}


def _validate_type(value, expected_type, path=""):
    """Validate a value matches the expected JSON Schema type.
    Returns (ok, error_message_or_none)."""
    checker = _TYPE_CHECKERS.get(expected_type)
    if checker is None:
        return True, None
    if checker(value):
        return True, None
    return False, f"{path}: expected {expected_type}, got {type(value).__name__}"


def _validate_number(value, schema_part: Dict, path: str, errors: list) -> None:
    """Validate numeric constraints (minimum/maximum)."""
    if not (isinstance(value, (int, float)) and not isinstance(value, bool)):
        return
    minimum = schema_part.get("minimum")
    maximum = schema_part.get("maximum")
    if minimum is not None and value < minimum:
        errors.append(f"{path}: {value} is less than minimum {minimum}")
    if maximum is not None and value > maximum:
        errors.append(f"{path}: {value} is greater than maximum {maximum}")


def _validate_string(value, schema_part: Dict, path: str, errors: list) -> None:
    """Validate string constraints (length, enum)."""
    if not isinstance(value, str):
        return
    min_length = schema_part.get("minLength")
    max_length = schema_part.get("maxLength")
    if min_length is not None and len(value) < min_length:
        errors.append(f"{path}: string length {len(value)} is less than minLength {min_length}")
    if max_length is not None and len(value) > max_length:
        errors.append(f"{path}: string length {len(value)} is greater than maxLength {max_length}")
    enum_values = schema_part.get("enum")
    if enum_values is not None and value not in enum_values:
        errors.append(f"{path}: '{value}' is not one of allowed values: {enum_values}")


def _validate_value(value, schema_part: Dict, path: str, errors: list) -> bool:
    """Recursively validate a value against a JSON Schema node."""
    if not schema_part:
        return True

    schema_type = schema_part.get("type")

    # Type check
    if schema_type:
        if isinstance(schema_type, list):
            if not any(_TYPE_CHECKERS.get(t, lambda _: True)(value) for t in schema_type):
                errors.append(f"{path}: expected one of {schema_type}, got {type(value).__name__}")
                return False
        else:
            ok, error = _validate_type(value, schema_type, path)
            if not ok:
                errors.append(error)
                return False

    # Object: required fields + recurse into properties
    if schema_type == "object" and isinstance(value, dict):
        for req in schema_part.get("required", []):
            if req not in value:
                errors.append(f"{path}: missing required property '{req}'")
        for prop, prop_schema in schema_part.get("properties", {}).items():
            if prop in value:
                _validate_value(value[prop], prop_schema, f"{path}.{prop}", errors)

    # Array: items schema + length constraints
    if schema_type == "array" and isinstance(value, list):
        items_schema = schema_part.get("items")
        if items_schema:
            for i, item in enumerate(value):
                _validate_value(item, items_schema, f"{path}[{i}]", errors)
        min_items = schema_part.get("minItems")
        max_items = schema_part.get("maxItems")
        if min_items is not None and len(value) < min_items:
            errors.append(f"{path}: array has {len(value)} items, minimum is {min_items}")
        if max_items is not None and len(value) > max_items:
            errors.append(f"{path}: array has {len(value)} items, maximum is {max_items}")

    _validate_number(value, schema_part, path, errors)
    _validate_string(value, schema_part, path, errors)

    return True


def validate_against_schema(data: Any, schema: Dict) -> tuple:
    """
    Simple JSON Schema validation without external dependencies.
    Returns (is_valid, errors)
    """
    errors: list = []
    _validate_value(data, schema, "root", errors)
    return len(errors) == 0, errors


@register_module(
    module_id='validate.json_schema',
    version='1.0.0',
    category='validate',
    tags=['validate', 'json', 'schema', 'format'],
    label='Validate JSON Schema',
    label_key='modules.validate.json_schema.label',
    description='Validate JSON data against a JSON Schema',
    description_key='modules.validate.json_schema.description',
    icon='FileJson',
    color='#10B981',
    input_types=['object', 'string'],
    output_types=['object'],

    can_receive_from=['*'],
    can_connect_to=['flow.*', 'data.*', 'notify.*'],

    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema={
        'data': {
            'type': 'text',
            'label': 'Data',
            'label_key': 'modules.validate.json_schema.params.data.label',
            'description': 'JSON data to validate (string or object)',
            'description_key': 'modules.validate.json_schema.params.data.description',
            'placeholder': '{"name": "John", "age": 30}',
            'required': True
        },
        'schema': {
            'type': 'text',
            'label': 'Schema',
            'label_key': 'modules.validate.json_schema.params.schema.label',
            'description': 'JSON Schema to validate against',
            'description_key': 'modules.validate.json_schema.params.schema.description',
            'placeholder': '{"type": "object", "properties": {...}}',
            'required': True
        }
    },
    output_schema={
        'valid': {
            'type': 'boolean',
            'description': 'Whether the data is valid',
            'description_key': 'modules.validate.json_schema.output.valid.description'
        },
        'errors': {
            'type': 'array',
            'description': 'List of validation errors',
            'description_key': 'modules.validate.json_schema.output.errors.description'
        },
        'error_count': {
            'type': 'number',
            'description': 'Number of validation errors',
            'description_key': 'modules.validate.json_schema.output.error_count.description'
        }
    },
    timeout_ms=10000,
)
async def validate_json_schema(context: Dict[str, Any]) -> Dict[str, Any]:
    """Validate JSON data against a JSON Schema."""
    params = context['params']
    data_param = params.get('data')
    schema_param = params.get('schema')

    if data_param is None:
        raise ValidationError("Missing required parameter: data", field="data")
    if schema_param is None:
        raise ValidationError("Missing required parameter: schema", field="schema")

    if isinstance(data_param, str):
        try:
            data = json.loads(data_param)
        except json.JSONDecodeError as e:
            return {
                'ok': True,
                'data': {
                    'valid': False,
                    'errors': [f"Invalid JSON data: {str(e)}"],
                    'error_count': 1
                }
            }
    else:
        data = data_param

    if isinstance(schema_param, str):
        try:
            schema = json.loads(schema_param)
        except json.JSONDecodeError as e:
            return {
                'ok': True,
                'data': {
                    'valid': False,
                    'errors': [f"Invalid JSON schema: {str(e)}"],
                    'error_count': 1
                }
            }
    else:
        schema = schema_param

    is_valid, errors = validate_against_schema(data, schema)

    return {
        'ok': True,
        'data': {
            'valid': is_valid,
            'errors': errors,
            'error_count': len(errors)
        }
    }
