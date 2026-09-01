# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Google Sheets Read Module
Read data from Google Sheets spreadsheet.

HOW FAR THE READ IS FOLLOWED

ACCEPTED. There is no status code to point at here -- `googleapiclient` raises
`HttpError` on any non-2xx -- so what stands in for one is the parsed body:
reaching the return means Google answered. The cells in it are Google's report
of what the spreadsheet holds, read once, with nothing corroborating it.

TWO THINGS THE COUNT IS NOT, both carried in the effect rather than left for a
reader of the integer to work out:

  * `row_count` is `len(values)`, which INCLUDES the header row when
    `include_header` is true, while the `data` list beside it excludes that row.
    So `row_count` and `len(data)` differ by one on the ordinary path. Neither
    is wrong; they answer different questions, and only the effect says which.

  * The API omits `values` entirely for a range with nothing in it, so an empty
    read and a range outside the sheet arrive here identically, as 0. That is
    still ACCEPTED and not lower -- Google answered -- but it is not evidence
    about what the sheet contains.
"""
import json
import logging
import os
from typing import Any, Dict

from ....registry import register_module
from .....engine.outcome import ClaimBy, Outcome, envelope


logger = logging.getLogger(__name__)


def _sheets_read_outcome(*, values: list, reported_range: Any, header_consumed: bool) -> Dict[str, Any]:
    """ACCEPTED, and the two measurements that earn it rather than DISPATCHED.

    `googleapiclient` raises on every non-2xx, so a parsed body IS the 2xx: a
    server received the request and answered. That is the distance between
    dispatched and accepted, and it is the whole distance -- one request, its
    reply, no read-back and nothing to read back for a query.
    """
    return envelope(
        Outcome.ACCEPTED,
        claim_by=ClaimBy.NONE,
        effects=[
            {
                'kind': 'sheets_reply_parsed',
                'operation': 'spreadsheets.values.get',
                'measured_by': 'the client returned a parsed body instead of raising',
                'detail': (
                    'googleapiclient raises HttpError on any non-2xx, so a body '
                    'here means Google answered. Nothing corroborates what it '
                    'says.'
                ),
            },
            {
                'kind': 'rows_returned',
                'count': len(values),
                'header_row_consumed': header_consumed,
                'range_reported_by_peer': reported_range,
                'measured_by': 'len() over the values array Google returned',
                'detail': (
                    'How many rows came back in this reply. With include_header '
                    'on, the first of them is the header and the `data` output '
                    'has one fewer entry than this number. `values` is omitted '
                    'entirely for an empty range, so 0 means "Google returned no '
                    'rows", which is not the same statement as "the sheet is '
                    'empty".'
                ),
            },
        ],
    )


@register_module(
    module_id='api.google_sheets.read',
    can_connect_to=['*'],
    can_receive_from=['data.*', 'http.*', 'flow.*', 'start'],
    version='1.0.0',
    category='productivity',
    tags=['productivity', 'google', 'sheets', 'spreadsheet', 'read', 'data', 'path_restricted', 'ssrf_protected'],
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
    timeout_ms=30000,
    retryable=True,
    max_retries=3,
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
        'values': {'type': 'array', 'description': 'Array of rows (each row is array of values)',
                'description_key': 'modules.api.google_sheets.read.output.values.description'},
        'data': {'type': 'array', 'description': 'Array of row objects (if include_header=true)',
                'description_key': 'modules.api.google_sheets.read.output.data.description'},
        'row_count': {'type': 'number', 'description': (
                    'Number of rows Google returned, including the header row '
                    'when include_header is on -- so one more than len(data)'),
                'description_key': 'modules.api.google_sheets.read.output.row_count.description'},
        'outcome': {'type': 'object', 'description': (
                    'How far the effect was followed. Always "accepted" on the '
                    'path that returns: Google answered and this is its account '
                    'of the cells. Error paths raise, so they carry no outcome'),
                'description_key': 'modules.api.google_sheets.read.output.outcome.description'}
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
    import asyncio
    params = context['params']

    service = _build_sheets_service(params)
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        lambda: service.spreadsheets().values().get(
            spreadsheetId=params['spreadsheet_id'],
            range=params['range']
        ).execute()
    )

    values = result.get('values', [])
    reported_range = result.get('range')
    if params.get('include_header', True) and values:
        headers = values[0]
        data = [
            dict(zip(headers, row + [''] * (len(headers) - len(row))))
            for row in values[1:]
        ]
        return {
            'values': values,
            'data': data,
            'row_count': len(values),
            'outcome': _sheets_read_outcome(
                values=values, reported_range=reported_range, header_consumed=True
            ),
        }
    return {
        'values': values,
        'row_count': len(values),
        'outcome': _sheets_read_outcome(
            values=values, reported_range=reported_range, header_consumed=False
        ),
    }


def _build_sheets_service(params):
    """Build Google Sheets API service from credentials."""
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError:
        raise ImportError(
            "google-api-python-client package required. "
            "Install with: pip install google-api-python-client google-auth"
        )

    credentials_json = params.get('credentials') or os.getenv('GOOGLE_CREDENTIALS_JSON')
    if not credentials_json:
        raise ValueError(
            "Credentials required: provide 'credentials' param or set GOOGLE_CREDENTIALS_JSON env variable"
        )
    if isinstance(credentials_json, str):
        credentials_json = json.loads(credentials_json)

    credentials = service_account.Credentials.from_service_account_info(
        credentials_json,
        scopes=['https://www.googleapis.com/auth/spreadsheets.readonly']
    )
    return build('sheets', 'v4', credentials=credentials)
