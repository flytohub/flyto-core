# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

"""
SFTP Upload Module
Upload files to remote servers via SFTP
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
    module_id='ssh.sftp_upload',
    version='1.0.0',
    category='atomic',
    subcategory='ssh',
    tags=['ssh', 'sftp', 'upload', 'file', 'devops'],
    label='SFTP Upload',
    label_key='modules.ssh.sftp_upload.label',
    description='Upload file to remote server via SFTP',
    description_key='modules.ssh.sftp_upload.description',
    icon='Upload',
    color='#3B82F6',

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
    required_permissions=['network.connect', 'filesystem.read'],

    params_schema=compose(
        field('host', type='string', label='Host', label_key='modules.ssh.sftp_upload.params.host.label',
              description='SSH server hostname or IP', required=True,
              placeholder='192.168.1.100', group=FieldGroup.CONNECTION),
        field('port', type='number', label='Port', label_key='modules.ssh.sftp_upload.params.port.label',
              description='SSH port', default=22, min=1, max=65535,
              group=FieldGroup.CONNECTION),
        field('username', type='string', label='Username', label_key='modules.ssh.sftp_upload.params.username.label',
              description='SSH username', required=True, placeholder='deploy',
              group=FieldGroup.CONNECTION),
        field('password', type='string', label='Password', label_key='modules.ssh.sftp_upload.params.password.label',
              description='SSH password', format='password',
              group=FieldGroup.CONNECTION),
        field('private_key', type='string', label='Private Key', label_key='modules.ssh.sftp_upload.params.private_key.label',
              description='PEM-format private key', format='multiline',
              group=FieldGroup.CONNECTION),
        field('local_path', type='string', label='Local Path', label_key='modules.ssh.sftp_upload.params.local_path.label',
              description='Path to local file to upload', required=True,
              placeholder='/tmp/deploy.tar.gz', group=FieldGroup.BASIC),
        field('remote_path', type='string', label='Remote Path', label_key='modules.ssh.sftp_upload.params.remote_path.label',
              description='Destination path on remote server', required=True,
              placeholder='/var/www/deploy.tar.gz', group=FieldGroup.BASIC),
        field('overwrite', type='boolean', label='Overwrite', label_key='modules.ssh.sftp_upload.params.overwrite.label',
              description='Overwrite existing remote file', default=True,
              group=FieldGroup.OPTIONS),
    ),
    output_schema={
        'ok': {'type': 'boolean', 'description': 'Whether upload succeeded'},
        'data': {
            'type': 'object',
            'properties': {
                'remote_path': {'type': 'string', 'description': 'Remote file path'},
                'size_bytes': {'type': 'number', 'description': 'File size in bytes'},
                'host': {'type': 'string', 'description': 'Target host'},
            }
        }
    },
    examples=[
        {
            'title': 'Upload deployment archive',
            'title_key': 'modules.ssh.sftp_upload.examples.deploy.title',
            'params': {
                'host': '10.0.0.5',
                'username': 'deploy',
                'local_path': '/tmp/app.tar.gz',
                'remote_path': '/opt/releases/app.tar.gz'
            }
        }
    ],
    author='Flyto Team',
    license='MIT'
)
async def ssh_sftp_upload(context: Dict[str, Any]) -> Dict[str, Any]:
    """Upload file to remote server via SFTP"""
    try:
        import asyncssh
    except ImportError:
        raise ImportError(
            "asyncssh is required for ssh.sftp_upload. "
            "Install with: pip install asyncssh"
        )

    params = context['params']
    host = params['host']
    port = params.get('port', 22)
    username = params['username']
    password = params.get('password')
    private_key = params.get('private_key')
    local_path = params['local_path']
    remote_path = params['remote_path']
    overwrite = params.get('overwrite', True)

    if not password and not private_key:
        return {
            'ok': False,
            'error': 'Either password or private_key must be provided',
            'error_code': 'MISSING_CREDENTIALS'
        }

    # Validate local file exists
    local_path = os.path.abspath(os.path.expanduser(local_path))
    if not os.path.isfile(local_path):
        return {
            'ok': False,
            'error': f'Local file not found: {local_path}',
            'error_code': 'FILE_NOT_FOUND'
        }

    file_size = os.path.getsize(local_path)

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
                # Check if remote file exists when overwrite is disabled
                if not overwrite:
                    try:
                        await sftp.stat(remote_path)
                        return {
                            'ok': False,
                            'error': f'Remote file already exists: {remote_path}',
                            'error_code': 'FILE_EXISTS'
                        }
                    except asyncssh.SFTPNoSuchFile:
                        pass  # File doesn't exist, safe to upload

                await sftp.put(local_path, remote_path)

                logger.info(
                    f"SFTP upload to {host}: {local_path} -> {remote_path} "
                    f"({file_size} bytes)"
                )

                return {
                    'ok': True,
                    'data': {
                        'remote_path': remote_path,
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
        logger.error(f"SFTP upload error on {host}: {e}")
        return {
            'ok': False,
            'error': str(e),
            'error_code': 'SFTP_ERROR',
            'data': {'host': host}
        }
