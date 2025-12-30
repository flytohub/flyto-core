"""
HTTP Response Assert Module
Assert and validate HTTP response properties
"""

import logging
import re
from typing import Any, Dict, List, Optional, Union

from ...registry import register_module


logger = logging.getLogger(__name__)


def _get_nested_value(obj: Any, path: str) -> Any:
    """Get value from nested object using dot notation path"""
    if not path:
        return obj

    parts = path.split('.')
    current = obj

    for part in parts:
        # Handle array index notation: items[0]
        match = re.match(r'(\w+)\[(\d+)\]', part)
        if match:
            key, index = match.groups()
            if isinstance(current, dict) and key in current:
                current = current[key]
                if isinstance(current, list) and int(index) < len(current):
                    current = current[int(index)]
                else:
                    return None
            else:
                return None
        elif isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None

    return current


@register_module(
    module_id='http.response_assert',
    version='1.0.0',
    category='atomic',
    subcategory='http',
    tags=['http', 'response', 'assert', 'test', 'validation', 'atomic'],
    label='Assert HTTP Response',
    label_key='modules.http.response_assert.label',
    description='Assert and validate HTTP response properties',
    description_key='modules.http.response_assert.description',
    icon='CheckCircle',
    color='#10B981',

    # Connection types
    input_types=['object'],
    output_types=['object', 'boolean'],
    can_connect_to=['test.*', 'flow.*'],

    # Execution settings
    timeout=5,
    retryable=False,
    concurrent_safe=True,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema={
        'response': {
            'type': 'object',
            'label': 'Response',
            'label_key': 'modules.http.response_assert.params.response.label',
            'description': 'HTTP response object from http.request',
            'description_key': 'modules.http.response_assert.params.response.description',
            'required': True
        },
        'status': {
            'type': 'any',
            'label': 'Expected Status',
            'label_key': 'modules.http.response_assert.params.status.label',
            'description': 'Expected status code (number, array of numbers, or range string "200-299")',
            'description_key': 'modules.http.response_assert.params.status.description',
            'required': False,
            'examples': [200, [200, 201], '200-299']
        },
        'body_contains': {
            'type': 'any',
            'label': 'Body Contains',
            'label_key': 'modules.http.response_assert.params.body_contains.label',
            'description': 'String or array of strings that body should contain',
            'description_key': 'modules.http.response_assert.params.body_contains.description',
            'required': False
        },
        'body_not_contains': {
            'type': 'any',
            'label': 'Body Not Contains',
            'label_key': 'modules.http.response_assert.params.body_not_contains.label',
            'description': 'String or array of strings that body should NOT contain',
            'description_key': 'modules.http.response_assert.params.body_not_contains.description',
            'required': False
        },
        'body_matches': {
            'type': 'string',
            'label': 'Body Matches Regex',
            'label_key': 'modules.http.response_assert.params.body_matches.label',
            'description': 'Regular expression pattern that body should match',
            'description_key': 'modules.http.response_assert.params.body_matches.description',
            'required': False
        },
        'json_path': {
            'type': 'object',
            'label': 'JSON Path Assertions',
            'label_key': 'modules.http.response_assert.params.json_path.label',
            'description': 'Object mapping JSON paths to expected values (e.g., {"data.id": 123})',
            'description_key': 'modules.http.response_assert.params.json_path.description',
            'required': False
        },
        'json_path_exists': {
            'type': 'array',
            'label': 'JSON Paths Exist',
            'label_key': 'modules.http.response_assert.params.json_path_exists.label',
            'description': 'Array of JSON paths that should exist',
            'description_key': 'modules.http.response_assert.params.json_path_exists.description',
            'required': False
        },
        'header_contains': {
            'type': 'object',
            'label': 'Headers Contain',
            'label_key': 'modules.http.response_assert.params.header_contains.label',
            'description': 'Object mapping header names to expected values',
            'description_key': 'modules.http.response_assert.params.header_contains.description',
            'required': False
        },
        'content_type': {
            'type': 'string',
            'label': 'Content Type',
            'label_key': 'modules.http.response_assert.params.content_type.label',
            'description': 'Expected Content-Type (partial match)',
            'description_key': 'modules.http.response_assert.params.content_type.description',
            'required': False
        },
        'max_duration_ms': {
            'type': 'number',
            'label': 'Max Duration (ms)',
            'label_key': 'modules.http.response_assert.params.max_duration_ms.label',
            'description': 'Maximum allowed response time in milliseconds',
            'description_key': 'modules.http.response_assert.params.max_duration_ms.description',
            'required': False
        },
        'schema': {
            'type': 'object',
            'label': 'JSON Schema',
            'label_key': 'modules.http.response_assert.params.schema.label',
            'description': 'JSON Schema to validate response body against',
            'description_key': 'modules.http.response_assert.params.schema.description',
            'required': False
        },
        'fail_fast': {
            'type': 'boolean',
            'label': 'Fail Fast',
            'label_key': 'modules.http.response_assert.params.fail_fast.label',
            'description': 'Stop on first assertion failure',
            'description_key': 'modules.http.response_assert.params.fail_fast.description',
            'required': False,
            'default': False
        }
    },
    output_schema={
        'ok': {
            'type': 'boolean',
            'description': 'Whether all assertions passed'
        },
        'passed': {
            'type': 'number',
            'description': 'Number of passed assertions'
        },
        'failed': {
            'type': 'number',
            'description': 'Number of failed assertions'
        },
        'total': {
            'type': 'number',
            'description': 'Total number of assertions'
        },
        'assertions': {
            'type': 'array',
            'description': 'Detailed assertion results'
        },
        'errors': {
            'type': 'array',
            'description': 'List of error messages for failed assertions'
        }
    },
    examples=[
        {
            'title': 'Assert status 200',
            'title_key': 'modules.http.response_assert.examples.status.title',
            'params': {
                'response': '${http_request.result}',
                'status': 200
            }
        },
        {
            'title': 'Assert JSON structure',
            'title_key': 'modules.http.response_assert.examples.json.title',
            'params': {
                'response': '${http_request.result}',
                'status': 200,
                'json_path': {
                    'data.id': '${expected_id}',
                    'data.name': 'John'
                },
                'json_path_exists': ['data.created_at', 'data.email']
            }
        },
        {
            'title': 'Assert API response',
            'title_key': 'modules.http.response_assert.examples.api.title',
            'params': {
                'response': '${api_result}',
                'status': [200, 201],
                'content_type': 'application/json',
                'max_duration_ms': 1000,
                'json_path': {
                    'success': True
                }
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def http_response_assert(context: Dict[str, Any]) -> Dict[str, Any]:
    """Assert HTTP response properties"""
    params = context['params']
    response = params['response']
    fail_fast = params.get('fail_fast', False)

    assertions: List[Dict[str, Any]] = []
    errors: List[str] = []

    def add_assertion(name: str, passed: bool, expected: Any, actual: Any, message: str = ''):
        assertion = {
            'name': name,
            'passed': passed,
            'expected': expected,
            'actual': actual
        }
        if message:
            assertion['message'] = message
        assertions.append(assertion)

        if not passed:
            error_msg = message or f'{name}: expected {expected}, got {actual}'
            errors.append(error_msg)
            if fail_fast:
                raise AssertionError(error_msg)

    try:
        # Assert status code
        if 'status' in params:
            expected_status = params['status']
            actual_status = response.get('status')

            if isinstance(expected_status, int):
                passed = actual_status == expected_status
                add_assertion(
                    'status',
                    passed,
                    expected_status,
                    actual_status,
                    f'Status code mismatch: expected {expected_status}, got {actual_status}'
                )
            elif isinstance(expected_status, list):
                passed = actual_status in expected_status
                add_assertion(
                    'status',
                    passed,
                    expected_status,
                    actual_status,
                    f'Status code {actual_status} not in allowed list {expected_status}'
                )
            elif isinstance(expected_status, str) and '-' in expected_status:
                # Range: "200-299"
                start, end = map(int, expected_status.split('-'))
                passed = start <= actual_status <= end
                add_assertion(
                    'status',
                    passed,
                    expected_status,
                    actual_status,
                    f'Status code {actual_status} not in range {expected_status}'
                )

        # Assert body contains
        if 'body_contains' in params:
            body = response.get('body', '')
            body_str = str(body) if not isinstance(body, str) else body
            contains_list = params['body_contains']
            if isinstance(contains_list, str):
                contains_list = [contains_list]

            for substring in contains_list:
                passed = substring in body_str
                add_assertion(
                    'body_contains',
                    passed,
                    f'contains "{substring}"',
                    f'body length: {len(body_str)}',
                    f'Body does not contain "{substring}"'
                )

        # Assert body not contains
        if 'body_not_contains' in params:
            body = response.get('body', '')
            body_str = str(body) if not isinstance(body, str) else body
            not_contains_list = params['body_not_contains']
            if isinstance(not_contains_list, str):
                not_contains_list = [not_contains_list]

            for substring in not_contains_list:
                passed = substring not in body_str
                add_assertion(
                    'body_not_contains',
                    passed,
                    f'not contains "{substring}"',
                    f'found in body',
                    f'Body should not contain "{substring}"'
                )

        # Assert body matches regex
        if 'body_matches' in params:
            body = response.get('body', '')
            body_str = str(body) if not isinstance(body, str) else body
            pattern = params['body_matches']
            passed = bool(re.search(pattern, body_str))
            add_assertion(
                'body_matches',
                passed,
                f'matches /{pattern}/',
                f'body length: {len(body_str)}',
                f'Body does not match pattern: {pattern}'
            )

        # Assert JSON path values
        if 'json_path' in params:
            body = response.get('body', {})
            if isinstance(body, str):
                import json
                try:
                    body = json.loads(body)
                except json.JSONDecodeError:
                    body = {}

            for path, expected_value in params['json_path'].items():
                actual_value = _get_nested_value(body, path)
                passed = actual_value == expected_value
                add_assertion(
                    f'json_path:{path}',
                    passed,
                    expected_value,
                    actual_value,
                    f'JSON path "{path}": expected {expected_value}, got {actual_value}'
                )

        # Assert JSON paths exist
        if 'json_path_exists' in params:
            body = response.get('body', {})
            if isinstance(body, str):
                import json
                try:
                    body = json.loads(body)
                except json.JSONDecodeError:
                    body = {}

            for path in params['json_path_exists']:
                value = _get_nested_value(body, path)
                passed = value is not None
                add_assertion(
                    f'json_path_exists:{path}',
                    passed,
                    'exists',
                    'not found' if not passed else 'found',
                    f'JSON path "{path}" does not exist'
                )

        # Assert headers
        if 'header_contains' in params:
            headers = response.get('headers', {})
            # Normalize header names to lowercase for comparison
            headers_lower = {k.lower(): v for k, v in headers.items()}

            for header_name, expected_value in params['header_contains'].items():
                actual_value = headers_lower.get(header_name.lower())
                if expected_value is None:
                    passed = actual_value is not None
                else:
                    passed = actual_value == expected_value
                add_assertion(
                    f'header:{header_name}',
                    passed,
                    expected_value or 'exists',
                    actual_value,
                    f'Header "{header_name}": expected {expected_value}, got {actual_value}'
                )

        # Assert content type
        if 'content_type' in params:
            expected_ct = params['content_type']
            actual_ct = response.get('content_type', '')
            passed = expected_ct in actual_ct
            add_assertion(
                'content_type',
                passed,
                f'contains "{expected_ct}"',
                actual_ct,
                f'Content-Type mismatch: expected "{expected_ct}" in "{actual_ct}"'
            )

        # Assert max duration
        if 'max_duration_ms' in params:
            max_ms = params['max_duration_ms']
            actual_ms = response.get('duration_ms', 0)
            passed = actual_ms <= max_ms
            add_assertion(
                'max_duration_ms',
                passed,
                f'<= {max_ms}ms',
                f'{actual_ms}ms',
                f'Response too slow: {actual_ms}ms > {max_ms}ms'
            )

        # Assert JSON schema (if jsonschema is available)
        if 'schema' in params:
            try:
                import jsonschema
                body = response.get('body', {})
                if isinstance(body, str):
                    import json
                    body = json.loads(body)

                try:
                    jsonschema.validate(body, params['schema'])
                    passed = True
                    schema_error = None
                except jsonschema.ValidationError as e:
                    passed = False
                    schema_error = str(e.message)

                add_assertion(
                    'json_schema',
                    passed,
                    'valid',
                    schema_error or 'valid',
                    f'JSON schema validation failed: {schema_error}'
                )
            except ImportError:
                add_assertion(
                    'json_schema',
                    False,
                    'validation',
                    'skipped',
                    'jsonschema library not installed'
                )

    except AssertionError:
        # fail_fast triggered
        pass

    passed_count = sum(1 for a in assertions if a['passed'])
    failed_count = len(assertions) - passed_count
    all_passed = failed_count == 0

    logger.info(
        f"HTTP response assert: {passed_count}/{len(assertions)} passed"
    )

    return {
        'ok': all_passed,
        'passed': passed_count,
        'failed': failed_count,
        'total': len(assertions),
        'assertions': assertions,
        'errors': errors
    }
