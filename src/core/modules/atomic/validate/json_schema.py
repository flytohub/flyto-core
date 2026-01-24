"""
JSON Schema Validation Module
Validate JSON data against a JSON Schema
"""
from typing import Any, Dict
import json

from ...registry import register_module
from ...errors import ValidationError


def validate_against_schema(data: Any, schema: Dict) -> tuple:
    """
    Simple JSON Schema validation without external dependencies.
    Returns (is_valid, errors)
    """
    errors = []

    def validate_type(value, expected_type, path=""):
        if expected_type == "string":
            if not isinstance(value, str):
                errors.append(f"{path}: expected string, got {type(value).__name__}")
                return False
        elif expected_type == "number":
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                errors.append(f"{path}: expected number, got {type(value).__name__}")
                return False
        elif expected_type == "integer":
            if not isinstance(value, int) or isinstance(value, bool):
                errors.append(f"{path}: expected integer, got {type(value).__name__}")
                return False
        elif expected_type == "boolean":
            if not isinstance(value, bool):
                errors.append(f"{path}: expected boolean, got {type(value).__name__}")
                return False
        elif expected_type == "array":
            if not isinstance(value, list):
                errors.append(f"{path}: expected array, got {type(value).__name__}")
                return False
        elif expected_type == "object":
            if not isinstance(value, dict):
                errors.append(f"{path}: expected object, got {type(value).__name__}")
                return False
        elif expected_type == "null":
            if value is not None:
                errors.append(f"{path}: expected null, got {type(value).__name__}")
                return False
        return True

    def validate_value(value, schema_part, path="root"):
        if not schema_part:
            return True

        schema_type = schema_part.get("type")
        if schema_type:
            if isinstance(schema_type, list):
                type_valid = any(validate_type(value, t, path) for t in schema_type)
                if not type_valid:
                    return False
            else:
                if not validate_type(value, schema_type, path):
                    return False

        if schema_type == "object" and isinstance(value, dict):
            properties = schema_part.get("properties", {})
            required = schema_part.get("required", [])

            for req in required:
                if req not in value:
                    errors.append(f"{path}: missing required property '{req}'")

            for prop, prop_schema in properties.items():
                if prop in value:
                    validate_value(value[prop], prop_schema, f"{path}.{prop}")

        if schema_type == "array" and isinstance(value, list):
            items_schema = schema_part.get("items")
            if items_schema:
                for i, item in enumerate(value):
                    validate_value(item, items_schema, f"{path}[{i}]")

            min_items = schema_part.get("minItems")
            max_items = schema_part.get("maxItems")
            if min_items is not None and len(value) < min_items:
                errors.append(f"{path}: array has {len(value)} items, minimum is {min_items}")
            if max_items is not None and len(value) > max_items:
                errors.append(f"{path}: array has {len(value)} items, maximum is {max_items}")

        if isinstance(value, (int, float)) and not isinstance(value, bool):
            minimum = schema_part.get("minimum")
            maximum = schema_part.get("maximum")
            if minimum is not None and value < minimum:
                errors.append(f"{path}: {value} is less than minimum {minimum}")
            if maximum is not None and value > maximum:
                errors.append(f"{path}: {value} is greater than maximum {maximum}")

        if isinstance(value, str):
            min_length = schema_part.get("minLength")
            max_length = schema_part.get("maxLength")
            if min_length is not None and len(value) < min_length:
                errors.append(f"{path}: string length {len(value)} is less than minLength {min_length}")
            if max_length is not None and len(value) > max_length:
                errors.append(f"{path}: string length {len(value)} is greater than maxLength {max_length}")

            enum_values = schema_part.get("enum")
            if enum_values is not None and value not in enum_values:
                errors.append(f"{path}: '{value}' is not one of allowed values: {enum_values}")

        return True

    validate_value(data, schema)
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
    can_connect_to=['flow.*', 'data.*', 'notification.*'],

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
