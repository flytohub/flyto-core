"""
Port Check Module
Check if a network port is open or closed
"""

import asyncio
import logging
import os
import socket
from typing import Any, Dict, List

from ...registry import register_module
from ....utils import is_private_ip


logger = logging.getLogger(__name__)


# SECURITY: Localhost-only hosts that are always allowed
_LOCALHOST_HOSTS = frozenset({'localhost', '127.0.0.1', '::1', '0.0.0.0'})


@register_module(
    module_id='port.check',
    version='1.0.0',
    category='atomic',
    subcategory='port',
    tags=['port', 'check', 'network', 'status', 'atomic', 'ssrf_protected'],
    label='Check Port',
    label_key='modules.port.check.label',
    description='Check if network port(s) are open or closed',
    description_key='modules.port.check.description',
    icon='Wifi',
    color='#8B5CF6',

    # Connection types
    input_types=['number', 'array', 'object'],
    output_types=['object', 'boolean'],
    can_connect_to=['test.*', 'flow.*'],
    can_receive_from=['*'],

    # Execution settings
    timeout_ms=10000,
    retryable=False,
    concurrent_safe=True,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema={
        'port': {
            'type': 'any',
            'label': 'Port(s)',
            'label_key': 'modules.port.check.params.port.label',
            'description': 'Port number or array of ports to check',
            'description_key': 'modules.port.check.params.port.description',
            'required': True,
            'examples': [3000, [3000, 8080, 5432]]
        },
        'host': {
            'type': 'string',
            'label': 'Host',
            'label_key': 'modules.port.check.params.host.label',
            'description': 'Host to connect to',
            'description_key': 'modules.port.check.params.host.description',
            'required': False,
            'default': 'localhost'
        },
        'connect_timeout': {
            'type': 'number',
            'label': 'Connect Timeout (seconds)',
            'label_key': 'modules.port.check.params.connect_timeout.label',
            'description': 'Timeout for each connection attempt',
            'description_key': 'modules.port.check.params.connect_timeout.description',
            'required': False,
            'default': 2
        },
        'expect_open': {
            'type': 'boolean',
            'label': 'Expect Open',
            'label_key': 'modules.port.check.params.expect_open.label',
            'description': 'Set to true to assert ports are open, false for closed',
            'description_key': 'modules.port.check.params.expect_open.description',
            'required': False
        }
    },
    output_schema={
        'ok': {
            'type': 'boolean',
            'description': 'Whether all checks passed (if expect_open is set)'
        ,
                'description_key': 'modules.port.check.output.ok.description'},
        'results': {
            'type': 'array',
            'description': 'Array of port check results'
        ,
                'description_key': 'modules.port.check.output.results.description'},
        'open_ports': {
            'type': 'array',
            'description': 'List of open ports'
        ,
                'description_key': 'modules.port.check.output.open_ports.description'},
        'closed_ports': {
            'type': 'array',
            'description': 'List of closed ports'
        ,
                'description_key': 'modules.port.check.output.closed_ports.description'},
        'summary': {
            'type': 'object',
            'description': 'Summary statistics'
        ,
                'description_key': 'modules.port.check.output.summary.description'}
    },
    examples=[
        {
            'title': 'Check single port',
            'title_key': 'modules.port.check.examples.single.title',
            'params': {
                'port': 3000
            }
        },
        {
            'title': 'Check multiple ports',
            'title_key': 'modules.port.check.examples.multiple.title',
            'params': {
                'port': [3000, 8080, 5432],
                'host': 'localhost'
            }
        },
        {
            'title': 'Assert ports are open',
            'title_key': 'modules.port.check.examples.assert.title',
            'params': {
                'port': [80, 443],
                'host': 'example.com',
                'expect_open': True
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def port_check(context: Dict[str, Any]) -> Dict[str, Any]:
    """Check if network port(s) are open or closed"""
    params = context['params']
    ports_input = params['port']
    host = params.get('host', 'localhost')
    connect_timeout = params.get('connect_timeout', 2)
    expect_open = params.get('expect_open')

    # SECURITY: Validate host to prevent internal network scanning
    host_lower = host.lower()
    if host_lower not in _LOCALHOST_HOSTS:
        # Check if scanning non-localhost is allowed
        allow_remote = os.environ.get('FLYTO_ALLOW_PORT_SCAN', '').lower() == 'true'
        if not allow_remote:
            # Try to resolve and check if it's a private IP
            try:
                resolved_ip = socket.gethostbyname(host)
                if is_private_ip(resolved_ip):
                    return {
                        'ok': False,
                        'error': f'SSRF blocked: Cannot scan private network host ({host} -> {resolved_ip}). '
                                 'Set FLYTO_ALLOW_PORT_SCAN=true to allow.',
                        'error_code': 'SSRF_BLOCKED',
                        'results': [],
                        'open_ports': [],
                        'closed_ports': [],
                        'summary': {'total': 0, 'open': 0, 'closed': 0}
                    }
            except socket.gaierror:
                # DNS resolution failed - allow the check to fail naturally
                pass

    # Normalize ports to list
    if isinstance(ports_input, int):
        ports = [ports_input]
    elif isinstance(ports_input, list):
        ports = [int(p) for p in ports_input]
    else:
        ports = [int(ports_input)]

    results: List[Dict[str, Any]] = []
    open_ports: List[int] = []
    closed_ports: List[int] = []

    # Check all ports concurrently
    async def check_single_port(port: int) -> Dict[str, Any]:
        is_open = await _check_port_async(host, port, connect_timeout)
        return {
            'port': port,
            'host': host,
            'open': is_open,
            'status': 'open' if is_open else 'closed'
        }

    check_tasks = [check_single_port(port) for port in ports]
    results = await asyncio.gather(*check_tasks)

    # Categorize results
    for result in results:
        if result['open']:
            open_ports.append(result['port'])
        else:
            closed_ports.append(result['port'])

    # Determine ok status
    ok = True
    if expect_open is not None:
        if expect_open:
            ok = len(closed_ports) == 0
        else:
            ok = len(open_ports) == 0

    summary = {
        'total': len(ports),
        'open': len(open_ports),
        'closed': len(closed_ports)
    }

    logger.info(
        f"Port check on {host}: {len(open_ports)} open, "
        f"{len(closed_ports)} closed"
    )

    return {
        'ok': ok,
        'results': results,
        'open_ports': open_ports,
        'closed_ports': closed_ports,
        'summary': summary
    }


async def _check_port_async(host: str, port: int, timeout: float) -> bool:
    """Check if a port is open using asyncio"""
    try:
        # Use asyncio's open_connection which is fully async
        future = asyncio.open_connection(host, port)
        reader, writer = await asyncio.wait_for(future, timeout=timeout)
        writer.close()
        await writer.wait_closed()
        return True
    except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
        return False
    except Exception:
        return False
