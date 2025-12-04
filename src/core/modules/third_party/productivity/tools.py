"""
Productivity API Integration Modules
Provides integrations with productivity tools like Notion and Google Sheets
"""
import json
import logging
import os

import aiohttp

from ...registry import register_module
from ....constants import APIEndpoints, EnvVars


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
    timeout=30,  # API calls should complete within 30s
    retryable=False,  # Could create duplicate pages if retried
    concurrent_safe=True,  # Multiple API calls can run in parallel

    # Phase 2: Security settings
    requires_credentials=True,  # Needs NOTION_API_KEY
    handles_sensitive_data=True,  # Page content may be sensitive
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
        'page_id': {
            'type': 'string',
            'description': 'Created page ID'
        },
        'url': {
            'type': 'string',
            'description': 'URL to the created page'
        },
        'created_time': {
            'type': 'string',
            'description': 'Page creation timestamp'
        }
    },
    examples=[
        {
            'title': 'Create task page',
            'title_key': 'modules.api.notion.create_page.examples.task.title',
            'params': {
                'database_id': 'your_database_id',
                'properties': {
                    'Name': {
                        'title': [{'text': {'content': 'New Task'}}]
                    },
                    'Status': {
                        'select': {'name': 'In Progress'}
                    },
                    'Priority': {
                        'select': {'name': 'High'}
                    }
                }
            }
        },
        {
            'title': 'Create page with content',
            'title_key': 'modules.api.notion.create_page.examples.content.title',
            'params': {
                'database_id': 'your_database_id',
                'properties': {
                    'Name': {
                        'title': [{'text': {'content': 'Meeting Notes'}}]
                    }
                },
                'content': [
                    {
                        'object': 'block',
                        'type': 'paragraph',
                        'paragraph': {
                            'rich_text': [{'text': {'content': 'Meeting summary here'}}]
                        }
                    }
                ]
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

    # Get API key
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
    timeout=30,  # API calls should complete within 30s
    retryable=True,  # Network errors can be retried
    max_retries=3,
    concurrent_safe=True,  # Multiple API calls can run in parallel

    # Phase 2: Security settings
    requires_credentials=True,  # Needs NOTION_API_KEY
    handles_sensitive_data=True,  # Database content may be sensitive
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
        'results': {
            'type': 'array',
            'description': 'Array of page objects'
        },
        'count': {
            'type': 'number',
            'description': 'Number of results returned'
        },
        'has_more': {
            'type': 'boolean',
            'description': 'Whether there are more results'
        }
    },
    examples=[
        {
            'title': 'Query all pages',
            'title_key': 'modules.api.notion.query_database.examples.all.title',
            'params': {
                'database_id': 'your_database_id'
            }
        },
        {
            'title': 'Query with filter',
            'title_key': 'modules.api.notion.query_database.examples.filter.title',
            'params': {
                'database_id': 'your_database_id',
                'filter': {
                    'property': 'Status',
                    'select': {'equals': 'In Progress'}
                },
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

    # Get API key
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


@register_module(
    module_id='api.google_sheets.read',
    version='1.0.0',
    category='productivity',
    tags=['productivity', 'google', 'sheets', 'spreadsheet', 'read', 'data'],
    label='Google Sheets Read',
    label_key='modules.api.google_sheets.read.label',
    description='Read data from Google Sheets spreadsheet',
    description_key='modules.api.google_sheets.read.description',
    icon='Table',
    color='#0F9D58',

    # Connection types
    input_types=['any'],
    output_types=['any'],

    # Phase 2: Execution settings
    timeout=30,  # API calls should complete within 30s
    retryable=True,  # Network errors can be retried
    max_retries=3,
    concurrent_safe=True,  # Multiple API calls can run in parallel

    # Phase 2: Security settings
    requires_credentials=True,  # Needs Google credentials
    handles_sensitive_data=True,  # Spreadsheet data may be sensitive
    required_permissions=['network.access'],

    params_schema={
        'credentials': {
            'type': 'object',
            'label': 'Service Account Credentials',
            'label_key': 'modules.api.google_sheets.read.params.credentials.label',
            'description': 'Google service account JSON credentials (defaults to env.GOOGLE_CREDENTIALS_JSON)',
            'description_key': 'modules.api.google_sheets.read.params.credentials.description',
            'required': False,
            'secret': True,
            'help': 'Create at https://console.cloud.google.com/iam-admin/serviceaccounts'
        },
        'spreadsheet_id': {
            'type': 'string',
            'label': 'Spreadsheet ID',
            'label_key': 'modules.api.google_sheets.read.params.spreadsheet_id.label',
            'description': 'Google Sheets spreadsheet ID (from URL)',
            'description_key': 'modules.api.google_sheets.read.params.spreadsheet_id.description',
            'required': True,
            'placeholder': '1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms',
            'help': 'Found in URL: /spreadsheets/d/{ID}/edit'
        },
        'range': {
            'type': 'string',
            'label': 'Range',
            'label_key': 'modules.api.google_sheets.read.params.range.label',
            'description': 'A1 notation range to read',
            'description_key': 'modules.api.google_sheets.read.params.range.description',
            'required': True,
            'placeholder': 'Sheet1!A1:E100',
            'help': 'Example: Sheet1!A1:E100 or just A1:E100 for first sheet'
        },
        'include_header': {
            'type': 'boolean',
            'label': 'Include Header',
            'label_key': 'modules.api.google_sheets.read.params.include_header.label',
            'description': 'Parse first row as column headers',
            'description_key': 'modules.api.google_sheets.read.params.include_header.description',
            'default': True,
            'required': False
        }
    },
    output_schema={
        'values': {
            'type': 'array',
            'description': 'Array of rows (each row is array of values)'
        },
        'data': {
            'type': 'array',
            'description': 'Array of row objects (if include_header=true)'
        },
        'row_count': {
            'type': 'number',
            'description': 'Number of rows read'
        }
    },
    examples=[
        {
            'title': 'Read with headers',
            'title_key': 'modules.api.google_sheets.read.examples.headers.title',
            'params': {
                'spreadsheet_id': '1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms',
                'range': 'Sheet1!A1:D100',
                'include_header': True
            }
        },
        {
            'title': 'Read raw values',
            'title_key': 'modules.api.google_sheets.read.examples.raw.title',
            'params': {
                'spreadsheet_id': '1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms',
                'range': 'Sheet1!A1:D100',
                'include_header': False
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    docs_url='https://developers.google.com/sheets/api/reference/rest/v4/spreadsheets.values/get'
)
async def google_sheets_read(context):
    """Read from Google Sheets"""
    params = context['params']

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        import asyncio
    except ImportError:
        raise ImportError("google-api-python-client package required. Install with: pip install google-api-python-client google-auth")

    # Get credentials
    credentials_json = params.get('credentials')
    if not credentials_json:
        credentials_json = os.getenv('GOOGLE_CREDENTIALS_JSON')
    if not credentials_json:
        raise ValueError("Credentials required: provide 'credentials' param or set GOOGLE_CREDENTIALS_JSON env variable")

    # Parse credentials
    if isinstance(credentials_json, str):
        credentials_json = json.loads(credentials_json)

    # Create credentials
    credentials = service_account.Credentials.from_service_account_info(
        credentials_json,
        scopes=['https://www.googleapis.com/auth/spreadsheets.readonly']
    )

    # Build service
    service = build('sheets', 'v4', credentials=credentials)

    # Read values (run in thread pool since it's not async)
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        lambda: service.spreadsheets().values().get(
            spreadsheetId=params['spreadsheet_id'],
            range=params['range']
        ).execute()
    )

    values = result.get('values', [])

    # Parse with headers if requested
    if params.get('include_header', True) and values:
        headers = values[0]
        data = []
        for row in values[1:]:
            # Pad row if shorter than headers
            row_padded = row + [''] * (len(headers) - len(row))
            data.append(dict(zip(headers, row_padded)))

        return {
            'values': values,
            'data': data,
            'row_count': len(values)
        }
    else:
        return {
            'values': values,
            'row_count': len(values)
        }


@register_module(
    module_id='api.google_sheets.write',
    version='1.0.0',
    category='productivity',
    tags=['productivity', 'google', 'sheets', 'spreadsheet', 'write', 'data'],
    label='Google Sheets Write',
    label_key='modules.api.google_sheets.write.label',
    description='Write data to Google Sheets spreadsheet',
    description_key='modules.api.google_sheets.write.description',
    icon='Table',
    color='#0F9D58',

    # Connection types
    input_types=['any'],
    output_types=['any'],

    # Phase 2: Execution settings
    timeout=30,  # API calls should complete within 30s
    retryable=False,  # Could create duplicate data if retried
    concurrent_safe=True,  # Multiple API calls can run in parallel

    # Phase 2: Security settings
    requires_credentials=True,  # Needs Google credentials
    handles_sensitive_data=True,  # Spreadsheet data may be sensitive
    required_permissions=['network.access'],

    params_schema={
        'credentials': {
            'type': 'object',
            'label': 'Service Account Credentials',
            'label_key': 'modules.api.google_sheets.write.params.credentials.label',
            'description': 'Google service account JSON credentials (defaults to env.GOOGLE_CREDENTIALS_JSON)',
            'description_key': 'modules.api.google_sheets.write.params.credentials.description',
            'required': False,
            'secret': True
        },
        'spreadsheet_id': {
            'type': 'string',
            'label': 'Spreadsheet ID',
            'label_key': 'modules.api.google_sheets.write.params.spreadsheet_id.label',
            'description': 'Google Sheets spreadsheet ID (from URL)',
            'description_key': 'modules.api.google_sheets.write.params.spreadsheet_id.description',
            'required': True,
            'placeholder': '1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms'
        },
        'range': {
            'type': 'string',
            'label': 'Range',
            'label_key': 'modules.api.google_sheets.write.params.range.label',
            'description': 'A1 notation range to write',
            'description_key': 'modules.api.google_sheets.write.params.range.description',
            'required': True,
            'placeholder': 'Sheet1!A1'
        },
        'values': {
            'type': 'array',
            'label': 'Values',
            'label_key': 'modules.api.google_sheets.write.params.values.label',
            'description': 'Array of rows to write (each row is array of values)',
            'description_key': 'modules.api.google_sheets.write.params.values.description',
            'required': True,
            'help': 'Example: [["Name", "Age"], ["John", 30], ["Jane", 25]]'
        },
        'value_input_option': {
            'type': 'string',
            'label': 'Value Input Option',
            'label_key': 'modules.api.google_sheets.write.params.value_input_option.label',
            'description': 'How to interpret input values',
            'description_key': 'modules.api.google_sheets.write.params.value_input_option.description',
            'default': 'USER_ENTERED',
            'required': False,
            'options': [
                {'value': 'USER_ENTERED', 'label': 'User Entered (parse formulas)'},
                {'value': 'RAW', 'label': 'Raw (no parsing)'}
            ]
        }
    },
    output_schema={
        'updated_range': {
            'type': 'string',
            'description': 'Range that was updated'
        },
        'updated_rows': {
            'type': 'number',
            'description': 'Number of rows updated'
        },
        'updated_columns': {
            'type': 'number',
            'description': 'Number of columns updated'
        },
        'updated_cells': {
            'type': 'number',
            'description': 'Number of cells updated'
        }
    },
    examples=[
        {
            'title': 'Write data with headers',
            'title_key': 'modules.api.google_sheets.write.examples.headers.title',
            'params': {
                'spreadsheet_id': '1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms',
                'range': 'Sheet1!A1',
                'values': [
                    ['Name', 'Email', 'Status'],
                    ['John Doe', 'john@example.com', 'Active'],
                    ['Jane Smith', 'jane@example.com', 'Active']
                ]
            }
        },
        {
            'title': 'Append scraped data',
            'title_key': 'modules.api.google_sheets.write.examples.append.title',
            'params': {
                'spreadsheet_id': '1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms',
                'range': 'Sheet1!A1',
                'values': '${extract.data}'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    docs_url='https://developers.google.com/sheets/api/reference/rest/v4/spreadsheets.values/update'
)
async def google_sheets_write(context):
    """Write to Google Sheets"""
    params = context['params']

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        import asyncio
    except ImportError:
        raise ImportError("google-api-python-client package required. Install with: pip install google-api-python-client google-auth")

    # Get credentials
    credentials_json = params.get('credentials')
    if not credentials_json:
        credentials_json = os.getenv('GOOGLE_CREDENTIALS_JSON')
    if not credentials_json:
        raise ValueError("Credentials required: provide 'credentials' param or set GOOGLE_CREDENTIALS_JSON env variable")

    # Parse credentials
    if isinstance(credentials_json, str):
        credentials_json = json.loads(credentials_json)

    # Create credentials
    credentials = service_account.Credentials.from_service_account_info(
        credentials_json,
        scopes=['https://www.googleapis.com/auth/spreadsheets']
    )

    # Build service
    service = build('sheets', 'v4', credentials=credentials)

    # Prepare body
    body = {
        'values': params['values']
    }

    # Write values (run in thread pool since it's not async)
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        lambda: service.spreadsheets().values().update(
            spreadsheetId=params['spreadsheet_id'],
            range=params['range'],
            valueInputOption=params.get('value_input_option', 'USER_ENTERED'),
            body=body
        ).execute()
    )

    return {
        'updated_range': result.get('updatedRange', ''),
        'updated_rows': result.get('updatedRows', 0),
        'updated_columns': result.get('updatedColumns', 0),
        'updated_cells': result.get('updatedCells', 0)
    }
