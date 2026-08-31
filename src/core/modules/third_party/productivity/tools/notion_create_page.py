# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Notion Create Page Module
Create a new page in Notion database.

HOW FAR THE CREATE IS FOLLOWED

ACCEPTED. Notion answers 200 with the page object it says it just made, and
that object carries an id, a URL and a created_time that this module could not
have produced from its own inputs -- which is what puts it above DISPATCHED,
the rung the engine stamps on a module that reports nothing.

It is not OBSERVED, and the reason is worth stating plainly because a created
resource is where the temptation is strongest: a 200 body is the peer reporting
on its own work. To observe the page this module would have to GET it back and
compare; it sends one request and reads the reply to that request, exactly like
`http.request`, which settled this same question the same way for every 201
Created in the product.

THE ERROR PATH CARRIES NOTHING, and this is the module in the group where that
hurts most. Any non-200 raises, so the payload is discarded and no rung
survives. A 5xx or a timeout on a POST that creates something is the textbook
INDETERMINATE -- the page may exist -- and a caller who retries may end up with
two. Today that arrives as an ordinary step failure. `api.github.create_issue`
can say it because it returns an error dict instead of raising; this module
cannot, and changing which one it does is a decision about step semantics.
"""
import logging
import os

import aiohttp

from ....registry import register_module
from .....constants import APIEndpoints, EnvVars
from .....engine.outcome import ClaimBy, Outcome, envelope


logger = logging.getLogger(__name__)


@register_module(
    module_id='api.notion.create_page',
    can_connect_to=['*'],
    can_receive_from=['data.*', 'http.*', 'flow.*', 'start'],
    version='1.0.0',
    category='productivity',
    tags=['productivity', 'notion', 'api', 'database', 'page', 'ssrf_protected'],
    label='Notion Create Page',
    label_key='modules.api.notion.create_page.label',
    description='Create a new page in Notion database',
    description_key='modules.api.notion.create_page.description',
    icon='FileText',
    color='#000000',

    # Connection types
    input_types=['object'],
    output_types=['json', 'object'],

    # Phase 2: Execution settings
    timeout_ms=30000,
    retryable=False,
    concurrent_safe=True,

    # Phase 2: Security settings
    requires_credentials=True,
    credential_keys=['NOTION_TOKEN'],
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
            'sensitive': True,
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
        'page_id': {'type': 'string', 'description': 'Created page ID',
                'description_key': 'modules.api.notion.create_page.output.page_id.description'},
        'url': {'type': 'string', 'description': 'URL to the created page',
                'description_key': 'modules.api.notion.create_page.output.url.description'},
        'created_time': {'type': 'string', 'description': 'Page creation timestamp',
                'description_key': 'modules.api.notion.create_page.output.created_time.description'},
        'outcome': {'type': 'object', 'description': (
                    'How far the effect was followed. Always "accepted" on the '
                    'path that returns: Notion says it created the page and names '
                    'it, and nothing reads the page back. Error paths raise, so '
                    'they carry no outcome at all'),
                'description_key': 'modules.api.notion.create_page.output.outcome.description'}
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

            status = response.status
            result = await response.json()

    return {
        'page_id': result['id'],
        'url': result['url'],
        'created_time': result['created_time'],
        'outcome': envelope(
            Outcome.ACCEPTED,
            claim_by=ClaimBy.NONE,
            effects=[
                {
                    'kind': 'notion_reply_read',
                    'status': status,
                    'measured_by': 'response.status on the reply to this request',
                    'detail': (
                        'A server received this request and chose a reply. That is '
                        'the whole distance between dispatched and accepted, and '
                        'the whole distance this module travels.'
                    ),
                },
                {
                    'kind': 'page_reported_created',
                    'page_id': result['id'],
                    'created_time': result['created_time'],
                    'measured_by': 'id and created_time in the 200 body Notion returned',
                    'detail': (
                        'Notion asserting that it created a page, and naming it. '
                        'Server-assigned, so it is more than an echo of the '
                        'properties sent -- and still the peer reporting on its own '
                        'work, so it is not an observation. Nothing here reads the '
                        'page back, and nothing checks that the properties written '
                        'are the properties requested.'
                    ),
                },
            ],
        ),
    }
