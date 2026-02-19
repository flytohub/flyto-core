# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

"""
Network Ping Module
Ping a host to check connectivity and measure latency.
"""
import asyncio
import logging
import platform
import re
import time
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError, ModuleError

logger = logging.getLogger(__name__)


@register_module(
    module_id='network.ping',
    version='1.0.0',
    category='network',
    tags=['network', 'ping', 'connectivity', 'latency', 'diagnostic'],
    label='Ping',
    label_key='modules.network.ping.label',
    description='Ping a host to check connectivity and measure latency',
    description_key='modules.network.ping.description',
    icon='Globe',
    color='#06B6D4',
    input_types=['string'],
    output_types=['object'],

    can_receive_from=['*'],
    can_connect_to=['*'],

    retryable=True,
    concurrent_safe=True,
    timeout_ms=30000,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema=compose(
        field(
            'host',
            type='string',
            label='Host',
            label_key='modules.network.ping.params.host.label',
            description='Hostname or IP address to ping',
            description_key='modules.network.ping.params.host.description',
            required=True,
            placeholder='example.com',
            group=FieldGroup.BASIC,
        ),
        field(
            'count',
            type='number',
            label='Count',
            label_key='modules.network.ping.params.count.label',
            description='Number of ping packets to send',
            description_key='modules.network.ping.params.count.description',
            default=4,
            min=1,
            max=100,
            group=FieldGroup.OPTIONS,
        ),
        field(
            'timeout',
            type='number',
            label='Timeout',
            label_key='modules.network.ping.params.timeout.label',
            description='Timeout in seconds for each packet',
            description_key='modules.network.ping.params.timeout.description',
            default=5,
            min=1,
            max=60,
            group=FieldGroup.ADVANCED,
        ),
    ),
    output_schema={
        'host': {
            'type': 'string',
            'description': 'The pinged host',
            'description_key': 'modules.network.ping.output.host.description',
        },
        'alive': {
            'type': 'boolean',
            'description': 'Whether the host responded',
            'description_key': 'modules.network.ping.output.alive.description',
        },
        'packets_sent': {
            'type': 'number',
            'description': 'Number of packets sent',
            'description_key': 'modules.network.ping.output.packets_sent.description',
        },
        'packets_received': {
            'type': 'number',
            'description': 'Number of packets received',
            'description_key': 'modules.network.ping.output.packets_received.description',
        },
        'packet_loss_pct': {
            'type': 'number',
            'description': 'Packet loss percentage',
            'description_key': 'modules.network.ping.output.packet_loss_pct.description',
        },
        'latency_ms': {
            'type': 'object',
            'description': 'Latency statistics in milliseconds (min, avg, max)',
            'description_key': 'modules.network.ping.output.latency_ms.description',
        },
    },
    examples=[
        {
            'title': 'Ping a host',
            'title_key': 'modules.network.ping.examples.basic.title',
            'params': {
                'host': 'google.com',
                'count': 4,
                'timeout': 5,
            },
        },
    ],
    author='Flyto Team',
    license='MIT',
)
async def network_ping(context: Dict[str, Any]) -> Dict[str, Any]:
    """Ping a host to check connectivity and measure latency."""
    params = context['params']
    host = params.get('host', '').strip()
    count = int(params.get('count', 4))
    timeout = int(params.get('timeout', 5))

    if not host:
        raise ValidationError("Missing required parameter: host", field="host")

    # Build ping command based on platform
    system = platform.system().lower()
    if system == 'windows':
        cmd = ['ping', '-n', str(count), '-w', str(timeout * 1000), host]
    else:
        cmd = ['ping', '-c', str(count), '-W', str(timeout), host]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(),
            timeout=count * timeout + 10,
        )
        stdout = stdout_bytes.decode('utf-8', errors='replace')
        stderr = stderr_bytes.decode('utf-8', errors='replace')
    except asyncio.TimeoutError:
        raise ModuleError("Ping command timed out")
    except FileNotFoundError:
        raise ModuleError("ping command not found on this system")
    except Exception as e:
        raise ModuleError("Failed to execute ping: {}".format(str(e)))

    # Parse packet statistics
    packets_sent = count
    packets_received = 0
    packet_loss_pct = 100.0
    latency_ms = {'min': 0.0, 'avg': 0.0, 'max': 0.0}

    # Parse packets: "4 packets transmitted, 4 received, 0% packet loss"
    pkt_match = re.search(
        r'(\d+)\s+packets?\s+transmitted.*?(\d+)\s+(?:packets?\s+)?received.*?(\d+(?:\.\d+)?)%\s+(?:packet\s+)?loss',
        stdout,
        re.IGNORECASE,
    )
    if pkt_match:
        packets_sent = int(pkt_match.group(1))
        packets_received = int(pkt_match.group(2))
        packet_loss_pct = float(pkt_match.group(3))

    # Parse latency: "min/avg/max/mdev = 1.234/5.678/9.012/1.234 ms"
    # or on macOS: "round-trip min/avg/max/stddev = 1.234/5.678/9.012/1.234 ms"
    lat_match = re.search(
        r'(?:rtt|round-trip)\s+min/avg/max/(?:mdev|stddev)\s*=\s*'
        r'([\d.]+)/([\d.]+)/([\d.]+)',
        stdout,
        re.IGNORECASE,
    )
    if lat_match:
        latency_ms = {
            'min': float(lat_match.group(1)),
            'avg': float(lat_match.group(2)),
            'max': float(lat_match.group(3)),
        }

    # Windows latency parsing: "Minimum = 1ms, Maximum = 5ms, Average = 3ms"
    if not lat_match and system == 'windows':
        win_match = re.search(
            r'Minimum\s*=\s*(\d+)ms.*Maximum\s*=\s*(\d+)ms.*Average\s*=\s*(\d+)ms',
            stdout,
            re.IGNORECASE,
        )
        if win_match:
            latency_ms = {
                'min': float(win_match.group(1)),
                'max': float(win_match.group(2)),
                'avg': float(win_match.group(3)),
            }

    alive = packets_received > 0

    logger.info(
        "Ping %s: %s (%d/%d packets, %.1f%% loss)",
        host, "alive" if alive else "dead",
        packets_received, packets_sent, packet_loss_pct,
    )

    return {
        'ok': True,
        'data': {
            'host': host,
            'alive': alive,
            'packets_sent': packets_sent,
            'packets_received': packets_received,
            'packet_loss_pct': packet_loss_pct,
            'latency_ms': latency_ms,
        },
    }
