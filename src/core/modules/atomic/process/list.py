"""
Process List Module
List all running background processes
"""

import asyncio
import logging
import os
from typing import Any, Dict, List

from ...registry import register_module
from .start import get_process_registry


logger = logging.getLogger(__name__)


@register_module(
    module_id='process.list',
    version='1.0.0',
    category='atomic',
    subcategory='process',
    tags=['process', 'list', 'status', 'monitor', 'atomic'],
    label='List Processes',
    label_key='modules.process.list.label',
    description='List all running background processes',
    description_key='modules.process.list.description',
    icon='List',
    color='#6366F1',

    # Connection types
    input_types=[],
    output_types=['array', 'object'],
    can_connect_to=['test.*', 'flow.*'],

    # Execution settings
    timeout=5,
    retryable=False,
    concurrent_safe=True,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema={
        'filter_name': {
            'type': 'string',
            'label': 'Filter by Name',
            'label_key': 'modules.process.list.params.filter_name.label',
            'description': 'Filter processes by name (substring match)',
            'description_key': 'modules.process.list.params.filter_name.description',
            'required': False
        },
        'include_status': {
            'type': 'boolean',
            'label': 'Include Status',
            'label_key': 'modules.process.list.params.include_status.label',
            'description': 'Include running/stopped status check',
            'description_key': 'modules.process.list.params.include_status.description',
            'required': False,
            'default': True
        }
    },
    output_schema={
        'ok': {
            'type': 'boolean',
            'description': 'Operation success'
        },
        'processes': {
            'type': 'array',
            'description': 'List of process information'
        },
        'count': {
            'type': 'number',
            'description': 'Total number of processes'
        },
        'running': {
            'type': 'number',
            'description': 'Number of running processes'
        },
        'stopped': {
            'type': 'number',
            'description': 'Number of stopped processes'
        }
    },
    examples=[
        {
            'title': 'List all processes',
            'title_key': 'modules.process.list.examples.all.title',
            'params': {}
        },
        {
            'title': 'Filter by name',
            'title_key': 'modules.process.list.examples.filter.title',
            'params': {
                'filter_name': 'dev'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def process_list(context: Dict[str, Any]) -> Dict[str, Any]:
    """List all running background processes"""
    params = context['params']
    filter_name = params.get('filter_name')
    include_status = params.get('include_status', True)

    registry = get_process_registry()
    processes: List[Dict[str, Any]] = []
    running_count = 0
    stopped_count = 0

    for proc_id, info in registry.items():
        # Apply name filter
        if filter_name and filter_name not in info.get('name', ''):
            continue

        process = info.get('process')
        status = 'unknown'

        if include_status and process:
            if process.returncode is None:
                # Check if actually running
                try:
                    os.kill(process.pid, 0)
                    status = 'running'
                    running_count += 1
                except (ProcessLookupError, PermissionError):
                    status = 'stopped'
                    stopped_count += 1
            else:
                status = 'stopped'
                stopped_count += 1

        proc_info = {
            'process_id': proc_id,
            'pid': info.get('pid'),
            'name': info.get('name'),
            'command': info.get('command'),
            'cwd': info.get('cwd'),
            'started_at': info.get('started_at')
        }

        if include_status:
            proc_info['status'] = status
            if process and process.returncode is not None:
                proc_info['exit_code'] = process.returncode

        processes.append(proc_info)

    logger.info(f"Listed {len(processes)} processes ({running_count} running)")

    return {
        'ok': True,
        'processes': processes,
        'count': len(processes),
        'running': running_count,
        'stopped': stopped_count
    }
