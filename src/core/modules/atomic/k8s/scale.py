# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

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


@register_module(
    module_id='k8s.scale',
    version='1.0.0',
    category='k8s',
    tags=['kubernetes', 'k8s', 'scale', 'deployment', 'replicas', 'autoscale'],
    label='Scale Deployment',
    description='Scale a Kubernetes deployment to a specified replica count',
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
              description='Kubernetes namespace'),
        field('kubeconfig', type='string', label='Kubeconfig Path',
              group=FieldGroup.CONNECTION,
              description='Path to kubeconfig file (uses default if not set)'),
    ),
    output_schema={
        'deployment': {
            'type': 'string',
            'description': 'Deployment name',
        },
        'replicas': {
            'type': 'number',
            'description': 'Requested replica count',
        },
        'namespace': {
            'type': 'string',
            'description': 'Kubernetes namespace',
        },
        'scaled': {
            'type': 'boolean',
            'description': 'Whether the scale operation succeeded',
        },
    },
)
async def k8s_scale(context: Dict[str, Any]) -> Dict[str, Any]:
    """Scale a Kubernetes deployment to a specified replica count."""
    params = context.get('params', {})
    deployment = params.get('deployment', '')
    replicas = params.get('replicas')
    namespace = params.get('namespace', 'default')
    kubeconfig = params.get('kubeconfig', '')

    if not deployment:
        raise ModuleError('Deployment name is required', code='K8S_MISSING_DEPLOYMENT')

    if replicas is None:
        raise ModuleError('Replicas count is required', code='K8S_MISSING_REPLICAS')

    replicas = int(replicas)
    if replicas < 0:
        raise ModuleError(
            f'Replicas must be >= 0, got {replicas}',
            code='K8S_INVALID_REPLICAS',
        )

    cmd = [
        'kubectl', 'scale',
        f'deployment/{deployment}',
        f'--replicas={replicas}',
        f'--namespace={namespace}',
    ]

    if kubeconfig:
        cmd.append(f'--kubeconfig={kubeconfig}')

    logger.info(f"k8s.scale: deployment={deployment} replicas={replicas} ns={namespace}")

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
                f"kubectl scale failed (exit {process.returncode}): {stderr_text}",
                code='K8S_COMMAND_FAILED',
            )

        stdout_text = stdout_bytes.decode('utf-8', errors='replace').strip()
        # kubectl scale output: "deployment.apps/my-app scaled"
        scaled = 'scaled' in stdout_text.lower()

        logger.info(f"k8s.scale: {stdout_text}")

        return {
            'ok': True,
            'data': {
                'deployment': deployment,
                'replicas': replicas,
                'namespace': namespace,
                'scaled': scaled,
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
