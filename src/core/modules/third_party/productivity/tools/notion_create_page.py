"""
Notion Create Page Module
Create a new page in Notion database.
"""
import logging
import os

import aiohttp

from ....registry import register_module
from .....constants import APIEndpoints, EnvVars


logger = logging.getLogger(__name__)


@register_module(
    module_id='api.notion.create_page',
    version='1.0.0',
    category='productivity',
    tags=['productivity', 'notion', 'api', 'database', 'page'],
    label='Notion Create Page',
    label_key='modules.api.notion.create_page.label',
    description='Create a new page in Notion database',
    description_key='modules.api.notion.create_page.description',
    icon='FileText',
    color='#000000',

    # Connection types
    input_types=['any'],
    output_types=['any'],

    # Phase 2: Execution settings
    timeout=30,
    retryable=False,
    concurrent_safe=True,

    # Phase 2: Security settings
    requires_credentials=True,
    handles_sensitive_data=True,
    required_permissions=['network.access'],

    params_schema={
        'api_key': {
            'type': 'string',
            'label': 'API Key',
            'label_key': 'modules.api.notion.create_page.params.api_key.label',
            'description': 'Notion integration token (defaults to env.NOTION_API_KEY)',
            'description_key': 'modules.api.notion.create_page.params.api_key.description',
            'placeholder': '${env.NOTION_API_KEY}',
            'required': False,
            'secret': True,
            'help': 'Create integration at https://www.notion.so/my-integrations'
        },
        'database_id': {
            'type': 'string',
            'label': 'Database ID',
            'label_key': 'modules.api.notion.create_page.params.database_id.label',
            'description': 'Notion database ID (32-char hex string)',
            'description_key': 'modules.api.notion.create_page.params.database_id.description',
            'required': True,
            'placeholder': 'a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6'
        },
        'properties': {
            'type': 'object',
            'label': 'Properties',
            'label_key': 'modules.api.notion.create_page.params.properties.label',
            'description': 'Page properties (title, text, select, etc.)',
            'description_key': 'modules.api.notion.create_page.params.properties.description',
            'required': True,
            'help': 'Must match your database schema'
        },
        'content': {
            'type': 'array',
            'label': 'Content Blocks',
            'label_key': 'modules.api.notion.create_page.params.content.label',
            'description': 'Page content as Notion blocks',
            'description_key': 'modules.api.notion.create_page.params.content.description',
            'required': False
        }
    },
    output_schema={
        'page_id': {'type': 'string', 'description': 'Created page ID'},
        'url': {'type': 'string', 'description': 'URL to the created page'},
        'created_time': {'type': 'string', 'description': 'Page creation timestamp'}
    },
    examples=[
        {
            'title': 'Create task page',
            'title_key': 'modules.api.notion.create_page.examples.task.title',
            'params': {
                'database_id': 'your_database_id',
                'properties': {
                    'Name': {'title': [{'text': {'content': 'New Task'}}]},
                    'Status': {'select': {'name': 'In Progress'}},
                    'Priority': {'select': {'name': 'High'}}
                }
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    docs_url='https://developers.notion.com/reference/post-page'
)
async def notion_create_page(context):
    """Create page in Notion database"""
    params = context['params']

    api_key = params.get('api_key') or os.getenv(EnvVars.NOTION_API_KEY)
    if not api_key:
        raise ValueError(f"API key required: provide 'api_key' param or set {EnvVars.NOTION_API_KEY} env variable")

    url = APIEndpoints.notion_pages()
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Notion-Version': APIEndpoints.NOTION_API_VERSION,
        'Content-Type': 'application/json'
    }

    payload = {
        'parent': {'database_id': params['database_id']},
        'properties': params['properties']
    }

    if params.get('content'):
        payload['children'] = params['content']

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload) as response:
            if response.status != 200:
                error_text = await response.text()
                raise Exception(f"Notion API error ({response.status}): {error_text}")

            result = await response.json()

    return {
        'page_id': result['id'],
        'url': result['url'],
        'created_time': result['created_time']
    }
