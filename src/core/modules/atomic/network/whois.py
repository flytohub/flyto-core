# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Network WHOIS Module
Perform WHOIS lookup for a domain to retrieve registration information.

HOW FAR THIS MODULE FOLLOWS REALITY

`whois` exits 0 and prints something for almost everything, including
"No match for EXAMPLE.COM". The module already refuses a completely empty
response, so on the returning path bytes did cross the wire from a whois
server -- but bytes arriving is not the same as registration data being read,
and the parsed fields are where the difference hides.

`registrar`, `creation_date`, `expiration_date` and `status` are all `None`
when no regex matched, and `name_servers` is `[]`. Those are the same values a
lookup for an unregistered domain produces, and the same values a lookup of a
perfectly ordinary ccTLD produces when its format is one of the many these
patterns do not cover. A payload of five empty fields is therefore not evidence
about the domain, so:

    at least one registration field parsed   OBSERVED
        Real record content was extracted from bytes the registry sent. What
        is observed is the registry's record, which is the world for this
        question.

    bytes arrived, nothing parsed            ACCEPTED
        A whois server answered. Nothing in this result says anything about
        the domain: every field reads exactly as it would if the effect had
        not happened.

The empty-response and process-failure paths raise, and an exception carries no
payload, so they have no envelope. A whois that timed out is the textbook
INDETERMINATE and is a real gap.
"""
import asyncio
import logging
import re
from typing import Any, Dict, List, Optional

from ....engine.outcome import ClaimBy, Outcome, envelope
from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError, ModuleError

logger = logging.getLogger(__name__)


def _whois_outcome(
    *,
    domain: str,
    raw_bytes: int,
    parsed_fields: List[str],
    name_server_count: int,
    exit_code: Optional[int],
) -> Dict[str, Any]:
    """The rung this lookup earned, decided by whether anything parsed.

    `raw_bytes` is `len(raw_output)` -- a genuine count of what arrived, and
    the reason ACCEPTED rather than DISPATCHED is available at all on the
    second branch. It is deliberately not enough for OBSERVED on its own:
    "No match for EXAMPLE.COM" is 26 bytes of a server answering and zero bytes
    of registration data.
    """
    measured = {
        'domain': domain,
        'raw_bytes': raw_bytes,
        'parsed_fields': sorted(parsed_fields),
        'name_servers': name_server_count,
        'exit_code': exit_code,
    }

    if parsed_fields:
        return envelope(
            Outcome.OBSERVED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'whois_record_parsed',
                'measured_by': 'fields matched in the bytes the whois server returned',
                **measured,
                'detail': (
                    'Registration data was extracted from the response. The '
                    'record is the registry reporting its own database, which '
                    'is what a WHOIS lookup is for; its accuracy is the '
                    "registry's problem and is not checked here."
                ),
            }],
        )

    return envelope(
        Outcome.ACCEPTED,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'whois_answered_unparsed',
            'measured_by': 'len(raw whois output)',
            **measured,
            'detail': (
                'A whois server answered and none of the registration patterns '
                'matched its output. The null registrar and dates in this '
                'result are absences of a match, not statements about the '
                'domain: an unregistered domain and a ccTLD format these '
                'patterns do not cover produce the identical payload. Read '
                'the raw field.'
            ),
        }],
    )


@register_module(
    module_id='network.whois',
    version='1.0.0',
    category='network',
    tags=['network', 'whois', 'domain', 'dns', 'registration', 'lookup'],
    label='WHOIS Lookup',
    label_key='modules.network.whois.label',
    description='Perform WHOIS lookup for a domain to retrieve registration information',
    description_key='modules.network.whois.description',
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
            'domain',
            type='string',
            label='Domain',
            label_key='modules.network.whois.params.domain.label',
            description='Domain name to look up',
            description_key='modules.network.whois.params.domain.description',
            required=True,
            placeholder='example.com',
            group=FieldGroup.BASIC,
        ),
    ),
    output_schema={
        'domain': {
            'type': 'string',
            'description': 'The queried domain',
            'description_key': 'modules.network.whois.output.domain.description',
        },
        'registrar': {
            'type': 'string',
            'description': 'Domain registrar',
            'description_key': 'modules.network.whois.output.registrar.description',
        },
        'creation_date': {
            'type': 'string',
            'description': 'Domain creation date',
            'description_key': 'modules.network.whois.output.creation_date.description',
        },
        'expiration_date': {
            'type': 'string',
            'description': 'Domain expiration date',
            'description_key': 'modules.network.whois.output.expiration_date.description',
        },
        'name_servers': {
            'type': 'array',
            'description': 'List of name servers',
            'description_key': 'modules.network.whois.output.name_servers.description',
        },
        'raw': {
            'type': 'string',
            'description': 'Full raw WHOIS output',
            'description_key': 'modules.network.whois.output.raw.description',
        },
        'outcome': {
            'type': 'object',
            'description': (
                'How far this lookup was followed: "observed" when at least '
                'one registration field was parsed out of the response, '
                '"accepted" when a server answered and nothing matched -- in '
                'which case the null fields above say nothing about the domain'
            ),
            'description_key': 'modules.network.whois.output.outcome.description',
        },
    },
    examples=[
        {
            'title': 'WHOIS lookup',
            'title_key': 'modules.network.whois.examples.basic.title',
            'params': {
                'domain': 'example.com',
            },
        },
    ],
    author='Flyto2 Team',
    license='MIT',
)
async def network_whois(context: Dict[str, Any]) -> Dict[str, Any]:
    """Perform WHOIS lookup for a domain."""
    params = context['params']
    domain = params.get('domain', '').strip().lower()

    if not domain:
        raise ValidationError("Missing required parameter: domain", field="domain")

    # Strip protocol prefix if provided
    domain = re.sub(r'^https?://', '', domain)
    # Strip trailing path
    domain = domain.split('/')[0]

    # SECURITY: `domain` becomes argv[1] of `whois`, and whois parses its own
    # options out of that position. A value of "-h 169.254.169.254" is a single
    # argv element that getopt reads as -h with a host attached, so the caller
    # chooses which server this connects to on port 43 -- an outbound
    # connection to any address, from a module whose parameter is documented as
    # a domain name. There is no shell here, so this is not command injection;
    # it is argument injection, and the fix is the same shape: refuse values
    # that cannot be a hostname. A domain label may not begin with a hyphen
    # (RFC 1035) and may not contain whitespace, so nothing legitimate is lost.
    if domain.startswith('-') or re.search(r'\s', domain):
        raise ValidationError(
            "Invalid domain: a domain cannot start with '-' or contain spaces",
            field="domain",
        )

    try:
        proc = await asyncio.create_subprocess_exec(
            'whois', domain,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(),
            timeout=30,
        )
        raw_output = stdout_bytes.decode('utf-8', errors='replace')
        # After communicate() the child has exited, so returncode is settled.
        exit_code = proc.returncode
    except asyncio.TimeoutError:
        raise ModuleError("WHOIS lookup timed out")
    except FileNotFoundError:
        raise ModuleError("whois command not found on this system")
    except Exception as e:
        raise ModuleError("Failed to execute whois: {}".format(str(e)))

    if not raw_output.strip():
        raise ModuleError("WHOIS returned empty response for domain: {}".format(domain))

    # Parse key fields from WHOIS output
    registrar = _extract_field(raw_output, [
        r'Registrar:\s*(.+)',
        r'registrar:\s*(.+)',
        r'Sponsoring Registrar:\s*(.+)',
    ])

    creation_date = _extract_field(raw_output, [
        r'Creation Date:\s*(.+)',
        r'created:\s*(.+)',
        r'Created On:\s*(.+)',
        r'Registration Date:\s*(.+)',
    ])

    expiration_date = _extract_field(raw_output, [
        r'(?:Registry )?Expir(?:y|ation) Date:\s*(.+)',
        r'expires:\s*(.+)',
        r'Expiration Date:\s*(.+)',
        r'paid-till:\s*(.+)',
    ])

    status = _extract_field(raw_output, [
        r'(?:Domain )?Status:\s*(.+)',
        r'status:\s*(.+)',
    ])

    name_servers = _extract_name_servers(raw_output)

    logger.info("WHOIS lookup for %s: registrar=%s", domain, registrar or "unknown")

    parsed_fields = [
        name for name, value in (
            ('registrar', registrar),
            ('creation_date', creation_date),
            ('expiration_date', expiration_date),
            ('status', status),
            ('name_servers', name_servers),
        )
        if value
    ]

    return {
        'ok': True,
        'data': {
            'domain': domain,
            'registrar': registrar,
            'creation_date': creation_date,
            'expiration_date': expiration_date,
            'status': status,
            'name_servers': name_servers,
            'raw': raw_output,
            'outcome': _whois_outcome(
                domain=domain,
                raw_bytes=len(raw_output),
                parsed_fields=parsed_fields,
                name_server_count=len(name_servers),
                exit_code=exit_code,
            ),
        },
    }


def _extract_field(text: str, patterns: List[str]) -> Optional[str]:
    """Extract a field value using multiple regex patterns (first match wins)."""
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            return match.group(1).strip()
    return None


def _extract_name_servers(text: str) -> List[str]:
    """Extract name server entries from WHOIS output."""
    servers = set()

    # Pattern: "Name Server: ns1.example.com"
    for match in re.finditer(
        r'(?:Name Server|nserver|name server):\s*(\S+)',
        text,
        re.IGNORECASE | re.MULTILINE,
    ):
        ns = match.group(1).strip().rstrip('.').lower()
        if ns:
            servers.add(ns)

    return sorted(servers)
