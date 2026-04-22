# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

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
    icon='CircleCheck',
    color='#22C55E',

    # Connection types
    input_types=['string', 'array'],
    output_types=['boolean'],


    can_receive_from=['*'],
    can_connect_to=['testing.*', 'test.*', 'flow.*', 'notify.*', 'data.*'],    params_schema={
        'collection': {
            'type': ['array', 'string'],
            'required': True,
            'description': 'Collection to search in'
        ,
                'description_key': 'modules.test.assert_contains.params.collection.description',
            'placeholder': 'collection_name',
            'label': 'Collection',
        },
        'value': {
            'type': ['string', 'number', 'boolean'],
            'required': True,
            'description': 'Value to find'
        ,
                'description_key': 'modules.test.assert_contains.params.value.description',
            'placeholder': 'value',
            'label': 'Value',
        },
        'message': {
            'type': 'string',
            'required': False,
            'description': 'Custom error message'
        ,
                'description_key': 'modules.test.assert_contains.params.message.description',
            'placeholder': 'Your message here',
            'label': 'Message',
        }
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
    },
    timeout_ms=5000,
)
class AssertContainsModule(BaseModule):
    """Assert that a collection contains a value.

    Two modes:
      1. Legacy single-value check: `collection` + `value` — passes/fails on
         a single `in` test.
      2. Pentest verdict mode: `source` (list-of-batch-results or wrapper
         dict with `data`) + `patterns` + `match_mode` ('any'|'all') +
         `on_match` + `on_no_match`. Returns a verdict string for the
         closed-loop aggregator.
    """

    module_name = "Assert Contains"
    module_description = "Assert that a collection contains a value"

    def validate_params(self) -> None:
        has_verdict_mode = 'source' in self.params and 'patterns' in self.params
        has_legacy = 'collection' in self.params and 'value' in self.params
        if not has_verdict_mode and not has_legacy:
            raise ValueError(
                "Parameter 'collection' + 'value' (legacy mode) "
                "or 'source' + 'patterns' (verdict mode) is required"
            )

    async def execute(self) -> Any:
        if 'source' in self.params and 'patterns' in self.params:
            return await self._execute_verdict_mode()
        return await self._execute_legacy_mode()

    async def _execute_legacy_mode(self) -> Any:
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

    async def _execute_verdict_mode(self) -> Any:
        """Pattern-match over http.batch output, return a verdict."""
        source = self.params.get('source')
        if isinstance(source, dict) and 'data' in source:
            source = source['data']

        patterns = list(self.params.get('patterns') or [])
        match_mode = self.params.get('match_mode', 'any')
        on_match = self.params.get('on_match', 'exploitable')
        on_no_match = self.params.get('on_no_match', 'sanitized')

        # Collect every string body to scan. Accepts a list-of-results, a
        # single result dict, or a bare string (for completeness).
        haystack_parts = []
        if isinstance(source, list):
            for entry in source:
                if isinstance(entry, dict):
                    body = entry.get('body', '')
                    if body:
                        haystack_parts.append(str(body))
                elif isinstance(entry, str):
                    haystack_parts.append(entry)
        elif isinstance(source, dict):
            haystack_parts.append(str(source.get('body', '')))
        elif isinstance(source, str):
            haystack_parts.append(source)

        haystack = "\n".join(haystack_parts).lower()

        matches = [p for p in patterns if p.lower() in haystack]
        if match_mode == 'all':
            found = len(matches) == len(patterns) and len(patterns) > 0
        else:  # 'any'
            found = len(matches) > 0

        verdict = on_match if found else on_no_match
        return {
            'passed': not found if on_match in ('exploitable', 'vulnerable') else found,
            'verdict': verdict,
            'matched_patterns': matches,
            'total_patterns': len(patterns),
            'source_length': len(haystack),
        }
