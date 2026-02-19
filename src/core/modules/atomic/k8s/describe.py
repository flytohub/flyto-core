# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

"""
Kubernetes Describe Module
Describe a Kubernetes resource in detail
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

# Common Kubernetes resource types for validation hint
_COMMON_RESOURCE_TYPES = frozenset({
    'pod', 'pods',
    'deployment', 'deployments',
    'service', 'services', 'svc',
    'ingress', 'ingresses', 'ing',
    'configmap', 'configmaps', 'cm',
    'secret', 'secrets',
    'namespace', 'namespaces', 'ns',
    'node', 'nodes',
    'persistentvolumeclaim', 'persistentvolumeclaims', 'pvc',
    'persistentvolume', 'persistentvolumes', 'pv',
    'statefulset', 'statefulsets', 'sts',
    'daemonset', 'daemonsets', 'ds',
    'replicaset', 'replicasets', 'rs',
    'job', 'jobs',
    'cronjob', 'cronjobs', 'cj',
    'serviceaccount', 'serviceaccounts', 'sa',
    'role', 'roles',
    'rolebinding', 'rolebindings',
    'clusterrole', 'clusterroles',
    'clusterrolebinding', 'clusterrolebindings',
    'networkpolicy', 'networkpolicies', 'netpol',
    'horizontalpodautoscaler', 'horizontalpodautoscalers', 'hpa',
})


@register_module(
    module_id='k8s.describe',
    version='1.0.0',
    category='k8s',
    tags=['kubernetes', 'k8s', 'describe', 'inspect', 'detail', 'debug'],
    label='Describe Resource',
    label_key='modules.k8s.describe.label',
    description='Describe a Kubernetes resource in detail',
    description_key='modules.k8s.describe.description',
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
        field('resource_type', type='string', label='Resource Type',
              required=True, group=FieldGroup.BASIC,
              description='Kubernetes resource type (e.g. pod, deployment, service)',
              placeholder='deployment'),
        field('name', type='string', label='Resource Name',
              required=True, group=FieldGroup.BASIC,
              description='Name of the resource to describe',
              placeholder='my-app'),
        field('namespace', type='string', label='Namespace',
              default='default', group=FieldGroup.OPTIONS,
              description='Kubernetes namespace (ignored for cluster-scoped resources)'),
        field('kubeconfig', type='string', label='Kubeconfig Path',
              group=FieldGroup.CONNECTION,
              description='Path to kubeconfig file (uses default if not set)'),
    ),
    output_schema={
        'resource_type': {
            'type': 'string',
            'description': 'Resource type that was described',
            'description_key': 'modules.k8s.describe.output.resource_type.description',
        },
        'name': {
            'type': 'string',
            'description': 'Resource name',
            'description_key': 'modules.k8s.describe.output.name.description',
        },
        'namespace': {
            'type': 'string',
            'description': 'Kubernetes namespace',
            'description_key': 'modules.k8s.describe.output.namespace.description',
        },
        'description': {
            'type': 'string',
            'description': 'Full kubectl describe output text',
            'description_key': 'modules.k8s.describe.output.description.description',
        },
    },
)
async def k8s_describe(context: Dict[str, Any]) -> Dict[str, Any]:
    """Describe a Kubernetes resource in detail."""
    params = context.get('params', {})
    resource_type = params.get('resource_type', '')
    name = params.get('name', '')
    namespace = params.get('namespace', 'default')
    kubeconfig = params.get('kubeconfig', '')

    if not resource_type:
        raise ModuleError('Resource type is required', code='K8S_MISSING_RESOURCE_TYPE')

    if not name:
        raise ModuleError('Resource name is required', code='K8S_MISSING_NAME')

    cmd = [
        'kubectl', 'describe', resource_type, name,
        f'--namespace={namespace}',
    ]

    if kubeconfig:
        cmd.append(f'--kubeconfig={kubeconfig}')

    logger.info(f"k8s.describe: {resource_type}/{name} ns={namespace}")

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
                f"kubectl describe failed (exit {process.returncode}): {stderr_text}",
                code='K8S_COMMAND_FAILED',
            )

        description_text = stdout_bytes.decode('utf-8', errors='replace')

        return {
            'ok': True,
            'data': {
                'resource_type': resource_type,
                'name': name,
                'namespace': namespace,
                'description': description_text,
            },
        }

    except asyncio.TimeoutError:
        raise ModuleError(
            f'kubectl describe timed out after 25 seconds for {resource_type}/{name}',
            code='K8S_TIMEOUT',
        )
    except ModuleError:
        raise
    except Exception as exc:
        raise ModuleError(
            f'Failed to describe {resource_type}/{name}: {exc}',
            code='K8S_ERROR',
        )
