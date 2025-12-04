"""
Airtable Integration Modules

Provides operations for Airtable database.
"""
import logging
import os
from typing import Any, Dict, List

from ...base import BaseModule
from ...registry import register_module
from ....constants import APIEndpoints, EnvVars


logger = logging.getLogger(__name__)


@register_module(
    module_id='productivity.airtable.read',
    version='1.0.0',
    category='productivity',
    subcategory='database',
    tags=['airtable', 'database', 'read', 'query'],
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
    timeout=30,
    retryable=True,
    max_retries=3,
    concurrent_safe=True,

    # Phase 2: Security settings
    requires_credentials=True,
    handles_sensitive_data=True,
    required_permissions=['network.access', 'data.read'],

    params_schema={
        'api_key': {
            'type': 'string',
            'label': 'API Key',
            'label_key': 'modules.productivity.airtable.read.params.api_key.label',
            'description': 'Airtable API key (or use AIRTABLE_API_KEY env)',
            'description_key': 'modules.productivity.airtable.read.params.api_key.description',
            'required': False,
            'sensitive': True
        },
        'base_id': {
            'type': 'string',
            'label': 'Base ID',
            'label_key': 'modules.productivity.airtable.read.params.base_id.label',
            'description': 'Airtable base ID',
            'description_key': 'modules.productivity.airtable.read.params.base_id.description',
            'required': True
        },
        'table_name': {
            'type': 'string',
            'label': 'Table Name',
            'label_key': 'modules.productivity.airtable.read.params.table_name.label',
            'description': 'Name of the table',
            'description_key': 'modules.productivity.airtable.read.params.table_name.description',
            'required': True
        },
        'view': {
            'type': 'string',
            'label': 'View',
            'label_key': 'modules.productivity.airtable.read.params.view.label',
            'description': 'View name to use (optional)',
            'description_key': 'modules.productivity.airtable.read.params.view.description',
            'required': False
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
        'records': {'type': 'array'},
        'count': {'type': 'number'}
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

    def validate_params(self):
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
                        "count": len(simplified_records)
                    }

        except Exception as e:
            raise RuntimeError(f"Airtable read error: {str(e)}")


@register_module(
    module_id='productivity.airtable.create',
    version='1.0.0',
    category='productivity',
    subcategory='database',
    tags=['airtable', 'database', 'create', 'insert'],
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
    timeout=30,
    retryable=True,
    max_retries=3,
    concurrent_safe=True,

    # Phase 2: Security settings
    requires_credentials=True,
    handles_sensitive_data=True,
    required_permissions=['network.access', 'data.write'],

    params_schema={
        'api_key': {
            'type': 'string',
            'label': 'API Key',
            'label_key': 'modules.productivity.airtable.create.params.api_key.label',
            'description': 'Airtable API key (or use AIRTABLE_API_KEY env)',
            'description_key': 'modules.productivity.airtable.create.params.api_key.description',
            'required': False,
            'sensitive': True
        },
        'base_id': {
            'type': 'string',
            'label': 'Base ID',
            'label_key': 'modules.productivity.airtable.create.params.base_id.label',
            'description': 'Airtable base ID',
            'description_key': 'modules.productivity.airtable.create.params.base_id.description',
            'required': True
        },
        'table_name': {
            'type': 'string',
            'label': 'Table Name',
            'label_key': 'modules.productivity.airtable.create.params.table_name.label',
            'description': 'Name of the table',
            'description_key': 'modules.productivity.airtable.create.params.table_name.description',
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
        'id': {'type': 'string'},
        'createdTime': {'type': 'string'},
        'fields': {'type': 'json'}
    },
    examples=[
        {
            'title': 'Create customer record',
            'params': {
                'base_id': 'appXXXXXXXXXXXXXX',
                'table_name': 'Customers',
                'fields': {
                    'Name': 'John Doe',
                    'Email': 'john@example.com',
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

    def validate_params(self):
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
                        "fields": data['fields']
                    }

        except Exception as e:
            raise RuntimeError(f"Airtable create error: {str(e)}")


@register_module(
    module_id='productivity.airtable.update',
    version='1.0.0',
    category='productivity',
    subcategory='database',
    tags=['airtable', 'database', 'update'],
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
    timeout=30,
    retryable=True,
    max_retries=3,
    concurrent_safe=False,  # Updates should not be concurrent

    # Phase 2: Security settings
    requires_credentials=True,
    handles_sensitive_data=True,
    required_permissions=['network.access', 'data.write'],

    params_schema={
        'api_key': {
            'type': 'string',
            'label': 'API Key',
            'label_key': 'modules.productivity.airtable.update.params.api_key.label',
            'description': 'Airtable API key (or use AIRTABLE_API_KEY env)',
            'description_key': 'modules.productivity.airtable.update.params.api_key.description',
            'required': False,
            'sensitive': True
        },
        'base_id': {
            'type': 'string',
            'label': 'Base ID',
            'label_key': 'modules.productivity.airtable.update.params.base_id.label',
            'description': 'Airtable base ID',
            'description_key': 'modules.productivity.airtable.update.params.base_id.description',
            'required': True
        },
        'table_name': {
            'type': 'string',
            'label': 'Table Name',
            'label_key': 'modules.productivity.airtable.update.params.table_name.label',
            'description': 'Name of the table',
            'description_key': 'modules.productivity.airtable.update.params.table_name.description',
            'required': True
        },
        'record_id': {
            'type': 'string',
            'label': 'Record ID',
            'label_key': 'modules.productivity.airtable.update.params.record_id.label',
            'description': 'ID of the record to update',
            'description_key': 'modules.productivity.airtable.update.params.record_id.description',
            'required': True
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
        'id': {'type': 'string'},
        'fields': {'type': 'json'}
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

    def validate_params(self):
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
                        "fields": data['fields']
                    }

        except Exception as e:
            raise RuntimeError(f"Airtable update error: {str(e)}")
