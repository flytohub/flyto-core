# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Kubernetes Apply Module
Apply a Kubernetes manifest (YAML or dict) via kubectl apply
"""

import asyncio
import json
import logging
import os
import tempfile
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ModuleError

logger = logging.getLogger(__name__)


def _to_yaml_string(manifest: Any) -> str:
    """Convert a manifest (dict or string) to a YAML string suitable for kubectl."""
    if isinstance(manifest, str):
        return manifest

    if isinstance(manifest, dict):
        # Try yaml first, fall back to json (kubectl accepts both)
        try:
            import yaml
            return yaml.dump(manifest, default_flow_style=False)
        except ImportError:
            return json.dumps(manifest, indent=2)

    raise ModuleError(
        f'Manifest must be a YAML string or dict, got {type(manifest).__name__}',
        code='K8S_INVALID_MANIFEST',
    )


def _parse_apply_output(output: str) -> Dict[str, Any]:
    """Parse the JSON output from kubectl apply to extract action details."""
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        # kubectl may return non-JSON on some actions; parse text
        # e.g. "deployment.apps/nginx configured"
        action = 'unknown'
        for keyword in ('created', 'configured', 'unchanged'):
            if keyword in output.lower():
                action = keyword
                break
        return {
            'kind': 'Unknown',
            'name': 'Unknown',
            'namespace': '',
            'action': action,
            'raw': output.strip(),
        }

    metadata = data.get('metadata', {})
    kind = data.get('kind', 'Unknown')
    name = metadata.get('name', 'Unknown')
    namespace = metadata.get('namespace', '')

    # Determine action from managedFields or annotation
    action = 'configured'
    managed = metadata.get('managedFields', [])
    if managed:
        last_op = managed[-1].get('operation', '')
        if last_op == 'Update':
            action = 'configured'
        elif last_op == 'Apply':
            action = 'configured'

    # Check creation timestamp vs last-applied to infer created
    creation = metadata.get('creationTimestamp', '')
    resource_version = metadata.get('resourceVersion', '')
    if resource_version and creation:
        # If resourceVersion is "1" it's likely just created
        # This is a heuristic; kubectl annotates differently
        pass

    return {
        'kind': kind,
        'name': name,
        'namespace': namespace,
        'action': action,
    }


def _write_manifest_to_tempfile(manifest_str: str):
    """Write manifest string to a temp file, returning (fd, path)."""
    tmp_fd, tmp_path = tempfile.mkstemp(suffix='.yaml', prefix='flyto-k8s-')
    os.write(tmp_fd, manifest_str.encode('utf-8'))
    os.close(tmp_fd)
    return tmp_path


def _cleanup_tempfile(tmp_path: str) -> None:
    """Remove a temp file if it exists."""
    if tmp_path and os.path.exists(tmp_path):
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


async def _run_kubectl_apply(tmp_path: str, namespace: str, kubeconfig: str) -> Dict[str, Any]:
    """Execute kubectl apply and return parsed result."""
    cmd = ['kubectl', 'apply', '-f', tmp_path, '--output=json']
    if namespace:
        cmd.append(f'--namespace={namespace}')
    if kubeconfig:
        cmd.append(f'--kubeconfig={kubeconfig}')

    process = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout_bytes, stderr_bytes = await asyncio.wait_for(
        process.communicate(), timeout=55,
    )
    if process.returncode != 0:
        stderr_text = stderr_bytes.decode('utf-8', errors='replace').strip()
        raise ModuleError(
            f"kubectl apply failed (exit {process.returncode}): {stderr_text}",
            code='K8S_COMMAND_FAILED',
        )
    stdout_text = stdout_bytes.decode('utf-8', errors='replace')
    return _parse_apply_output(stdout_text)


@register_module(
    module_id='k8s.apply',
    version='1.0.0',
    category='k8s',
    tags=['kubernetes', 'k8s', 'apply', 'deploy', 'manifest', 'yaml'],
    label='Apply Manifest',
    label_key='modules.k8s.apply.label',
    description='Apply a Kubernetes manifest via kubectl apply',
    description_key='modules.k8s.apply.description',
    icon='Cloud',
    color='#326CE5',
    input_types=['string', 'object'],
    output_types=['object'],
    can_receive_from=['*'],
    can_connect_to=['*'],
    retryable=True,
    concurrent_safe=True,
    timeout_ms=60000,
    params_schema=compose(
        field('manifest', type='string', label='Manifest',
              required=True, group=FieldGroup.BASIC,
              format='multiline',
              description='Kubernetes manifest as YAML string or JSON object',
              placeholder='apiVersion: v1\nkind: Pod\n...'),
        field('namespace', type='string', label='Namespace',
              group=FieldGroup.OPTIONS,
              description='Override namespace for the resource (optional)',
              placeholder='default'),
        field('kubeconfig', type='string', label='Kubeconfig Path',
              group=FieldGroup.CONNECTION,
              description='Path to kubeconfig file (uses default if not set)',
              placeholder='~/.kube/config'),
    ),
    output_schema={
        'kind': {
            'type': 'string',
            'description': 'Resource kind (e.g. Deployment, Service)',
            'description_key': 'modules.k8s.apply.output.kind.description',
        },
        'name': {
            'type': 'string',
            'description': 'Resource name',
            'description_key': 'modules.k8s.apply.output.name.description',
        },
        'namespace': {
            'type': 'string',
            'description': 'Resource namespace',
            'description_key': 'modules.k8s.apply.output.namespace.description',
        },
        'action': {
            'type': 'string',
            'description': 'Action taken (created, configured, unchanged)',
            'description_key': 'modules.k8s.apply.output.action.description',
        },
    },
)
async def k8s_apply(context: Dict[str, Any]) -> Dict[str, Any]:
    """Apply a Kubernetes manifest via kubectl apply."""
    params = context.get('params', {})
    manifest = params.get('manifest')
    namespace = params.get('namespace', '')
    kubeconfig = params.get('kubeconfig', '')

    if not manifest:
        raise ModuleError('Manifest is required', code='K8S_MISSING_MANIFEST')

    manifest_str = _to_yaml_string(manifest)
    logger.info(f"k8s.apply: applying manifest ({len(manifest_str)} bytes)")

    tmp_path = _write_manifest_to_tempfile(manifest_str)
    try:
        result = await _run_kubectl_apply(tmp_path, namespace, kubeconfig)
        return {'ok': True, 'data': result}
    except asyncio.TimeoutError:
        raise ModuleError(
            'kubectl apply timed out after 55 seconds', code='K8S_TIMEOUT',
        )
    except ModuleError:
        raise
    except Exception as exc:
        raise ModuleError(
            f'Failed to apply manifest: {exc}', code='K8S_ERROR',
        )
    finally:
        _cleanup_tempfile(tmp_path)
