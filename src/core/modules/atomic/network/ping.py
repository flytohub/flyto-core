# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Network Ping Module
Ping a host to check connectivity and measure latency.

HOW FAR THIS MODULE FOLLOWS REALITY

Everything this module returns is scraped out of another program's stdout, and
that is the whole difficulty. `packets_sent`, `packets_received`,
`packet_loss_pct` and `latency_ms` are all initialised to constants written in
this file -- `count`, `0`, `100.0`, zeros -- and only some of them are ever
replaced by a number `ping(8)` actually printed. Whether the replacement
happened is not visible anywhere in the payload: a host that is genuinely down
and a `ping` whose output this module could not parse produce byte-identical
results, both with `ok: True`.

So the rung is decided by whether the summary line parsed, and then by what it
said:

    summary line parsed, replies counted > 0     OBSERVED
        Echo replies came back and the ping binary counted them. Reachability
        is not something the far end can misreport: the reply packet arriving
        IS the reachability. What is observed is that the host answered ICMP,
        never that it is healthy.

    summary line parsed, replies counted == 0    DISPATCHED
        `N packets transmitted, 0 received` -- the packets left us and nobody
        confirmed receipt, which is the definition of the bottom rung and is
        exactly right here. It does not distinguish "host down" from "ICMP
        filtered", and it does not pretend to.

    summary line did not parse                   INDETERMINATE
        Every counter in the payload is the default written above, so the
        `100.0` loss and the `alive: False` are this module's initial values
        and not a measurement of anything. INDETERMINATE and not FAILED: the
        ping may well have run correctly and printed a form these regexes do
        not cover (a localised binary, a busybox applet), which is our
        inference being wrong rather than the host being unreachable.

The module has exactly one return and three raises. The raises -- the command
timed out, `ping` is not installed, the spawn failed -- carry no envelope,
because a ModuleError has no payload for one to live in and the executor keeps
only its message and code. The first of those three is the textbook
INDETERMINATE and it is a real gap, written down here rather than papered over
with a rung nothing could read.
"""
import asyncio
import logging
import platform
import re
import time
from typing import Any, Dict, Optional

from ....utils import enforce_outbound_host
from ....engine.outcome import ClaimBy, Outcome, envelope
from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError, ModuleError

logger = logging.getLogger(__name__)


def _ping_outcome(
    *,
    summary_parsed: bool,
    packets_sent: int,
    packets_received: int,
    exit_code: Optional[int],
    stderr_excerpt: str,
) -> Dict[str, Any]:
    """The rung this ping earned, and the measurement that earned it.

    `summary_parsed` is the whole decision and it is a runtime fact: the same
    binary prints a parsable summary for a reachable host and for an unreachable
    one, and prints nothing parsable at all when it fails to resolve the name.

    `exit_code` rides along in every effect but decides nothing. It is a real
    measurement -- the OS reporting on a process rather than us restating an
    input -- but its meaning is not portable enough to hang a rung on: iputils
    returns 1 for "no replies" and 2 for "other error", BSD returns 2 for both,
    and Windows `ping` returns 0 for some "Destination host unreachable"
    replies. It is recorded so a reader can see it, not relied upon.
    """
    counters = {
        'packets_sent': packets_sent,
        'packets_received': packets_received,
        'exit_code': exit_code,
    }

    if not summary_parsed:
        return envelope(
            Outcome.INDETERMINATE,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'ping_summary_not_parsed',
                'measured_by': None,
                **counters,
                'stderr_excerpt': stderr_excerpt,
                'detail': (
                    'No "N packets transmitted, M received, P% packet loss" line '
                    'was found in the output. Every counter in this result is the '
                    'default written in the module -- packets_sent is the count '
                    'parameter, packets_received is 0 and packet_loss_pct is '
                    '100.0 -- so "alive: false" here is an initial value and not '
                    'an observation. The ping may have run correctly and printed '
                    'a form these patterns do not cover.'
                ),
            }],
        )

    if packets_received > 0:
        return envelope(
            Outcome.OBSERVED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'icmp_replies_counted',
                'measured_by': "ping's own 'N packets transmitted, M received' summary",
                **counters,
                'detail': (
                    'Echo replies came back and were counted. This observes that '
                    'the host answers ICMP from here -- not that it is healthy, '
                    'not that any service on it is up.'
                ),
            }],
        )

    return envelope(
        Outcome.DISPATCHED,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'icmp_no_replies',
            'measured_by': "ping's own 'N packets transmitted, M received' summary",
            **counters,
            'detail': (
                'The packets were transmitted and none came back. Nobody '
                'confirmed receipt, which is all this says: a filtered host, a '
                'down host and a dropped reply are the same result here.'
            ),
        }],
    )


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
        'outcome': {
            'type': 'object',
            'description': (
                'How far this probe was followed: "observed" when replies were '
                'counted, "dispatched" when packets were transmitted and none '
                'came back, "indeterminate" when the summary line could not be '
                'parsed and every counter above is a default'
            ),
            'description_key': 'modules.network.ping.output.outcome.description',
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
    author='Flyto2 Team',
    license='MIT',
)
async def network_ping(context: Dict[str, Any]) -> Dict[str, Any]:
    """Ping a host to check connectivity and measure latency."""
    params = context['params']
    host = params.get('host', '').strip()
    # SECURITY: probing is this module's purpose, which is exactly why the
    # target must be bounded — otherwise it is a ready-made internal network
    # scanner reachable from any workflow. Loopback stays allowed; private
    # ranges need FLYTO_ALLOWED_HOSTS or FLYTO_ALLOW_PRIVATE_NETWORK.
    enforce_outbound_host(host, purpose='ping')
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
        # After communicate() the child has exited, so returncode is a number
        # and not a race. It decides nothing (see _ping_outcome) but it is the
        # one signal here the OS produced rather than this module.
        exit_code = proc.returncode
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
            'outcome': _ping_outcome(
                summary_parsed=pkt_match is not None,
                packets_sent=packets_sent,
                packets_received=packets_received,
                exit_code=exit_code,
                stderr_excerpt=stderr.strip()[:200],
            ),
        },
    }
