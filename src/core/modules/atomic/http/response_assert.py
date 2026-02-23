# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
HTTP Response Assert Module
Assert and validate HTTP response properties
"""

import logging
import re
from typing import Any, Dict, List, Optional, Union

from ...registry import register_module
from ...schema import compose, field, presets


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
    tags=['http', 'response', 'assert', 'test', 'validation', 'atomic', 'ssrf_protected', 'path_restricted'],
    label='Assert HTTP Response',
    label_key='modules.http.response_assert.label',
    description='Assert and validate HTTP response properties',
    description_key='modules.http.response_assert.description',
    icon='CircleCheck',
    color='#10B981',

    # Connection types
    input_types=['object'],
    output_types=['object', 'boolean'],
    can_connect_to=['test.*', 'flow.*'],
    can_receive_from=['*'],

    # Execution settings
    timeout_ms=5000,
    retryable=False,
    concurrent_safe=True,

    # Security settings (no network access - just validates response objects)
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],  # This module doesn't make network calls

    # Schema-driven params
    params_schema=compose(
        field('response', type='object', label='Response', label_key='schema.field.response',
              required=True, description='HTTP response object from http.request'),
        presets.HTTP_STATUS(),
        presets.BODY_CONTAINS(),
        presets.BODY_NOT_CONTAINS(),
        presets.REGEX_PATTERN(key='body_matches', label='Body Matches Regex',
                              label_key='schema.field.body_matches'),
        presets.JSON_PATH_ASSERTIONS(),
        presets.JSON_PATH_EXISTS(),
        presets.HEADER_CONTAINS(),
        presets.CONTENT_TYPE(key='content_type', default=''),
        presets.MAX_DURATION_MS(),
        presets.JSON_SCHEMA(),
        presets.FAIL_FAST(default=False),
    ),
    output_schema={
        'ok': {
            'type': 'boolean',
            'description': 'Whether all assertions passed'
        ,
                'description_key': 'modules.http.response_assert.output.ok.description'},
        'passed': {
            'type': 'number',
            'description': 'Number of passed assertions'
        ,
                'description_key': 'modules.http.response_assert.output.passed.description'},
        'failed': {
            'type': 'number',
            'description': 'Number of failed assertions'
        ,
                'description_key': 'modules.http.response_assert.output.failed.description'},
        'total': {
            'type': 'number',
            'description': 'Total number of assertions'
        ,
                'description_key': 'modules.http.response_assert.output.total.description'},
        'assertions': {
            'type': 'array',
            'description': 'Detailed assertion results'
        ,
                'description_key': 'modules.http.response_assert.output.assertions.description'},
        'errors': {
            'type': 'array',
            'description': 'List of error messages for failed assertions'
        ,
                'description_key': 'modules.http.response_assert.output.errors.description'}
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
    author='Flyto Team',
    license='MIT'
)
def _add_assertion(
    assertions: List[Dict[str, Any]], errors: List[str],
    name: str, passed: bool, expected: Any, actual: Any,
    message: str = '', fail_fast: bool = False,
):
    """Record an assertion result and optionally raise on failure."""
    assertion = {'name': name, 'passed': passed, 'expected': expected, 'actual': actual}
    if message:
        assertion['message'] = message
    assertions.append(assertion)
    if not passed:
        error_msg = message or f'{name}: expected {expected}, got {actual}'
        errors.append(error_msg)
        if fail_fast:
            raise AssertionError(error_msg)


def _get_body_str(response: dict) -> str:
    """Extract body from response as string."""
    body = response.get('body', '')
    return str(body) if not isinstance(body, str) else body


def _parse_json_body(response: dict) -> Any:
    """Parse body as JSON, returning empty dict on failure."""
    import json
    body = response.get('body', {})
    if isinstance(body, str):
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {}
    return body


def _assert_status(params: dict, response: dict, assertions: list, errors: list, fail_fast: bool):
    """Assert HTTP status code."""
    expected_status = params['status']
    actual_status = response.get('status')
    if isinstance(expected_status, int):
        _add_assertion(assertions, errors, 'status', actual_status == expected_status,
                       expected_status, actual_status,
                       f'Status code mismatch: expected {expected_status}, got {actual_status}', fail_fast)
    elif isinstance(expected_status, list):
        _add_assertion(assertions, errors, 'status', actual_status in expected_status,
                       expected_status, actual_status,
                       f'Status code {actual_status} not in allowed list {expected_status}', fail_fast)
    elif isinstance(expected_status, str) and '-' in expected_status:
        start, end = map(int, expected_status.split('-'))
        _add_assertion(assertions, errors, 'status', start <= actual_status <= end,
                       expected_status, actual_status,
                       f'Status code {actual_status} not in range {expected_status}', fail_fast)


def _assert_body_contains(params: dict, response: dict, assertions: list, errors: list, fail_fast: bool):
    """Assert body contains / not contains / regex."""
    body_str = _get_body_str(response)

    if 'body_contains' in params:
        contains_list = params['body_contains']
        if isinstance(contains_list, str):
            contains_list = [contains_list]
        for substring in contains_list:
            _add_assertion(assertions, errors, 'body_contains', substring in body_str,
                           f'contains "{substring}"', f'body length: {len(body_str)}',
                           f'Body does not contain "{substring}"', fail_fast)

    if 'body_not_contains' in params:
        not_list = params['body_not_contains']
        if isinstance(not_list, str):
            not_list = [not_list]
        for substring in not_list:
            _add_assertion(assertions, errors, 'body_not_contains', substring not in body_str,
                           f'not contains "{substring}"', 'found in body',
                           f'Body should not contain "{substring}"', fail_fast)

    if 'body_matches' in params:
        pattern = params['body_matches']
        _add_assertion(assertions, errors, 'body_matches', bool(re.search(pattern, body_str)),
                       f'matches /{pattern}/', f'body length: {len(body_str)}',
                       f'Body does not match pattern: {pattern}', fail_fast)


def _assert_json_paths(params: dict, response: dict, assertions: list, errors: list, fail_fast: bool):
    """Assert JSON path values and existence."""
    if 'json_path' in params:
        body = _parse_json_body(response)
        for path, expected_value in params['json_path'].items():
            actual_value = _get_nested_value(body, path)
            _add_assertion(assertions, errors, f'json_path:{path}', actual_value == expected_value,
                           expected_value, actual_value,
                           f'JSON path "{path}": expected {expected_value}, got {actual_value}', fail_fast)

    if 'json_path_exists' in params:
        body = _parse_json_body(response)
        for path in params['json_path_exists']:
            value = _get_nested_value(body, path)
            passed = value is not None
            _add_assertion(assertions, errors, f'json_path_exists:{path}', passed,
                           'exists', 'not found' if not passed else 'found',
                           f'JSON path "{path}" does not exist', fail_fast)


def _assert_headers_and_meta(params: dict, response: dict, assertions: list, errors: list, fail_fast: bool):
    """Assert headers, content-type, duration, and JSON schema."""
    if 'header_contains' in params:
        headers_lower = {k.lower(): v for k, v in response.get('headers', {}).items()}
        for header_name, expected_value in params['header_contains'].items():
            actual_value = headers_lower.get(header_name.lower())
            passed = actual_value is not None if expected_value is None else actual_value == expected_value
            _add_assertion(assertions, errors, f'header:{header_name}', passed,
                           expected_value or 'exists', actual_value,
                           f'Header "{header_name}": expected {expected_value}, got {actual_value}', fail_fast)

    if 'content_type' in params:
        expected_ct = params['content_type']
        actual_ct = response.get('content_type', '')
        _add_assertion(assertions, errors, 'content_type', expected_ct in actual_ct,
                       f'contains "{expected_ct}"', actual_ct,
                       f'Content-Type mismatch: expected "{expected_ct}" in "{actual_ct}"', fail_fast)

    if 'max_duration_ms' in params:
        max_ms = params['max_duration_ms']
        actual_ms = response.get('duration_ms', 0)
        _add_assertion(assertions, errors, 'max_duration_ms', actual_ms <= max_ms,
                       f'<= {max_ms}ms', f'{actual_ms}ms',
                       f'Response too slow: {actual_ms}ms > {max_ms}ms', fail_fast)


def _assert_json_schema(params: dict, response: dict, assertions: list, errors: list, fail_fast: bool):
    """Assert response body against JSON schema."""
    try:
        import jsonschema
        body = _parse_json_body(response)
        try:
            jsonschema.validate(body, params['schema'])
            _add_assertion(assertions, errors, 'json_schema', True, 'valid', 'valid', '', fail_fast)
        except jsonschema.ValidationError as e:
            _add_assertion(assertions, errors, 'json_schema', False, 'valid', str(e.message),
                           f'JSON schema validation failed: {e.message}', fail_fast)
    except ImportError:
        _add_assertion(assertions, errors, 'json_schema', False, 'validation', 'skipped',
                       'jsonschema library not installed', fail_fast)


async def http_response_assert(context: Dict[str, Any]) -> Dict[str, Any]:
    """Assert HTTP response properties"""
    params = context['params']
    response = params['response']
    fail_fast = params.get('fail_fast', False)
    assertions: List[Dict[str, Any]] = []
    errors: List[str] = []

    try:
        if 'status' in params:
            _assert_status(params, response, assertions, errors, fail_fast)
        _assert_body_contains(params, response, assertions, errors, fail_fast)
        _assert_json_paths(params, response, assertions, errors, fail_fast)
        _assert_headers_and_meta(params, response, assertions, errors, fail_fast)
        if 'schema' in params:
            _assert_json_schema(params, response, assertions, errors, fail_fast)
    except AssertionError:
        pass  # fail_fast triggered

    passed_count = sum(1 for a in assertions if a['passed'])
    failed_count = len(assertions) - passed_count

    logger.info(f"HTTP response assert: {passed_count}/{len(assertions)} passed")
    return {
        'ok': failed_count == 0,
        'passed': passed_count,
        'failed': failed_count,
        'total': len(assertions),
        'assertions': assertions,
        'errors': errors,
    }
