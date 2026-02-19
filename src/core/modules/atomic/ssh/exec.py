"""
SSH Execute Module
Execute commands on remote servers via SSH
"""

import asyncio
import logging
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup


logger = logging.getLogger(__name__)


@register_module(
    module_id='ssh.exec',
    version='1.0.0',
    category='atomic',
    subcategory='ssh',
    tags=['ssh', 'remote', 'command', 'devops'],
    label='SSH Execute',
    label_key='modules.ssh.exec.label',
    description='Execute command on remote server via SSH',
    description_key='modules.ssh.exec.description',
    icon='Terminal',
    color='#1E293B',

    input_types=['string', 'object'],
    output_types=['object'],
    can_connect_to=['*'],
    can_receive_from=['*'],

    timeout_ms=60000,
    retryable=True,
    max_retries=2,
    concurrent_safe=True,

    requires_credentials=True,
    handles_sensitive_data=True,
    required_permissions=['network.connect'],

    params_schema=compose(
        field('host', type='string', label='Host', label_key='modules.ssh.exec.params.host.label',
              description='SSH server hostname or IP', required=True,
              placeholder='192.168.1.100', group=FieldGroup.CONNECTION),
        field('port', type='number', label='Port', label_key='modules.ssh.exec.params.port.label',
              description='SSH port', default=22, min=1, max=65535,
              group=FieldGroup.CONNECTION),
        field('username', type='string', label='Username', label_key='modules.ssh.exec.params.username.label',
              description='SSH username', required=True, placeholder='root',
              group=FieldGroup.CONNECTION),
        field('password', type='string', label='Password', label_key='modules.ssh.exec.params.password.label',
              description='SSH password', format='password',
              group=FieldGroup.CONNECTION),
        field('private_key', type='string', label='Private Key', label_key='modules.ssh.exec.params.private_key.label',
              description='PEM-format private key', format='multiline',
              group=FieldGroup.CONNECTION),
        field('command', type='string', label='Command', label_key='modules.ssh.exec.params.command.label',
              description='Command to execute on remote server', required=True,
              format='multiline', placeholder='ls -la /var/log',
              group=FieldGroup.BASIC),
        field('timeout', type='number', label='Timeout', label_key='modules.ssh.exec.params.timeout.label',
              description='Command timeout in seconds', default=30, min=1, max=3600,
              group=FieldGroup.ADVANCED),
    ),
    output_schema={
        'ok': {'type': 'boolean', 'description': 'Whether command succeeded'},
        'data': {
            'type': 'object',
            'properties': {
                'stdout': {'type': 'string', 'description': 'Standard output'},
                'stderr': {'type': 'string', 'description': 'Standard error'},
                'exit_code': {'type': 'number', 'description': 'Exit code'},
                'host': {'type': 'string', 'description': 'Target host'},
            }
        }
    },
    examples=[
        {
            'title': 'List files on remote server',
            'title_key': 'modules.ssh.exec.examples.ls.title',
            'params': {
                'host': '192.168.1.100',
                'username': 'deploy',
                'command': 'ls -la /var/www'
            }
        },
        {
            'title': 'Restart service',
            'title_key': 'modules.ssh.exec.examples.restart.title',
            'params': {
                'host': '10.0.0.5',
                'username': 'root',
                'command': 'systemctl restart nginx'
            }
        }
    ],
    author='Flyto Team',
    license='MIT'
)
async def ssh_exec(context: Dict[str, Any]) -> Dict[str, Any]:
    """Execute command on remote server via SSH"""
    try:
        import asyncssh
    except ImportError:
        raise ImportError(
            "asyncssh is required for ssh.exec. "
            "Install with: pip install asyncssh"
        )

    params = context['params']
    host = params['host']
    port = params.get('port', 22)
    username = params['username']
    password = params.get('password')
    private_key = params.get('private_key')
    command = params['command']
    timeout = params.get('timeout', 30)

    if not password and not private_key:
        return {
            'ok': False,
            'error': 'Either password or private_key must be provided',
            'error_code': 'MISSING_CREDENTIALS'
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
            result = await asyncio.wait_for(
                conn.run(command, check=False),
                timeout=timeout
            )

            stdout = result.stdout or ''
            stderr = result.stderr or ''
            exit_code = result.exit_status or 0

            logger.info(
                f"SSH exec on {host}: exit_code={exit_code}, "
                f"stdout_len={len(stdout)}, stderr_len={len(stderr)}"
            )

            return {
                'ok': True,
                'data': {
                    'stdout': stdout,
                    'stderr': stderr,
                    'exit_code': exit_code,
                    'host': host,
                }
            }

    except asyncio.TimeoutError:
        logger.error(f"SSH command timed out on {host} after {timeout}s")
        return {
            'ok': False,
            'error': f'Command timed out after {timeout} seconds',
            'error_code': 'TIMEOUT',
            'data': {'host': host}
        }

    except asyncssh.DisconnectError as e:
        logger.error(f"SSH disconnect error on {host}: {e}")
        return {
            'ok': False,
            'error': f'SSH connection disconnected: {e}',
            'error_code': 'DISCONNECT',
            'data': {'host': host}
        }

    except asyncssh.PermissionDenied as e:
        logger.error(f"SSH permission denied on {host}: {e}")
        return {
            'ok': False,
            'error': f'SSH authentication failed: {e}',
            'error_code': 'AUTH_FAILED',
            'data': {'host': host}
        }

    except OSError as e:
        logger.error(f"SSH connection failed to {host}: {e}")
        return {
            'ok': False,
            'error': f'Connection failed: {e}',
            'error_code': 'CONNECTION_ERROR',
            'data': {'host': host}
        }

    except Exception as e:
        logger.error(f"SSH exec error on {host}: {e}")
        return {
            'ok': False,
            'error': str(e),
            'error_code': 'SSH_ERROR',
            'data': {'host': host}
        }
