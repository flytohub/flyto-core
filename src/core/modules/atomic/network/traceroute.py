# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Network Traceroute Module
Trace the route packets take to reach a destination host.

HOW FAR THIS MODULE FOLLOWS REALITY

A hop with an address in it is a router that answered: it received a probe with
an expired TTL and sent back an ICMP time-exceeded carrying its own source
address. Nothing in that is a report by a peer about its own work, so an
identified hop is a measurement of the world and the rung rests on it.

A hop of `*` is the opposite -- the absence of an answer -- and the parser
records those as hops too, with `ip: '*'`. So `total_hops` counts PARSED LINES,
not routers found and emphatically not "hops to reach the destination" as the
output schema has always claimed: a trace that dies at hop 3 and prints 27 rows
of asterisks still reports `total_hops: 30`. The envelope reports
`hops_identified` beside it so the difference is visible in the data rather
than only in this paragraph.

    at least one hop carries an address    OBSERVED
    hops parsed, every one of them `*`     DISPATCHED
    nothing parsed at all                  INDETERMINATE

The last one matters because the module returns `ok: True` regardless. An empty
`hops` list and `total_hops: 0` are what this module initialises to, so they
read identically whether the trace found nothing or its output was in a form
these regexes do not cover.
"""
import asyncio
import logging
import platform
import re
from typing import Any, Dict, List, Optional

from ....utils import enforce_outbound_host
from ....engine.outcome import ClaimBy, Outcome, envelope
from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError, ModuleError

logger = logging.getLogger(__name__)


def _traceroute_outcome(
    *,
    host: str,
    hops: List[Dict[str, Any]],
    exit_code: Optional[int],
    stderr_excerpt: str,
) -> Dict[str, Any]:
    """The rung this trace earned, and what was counted to earn it.

    The count that decides it is `hops_identified` -- rows whose `ip` is not
    the `'*'` placeholder this module writes for a hop that never answered.
    `len(hops)` cannot decide it: an all-asterisk trace has a long `hops` list
    and zero information in it.

    Nothing here observes that the destination was reached. Doing so would mean
    resolving the target and comparing it with the last identified hop, and the
    module does neither, so no rung is claimed about arrival.
    """
    identified = [hop for hop in hops if hop.get('ip') and hop.get('ip') != '*']
    counts = {
        'host': host,
        'hops_parsed': len(hops),
        'hops_identified': len(identified),
        'exit_code': exit_code,
    }

    if identified:
        return envelope(
            Outcome.OBSERVED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'route_hops_identified',
                'measured_by': 'addresses parsed out of traceroute stdout',
                **counts,
                'last_identified_hop': identified[-1].get('ip'),
                'detail': (
                    'At least one router answered with its own address. This '
                    'observes part of the path; it does not observe that the '
                    'destination was reached -- nothing here compares the last '
                    'hop with the target.'
                ),
            }],
        )

    if hops:
        return envelope(
            Outcome.DISPATCHED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'route_hops_all_silent',
                'measured_by': 'addresses parsed out of traceroute stdout',
                **counts,
                'detail': (
                    'Probes were sent for every hop and not one router '
                    'identified itself. The instruction left us; nobody '
                    'confirmed anything.'
                ),
            }],
        )

    return envelope(
        Outcome.INDETERMINATE,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'traceroute_output_not_parsed',
            'measured_by': None,
            **counts,
            'stderr_excerpt': stderr_excerpt,
            'detail': (
                'No hop line was recognised in the output, so hops: [] and '
                'total_hops: 0 are this module initialising rather than a '
                'result. The trace may have run and printed a form these '
                'patterns do not cover.'
            ),
        }],
    )


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
            'description': (
                'Number of hop lines parsed from the output. This counts rows, '
                'including hops that never answered and appear as "*" -- it is '
                'not the number of hops needed to reach the destination, and a '
                'trace that never arrives still fills it up to max_hops. See '
                'outcome.effects[0].hops_identified for how many of them '
                'carried an address'
            ),
            'description_key': 'modules.network.traceroute.output.total_hops.description',
        },
        'outcome': {
            'type': 'object',
            'description': (
                'How far this trace was followed: "observed" when at least one '
                'router answered with its address, "dispatched" when every hop '
                'was silent, "indeterminate" when no hop line could be parsed '
                'and the empty hops list is a default rather than a result'
            ),
            'description_key': 'modules.network.traceroute.output.outcome.description',
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
    author='Flyto2 Team',
    license='MIT',
)
async def network_traceroute(context: Dict[str, Any]) -> Dict[str, Any]:
    """Trace the route packets take to reach a destination host."""
    params = context['params']
    host = params.get('host', '').strip()
    # SECURITY: probing is this module's purpose, which is exactly why the
    # target must be bounded — otherwise it is a ready-made internal network
    # scanner reachable from any workflow. Loopback stays allowed; private
    # ranges need FLYTO_ALLOWED_HOSTS or FLYTO_ALLOW_PRIVATE_NETWORK.
    enforce_outbound_host(host, purpose='traceroute')
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
        stderr = stderr_bytes.decode('utf-8', errors='replace')
        # After communicate() the child has exited, so returncode is settled.
        exit_code = proc.returncode
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
            'outcome': _traceroute_outcome(
                host=host,
                hops=hops,
                exit_code=exit_code,
                stderr_excerpt=stderr.strip()[:200],
            ),
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
