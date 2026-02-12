"""
Google Sheets Write Module
Write data to Google Sheets spreadsheet.
"""
import json
import logging
import os

from ....registry import register_module


logger = logging.getLogger(__name__)


@register_module(
    module_id='api.google_sheets.write',
    can_connect_to=['*'],
    can_receive_from=['data.*', 'api.*', 'flow.*', 'start'],
    version='1.0.0',
    category='productivity',
    tags=['productivity', 'google', 'sheets', 'spreadsheet', 'write', 'data', 'path_restricted', 'ssrf_protected'],
    label='Google Sheets Write',
    label_key='modules.api.google_sheets.write.label',
    description='Write data to Google Sheets spreadsheet',
    description_key='modules.api.google_sheets.write.description',
    icon='Table',
    color='#0F9D58',

    # Connection types
    input_types=['table', 'array'],
    output_types=['object'],

    # Phase 2: Execution settings
    timeout_ms=30000,
    retryable=False,
    concurrent_safe=True,

    # Phase 2: Security settings
    requires_credentials=True,
    credential_keys=['GOOGLE_CREDENTIALS'],
    handles_sensitive_data=True,
    required_permissions=['network.access'],

    params_schema={
        'credentials': {
            'type': 'object',
            'label': 'Service Account Credentials',
            'label_key': 'modules.api.google_sheets.write.params.credentials.label',
            'description': 'Google service account JSON credentials (defaults to env.GOOGLE_CREDENTIALS_JSON)',
            'description_key': 'modules.api.google_sheets.write.params.credentials.description',
            'required': False,
            'sensitive': True
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
        'updated_range': {'type': 'string', 'description': 'Range that was updated',
                'description_key': 'modules.api.google_sheets.write.output.updated_range.description'},
        'updated_rows': {'type': 'number', 'description': 'Number of rows updated',
                'description_key': 'modules.api.google_sheets.write.output.updated_rows.description'},
        'updated_columns': {'type': 'number', 'description': 'Number of columns updated',
                'description_key': 'modules.api.google_sheets.write.output.updated_columns.description'},
        'updated_cells': {'type': 'number', 'description': 'Number of cells updated',
                'description_key': 'modules.api.google_sheets.write.output.updated_cells.description'}
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
        }
    ],
    author='Flyto Team',
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

    credentials_json = params.get('credentials')
    if not credentials_json:
        credentials_json = os.getenv('GOOGLE_CREDENTIALS_JSON')
    if not credentials_json:
        raise ValueError("Credentials required: provide 'credentials' param or set GOOGLE_CREDENTIALS_JSON env variable")

    if isinstance(credentials_json, str):
        credentials_json = json.loads(credentials_json)

    credentials = service_account.Credentials.from_service_account_info(
        credentials_json,
        scopes=['https://www.googleapis.com/auth/spreadsheets']
    )

    service = build('sheets', 'v4', credentials=credentials)

    body = {'values': params['values']}

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
