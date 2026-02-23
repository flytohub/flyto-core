# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Kubernetes Get Pods Module
List pods in a namespace with optional label filtering
"""

import asyncio
import json
import logging
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ModuleError

logger = logging.getLogger(__name__)


def _parse_pod_status(pod: Dict[str, Any]) -> Dict[str, Any]:
    """Extract a concise pod summary from kubectl JSON output."""
    metadata = pod.get('metadata', {})
    spec = pod.get('spec', {})
    status = pod.get('status', {})

    # Determine ready containers
    container_statuses = status.get('containerStatuses', [])
    ready_count = sum(1 for cs in container_statuses if cs.get('ready', False))
    total_count = len(container_statuses)

    # Sum restarts across all containers
    total_restarts = sum(cs.get('restartCount', 0) for cs in container_statuses)

    # Calculate age from startTime
    age = ''
    start_time = status.get('startTime', '')
    if start_time:
        try:
            from datetime import datetime, timezone
            started = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            delta = now - started
            days = delta.days
            hours = delta.seconds // 3600
            minutes = (delta.seconds % 3600) // 60
            if days > 0:
                age = f"{days}d"
            elif hours > 0:
                age = f"{hours}h"
            else:
                age = f"{minutes}m"
        except Exception:
            age = start_time

    return {
        'name': metadata.get('name', ''),
        'namespace': metadata.get('namespace', ''),
        'status': status.get('phase', 'Unknown'),
        'ready': f"{ready_count}/{total_count}",
        'restarts': total_restarts,
        'age': age,
        'node': spec.get('nodeName', ''),
        'ip': status.get('podIP', ''),
    }


def _build_get_pods_cmd(namespace: str, label_selector: str, kubeconfig: str) -> list:
    """Build the kubectl get pods command."""
    cmd = ['kubectl', 'get', 'pods', f'--namespace={namespace}', '--output=json']
    if label_selector:
        cmd.append(f'--selector={label_selector}')
    if kubeconfig:
        cmd.append(f'--kubeconfig={kubeconfig}')
    return cmd


async def _run_kubectl_get_pods(cmd: list) -> Dict[str, Any]:
    """Execute kubectl get pods and return parsed pod list."""
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_bytes, stderr_bytes = await asyncio.wait_for(
        process.communicate(), timeout=25,
    )
    if process.returncode != 0:
        stderr_text = stderr_bytes.decode('utf-8', errors='replace').strip()
        raise ModuleError(
            f"kubectl get pods failed (exit {process.returncode}): {stderr_text}",
            code='K8S_COMMAND_FAILED',
        )
    stdout_text = stdout_bytes.decode('utf-8', errors='replace')
    data = json.loads(stdout_text)
    items = data.get('items', [])
    pods = [_parse_pod_status(pod) for pod in items]
    return {'pods': pods, 'count': len(pods)}


@register_module(
    module_id='k8s.get_pods',
    version='1.0.0',
    category='k8s',
    tags=['kubernetes', 'k8s', 'pods', 'list', 'container'],
    label='Get Pods',
    label_key='modules.k8s.get_pods.label',
    description='List Kubernetes pods in a namespace',
    description_key='modules.k8s.get_pods.description',
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
        field('namespace', type='string', label='Namespace',
              default='default', group=FieldGroup.BASIC,
              description='Kubernetes namespace to list pods from',
              placeholder='default'),
        field('label_selector', type='string', label='Label Selector',
              group=FieldGroup.OPTIONS,
              description='Filter pods by label selector (e.g. app=nginx)',
              placeholder='app=nginx,env=production'),
        field('kubeconfig', type='string', label='Kubeconfig Path',
              group=FieldGroup.CONNECTION,
              description='Path to kubeconfig file (uses default if not set)',
              placeholder='~/.kube/config'),
    ),
    output_schema={
        'pods': {
            'type': 'array',
            'description': 'List of pods with status information',
            'description_key': 'modules.k8s.get_pods.output.pods.description',
        },
        'count': {
            'type': 'number',
            'description': 'Total number of pods found',
            'description_key': 'modules.k8s.get_pods.output.count.description',
        },
    },
)
async def k8s_get_pods(context: Dict[str, Any]) -> Dict[str, Any]:
    """List Kubernetes pods in a namespace."""
    params = context.get('params', {})
    namespace = params.get('namespace', 'default')
    label_selector = params.get('label_selector', '')
    kubeconfig = params.get('kubeconfig', '')

    cmd = _build_get_pods_cmd(namespace, label_selector, kubeconfig)
    logger.info(f"k8s.get_pods: namespace={namespace} selector={label_selector or '(none)'}")

    try:
        data = await _run_kubectl_get_pods(cmd)
        return {'ok': True, 'data': data}
    except asyncio.TimeoutError:
        raise ModuleError(
            'kubectl get pods timed out after 25 seconds',
            code='K8S_TIMEOUT',
        )
    except json.JSONDecodeError as exc:
        raise ModuleError(
            f'Failed to parse kubectl JSON output: {exc}',
            code='K8S_PARSE_ERROR',
        )
    except ModuleError:
        raise
    except Exception as exc:
        raise ModuleError(
            f'Failed to get pods: {exc}',
            code='K8S_ERROR',
        )
