"""
SFTP Download Module
Download files from remote servers via SFTP
"""

import logging
import os
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup


logger = logging.getLogger(__name__)


@register_module(
    module_id='ssh.sftp_download',
    version='1.0.0',
    category='atomic',
    subcategory='ssh',
    tags=['ssh', 'sftp', 'download', 'file', 'devops'],
    label='SFTP Download',
    label_key='modules.ssh.sftp_download.label',
    description='Download file from remote server via SFTP',
    description_key='modules.ssh.sftp_download.description',
    icon='Download',
    color='#10B981',

    input_types=['string', 'object'],
    output_types=['object'],
    can_connect_to=['*'],
    can_receive_from=['*'],

    timeout_ms=120000,
    retryable=True,
    max_retries=2,
    concurrent_safe=True,

    requires_credentials=True,
    handles_sensitive_data=True,
    required_permissions=['network.connect', 'filesystem.write'],

    params_schema=compose(
        field('host', type='string', label='Host', label_key='modules.ssh.sftp_download.params.host.label',
              description='SSH server hostname or IP', required=True,
              placeholder='192.168.1.100', group=FieldGroup.CONNECTION),
        field('port', type='number', label='Port', label_key='modules.ssh.sftp_download.params.port.label',
              description='SSH port', default=22, min=1, max=65535,
              group=FieldGroup.CONNECTION),
        field('username', type='string', label='Username', label_key='modules.ssh.sftp_download.params.username.label',
              description='SSH username', required=True, placeholder='deploy',
              group=FieldGroup.CONNECTION),
        field('password', type='string', label='Password', label_key='modules.ssh.sftp_download.params.password.label',
              description='SSH password', format='password',
              group=FieldGroup.CONNECTION),
        field('private_key', type='string', label='Private Key', label_key='modules.ssh.sftp_download.params.private_key.label',
              description='PEM-format private key', format='multiline',
              group=FieldGroup.CONNECTION),
        field('remote_path', type='string', label='Remote Path', label_key='modules.ssh.sftp_download.params.remote_path.label',
              description='Path to file on remote server', required=True,
              placeholder='/var/log/app.log', group=FieldGroup.BASIC),
        field('local_path', type='string', label='Local Path', label_key='modules.ssh.sftp_download.params.local_path.label',
              description='Destination path on local machine', required=True,
              placeholder='/tmp/app.log', group=FieldGroup.BASIC),
    ),
    output_schema={
        'ok': {'type': 'boolean', 'description': 'Whether download succeeded'},
        'data': {
            'type': 'object',
            'properties': {
                'local_path': {'type': 'string', 'description': 'Local file path'},
                'size_bytes': {'type': 'number', 'description': 'File size in bytes'},
                'host': {'type': 'string', 'description': 'Source host'},
            }
        }
    },
    examples=[
        {
            'title': 'Download server log',
            'title_key': 'modules.ssh.sftp_download.examples.log.title',
            'params': {
                'host': '10.0.0.5',
                'username': 'deploy',
                'remote_path': '/var/log/nginx/access.log',
                'local_path': '/tmp/access.log'
            }
        }
    ],
    author='Flyto Team',
    license='MIT'
)
async def ssh_sftp_download(context: Dict[str, Any]) -> Dict[str, Any]:
    """Download file from remote server via SFTP"""
    try:
        import asyncssh
    except ImportError:
        raise ImportError(
            "asyncssh is required for ssh.sftp_download. "
            "Install with: pip install asyncssh"
        )

    params = context['params']
    host = params['host']
    port = params.get('port', 22)
    username = params['username']
    password = params.get('password')
    private_key = params.get('private_key')
    remote_path = params['remote_path']
    local_path = params['local_path']

    if not password and not private_key:
        return {
            'ok': False,
            'error': 'Either password or private_key must be provided',
            'error_code': 'MISSING_CREDENTIALS'
        }

    # Ensure local directory exists
    local_path = os.path.abspath(os.path.expanduser(local_path))
    local_dir = os.path.dirname(local_path)
    if not os.path.isdir(local_dir):
        try:
            os.makedirs(local_dir, exist_ok=True)
        except OSError as e:
            return {
                'ok': False,
                'error': f'Cannot create local directory: {e}',
                'error_code': 'DIRECTORY_ERROR'
            }

    connect_opts: Dict[str, Any] = {
        'host': host,
        'port': port,
        'username': username,
        'known_hosts': None,
    }

    if private_key:
        connect_opts['client_keys'] = [asyncssh.import_private_key(private_key)]
    if password:
        connect_opts['password'] = password

    try:
        async with asyncssh.connect(**connect_opts) as conn:
            async with conn.start_sftp_client() as sftp:
                # Check if remote file exists
                try:
                    remote_attrs = await sftp.stat(remote_path)
                except asyncssh.SFTPNoSuchFile:
                    return {
                        'ok': False,
                        'error': f'Remote file not found: {remote_path}',
                        'error_code': 'FILE_NOT_FOUND',
                        'data': {'host': host}
                    }

                await sftp.get(remote_path, local_path)

                file_size = os.path.getsize(local_path)

                logger.info(
                    f"SFTP download from {host}: {remote_path} -> {local_path} "
                    f"({file_size} bytes)"
                )

                return {
                    'ok': True,
                    'data': {
                        'local_path': local_path,
                        'size_bytes': file_size,
                        'host': host,
                    }
                }

    except asyncssh.PermissionDenied as e:
        logger.error(f"SFTP permission denied on {host}: {e}")
        return {
            'ok': False,
            'error': f'SSH authentication failed: {e}',
            'error_code': 'AUTH_FAILED',
            'data': {'host': host}
        }

    except asyncssh.SFTPError as e:
        logger.error(f"SFTP error on {host}: {e}")
        return {
            'ok': False,
            'error': f'SFTP error: {e}',
            'error_code': 'SFTP_ERROR',
            'data': {'host': host}
        }

    except OSError as e:
        logger.error(f"SFTP connection failed to {host}: {e}")
        return {
            'ok': False,
            'error': f'Connection failed: {e}',
            'error_code': 'CONNECTION_ERROR',
            'data': {'host': host}
        }

    except Exception as e:
        logger.error(f"SFTP download error on {host}: {e}")
        return {
            'ok': False,
            'error': str(e),
            'error_code': 'SFTP_ERROR',
            'data': {'host': host}
        }
