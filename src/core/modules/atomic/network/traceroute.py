"""
Network Traceroute Module
Trace the route packets take to reach a destination host.
"""
import asyncio
import logging
import platform
import re
from typing import Any, Dict, List

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError, ModuleError

logger = logging.getLogger(__name__)


@register_module(
    module_id='network.traceroute',
    version='1.0.0',
    category='network',
    tags=['network', 'traceroute', 'routing', 'diagnostic', 'hops'],
    label='Traceroute',
    label_key='modules.network.traceroute.label',
    description='Trace the route packets take to reach a destination host',
    description_key='modules.network.traceroute.description',
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
            label_key='modules.network.traceroute.params.host.label',
            description='Hostname or IP address to trace route to',
            description_key='modules.network.traceroute.params.host.description',
            required=True,
            placeholder='example.com',
            group=FieldGroup.BASIC,
        ),
        field(
            'max_hops',
            type='number',
            label='Max Hops',
            label_key='modules.network.traceroute.params.max_hops.label',
            description='Maximum number of hops to trace',
            description_key='modules.network.traceroute.params.max_hops.description',
            default=30,
            min=1,
            max=64,
            group=FieldGroup.OPTIONS,
        ),
        field(
            'timeout',
            type='number',
            label='Timeout',
            label_key='modules.network.traceroute.params.timeout.label',
            description='Timeout in seconds for each probe',
            description_key='modules.network.traceroute.params.timeout.description',
            default=5,
            min=1,
            max=30,
            group=FieldGroup.ADVANCED,
        ),
    ),
    output_schema={
        'host': {
            'type': 'string',
            'description': 'The target host',
            'description_key': 'modules.network.traceroute.output.host.description',
        },
        'hops': {
            'type': 'array',
            'description': 'List of hops along the route',
            'description_key': 'modules.network.traceroute.output.hops.description',
        },
        'total_hops': {
            'type': 'number',
            'description': 'Total number of hops to reach destination',
            'description_key': 'modules.network.traceroute.output.total_hops.description',
        },
    },
    examples=[
        {
            'title': 'Trace route to host',
            'title_key': 'modules.network.traceroute.examples.basic.title',
            'params': {
                'host': 'google.com',
                'max_hops': 30,
            },
        },
    ],
    author='Flyto Team',
    license='MIT',
)
async def network_traceroute(context: Dict[str, Any]) -> Dict[str, Any]:
    """Trace the route packets take to reach a destination host."""
    params = context['params']
    host = params.get('host', '').strip()
    max_hops = int(params.get('max_hops', 30))
    timeout = int(params.get('timeout', 5))

    if not host:
        raise ValidationError("Missing required parameter: host", field="host")

    # Build traceroute command based on platform
    system = platform.system().lower()
    if system == 'windows':
        cmd = ['tracert', '-h', str(max_hops), '-w', str(timeout * 1000), host]
    elif system == 'darwin':
        # macOS traceroute uses -m for max hops and -w for wait time
        cmd = ['traceroute', '-m', str(max_hops), '-w', str(timeout), host]
    else:
        cmd = ['traceroute', '-m', str(max_hops), '-w', str(timeout), host]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        overall_timeout = max_hops * timeout + 30
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(),
            timeout=overall_timeout,
        )
        stdout = stdout_bytes.decode('utf-8', errors='replace')
    except asyncio.TimeoutError:
        raise ModuleError("Traceroute command timed out")
    except FileNotFoundError:
        raise ModuleError("traceroute command not found on this system")
    except Exception as e:
        raise ModuleError("Failed to execute traceroute: {}".format(str(e)))

    # Parse traceroute output
    hops = _parse_traceroute_output(stdout)

    total_hops = len(hops)

    logger.info("Traceroute to %s completed with %d hops", host, total_hops)

    return {
        'ok': True,
        'data': {
            'host': host,
            'hops': hops,
            'total_hops': total_hops,
        },
    }


def _parse_traceroute_output(output: str) -> List[Dict[str, Any]]:
    """Parse traceroute output lines into structured hop data."""
    hops = []
    lines = output.strip().split('\n')

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Match hop number at the start of line: " 1  hostname (ip)  1.234 ms ..."
        hop_match = re.match(r'^\s*(\d+)\s+(.+)', line)
        if not hop_match:
            continue

        hop_number = int(hop_match.group(1))
        rest = hop_match.group(2).strip()

        # Check for timeout (all asterisks)
        if re.match(r'^[\s*]+$', rest):
            hops.append({
                'hop_number': hop_number,
                'ip': '*',
                'hostname': '*',
                'latency_ms': None,
            })
            continue

        # Extract hostname and IP: "hostname (ip) latency ms" or "ip latency ms"
        ip = '*'
        hostname = '*'
        latency_values = []

        # Pattern: hostname (ip) followed by latency values
        host_ip_match = re.match(r'([\w.\-]+)\s+\(([\d.]+)\)\s+(.*)', rest)
        if host_ip_match:
            hostname = host_ip_match.group(1)
            ip = host_ip_match.group(2)
            rest_latency = host_ip_match.group(3)
        else:
            # Pattern: bare IP followed by latency values
            bare_ip_match = re.match(r'([\d.]+)\s+(.*)', rest)
            if bare_ip_match:
                ip = bare_ip_match.group(1)
                hostname = ip
                rest_latency = bare_ip_match.group(2)
            else:
                rest_latency = rest

        # Extract latency values (e.g., "1.234 ms  2.345 ms  3.456 ms")
        latency_values = re.findall(r'([\d.]+)\s*ms', rest_latency)

        # Compute average latency
        avg_latency = None
        if latency_values:
            float_vals = [float(v) for v in latency_values]
            avg_latency = round(sum(float_vals) / len(float_vals), 3)

        hops.append({
            'hop_number': hop_number,
            'ip': ip,
            'hostname': hostname,
            'latency_ms': avg_latency,
        })

    return hops
