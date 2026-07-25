# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Reverse Scripts Module

Inspect JavaScript sources loaded by the debugged page: list every parsed
script, fetch a script's full source, or search across all sources for a
string or regex (via CDP's Debugger.searchInContent — no hand-rolled grep).
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field
from ...schema.constants import FieldGroup
from ...types import StabilityLevel


@register_module(
    module_id='reverse.scripts',
    version='1.0.0',
    category='reverse',
    stability=StabilityLevel.BETA,
    tags=['reverse', 'debugger', 'cdp', 'scripts', 'source'],
    label='Debugger Scripts',
    label_key='modules.reverse.scripts.label',
    description='List, fetch, or search loaded JavaScript sources',
    description_key='modules.reverse.scripts.description',
    icon='FileSearch',
    color='#DC2626',

    input_types=['object'],
    output_types=['object'],

    can_receive_from=['reverse.*', 'flow.*'],
    can_connect_to=['reverse.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*'],

    params_schema=compose(
        field(
            'action',
            type='select',
            label='Action',
            label_key='modules.reverse.scripts.params.action.label',
            description='Script operation to perform',
            required=True,
            options=[
                {'value': 'list', 'label': 'List loaded scripts'},
                {'value': 'get_source', 'label': 'Get full script source'},
                {'value': 'search', 'label': 'Search script sources'},
            ],
            group=FieldGroup.BASIC,
        ),
        field(
            'script_id',
            type='string',
            label='Script ID',
            label_key='modules.reverse.scripts.params.script_id.label',
            description='Script ID from a previous "list" call (required for get_source; optional filter for search)',
            placeholder='42',
            required=False,
            showIf={"action": {"$in": ["get_source", "search"]}},
            group=FieldGroup.OPTIONS,
        ),
        field(
            'query',
            type='string',
            label='Search Query',
            label_key='modules.reverse.scripts.params.query.label',
            description='Text or regex pattern to search for across loaded sources',
            placeholder='function login(',
            required=False,
            showIf={"action": {"$in": ["search"]}},
            group=FieldGroup.OPTIONS,
        ),
        field(
            'is_regex',
            type='boolean',
            label='Is Regex',
            label_key='modules.reverse.scripts.params.is_regex.label',
            description='Treat query as a regular expression',
            default=False,
            required=False,
            showIf={"action": {"$in": ["search"]}},
            group=FieldGroup.ADVANCED,
        ),
        field(
            'case_sensitive',
            type='boolean',
            label='Case Sensitive',
            label_key='modules.reverse.scripts.params.case_sensitive.label',
            description='Match query case-sensitively',
            default=False,
            required=False,
            showIf={"action": {"$in": ["search"]}},
            group=FieldGroup.ADVANCED,
        ),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.reverse.scripts.output.status.description'},
        'scripts': {'type': 'array', 'description': 'Loaded scripts (list action)',
                'description_key': 'modules.reverse.scripts.output.scripts.description'},
        'source': {'type': 'string', 'description': 'Full script source (get_source action)',
                'description_key': 'modules.reverse.scripts.output.source.description'},
        'matches': {'type': 'array', 'description': 'Search matches grouped by script (search action)',
                'description_key': 'modules.reverse.scripts.output.matches.description'},
    },
    examples=[
        {'name': 'List loaded scripts', 'params': {'action': 'list'}},
        {'name': 'Get a script source', 'params': {'action': 'get_source', 'script_id': '42'}},
        {'name': 'Search for a function', 'params': {'action': 'search', 'query': 'function login('}},
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=30000,
    required_permissions=['browser.debug'],
)
class ReverseScriptsModule(BaseModule):
    """List, fetch, or search JavaScript sources loaded by the debugged page."""

    module_name = "Debugger Scripts"
    module_description = "List, fetch, or search loaded JavaScript sources"
    required_permission = "browser.debug"

    def validate_params(self) -> None:
        self.action = self.params.get('action')
        if self.action not in ('list', 'get_source', 'search'):
            raise ValueError(f"Invalid action: {self.action}. Must be list, get_source, or search")

        self.script_id = self.params.get('script_id')
        if self.action == 'get_source' and not self.script_id:
            raise ValueError("get_source requires script_id")

        self.query = self.params.get('query')
        if self.action == 'search' and not self.query:
            raise ValueError("search requires query")

        self.is_regex = self.params.get('is_regex', False)
        self.case_sensitive = self.params.get('case_sensitive', False)

    async def execute(self) -> Dict[str, Any]:
        session = self.context.get('reverse_session')
        if not session:
            raise RuntimeError("No active debugger session. Please run reverse.attach first")

        if self.action == 'list':
            scripts = session.list_scripts()
            return {'status': 'success', 'scripts': scripts, 'count': len(scripts)}

        if self.action == 'get_source':
            source = await session.get_script_source(self.script_id)
            return {'status': 'success', 'script_id': self.script_id, 'source': source}

        matches = await session.search_scripts(
            query=self.query,
            is_regex=self.is_regex,
            case_sensitive=self.case_sensitive,
            script_id=self.script_id,
        )
        return {'status': 'success', 'matches': matches, 'count': len(matches)}
