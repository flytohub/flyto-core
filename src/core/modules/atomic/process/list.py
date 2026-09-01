# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Process List Module
List all running background processes

HOW FAR THIS MODULE FOLLOWS REALITY

Two answers, and what separates them is whether anything outside this Python
process was asked a question.

  at least one process was probed             OBSERVED
      `os.kill(pid, 0)` is a real syscall against the OS process table, and a
      `returncode` that is already set means the event loop's child watcher
      reaped that child and read its exit status. Both are readings of the
      world, and `running` / `stopped` are counted from them.

  nothing was probed                          DISPATCHED
      With `include_status` false, or a registry holding no process objects,
      this module reads `_process_registry` -- a dict in this interpreter's own
      memory, written by `process.start` and never reconciled with the OS.
      Every field returned then (`pid`, `name`, `command`, `started_at`) is our
      own bookkeeping repeated back, and `status` is the literal 'unknown'. A
      count of 0 there means "our dict is empty", which is not a statement
      about any machine.

      DISPATCHED rather than ACCEPTED, deliberately: nobody acknowledged
      anything, and it is the rung the engine stamps on a module that reports
      nothing at all -- which is precisely what this path has to say.

A limit on the OBSERVED worth stating: pids are reused. `os.kill(pid, 0)`
succeeding says a process with that number exists, not that it is the one
`process.start` spawned, and it succeeds for a zombie that has already exited.
"""

import asyncio
import logging
import os
from typing import Any, Dict, List

from ....engine.outcome import ClaimBy, Outcome, envelope
from ...registry import register_module
from ...schema import compose, presets
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
    can_receive_from=['start', 'flow.*'],

    # Execution settings
    timeout_ms=5000,
    retryable=False,
    concurrent_safe=True,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    # Schema-driven params
    params_schema=compose(
        presets.FILTER_NAME(),
        presets.INCLUDE_STATUS(default=True),
    ),
    output_schema={
        'ok': {
            'type': 'boolean',
            'description': 'Operation success'
        ,
                'description_key': 'modules.process.list.output.ok.description'},
        'processes': {
            'type': 'array',
            'description': 'List of process information'
        ,
                'description_key': 'modules.process.list.output.processes.description'},
        'count': {
            'type': 'number',
            'description': 'Total number of processes'
        ,
                'description_key': 'modules.process.list.output.count.description'},
        'running': {
            'type': 'number',
            'description': 'Number of running processes'
        ,
                'description_key': 'modules.process.list.output.running.description'},
        'stopped': {
            'type': 'number',
            'description': 'Number of stopped processes'
        ,
                'description_key': 'modules.process.list.output.stopped.description'},
        'outcome': {
            'type': 'object',
            'description': (
                'How far the listing was followed: observed when process state '
                'was probed against the OS, dispatched when only the in-memory '
                'registry was read'
            ),
            'description_key': 'modules.process.list.output.outcome.description'}
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
    # How many entries had their state read from something other than our own
    # dict. Counted where the reading happens, so it cannot drift from it.
    probed_count = 0

    for proc_id, info in registry.items():
        # Apply name filter
        if filter_name and filter_name not in info.get('name', ''):
            continue

        process = info.get('process')
        status = 'unknown'

        if include_status and process:
            probed_count += 1
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

    if probed_count:
        outcome = envelope(
            Outcome.OBSERVED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'process_state_probed',
                'probed': probed_count,
                'running': running_count,
                'stopped': stopped_count,
                'measured_by': (
                    'os.kill(pid, 0) against the OS process table, or a '
                    'returncode already reaped by the event loop'
                ),
                'detail': (
                    'A pid that answers is not certainly the process we started '
                    '-- pids are reused, and a zombie answers too. A pid that '
                    'raises PermissionError is counted as stopped here although '
                    'it means the opposite: the process exists and is not ours.'
                ),
            }],
        )
    else:
        outcome = envelope(
            Outcome.DISPATCHED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'registry_read_only',
                'entries': len(processes),
                'measured_by': None,
                'detail': (
                    'No process was probed, so nothing outside this interpreter '
                    'was consulted. These entries are the in-memory registry '
                    'repeated back, and their status is the literal "unknown".'
                ),
            }],
        )

    return {
        'ok': True,
        'processes': processes,
        'count': len(processes),
        'running': running_count,
        'stopped': stopped_count,
        'outcome': outcome,
    }
