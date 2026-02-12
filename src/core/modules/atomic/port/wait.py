"""
Port Wait Module
Wait for a network port to become available
"""

import asyncio
import logging
import socket
import time
from typing import Any, Dict

from ...registry import register_module


logger = logging.getLogger(__name__)


@register_module(
    module_id='port.wait',
    version='1.0.0',
    category='atomic',
    subcategory='port',
    tags=['port', 'wait', 'network', 'server', 'ready', 'atomic', 'ssrf_protected', 'path_restricted'],
    label='Wait for Port',
    label_key='modules.port.wait.label',
    description='Wait for a network port to become available',
    description_key='modules.port.wait.description',
    icon='Clock',
    color='#F59E0B',

    # Connection types
    input_types=['number', 'object'],
    output_types=['object', 'boolean'],
    can_connect_to=['browser.*', 'http.*', 'test.*'],
    can_receive_from=['*'],

    # Execution settings
    timeout_ms=120000,  # 2 minutes max wait
    retryable=False,
    concurrent_safe=True,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema={
        'port': {
            'type': 'number',
            'label': 'Port',
            'label_key': 'modules.port.wait.params.port.label',
            'description': 'Port number to wait for',
            'description_key': 'modules.port.wait.params.port.description',
            'required': True,
            'placeholder': '3000',
            'validation': {
                'minimum': 1,
                'maximum': 65535
            }
        },
        'host': {
            'type': 'string',
            'label': 'Host',
            'label_key': 'modules.port.wait.params.host.label',
            'description': 'Host to connect to',
            'description_key': 'modules.port.wait.params.host.description',
            'required': False,
            'default': 'localhost',
            'placeholder': 'localhost',
},
        'timeout': {
            'type': 'number',
            'label': 'Timeout (seconds)',
            'label_key': 'modules.port.wait.params.timeout.label',
            'description': 'Maximum time to wait',
            'description_key': 'modules.port.wait.params.timeout.description',
            'required': False,
            'default': 60
        },
        'interval': {
            'type': 'number',
            'label': 'Check Interval (ms)',
            'label_key': 'modules.port.wait.params.interval.label',
            'description': 'Time between connection attempts in milliseconds',
            'description_key': 'modules.port.wait.params.interval.description',
            'required': False,
            'default': 500
        },
        'expect_closed': {
            'type': 'boolean',
            'label': 'Expect Closed',
            'label_key': 'modules.port.wait.params.expect_closed.label',
            'description': 'Wait for port to become unavailable instead',
            'description_key': 'modules.port.wait.params.expect_closed.description',
            'required': False,
            'default': False
        }
    },
    output_schema={
        'ok': {
            'type': 'boolean',
            'description': 'Whether port is in expected state'
        ,
                'description_key': 'modules.port.wait.output.ok.description'},
        'available': {
            'type': 'boolean',
            'description': 'Whether port is currently available'
        ,
                'description_key': 'modules.port.wait.output.available.description'},
        'host': {
            'type': 'string',
            'description': 'Host that was checked'
        ,
                'description_key': 'modules.port.wait.output.host.description'},
        'port': {
            'type': 'number',
            'description': 'Port that was checked'
        ,
                'description_key': 'modules.port.wait.output.port.description'},
        'wait_time_ms': {
            'type': 'number',
            'description': 'Time spent waiting in milliseconds'
        ,
                'description_key': 'modules.port.wait.output.wait_time_ms.description'},
        'attempts': {
            'type': 'number',
            'description': 'Number of connection attempts'
        ,
                'description_key': 'modules.port.wait.output.attempts.description'}
    },
    examples=[
        {
            'title': 'Wait for dev server',
            'title_key': 'modules.port.wait.examples.dev.title',
            'params': {
                'port': 3000,
                'timeout': 30
            }
        },
        {
            'title': 'Wait for database',
            'title_key': 'modules.port.wait.examples.db.title',
            'params': {
                'port': 5432,
                'host': 'localhost',
                'timeout': 60
            }
        },
        {
            'title': 'Wait for port to close',
            'title_key': 'modules.port.wait.examples.close.title',
            'params': {
                'port': 8080,
                'expect_closed': True,
                'timeout': 10
            }
        }
    ],
    author='Flyto Team',
    license='MIT'
)
async def port_wait(context: Dict[str, Any]) -> Dict[str, Any]:
    """Wait for a network port to become available"""
    params = context['params']
    port = int(params['port'])
    host = params.get('host', 'localhost')
    timeout_seconds = params.get('timeout', 60)
    interval_ms = params.get('interval', 500)
    expect_closed = params.get('expect_closed', False)

    interval_seconds = interval_ms / 1000
    start_time = time.time()
    attempts = 0

    while True:
        elapsed = time.time() - start_time
        if elapsed >= timeout_seconds:
            wait_time_ms = int(elapsed * 1000)

            if expect_closed:
                error_msg = f'Port {host}:{port} did not close within {timeout_seconds}s'
            else:
                error_msg = f'Port {host}:{port} did not become available within {timeout_seconds}s'

            logger.warning(error_msg)
            return {
                'ok': False,
                'available': not expect_closed,
                'host': host,
                'port': port,
                'wait_time_ms': wait_time_ms,
                'attempts': attempts,
                'error': error_msg,
                'error_code': 'TIMEOUT'
            }

        attempts += 1
        is_open = await _check_port(host, port)

        if expect_closed:
            if not is_open:
                wait_time_ms = int((time.time() - start_time) * 1000)
                logger.info(f"Port {host}:{port} is now closed (waited {wait_time_ms}ms)")
                return {
                    'ok': True,
                    'available': False,
                    'host': host,
                    'port': port,
                    'wait_time_ms': wait_time_ms,
                    'attempts': attempts
                }
        else:
            if is_open:
                wait_time_ms = int((time.time() - start_time) * 1000)
                logger.info(f"Port {host}:{port} is now available (waited {wait_time_ms}ms)")
                return {
                    'ok': True,
                    'available': True,
                    'host': host,
                    'port': port,
                    'wait_time_ms': wait_time_ms,
                    'attempts': attempts
                }

        await asyncio.sleep(interval_seconds)


async def _check_port(host: str, port: int) -> bool:
    """Check if a port is open"""
    try:
        # Use asyncio's socket operations for non-blocking check
        loop = asyncio.get_event_loop()

        def sync_check():
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            try:
                result = sock.connect_ex((host, port))
                return result == 0
            finally:
                sock.close()

        return await loop.run_in_executor(None, sync_check)
    except Exception:
        return False
