"""
Notion Query Database Module
Query pages from Notion database with filters and sorting.
"""
import logging
import os

import aiohttp

from ....registry import register_module
from .....constants import APIEndpoints, EnvVars


logger = logging.getLogger(__name__)


@register_module(
    module_id='api.notion.query_database',
    version='1.0.0',
    category='productivity',
    tags=['productivity', 'notion', 'api', 'database', 'query'],
    label='Notion Query Database',
    label_key='modules.api.notion.query_database.label',
    description='Query pages from Notion database with filters and sorting',
    description_key='modules.api.notion.query_database.description',
    icon='Search',
    color='#000000',

    # Connection types
    input_types=['any'],
    output_types=['any'],

    # Phase 2: Execution settings
    timeout=30,
    retryable=True,
    max_retries=3,
    concurrent_safe=True,

    # Phase 2: Security settings
    requires_credentials=True,
    handles_sensitive_data=True,
    required_permissions=['network.access'],

    params_schema={
        'api_key': {
            'type': 'string',
            'label': 'API Key',
            'label_key': 'modules.api.notion.query_database.params.api_key.label',
            'description': 'Notion integration token (defaults to env.NOTION_API_KEY)',
            'description_key': 'modules.api.notion.query_database.params.api_key.description',
            'placeholder': '${env.NOTION_API_KEY}',
            'required': False,
            'secret': True
        },
        'database_id': {
            'type': 'string',
            'label': 'Database ID',
            'label_key': 'modules.api.notion.query_database.params.database_id.label',
            'description': 'Notion database ID',
            'description_key': 'modules.api.notion.query_database.params.database_id.description',
            'required': True
        },
        'filter': {
            'type': 'object',
            'label': 'Filter',
            'label_key': 'modules.api.notion.query_database.params.filter.label',
            'description': 'Filter conditions for query',
            'description_key': 'modules.api.notion.query_database.params.filter.description',
            'required': False
        },
        'sorts': {
            'type': 'array',
            'label': 'Sorts',
            'label_key': 'modules.api.notion.query_database.params.sorts.label',
            'description': 'Sort order for results',
            'description_key': 'modules.api.notion.query_database.params.sorts.description',
            'required': False
        },
        'page_size': {
            'type': 'number',
            'label': 'Page Size',
            'label_key': 'modules.api.notion.query_database.params.page_size.label',
            'description': 'Number of results to return',
            'description_key': 'modules.api.notion.query_database.params.page_size.description',
            'default': 100,
            'required': False,
            'min': 1,
            'max': 100
        }
    },
    output_schema={
        'results': {'type': 'array', 'description': 'Array of page objects'},
        'count': {'type': 'number', 'description': 'Number of results returned'},
        'has_more': {'type': 'boolean', 'description': 'Whether there are more results'}
    },
    examples=[
        {
            'title': 'Query all pages',
            'title_key': 'modules.api.notion.query_database.examples.all.title',
            'params': {'database_id': 'your_database_id'}
        },
        {
            'title': 'Query with filter',
            'title_key': 'modules.api.notion.query_database.examples.filter.title',
            'params': {
                'database_id': 'your_database_id',
                'filter': {'property': 'Status', 'select': {'equals': 'In Progress'}},
                'sorts': [{'property': 'Created', 'direction': 'descending'}]
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    docs_url='https://developers.notion.com/reference/post-database-query'
)
async def notion_query_database(context):
    """Query Notion database"""
    params = context['params']

    api_key = params.get('api_key') or os.getenv(EnvVars.NOTION_API_KEY)
    if not api_key:
        raise ValueError(f"API key required: provide 'api_key' param or set {EnvVars.NOTION_API_KEY} env variable")

    database_id = params['database_id']
    url = APIEndpoints.notion_database_query(database_id)

    headers = {
        'Authorization': f'Bearer {api_key}',
        'Notion-Version': APIEndpoints.NOTION_API_VERSION,
        'Content-Type': 'application/json'
    }

    payload = {}
    if params.get('filter'):
        payload['filter'] = params['filter']
    if params.get('sorts'):
        payload['sorts'] = params['sorts']
    if params.get('page_size'):
        payload['page_size'] = params['page_size']

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload) as response:
            if response.status != 200:
                error_text = await response.text()
                raise Exception(f"Notion API error ({response.status}): {error_text}")

            result = await response.json()

    return {
        'results': result['results'],
        'count': len(result['results']),
        'has_more': result.get('has_more', False)
    }
