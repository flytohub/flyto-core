"""
Network Port Scan Module
Scan ports on a host to check which are open.
"""
import asyncio
import logging
import re
import time
from typing import Any, Dict, List, Union

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError, ModuleError

logger = logging.getLogger(__name__)

# Common well-known ports for default scanning
DEFAULT_PORTS = [21, 22, 23, 25, 53, 80, 110, 143, 443, 993, 995, 3306, 3389, 5432, 8080, 8443]


@register_module(
    module_id='network.port_scan',
    version='1.0.0',
    category='network',
    tags=['network', 'port', 'scan', 'security', 'diagnostic'],
    label='Port Scan',
    label_key='modules.network.port_scan.label',
    description='Scan ports on a host to check which are open',
    description_key='modules.network.port_scan.description',
    icon='Globe',
    color='#06B6D4',
    input_types=['string'],
    output_types=['object'],

    can_receive_from=['*'],
    can_connect_to=['*'],

    retryable=True,
    concurrent_safe=True,
    timeout_ms=120000,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema=compose(
        field(
            'host',
            type='string',
            label='Host',
            label_key='modules.network.port_scan.params.host.label',
            description='Hostname or IP address to scan',
            description_key='modules.network.port_scan.params.host.description',
            required=True,
            placeholder='example.com',
            group=FieldGroup.BASIC,
        ),
        field(
            'ports',
            type='string',
            label='Ports',
            label_key='modules.network.port_scan.params.ports.label',
            description='Ports to scan: comma-separated (80,443), range (80-443), or leave empty for common ports',
            description_key='modules.network.port_scan.params.ports.description',
            placeholder='80,443,8080 or 1-1024',
            group=FieldGroup.BASIC,
        ),
        field(
            'timeout',
            type='number',
            label='Timeout',
            label_key='modules.network.port_scan.params.timeout.label',
            description='Connection timeout in seconds per port',
            description_key='modules.network.port_scan.params.timeout.description',
            default=1.0,
            min=0.1,
            max=10.0,
            step=0.1,
            group=FieldGroup.ADVANCED,
        ),
    ),
    output_schema={
        'host': {
            'type': 'string',
            'description': 'The scanned host',
            'description_key': 'modules.network.port_scan.output.host.description',
        },
        'open_ports': {
            'type': 'array',
            'description': 'List of open port numbers',
            'description_key': 'modules.network.port_scan.output.open_ports.description',
        },
        'closed_ports': {
            'type': 'array',
            'description': 'List of closed port numbers',
            'description_key': 'modules.network.port_scan.output.closed_ports.description',
        },
        'scan_time_ms': {
            'type': 'number',
            'description': 'Total scan time in milliseconds',
            'description_key': 'modules.network.port_scan.output.scan_time_ms.description',
        },
    },
    examples=[
        {
            'title': 'Scan common ports',
            'title_key': 'modules.network.port_scan.examples.common.title',
            'params': {
                'host': 'example.com',
            },
        },
        {
            'title': 'Scan specific port range',
            'title_key': 'modules.network.port_scan.examples.range.title',
            'params': {
                'host': 'example.com',
                'ports': '80-443',
                'timeout': 2.0,
            },
        },
    ],
    author='Flyto Team',
    license='MIT',
)
async def network_port_scan(context: Dict[str, Any]) -> Dict[str, Any]:
    """Scan ports on a host to check which are open."""
    params = context['params']
    host = params.get('host', '').strip()
    ports_input = params.get('ports', '')
    timeout = float(params.get('timeout', 1.0))

    if not host:
        raise ValidationError("Missing required parameter: host", field="host")

    # Parse ports
    port_list = _parse_ports(ports_input)

    if len(port_list) > 10000:
        raise ValidationError(
            "Too many ports to scan (max 10000). Narrow the range.",
            field="ports",
        )

    start_time = time.monotonic()

    # Scan all ports concurrently
    sem = asyncio.Semaphore(200)  # limit concurrency

    async def _check_port(port: int) -> bool:
        async with sem:
            return await _is_port_open(host, port, timeout)

    tasks = [_check_port(port) for port in port_list]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    open_ports = []
    closed_ports = []
    for port, result in zip(port_list, results):
        if isinstance(result, Exception):
            closed_ports.append(port)
        elif result:
            open_ports.append(port)
        else:
            closed_ports.append(port)

    open_ports.sort()
    closed_ports.sort()

    elapsed_ms = round((time.monotonic() - start_time) * 1000, 2)

    logger.info(
        "Port scan %s: %d open, %d closed (%.1fms)",
        host, len(open_ports), len(closed_ports), elapsed_ms,
    )

    return {
        'ok': True,
        'data': {
            'host': host,
            'open_ports': open_ports,
            'closed_ports': closed_ports,
            'scan_time_ms': elapsed_ms,
        },
    }


async def _is_port_open(host: str, port: int, timeout: float) -> bool:
    """Check if a single port is open using TCP connect."""
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout,
        )
        writer.close()
        # Compatibility: wait_for close if available
        try:
            await writer.wait_closed()
        except AttributeError:
            pass
        return True
    except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
        return False


def _parse_ports(ports_input: Union[str, list, None]) -> List[int]:
    """Parse port specification into a list of port numbers."""
    if not ports_input:
        return list(DEFAULT_PORTS)

    # If already a list of ints
    if isinstance(ports_input, list):
        return [int(p) for p in ports_input if 1 <= int(p) <= 65535]

    ports_str = str(ports_input).strip()
    if not ports_str:
        return list(DEFAULT_PORTS)

    result = []
    parts = re.split(r'[,\s]+', ports_str)
    for part in parts:
        part = part.strip()
        if not part:
            continue

        # Range: "80-443"
        range_match = re.match(r'^(\d+)-(\d+)$', part)
        if range_match:
            start = int(range_match.group(1))
            end = int(range_match.group(2))
            if start > end:
                start, end = end, start
            for p in range(start, end + 1):
                if 1 <= p <= 65535:
                    result.append(p)
            continue

        # Single port
        if part.isdigit():
            p = int(part)
            if 1 <= p <= 65535:
                result.append(p)

    # Deduplicate while preserving order
    seen = set()
    deduped = []
    for p in result:
        if p not in seen:
            seen.add(p)
            deduped.append(p)

    return deduped
