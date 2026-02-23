# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Kubernetes Scale Module
Scale a Kubernetes deployment to a specified number of replicas
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


def _validate_scale_params(deployment: str, replicas) -> int:
    """Validate and return the integer replicas count."""
    if not deployment:
        raise ModuleError('Deployment name is required', code='K8S_MISSING_DEPLOYMENT')
    if replicas is None:
        raise ModuleError('Replicas count is required', code='K8S_MISSING_REPLICAS')
    replicas = int(replicas)
    if replicas < 0:
        raise ModuleError(
            f'Replicas must be >= 0, got {replicas}', code='K8S_INVALID_REPLICAS',
        )
    return replicas


async def _run_kubectl_scale(cmd: list, deployment: str) -> str:
    """Execute kubectl scale and return stdout text."""
    process = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout_bytes, stderr_bytes = await asyncio.wait_for(
        process.communicate(), timeout=25,
    )
    if process.returncode != 0:
        stderr_text = stderr_bytes.decode('utf-8', errors='replace').strip()
        raise ModuleError(
            f"kubectl scale failed (exit {process.returncode}): {stderr_text}",
            code='K8S_COMMAND_FAILED',
        )
    return stdout_bytes.decode('utf-8', errors='replace').strip()


@register_module(
    module_id='k8s.scale',
    version='1.0.0',
    category='k8s',
    tags=['kubernetes', 'k8s', 'scale', 'deployment', 'replicas', 'autoscale'],
    label='Scale Deployment',
    label_key='modules.k8s.scale.label',
    description='Scale a Kubernetes deployment to a specified replica count',
    description_key='modules.k8s.scale.description',
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
        field('deployment', type='string', label='Deployment Name',
              required=True, group=FieldGroup.BASIC,
              description='Name of the deployment to scale',
              placeholder='my-app'),
        field('replicas', type='number', label='Replicas',
              required=True, group=FieldGroup.BASIC,
              min=0, max=1000,
              description='Desired number of replicas'),
        field('namespace', type='string', label='Namespace',
              default='default', group=FieldGroup.BASIC,
              description='Kubernetes namespace',
              placeholder='default'),
        field('kubeconfig', type='string', label='Kubeconfig Path',
              group=FieldGroup.CONNECTION,
              description='Path to kubeconfig file (uses default if not set)',
              placeholder='~/.kube/config'),
    ),
    output_schema={
        'deployment': {
            'type': 'string',
            'description': 'Deployment name',
            'description_key': 'modules.k8s.scale.output.deployment.description',
        },
        'replicas': {
            'type': 'number',
            'description': 'Requested replica count',
            'description_key': 'modules.k8s.scale.output.replicas.description',
        },
        'namespace': {
            'type': 'string',
            'description': 'Kubernetes namespace',
            'description_key': 'modules.k8s.scale.output.namespace.description',
        },
        'scaled': {
            'type': 'boolean',
            'description': 'Whether the scale operation succeeded',
            'description_key': 'modules.k8s.scale.output.scaled.description',
        },
    },
)
async def k8s_scale(context: Dict[str, Any]) -> Dict[str, Any]:
    """Scale a Kubernetes deployment to a specified replica count."""
    params = context.get('params', {})
    deployment = params.get('deployment', '')
    replicas = _validate_scale_params(deployment, params.get('replicas'))
    namespace = params.get('namespace', 'default')
    kubeconfig = params.get('kubeconfig', '')

    cmd = [
        'kubectl', 'scale', f'deployment/{deployment}',
        f'--replicas={replicas}', f'--namespace={namespace}',
    ]
    if kubeconfig:
        cmd.append(f'--kubeconfig={kubeconfig}')

    logger.info(f"k8s.scale: deployment={deployment} replicas={replicas} ns={namespace}")

    try:
        stdout_text = await _run_kubectl_scale(cmd, deployment)
        scaled = 'scaled' in stdout_text.lower()
        logger.info(f"k8s.scale: {stdout_text}")
        return {
            'ok': True,
            'data': {
                'deployment': deployment, 'replicas': replicas,
                'namespace': namespace, 'scaled': scaled,
            },
        }
    except asyncio.TimeoutError:
        raise ModuleError(
            f'kubectl scale timed out after 25 seconds for {deployment}',
            code='K8S_TIMEOUT',
        )
    except ModuleError:
        raise
    except Exception as exc:
        raise ModuleError(
            f'Failed to scale deployment {deployment}: {exc}',
            code='K8S_ERROR',
        )
