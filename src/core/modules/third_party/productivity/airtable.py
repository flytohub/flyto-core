# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Airtable Integration Modules

Provides operations for Airtable database.

HOW FAR AN AIRTABLE CALL IS FOLLOWED

ACCEPTED, on all three, on the one path each of them returns from. Every module
here sends one HTTPS request and reads the reply to that same request; none
reads anything back afterwards. A 200 body describing the record Airtable says
it just created or patched is the peer reporting on its own work, which is
`http.request`'s settled position for every 2xx in this product and
`api.notion.create_page`'s for the same shape of create.

ACCEPTED is still worth attaching, because the alternative is not OBSERVED, it
is DISPATCHED -- what the engine stamps on a module that reports nothing, and
what all three said before this change. On the create and the update the reply
carries a server-assigned `id` and `createdTime` that no input here could have
produced, so "the instruction left us and nobody confirmed anything" is untrue
of it.

THE ERROR PATHS CARRY NOTHING, and that is the honest gap in this file. Every
non-200 raises, and the `except Exception` around each body re-raises as
`RuntimeError`, so the payload is discarded and no rung survives. For the read
that is the smaller loss -- a refused read changed nothing. For the create it is
not: a 5xx or a timeout on a POST is the textbook INDETERMINATE, the record may
exist, and today that arrives as an ordinary step failure. Changing a raise into
a returned error dict is a decision about step semantics, not about reporting,
so it is written down here rather than made.

WORSE THAN THE MISSING RUNG, on the same path: `productivity.airtable.create`
declares `retryable=True, max_retries=3` and sends no idempotency key, so a
timeout on a POST Airtable already accepted re-runs the create and leaves two
records. The rung cannot fix that and does not pretend to; it is reported
alongside this change.
"""
import logging
import os
from typing import Any, Dict, List

from ...base import BaseModule
from ...registry import register_module
from ....constants import APIEndpoints, EnvVars
from ....engine.outcome import ClaimBy, Outcome, envelope


logger = logging.getLogger(__name__)


def _airtable_answered(status: int) -> Dict[str, Any]:
    """The one thing every path in this file measures: a status line came back.

    This is the whole distance between DISPATCHED and ACCEPTED. A server
    received the request, processed it far enough to choose a reply, and sent
    one. It is not an observation of Airtable's state -- nothing in this file
    looks at anything except the answer to the message it just sent.
    """
    return {
        'kind': 'airtable_reply_read',
        'status': status,
        'measured_by': 'response.status -- the status line of the reply to this request',
        'detail': (
            'A server received this request and chose a reply. That is what '
            'separates accepted from dispatched, and it is all it separates: no '
            'Airtable state is read back anywhere in this module.'
        ),
    }


@register_module(
    module_id='productivity.airtable.read',
    can_connect_to=['*'],
    can_receive_from=['data.*', 'http.*', 'flow.*', 'start'],
    version='1.0.0',
    category='productivity',
    subcategory='database',
    tags=['airtable', 'database', 'read', 'query', 'path_restricted', 'ssrf_protected'],
    label='Airtable Read Records',
    label_key='modules.productivity.airtable.read.label',
    description='Read records from Airtable table',
    description_key='modules.productivity.airtable.read.description',
    icon='Database',
    color='#FCB400',

    # Connection types
    input_types=['json'],
    output_types=['array', 'json'],

    # Phase 2: Execution settings
    timeout_ms=30000,
    retryable=True,
    max_retries=3,
    concurrent_safe=True,

    # Phase 2: Security settings
    requires_credentials=True,
    credential_keys=['AIRTABLE_API_KEY'],
    handles_sensitive_data=True,
    required_permissions=['network.access'],

    params_schema={
        'api_key': {
            'type': 'string',
            'label': 'API Key',
            'label_key': 'modules.productivity.airtable.read.params.api_key.label',
            'description': 'Airtable API key (or use AIRTABLE_API_KEY env)',
            'description_key': 'modules.productivity.airtable.read.params.api_key.description',
            'required': False,
            'sensitive': True
        ,
            'placeholder': 'sk-...',
},
        'base_id': {
            'type': 'string',
            'label': 'Base ID',
            'label_key': 'modules.productivity.airtable.read.params.base_id.label',
            'description': 'Airtable base ID',
            'description_key': 'modules.productivity.airtable.read.params.base_id.description',
            'required': True
        ,
            'placeholder': 'app12345',
},
        'table_name': {
            'type': 'string',
            'label': 'Table Name',
            'label_key': 'modules.productivity.airtable.read.params.table_name.label',
            'description': 'Name of the table',
            'description_key': 'modules.productivity.airtable.read.params.table_name.description',
            'required': True
        ,
            'placeholder': 'my_table',
},
        'view': {
            'type': 'string',
            'label': 'View',
            'label_key': 'modules.productivity.airtable.read.params.view.label',
            'description': 'View name to use (optional)',
            'description_key': 'modules.productivity.airtable.read.params.view.description',
            'required': False
        ,
            'placeholder': 'Enter view...',
},
        'max_records': {
            'type': 'number',
            'label': 'Max Records',
            'label_key': 'modules.productivity.airtable.read.params.max_records.label',
            'description': 'Maximum number of records to return',
            'description_key': 'modules.productivity.airtable.read.params.max_records.description',
            'default': 100,
            'required': False
        }
    },
    output_schema={
        'records': {'type': 'array', 'description': 'One page of records, bounded by max_records',
                'description_key': 'modules.productivity.airtable.read.output.records.description'},
        'count': {'type': 'number', 'description': (
                    'Records returned on this page. Not the number of rows in the '
                    'table -- Airtable pages at 100 and the offset is never followed'),
                'description_key': 'modules.productivity.airtable.read.output.count.description'},
        'outcome': {'type': 'object', 'description': (
                    'How far the read was followed. Always "accepted" on the path '
                    'that returns: Airtable answered, and nothing is read back. '
                    'Error paths raise, so they carry no outcome at all'),
                'description_key': 'modules.productivity.airtable.read.output.outcome.description'}
    },
    examples=[
        {
            'title': 'Read all customers',
            'params': {
                'base_id': 'appXXXXXXXXXXXXXX',
                'table_name': 'Customers',
                'max_records': 100
            }
        },
        {
            'title': 'Read from specific view',
            'params': {
                'base_id': 'appXXXXXXXXXXXXXX',
                'table_name': 'Tasks',
                'view': 'Active Tasks',
                'max_records': 50
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class AirtableReadModule(BaseModule):
    """Airtable Read Records Module"""

    def validate_params(self) -> None:
        self.api_key = self.params.get('api_key')
        self.base_id = self.params.get('base_id')
        self.table_name = self.params.get('table_name')
        self.view = self.params.get('view')
        self.max_records = self.params.get('max_records', 100)

        if not self.api_key:
            self.api_key = os.environ.get(EnvVars.AIRTABLE_API_KEY)
            if not self.api_key:
                raise ValueError(f"api_key or {EnvVars.AIRTABLE_API_KEY} environment variable is required")

        if not self.base_id or not self.table_name:
            raise ValueError("base_id and table_name are required")

    async def execute(self) -> Any:
        try:
            import aiohttp

            # Build URL
            url = APIEndpoints.airtable_table(self.base_id, self.table_name)

            # Build query parameters
            params = {
                'maxRecords': self.max_records
            }
            if self.view:
                params['view'] = self.view

            # Make API request
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, params=params) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise RuntimeError(f"Airtable API error ({response.status}): {error_text}")

                    data = await response.json()
                    records = data.get('records', [])

                    # Extract just the fields for easier use
                    simplified_records = []
                    for record in records:
                        simplified_records.append({
                            'id': record['id'],
                            'createdTime': record['createdTime'],
                            'fields': record['fields']
                        })

                    return {
                        "records": simplified_records,
                        "count": len(simplified_records),
                        "outcome": envelope(
                            Outcome.ACCEPTED,
                            claim_by=ClaimBy.NONE,
                            effects=[
                                _airtable_answered(response.status),
                                {
                                    'kind': 'records_returned',
                                    'count': len(simplified_records),
                                    'max_records_requested': self.max_records,
                                    'view': self.view,
                                    # Airtable sends an offset when the table
                                    # holds more rows than this page. It is
                                    # recorded rather than followed, so a reader
                                    # can at least see the list is partial.
                                    'more_pages_available': 'offset' in data,
                                    'measured_by': (
                                        'len() over the records array Airtable '
                                        'returned, and the offset field of that same '
                                        'body'
                                    ),
                                    'detail': (
                                        'count is ONE PAGE. Airtable returns at most '
                                        '100 records per request and hands back an '
                                        'offset this module never sends, so when '
                                        'more_pages_available is true the table holds '
                                        'rows that are not in this list. The records '
                                        'themselves are Airtable\'s report of its own '
                                        'data, read once, with nothing corroborating '
                                        'them.'
                                    ),
                                },
                            ],
                        ),
                    }

        except Exception as e:
            raise RuntimeError(f"Airtable read error: {str(e)}")


@register_module(
    module_id='productivity.airtable.create',
    can_connect_to=['*'],
    can_receive_from=['data.*', 'http.*', 'flow.*', 'start'],
    version='1.0.0',
    category='productivity',
    subcategory='database',
    tags=['airtable', 'database', 'create', 'insert', 'ssrf_protected'],
    label='Airtable Create Record',
    label_key='modules.productivity.airtable.create.label',
    description='Create a new record in Airtable table',
    description_key='modules.productivity.airtable.create.description',
    icon='Plus',
    color='#FCB400',

    # Connection types
    input_types=['json'],
    output_types=['json'],

    # Phase 2: Execution settings
    timeout_ms=30000,
    retryable=True,
    max_retries=3,
    concurrent_safe=True,

    # Phase 2: Security settings
    requires_credentials=True,
    credential_keys=['AIRTABLE_API_KEY'],
    handles_sensitive_data=True,
    required_permissions=['network.access'],

    params_schema={
        'api_key': {
            'type': 'string',
            'label': 'API Key',
            'label_key': 'modules.productivity.airtable.create.params.api_key.label',
            'description': 'Airtable API key (or use AIRTABLE_API_KEY env)',
            'description_key': 'modules.productivity.airtable.create.params.api_key.description',
            'placeholder': 'sk-...',
            'required': False,
            'sensitive': True
        },
        'base_id': {
            'type': 'string',
            'label': 'Base ID',
            'label_key': 'modules.productivity.airtable.create.params.base_id.label',
            'description': 'Airtable base ID',
            'description_key': 'modules.productivity.airtable.create.params.base_id.description',
            'placeholder': 'app12345',
            'required': True
        },
        'table_name': {
            'type': 'string',
            'label': 'Table Name',
            'label_key': 'modules.productivity.airtable.create.params.table_name.label',
            'description': 'Name of the table',
            'description_key': 'modules.productivity.airtable.create.params.table_name.description',
            'placeholder': 'my_table',
            'required': True
        },
        'fields': {
            'type': 'json',
            'label': 'Fields',
            'label_key': 'modules.productivity.airtable.create.params.fields.label',
            'description': 'Record fields as JSON object',
            'description_key': 'modules.productivity.airtable.create.params.fields.description',
            'required': True
        }
    },
    output_schema={
        'id': {'type': 'string', 'description': 'Record id, assigned by Airtable'},
        'createdTime': {'type': 'string', 'description': 'Record creation timestamp, from Airtable'},
        'fields': {'type': 'json', 'description': 'The fields, as Airtable reports them back'},
        'outcome': {'type': 'object', 'description': (
                    'How far the create was followed. Always "accepted" on the path '
                    'that returns: Airtable says it created the record and names it, '
                    'and nothing reads the record back. Error paths raise, so they '
                    'carry no outcome -- including the timeout on a POST that leaves '
                    'a record which may exist')}
    },
    examples=[
        {
            'title': 'Create customer record',
            'params': {
                'base_id': 'appXXXXXXXXXXXXXX',
                'table_name': 'Customers',
                'fields': {
                    'Name': 'John Doe',
                    'Email': 'dev@flyto2.com',
                    'Status': 'Active'
                }
            }
        },
        {
            'title': 'Create task',
            'params': {
                'base_id': 'appXXXXXXXXXXXXXX',
                'table_name': 'Tasks',
                'fields': {
                    'Title': 'Review PR',
                    'Assignee': 'Alice',
                    'Priority': 'High'
                }
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class AirtableCreateModule(BaseModule):
    """Airtable Create Record Module"""

    def validate_params(self) -> None:
        self.api_key = self.params.get('api_key')
        self.base_id = self.params.get('base_id')
        self.table_name = self.params.get('table_name')
        self.fields = self.params.get('fields')

        if not self.api_key:
            self.api_key = os.environ.get(EnvVars.AIRTABLE_API_KEY)
            if not self.api_key:
                raise ValueError(f"api_key or {EnvVars.AIRTABLE_API_KEY} environment variable is required")

        if not self.base_id or not self.table_name or not self.fields:
            raise ValueError("base_id, table_name, and fields are required")

    async def execute(self) -> Any:
        try:
            import aiohttp

            # Build URL
            url = APIEndpoints.airtable_table(self.base_id, self.table_name)

            # Build request body
            body = {
                'fields': self.fields
            }

            # Make API request
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=body) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise RuntimeError(f"Airtable API error ({response.status}): {error_text}")

                    data = await response.json()

                    return {
                        "id": data['id'],
                        "createdTime": data['createdTime'],
                        "fields": data['fields'],
                        "outcome": envelope(
                            Outcome.ACCEPTED,
                            claim_by=ClaimBy.NONE,
                            effects=[
                                _airtable_answered(response.status),
                                {
                                    'kind': 'record_reported_created',
                                    'record_id': data['id'],
                                    'created_time': data['createdTime'],
                                    'fields_sent': sorted(self.fields)
                                    if isinstance(self.fields, dict) else None,
                                    'measured_by': (
                                        'id and createdTime in the 200 body Airtable '
                                        'returned to this POST'
                                    ),
                                    'detail': (
                                        'Airtable asserting that it created a record, '
                                        'and naming it. Both values are '
                                        'server-assigned, so they are more than an '
                                        'echo of the fields sent -- and still the peer '
                                        'reporting on its own work, so this is not an '
                                        'observation. Nothing reads the record back. '
                                        'Nothing here would show a SECOND record: this '
                                        'module is retryable and sends no idempotency '
                                        'key, so a retried timeout creates one more.'
                                    ),
                                },
                            ],
                        ),
                    }

        except Exception as e:
            raise RuntimeError(f"Airtable create error: {str(e)}")


@register_module(
    module_id='productivity.airtable.update',
    can_connect_to=['*'],
    can_receive_from=['data.*', 'http.*', 'flow.*', 'start'],
    version='1.0.0',
    category='productivity',
    subcategory='database',
    tags=['airtable', 'database', 'update', 'ssrf_protected'],
    label='Airtable Update Record',
    label_key='modules.productivity.airtable.update.label',
    description='Update an existing record in Airtable table',
    description_key='modules.productivity.airtable.update.description',
    icon='Edit',
    color='#FCB400',

    # Connection types
    input_types=['json'],
    output_types=['json'],

    # Phase 2: Execution settings
    timeout_ms=30000,
    retryable=True,
    max_retries=3,
    concurrent_safe=False,  # Updates should not be concurrent

    # Phase 2: Security settings
    requires_credentials=True,
    credential_keys=['AIRTABLE_API_KEY'],
    handles_sensitive_data=True,
    required_permissions=['network.access'],

    params_schema={
        'api_key': {
            'type': 'string',
            'label': 'API Key',
            'label_key': 'modules.productivity.airtable.update.params.api_key.label',
            'description': 'Airtable API key (or use AIRTABLE_API_KEY env)',
            'description_key': 'modules.productivity.airtable.update.params.api_key.description',
            'placeholder': 'sk-...',
            'required': False,
            'sensitive': True
        },
        'base_id': {
            'type': 'string',
            'label': 'Base ID',
            'label_key': 'modules.productivity.airtable.update.params.base_id.label',
            'description': 'Airtable base ID',
            'description_key': 'modules.productivity.airtable.update.params.base_id.description',
            'placeholder': 'app12345',
            'required': True
        },
        'table_name': {
            'type': 'string',
            'label': 'Table Name',
            'label_key': 'modules.productivity.airtable.update.params.table_name.label',
            'description': 'Name of the table',
            'description_key': 'modules.productivity.airtable.update.params.table_name.description',
            'placeholder': 'my_table',
            'required': True
        },
        'record_id': {
            'type': 'string',
            'label': 'Record ID',
            'label_key': 'modules.productivity.airtable.update.params.record_id.label',
            'description': 'ID of the record to update',
            'description_key': 'modules.productivity.airtable.update.params.record_id.description',
            'required': True
        ,
            'placeholder': 'recXXXXXXXX',
},
        'fields': {
            'type': 'json',
            'label': 'Fields',
            'label_key': 'modules.productivity.airtable.update.params.fields.label',
            'description': 'Fields to update as JSON object',
            'description_key': 'modules.productivity.airtable.update.params.fields.description',
            'required': True
        }
    },
    output_schema={
        'id': {'type': 'string', 'description': 'Record id, echoed back by Airtable'},
        'fields': {'type': 'json', 'description': (
                    'The record as Airtable reports it after the patch. Airtable '
                    'omits fields that hold no value, so this is not a checklist of '
                    'what was applied')},
        'outcome': {'type': 'object', 'description': (
                    'How far the update was followed. Always "accepted" on the path '
                    'that returns: Airtable answered with the record it says it '
                    'holds, and nothing reads it back. Error paths raise, so they '
                    'carry no outcome at all')}
    },
    examples=[
        {
            'title': 'Update customer status',
            'params': {
                'base_id': 'appXXXXXXXXXXXXXX',
                'table_name': 'Customers',
                'record_id': 'recXXXXXXXXXXXXXX',
                'fields': {
                    'Status': 'Inactive'
                }
            }
        },
        {
            'title': 'Update task',
            'params': {
                'base_id': 'appXXXXXXXXXXXXXX',
                'table_name': 'Tasks',
                'record_id': 'recYYYYYYYYYYYYYY',
                'fields': {
                    'Status': 'Completed',
                    'Completed Date': '2024-01-15'
                }
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class AirtableUpdateModule(BaseModule):
    """Airtable Update Record Module"""

    def validate_params(self) -> None:
        self.api_key = self.params.get('api_key')
        self.base_id = self.params.get('base_id')
        self.table_name = self.params.get('table_name')
        self.record_id = self.params.get('record_id')
        self.fields = self.params.get('fields')

        if not self.api_key:
            self.api_key = os.environ.get(EnvVars.AIRTABLE_API_KEY)
            if not self.api_key:
                raise ValueError(f"api_key or {EnvVars.AIRTABLE_API_KEY} environment variable is required")

        if not self.base_id or not self.table_name or not self.record_id or not self.fields:
            raise ValueError("base_id, table_name, record_id, and fields are required")

    async def execute(self) -> Any:
        try:
            import aiohttp

            # Build URL
            url = f"{APIEndpoints.airtable_table(self.base_id, self.table_name)}/{self.record_id}"

            # Build request body
            body = {
                'fields': self.fields
            }

            # Make API request
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }

            async with aiohttp.ClientSession() as session:
                async with session.patch(url, headers=headers, json=body) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise RuntimeError(f"Airtable API error ({response.status}): {error_text}")

                    data = await response.json()

                    return {
                        "id": data['id'],
                        "fields": data['fields'],
                        "outcome": envelope(
                            Outcome.ACCEPTED,
                            claim_by=ClaimBy.NONE,
                            effects=[
                                _airtable_answered(response.status),
                                {
                                    'kind': 'record_update_reported',
                                    'record_id': data['id'],
                                    'fields_sent': sorted(self.fields)
                                    if isinstance(self.fields, dict) else None,
                                    'fields_in_reply': sorted(data['fields'])
                                    if isinstance(data['fields'], dict) else None,
                                    'measured_by': (
                                        'the record object in the 200 body Airtable '
                                        'returned to this PATCH'
                                    ),
                                    'detail': (
                                        "Airtable's description of the record it says "
                                        'it now holds, in the reply to the request '
                                        'that changed it. Not a read-back: no second '
                                        'request is made, and no field is compared. '
                                        'fields_sent and fields_in_reply are listed '
                                        'side by side for a reader, and deliberately '
                                        'do not move the rung -- Airtable omits a '
                                        'field it holds no value for, so a field set '
                                        'to empty is legitimately absent from the '
                                        'reply and a mismatch here is not evidence of '
                                        'a failed write.'
                                    ),
                                },
                            ],
                        ),
                    }

        except Exception as e:
            raise RuntimeError(f"Airtable update error: {str(e)}")
