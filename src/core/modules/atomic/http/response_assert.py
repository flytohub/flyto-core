# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
HTTP Response Assert Module
Assert and validate HTTP response properties

HOW FAR THIS MODULE FOLLOWS REALITY

The only module in the http group that reaches VERIFIED, and the only one that
could: `verified` is defined as "a postcondition was evaluated and it held",
and evaluating caller-supplied predicates is the entire job here. The
predicates come from parameters rather than from the decorator, so `claim_by`
is CALLER -- which is also what makes a failure FAILED rather than
INDETERMINATE. A contract somebody stated was broken; that is not "we could not
tell".

WHAT IS AND IS NOT VERIFIED, because this is where a false green would live.
The postcondition declared below says "against the response object it was
given", and that clause is the whole limit. This module opens no socket. It
grades a response another step captured, and it cannot know whether that
response is stale, from a different request, or a literal the caller typed. So
`verified` here means the assertions held over the recorded response -- never
that the HTTP effect the response describes actually happened. The step that
made the request says how far THAT was followed; this one says whether what
came back matched.

THE VACUOUS PASS is the reason `total == 0` is INDETERMINATE and not VERIFIED.
Supply no assertion parameters and this module returns `ok: True, passed: 0,
failed: 0` -- a green tick for having checked nothing, and byte-identical to a
run where everything passed. It is reachable by accident: `_assert_status` has
branches for an int, a list and a `"200-299"` range string, and none for a bare
`"200"`, so a status that arrives as a string from a resolved template is
silently not asserted. Nothing was evaluated, so there is nothing a rung could
be about, and INDETERMINATE says exactly that.

A SKIPPED CHECK IS NOT A FAILED ONE. When `jsonschema` is not installed the
schema check is recorded as a failed assertion, which makes `ok` false for a
reason that has nothing to do with the response. Those entries are marked
`skipped` so the envelope can separate them: a run whose only non-passing entry
is a skip is INDETERMINATE -- we could not check -- while a real assertion
failure alongside it is FAILED, because a broken contract is the answer
somebody has to act on.
"""

import logging
import re
from typing import Any, Dict, List

from ....engine.outcome import ClaimBy, Outcome, envelope
from ...registry import register_module
from ...schema import compose, field, presets
from ...schema.presets.assertion import REGEX_PATTERN as ASSERTION_REGEX_PATTERN

logger = logging.getLogger(__name__)

#: The predicate this module evaluates, declared so `ceiling_for` permits
#: VERIFIED at all. Every clause in it is load-bearing: "supplied by the
#: caller" twice, because both the predicates and the thing they are evaluated
#: against come from parameters and neither is re-read from the network.
POSTCONDITION = (
    'every assertion supplied by the caller was evaluated against the response '
    'object supplied by the caller, and all of them held'
)


def _assertion_outcome(
    assertions: List[Dict[str, Any]], *, stopped_early: bool
) -> Dict[str, Any]:
    """The rung for one assert run, decided from what was actually evaluated.

    Four answers, in the order they take precedence:

    * nothing was evaluated             -> INDETERMINATE. `ok: True` on this
      path means "nothing was checked" and reads identically to "everything
      passed", so no rung may rest on it.
    * a real assertion did not hold     -> FAILED, claim_by CALLER. The caller
      stated the predicate; it was evaluated; it was false.
    * the only non-passing entries are
      skips (jsonschema missing)        -> INDETERMINATE. We could not check.
    * everything held                   -> VERIFIED, claim_by CALLER, within
      the limit the declared postcondition names.

    `stopped_early` records that `fail_fast` aborted the run, so a reader can
    tell that the assertions listed are a prefix of the ones requested rather
    than all of them.
    """
    total = len(assertions)
    skipped = [a for a in assertions if a.get('skipped')]
    failed = [a for a in assertions if not a['passed'] and not a.get('skipped')]
    measured = {
        'kind': 'assertions_evaluated',
        'total': total,
        'passed': sum(1 for a in assertions if a['passed']),
        'failed': len(failed),
        'skipped': len(skipped),
        'stopped_early': stopped_early,
        'measured_by': 'the predicates evaluated in this module, one per entry',
    }

    if total == 0:
        return envelope(
            Outcome.INDETERMINATE,
            claim_by=ClaimBy.NONE,
            effects=[dict(
                measured,
                kind='no_assertions_evaluated',
                detail=(
                    'No assertion parameter was recognised, so nothing was '
                    'checked. ok: true here means "nothing was checked" and '
                    'not "everything passed" -- note that a status supplied as '
                    'the string "200" matches none of the status branches and '
                    'lands here.'
                ),
            )],
        )

    if failed:
        return envelope(
            Outcome.FAILED,
            claim_by=ClaimBy.CALLER,
            postcondition=POSTCONDITION,
            effects=[dict(
                measured,
                kind='assertion_did_not_hold',
                first_failure=failed[0].get('name'),
                detail=(
                    'A predicate the caller stated was evaluated and was '
                    'false. FAILED rather than INDETERMINATE precisely because '
                    'the caller stated it: there is a contract to break.'
                ),
            )],
        )

    if skipped:
        return envelope(
            Outcome.INDETERMINATE,
            claim_by=ClaimBy.CALLER,
            postcondition=POSTCONDITION,
            effects=[dict(
                measured,
                kind='assertion_not_evaluated',
                detail=(
                    'Every assertion that ran held, but at least one could not '
                    'be evaluated at all -- the JSON schema check needs the '
                    'jsonschema package. Not being able to check is not the '
                    'same as checking and failing.'
                ),
            )],
        )

    return envelope(
        Outcome.VERIFIED,
        claim_by=ClaimBy.CALLER,
        postcondition=POSTCONDITION,
        effects=[dict(
            measured,
            detail=(
                'Every assertion held against the response object it was '
                'given. This module makes no request and re-reads nothing, so '
                'this is not evidence that the effect the response describes '
                'happened -- only that the recorded response matches.'
            ),
        )],
    )


def _get_nested_value(obj: Any, path: str) -> Any:
    """Get value from nested object using dot notation path."""
    from core.engine.variable_resolver import VariableResolver
    if not path:
        return obj
    return VariableResolver.get_nested_value(obj, path)


def _add_assertion(
    assertions: List[Dict[str, Any]], errors: List[str],
    name: str, passed: bool, expected: Any, actual: Any,
    message: str = '', fail_fast: bool = False, skipped: bool = False,
):
    """Record an assertion result and optionally raise on failure.

    ``skipped`` marks an entry that could not be evaluated rather than one that
    was evaluated and was false. It still counts as not-passed, so ``ok`` is
    unchanged, but the outcome envelope reads it to tell INDETERMINATE from
    FAILED -- a missing library is not a broken contract.
    """
    assertion = {'name': name, 'passed': passed, 'expected': expected, 'actual': actual}
    if message:
        assertion['message'] = message
    if skipped:
        assertion['skipped'] = True
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
                       'jsonschema library not installed', fail_fast, skipped=True)


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

    # The predicate that makes VERIFIED reachable here. `ceiling_for` caps an
    # undeclared module at OBSERVED because there would be no predicate the
    # claim could be about; this module has one, evaluates it, and says so.
    postcondition=POSTCONDITION,

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
        ASSERTION_REGEX_PATTERN(key='body_matches', label='Body Matches Regex',
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
                'description_key': 'modules.http.response_assert.output.errors.description'},
        'stopped_early': {
            'type': 'boolean',
            'description': (
                'True when fail_fast aborted the run, so the assertions listed '
                'are a prefix of the ones requested'
            ),
            'description_key': 'modules.http.response_assert.output.stopped_early.description'},
        'outcome': {
            'type': 'object',
            'description': (
                'How far this check was followed: "verified" when every '
                'assertion held against the response object supplied -- which '
                'is not evidence the request itself succeeded -- "failed" when '
                'one did not hold, "indeterminate" when nothing was evaluated '
                'or a check could not run'
            ),
            'description_key': 'modules.http.response_assert.output.outcome.description'}
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
    stopped_early = False

    try:
        if 'status' in params:
            _assert_status(params, response, assertions, errors, fail_fast)
        _assert_body_contains(params, response, assertions, errors, fail_fast)
        _assert_json_paths(params, response, assertions, errors, fail_fast)
        _assert_headers_and_meta(params, response, assertions, errors, fail_fast)
        if 'schema' in params:
            _assert_json_schema(params, response, assertions, errors, fail_fast)
    except AssertionError:
        # fail_fast triggered. Recorded rather than swallowed: the assertions
        # below are a prefix of the ones requested, and a consumer reading
        # total=1 has to be able to tell "one check ran" from "one was asked".
        stopped_early = True

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
        'stopped_early': stopped_early,
        'outcome': _assertion_outcome(assertions, stopped_early=stopped_early),
    }
