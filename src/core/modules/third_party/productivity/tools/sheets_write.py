# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Google Sheets Write Module
Write data to Google Sheets spreadsheet.

HOW FAR THE WRITE IS FOLLOWED

ACCEPTED, and this is the module in the group where the case for OBSERVED is
strongest and still fails. Google does not merely say "ok": it says
`updatedCells: 12`, a number that varies with the effect and that this module
could not have produced from its own inputs. `database.query` calls the same
shape OBSERVED when a row count crosses the wire from a database server.

The difference is what is on the other end of the wire and what the number is a
report OF. `updatedCells` is Google's account of work Google did, arriving in
the reply to the very request that asked for it -- the definition of taking a
peer's word, which is what `http.request` settled for every 2xx in this product.
Nothing here reads a single cell back. A `values.get` on the same range
afterwards would be an observation; it is one more quota unit and one more
round trip, and it is not what this module does today.

THE FABRICATED ZERO, which is the `database.query` bug in a second costume.
`result.get('updatedCells', 0)` writes a literal 0 into the output when the key
is absent, and that 0 is indistinguishable from Google reporting that nothing
changed. The outputs are left alone -- a consumer doing arithmetic on them would
break on None -- but the envelope records which of the two it was, so a rung is
never resting on a number this file invented.
"""
import json
import logging
import os
from typing import Any, Dict

from ....registry import register_module
from .....engine.outcome import ClaimBy, Outcome, envelope


logger = logging.getLogger(__name__)


def _sheets_write_outcome(result: Dict[str, Any]) -> Dict[str, Any]:
    """ACCEPTED either way, with `count_reported` saying which 0 a 0 is.

    The rung does not split on `counted`, and that is deliberate: both branches
    are the peer reporting on its own work, so both stop at ACCEPTED. What
    splits is the evidence. `database.query` had to split the rung because its
    two zeros came from different SOURCES -- one from the server, one from a
    literal in the module -- and only one of them was a measurement. Here
    neither is an observation, so the honest thing is one rung and an effect
    that says whether a number arrived at all.
    """
    counted = 'updatedCells' in result
    return envelope(
        Outcome.ACCEPTED,
        claim_by=ClaimBy.NONE,
        effects=[
            {
                'kind': 'sheets_reply_parsed',
                'operation': 'spreadsheets.values.update',
                'measured_by': 'the client returned a parsed body instead of raising',
                'detail': (
                    'googleapiclient raises HttpError on any non-2xx, so a body '
                    'here means Google took the update and answered.'
                ),
            },
            {
                'kind': 'update_reported_by_peer' if counted else 'update_uncounted',
                'count_reported': counted,
                'cells': result.get('updatedCells') if counted else None,
                'rows': result.get('updatedRows') if counted else None,
                'range_reported_by_peer': result.get('updatedRange'),
                'measured_by': (
                    'updatedCells/updatedRows in the body Google returned'
                    if counted else None
                ),
                'detail': (
                    "Google's account of the cells it changed. It varies with the "
                    'effect and could not be produced from this module\'s inputs, '
                    'which is why the rung is accepted and not dispatched -- and '
                    'it is the peer describing its own work, with no cell read '
                    'back, which is why it is not observed.'
                    if counted else
                    'Google returned no updatedCells for this request. The 0 in '
                    'the output above is a literal written by this module, not a '
                    'count from the API, and nothing about how much changed is '
                    'known.'
                ),
            },
        ],
    )


@register_module(
    module_id='api.google_sheets.write',
    can_connect_to=['*'],
    can_receive_from=['data.*', 'http.*', 'flow.*', 'start'],
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
        'updated_cells': {'type': 'number', 'description': (
                    'Number of cells Google reports it updated. 0 when Google '
                    'reported no count at all -- outcome.effects says which'),
                'description_key': 'modules.api.google_sheets.write.output.updated_cells.description'},
        'outcome': {'type': 'object', 'description': (
                    'How far the effect was followed. Always "accepted" on the '
                    'path that returns: the counts are Google reporting on its '
                    'own work and no cell is read back. Error paths raise, so '
                    'they carry no outcome'),
                'description_key': 'modules.api.google_sheets.write.output.outcome.description'}
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
                    ['John Doe', 'dev@flyto2.com', 'Active'],
                    ['Jane Smith', 'team@flyto2.com', 'Active']
                ]
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
        'updated_cells': result.get('updatedCells', 0),
        'outcome': _sheets_write_outcome(result)
    }
