# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Network WHOIS Module
Perform WHOIS lookup for a domain to retrieve registration information.
"""
import asyncio
import logging
import re
from typing import Any, Dict, List, Optional

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError, ModuleError

logger = logging.getLogger(__name__)


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
    author='Flyto Team',
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
