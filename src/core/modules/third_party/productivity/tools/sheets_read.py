"""
Google Sheets Read Module
Read data from Google Sheets spreadsheet.
"""
import json
import logging
import os

from ....registry import register_module


logger = logging.getLogger(__name__)


@register_module(
    module_id='api.google_sheets.read',
    can_connect_to=['*'],
    can_receive_from=['data.*', 'api.*', 'flow.*', 'start'],
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
    input_types=['string'],
    output_types=['table', 'array'],

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
        'credentials': {
            'type': 'object',
            'label': 'Service Account Credentials',
            'label_key': 'modules.api.google_sheets.read.params.credentials.label',
            'description': 'Google service account JSON credentials (defaults to env.GOOGLE_CREDENTIALS_JSON)',
            'description_key': 'modules.api.google_sheets.read.params.credentials.description',
            'required': False,
            'sensitive': True,
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
        'values': {'type': 'array', 'description': 'Array of rows (each row is array of values)'},
        'data': {'type': 'array', 'description': 'Array of row objects (if include_header=true)'},
        'row_count': {'type': 'number', 'description': 'Number of rows read'}
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

    credentials_json = params.get('credentials')
    if not credentials_json:
        credentials_json = os.getenv('GOOGLE_CREDENTIALS_JSON')
    if not credentials_json:
        raise ValueError("Credentials required: provide 'credentials' param or set GOOGLE_CREDENTIALS_JSON env variable")

    if isinstance(credentials_json, str):
        credentials_json = json.loads(credentials_json)

    credentials = service_account.Credentials.from_service_account_info(
        credentials_json,
        scopes=['https://www.googleapis.com/auth/spreadsheets.readonly']
    )

    service = build('sheets', 'v4', credentials=credentials)

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        lambda: service.spreadsheets().values().get(
            spreadsheetId=params['spreadsheet_id'],
            range=params['range']
        ).execute()
    )

    values = result.get('values', [])

    if params.get('include_header', True) and values:
        headers = values[0]
        data = []
        for row in values[1:]:
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
