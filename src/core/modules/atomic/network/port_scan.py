# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Network Port Scan Module
Scan ports on a host to check which are open.

HOW FAR THIS MODULE FOLLOWS REALITY

A completed TCP handshake is about as direct a measurement of the world as this
registry contains: something on the far end accepted a connection, and no
report by a peer about itself is involved. `open_ports` is therefore evidence
and the rung rests on it.

`closed_ports` is not evidence, and the output field's name is the reason this
needed care. Three different outcomes land in it -- a RST (the host is up and
nothing is listening), a timeout (something dropped the packet, or the host is
gone), and any other socket error -- and the probe used to collapse all three
into `False` before anything could tell them apart. A scan that returns
`open_ports: []` would then read identically whether every port was refused by
a live host or every packet vanished into a firewall, which is precisely the
"would this value be the same if the effect had not happened" failure this
contract exists to stop.

So the probe now reports which of the three happened, `closed_ports` keeps its
old contents exactly, and the rung is decided from the distinction:

    a port accepted a connection          OBSERVED
    nothing accepted, something refused   OBSERVED  (the host answered)
    nothing accepted, nothing refused     DISPATCHED (SYNs left, silence back)

DISPATCHED and not INDETERMINATE for the last one: we do know the packets left,
which is exactly what the bottom rung says and more than "we cannot tell".
"""
import asyncio
import logging
import re
import time
from typing import Any, Dict, List, Union

from ....utils import enforce_outbound_host
from ....engine.outcome import ClaimBy, Outcome, envelope
from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError, ModuleError

logger = logging.getLogger(__name__)

# Common well-known ports for default scanning
DEFAULT_PORTS = [21, 22, 23, 25, 53, 80, 110, 143, 443, 993, 995, 3306, 3389, 5432, 8080, 8443]

#: What one TCP probe found. Three answers, because collapsing the last two
#: into "closed" is what made a silent scan indistinguishable from a refused
#: one. `closed_ports` in the output still contains REFUSED and SILENT alike --
#: this distinction exists for the outcome envelope, not to reclassify results.
PROBE_OPEN = 'open'
PROBE_REFUSED = 'refused'
PROBE_SILENT = 'silent'


def _scan_outcome(
    *,
    host: str,
    ports_probed: int,
    open_count: int,
    refused_count: int,
    silent_count: int,
) -> Dict[str, Any]:
    """The rung this scan earned, and the probe counts that earned it.

    OBSERVED twice, for two different observations, which is why they are
    separate effect kinds rather than one:

    * `tcp_connections_accepted` -- a listener completed a handshake. The
      strongest thing here.
    * `tcp_connections_refused` -- no listener, but the host sent a RST. That
      is the host answering: it observes that the machine is up and reachable,
      and nothing about any service on it.

    DISPATCHED when neither happened. Every probe timed out or errored, so the
    only fact is that the connection attempts left this machine. `closed_ports`
    is still fully populated on that path and still says "closed"; the envelope
    is where a consumer finds out that nothing confirmed it.
    """
    counts = {
        'host': host,
        'ports_probed': ports_probed,
        'open': open_count,
        'refused': refused_count,
        'silent': silent_count,
    }

    if open_count > 0:
        return envelope(
            Outcome.OBSERVED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'tcp_connections_accepted',
                'measured_by': 'asyncio.open_connection returning a writer',
                **counts,
                'detail': (
                    'At least one port completed a TCP handshake. Something on '
                    'the far end accepted the connection; what it is was not '
                    'asked and is not claimed.'
                ),
            }],
        )

    if refused_count > 0:
        return envelope(
            Outcome.OBSERVED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'tcp_connections_refused',
                'measured_by': 'ConnectionRefusedError from asyncio.open_connection',
                **counts,
                'detail': (
                    'No port accepted a connection, but the host actively '
                    'refused at least one. The refusal is an answer from the '
                    'host, so its reachability is observed even though no '
                    'service was found.'
                ),
            }],
        )

    return envelope(
        Outcome.DISPATCHED,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'tcp_no_response',
            'measured_by': None,
            **counts,
            'detail': (
                'Every probe timed out or errored: connection attempts left '
                'this machine and nothing came back. The ports listed as '
                'closed may be closed, filtered, or on a host that is not '
                'there at all -- this scan cannot tell those apart.'
            ),
        }],
    )


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
        'outcome': {
            'type': 'object',
            'description': (
                'How far this scan was followed: "observed" when a port '
                'accepted or the host refused a connection, "dispatched" when '
                'every probe met silence -- in which case closed_ports may be '
                'closed, filtered, or a host that is not there'
            ),
            'description_key': 'modules.network.port_scan.output.outcome.description',
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
    author='Flyto2 Team',
    license='MIT',
)
async def network_port_scan(context: Dict[str, Any]) -> Dict[str, Any]:
    """Scan ports on a host to check which are open."""
    params = context['params']
    host = params.get('host', '').strip()
    # SECURITY: probing is this module's purpose, which is exactly why the
    # target must be bounded — otherwise it is a ready-made internal network
    # scanner reachable from any workflow. Loopback stays allowed; private
    # ranges need FLYTO_ALLOWED_HOSTS or FLYTO_ALLOW_PRIVATE_NETWORK.
    enforce_outbound_host(host, purpose='port scan')
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

    async def _check_port(port: int) -> str:
        async with sem:
            return await _probe_port(host, port, timeout)

    tasks = [_check_port(port) for port in port_list]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    open_ports = []
    closed_ports = []
    refused_count = 0
    silent_count = 0
    for port, result in zip(port_list, results):
        # An exception escaping the gather is neither a refusal nor a timeout --
        # it is the probe itself failing -- so it counts as silence, which is
        # the answer that claims the least.
        if isinstance(result, BaseException):
            closed_ports.append(port)
            silent_count += 1
        elif result == PROBE_OPEN:
            open_ports.append(port)
        else:
            closed_ports.append(port)
            if result == PROBE_REFUSED:
                refused_count += 1
            else:
                silent_count += 1

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
            'outcome': _scan_outcome(
                host=host,
                ports_probed=len(port_list),
                open_count=len(open_ports),
                refused_count=refused_count,
                silent_count=silent_count,
            ),
        },
    }


async def _probe_port(host: str, port: int, timeout: float) -> str:
    """One TCP probe: PROBE_OPEN, PROBE_REFUSED or PROBE_SILENT.

    Three answers rather than a bool because a refusal and a timeout are
    different facts about the world -- the first is the host talking to us, the
    second is nothing at all -- and the caller cannot recover the difference
    once they have been collapsed. ``ConnectionRefusedError`` is a subclass of
    ``OSError``, so it must be tested first.
    """
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout,
        )
        writer.close()
        # Compatibility: wait_for close if available.
        #
        # OSError is caught here and not by the outer handler on purpose: the
        # handshake has already completed by this point, so a reset while
        # tearing the connection down is not evidence that the port was shut.
        # Letting it fall through would report an open port as silent.
        try:
            await writer.wait_closed()
        except (AttributeError, OSError):
            pass
        return PROBE_OPEN
    except ConnectionRefusedError:
        return PROBE_REFUSED
    except (asyncio.TimeoutError, OSError):
        return PROBE_SILENT


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
