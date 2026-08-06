# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Regex Match Module
Find matches of a pattern in text.
"""
import re
from typing import Any, Dict

from ...errors import ValidationError
from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ._safe import compile_guarded, run_regex_safely, validate_regex_inputs


@register_module(
    module_id='regex.match',
    version='1.0.0',
    category='regex',
    tags=['regex', 'match', 'find', 'pattern', 'extract'],
    label='Regex Match',
    label_key='modules.regex.match.label',
    description='Find all matches of a pattern in text',
    description_key='modules.regex.match.description',
    icon='Search',
    color='#EC4899',
    input_types=['string'],
    output_types=['array'],

    can_receive_from=['*'],
    can_connect_to=['array.*', 'string.*', 'data.*', 'flow.*'],

    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema=compose(
        field(
            'text',
            type='string',
            label='Text',
            label_key='modules.regex.match.params.text.label',
            description='Text to search',
            description_key='modules.regex.match.params.text.description',
            required=True,
            placeholder='abc123def456',
            group=FieldGroup.BASIC,
        ),
        field(
            'pattern',
            type='string',
            label='Pattern',
            label_key='modules.regex.match.params.pattern.label',
            description='Regular expression pattern',
            description_key='modules.regex.match.params.pattern.description',
            required=True,
            placeholder='\\d+',
            group=FieldGroup.BASIC,
        ),
        field(
            'ignore_case',
            type='boolean',
            label='Ignore Case',
            label_key='modules.regex.match.params.ignore_case.label',
            description='Case-insensitive matching',
            description_key='modules.regex.match.params.ignore_case.description',
            default=False,
            group=FieldGroup.OPTIONS,
        ),
        field(
            'first_only',
            type='boolean',
            label='First Only',
            label_key='modules.regex.match.params.first_only.label',
            description='Return only the first match',
            description_key='modules.regex.match.params.first_only.description',
            default=False,
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'matches': {
            'type': 'array',
            'description': 'List of matches',
            'description_key': 'modules.regex.match.output.matches.description'
        },
        'count': {
            'type': 'number',
            'description': 'Number of matches',
            'description_key': 'modules.regex.match.output.count.description'
        },
        'groups': {
            'type': 'array',
            'description': 'Captured groups from each match',
            'description_key': 'modules.regex.match.output.groups.description'
        }
    },
    timeout_ms=5000,
)
async def regex_match(context: Dict[str, Any]) -> Dict[str, Any]:
    """Find all matches of a pattern in text."""
    params = context['params']
    text = params.get('text')
    pattern = params.get('pattern')
    ignore_case = params.get('ignore_case', False)
    first_only = params.get('first_only', False)

    if text is None:
        raise ValidationError("Missing required parameter: text", field="text")

    if pattern is None:
        raise ValidationError("Missing required parameter: pattern", field="pattern")

    flags = re.IGNORECASE if ignore_case else 0
    text_str = str(text)
    validate_regex_inputs(pattern, text_str)
    compiled = compile_guarded(pattern, flags)

    def _run():
        if first_only:
            match = compiled.search(text_str)
            if match:
                return [match.group()], ([list(match.groups())] if match.groups() else [])
            return [], []
        all_matches = compiled.finditer(text_str)
        return (
            [m.group() for m in all_matches],
            [list(m.groups()) for m in all_matches if m.groups()],
        )

    matches, groups = await run_regex_safely(_run)

    return {
        'ok': True,
        'data': {
            'matches': matches,
            'count': len(matches),
            'groups': groups
        }
    }
