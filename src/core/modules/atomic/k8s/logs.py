# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Kubernetes Logs Module
Retrieve logs from a Kubernetes pod
"""

import asyncio
import logging
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ModuleError

logger = logging.getLogger(__name__)


@register_module(
    module_id='k8s.logs',
    version='1.0.0',
    category='k8s',
    tags=['kubernetes', 'k8s', 'logs', 'pod', 'debug', 'troubleshoot'],
    label='Get Pod Logs',
    label_key='modules.k8s.logs.label',
    description='Retrieve logs from a Kubernetes pod',
    description_key='modules.k8s.logs.description',
    icon='Cloud',
    color='#326CE5',
    input_types=['string', 'object'],
    output_types=['object'],
    can_receive_from=['*'],
    can_connect_to=['*'],
    retryable=True,
    concurrent_safe=True,
    timeout_ms=30000,
    params_schema=compose(
        field('pod', type='string', label='Pod Name',
              required=True, group=FieldGroup.BASIC,
              description='Name of the pod to retrieve logs from',
              placeholder='my-app-7d4b8c6f5-x2k9q'),
        field('namespace', type='string', label='Namespace',
              default='default', group=FieldGroup.BASIC,
              description='Kubernetes namespace'),
        field('container', type='string', label='Container',
              group=FieldGroup.OPTIONS,
              description='Specific container name (for multi-container pods)'),
        field('tail', type='number', label='Tail Lines',
              default=100, group=FieldGroup.OPTIONS,
              min=1, max=10000,
              description='Number of recent log lines to retrieve'),
        field('previous', type='boolean', label='Previous Container',
              default=False, group=FieldGroup.OPTIONS,
              description='Get logs from the previous terminated container instance'),
        field('kubeconfig', type='string', label='Kubeconfig Path',
              group=FieldGroup.CONNECTION,
              description='Path to kubeconfig file (uses default if not set)'),
    ),
    output_schema={
        'pod': {
            'type': 'string',
            'description': 'Pod name',
            'description_key': 'modules.k8s.logs.output.pod.description',
        },
        'logs': {
            'type': 'string',
            'description': 'Log output text',
            'description_key': 'modules.k8s.logs.output.logs.description',
        },
        'lines': {
            'type': 'number',
            'description': 'Number of log lines returned',
            'description_key': 'modules.k8s.logs.output.lines.description',
        },
    },
)
async def k8s_logs(context: Dict[str, Any]) -> Dict[str, Any]:
    """Retrieve logs from a Kubernetes pod."""
    params = context.get('params', {})
    pod = params.get('pod', '')
    namespace = params.get('namespace', 'default')
    container = params.get('container', '')
    tail = params.get('tail', 100)
    previous = params.get('previous', False)
    kubeconfig = params.get('kubeconfig', '')

    if not pod:
        raise ModuleError('Pod name is required', code='K8S_MISSING_POD')

    cmd = [
        'kubectl', 'logs', pod,
        f'--namespace={namespace}',
        f'--tail={tail}',
    ]

    if container:
        cmd.extend(['--container', container])

    if previous:
        cmd.append('--previous')

    if kubeconfig:
        cmd.append(f'--kubeconfig={kubeconfig}')

    log_detail = f"pod={pod} ns={namespace}"
    if container:
        log_detail += f" container={container}"
    logger.info(f"k8s.logs: {log_detail} tail={tail}")

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(),
            timeout=25,
        )

        if process.returncode != 0:
            stderr_text = stderr_bytes.decode('utf-8', errors='replace').strip()
            raise ModuleError(
                f"kubectl logs failed (exit {process.returncode}): {stderr_text}",
                code='K8S_COMMAND_FAILED',
            )

        logs_text = stdout_bytes.decode('utf-8', errors='replace')
        line_count = logs_text.count('\n')
        # If the last line doesn't end with newline, count it too
        if logs_text and not logs_text.endswith('\n'):
            line_count += 1

        return {
            'ok': True,
            'data': {
                'pod': pod,
                'logs': logs_text,
                'lines': line_count,
            },
        }

    except asyncio.TimeoutError:
        raise ModuleError(
            f'kubectl logs timed out after 25 seconds for pod {pod}',
            code='K8S_TIMEOUT',
        )
    except ModuleError:
        raise
    except Exception as exc:
        raise ModuleError(
            f'Failed to get logs for pod {pod}: {exc}',
            code='K8S_ERROR',
        )
