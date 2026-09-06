"""HTTP, PostgreSQL and Chromium adapters for operator-provisioned connections.

Connection bindings are injected by the trusted runner host after tenant,
project and environment admission. Suite inputs cannot choose credentials or
expand network scope. No arbitrary JavaScript, shell, or SQL mutation adapter
is exposed.
"""
from __future__ import annotations

import asyncio
import ipaddress
import json
import re
import ssl
from dataclasses import dataclass, field
from urllib.parse import parse_qs, unquote, urljoin, urlsplit

from core.utils import (
    guarded_client_session,
    trusted_outbound_network_scope,
    validate_url_with_env_config,
)

from .contracts import Step, evaluate
from .runtime import BlockedError


@dataclass(frozen=True)
class Connection:
    adapter: str
    endpoint: str
    isolated: bool = False
    headers: dict = field(default_factory=dict, repr=False)
    database_dsn: str = field(default='', repr=False)
    queries: dict[str, str] = field(default_factory=dict)


def substitute(value, context):
    if isinstance(value, str):
        for key in ('run_id', 'attempt_id', 'case_id'):
            value = value.replace('{{' + key + '}}', str(context[key]))
        return value
    if isinstance(value, list):
        return [substitute(v, context) for v in value]
    if isinstance(value, dict):
        return {k: substitute(v, context) for k, v in value.items()}
    return value


def redact(value, secrets=()):
    if isinstance(value, dict):
        return {k: '[redacted]' if re.search('password|secret|token|authorization|cookie|api.?key', k, re.I)
                else redact(v, secrets) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v, secrets) for v in value]
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, '[redacted]')
        return value[:8192]
    return value


def database_connection_options(connection: Connection) -> dict:
    """Bind credentials to an approved literal address without a second DNS lookup.

    Remote connections require certificate verification against that address.
    DSN query options cannot replace the host, service, credentials or TLS policy.
    """
    try:
        endpoint, dsn = urlsplit(connection.endpoint), urlsplit(connection.database_dsn)
        if (endpoint.scheme not in ('postgres', 'postgresql') or dsn.scheme not in ('postgres', 'postgresql')
                or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment or dsn.fragment):
            raise ValueError('invalid database endpoint')
        address = ipaddress.ip_address(endpoint.hostname)
        if dsn.hostname != endpoint.hostname or (dsn.port or 5432) != (endpoint.port or 5432):
            raise ValueError('database credential scope mismatch')
        options = parse_qs(dsn.query, keep_blank_values=True, strict_parsing=True)
        if set(options) - {'sslmode'} or any(len(value) != 1 for value in options.values()):
            raise ValueError('unsupported database connection options')
        mode = options.get('sslmode', ['verify-full' if not connection.isolated else 'disable'])[0]
        if mode not in ('disable', 'verify-full') or (mode == 'disable' and not connection.isolated):
            raise ValueError('database TLS verification required')
        if not dsn.username or not dsn.path.strip('/'):
            raise ValueError('explicit database and user required')
        host = str(address)
        authority = '[' + host + ']' if address.version == 6 else host
        port = endpoint.port or 5432
        with trusted_outbound_network_scope(allowed_hosts=[host], allowed_ports=[port],
                                            allow_private_targets=connection.isolated):
            validate_url_with_env_config(f'http://{authority}:{port}/')
        return {'host': host, 'port': port, 'user': unquote(dsn.username),
                'password': unquote(dsn.password or ''), 'database': unquote(dsn.path[1:]),
                'ssl': ssl.create_default_context() if mode == 'verify-full' else False}
    except Exception as exc:
        raise BlockedError() from exc


class Adapters:
    """One runner invocation owns all browser contexts and connection bindings."""
    def __init__(self, connections: dict[str, Connection]):
        self.connections = connections

    async def __call__(self, step: Step, context: dict) -> dict:
        connection = self.connections.get(step.connection)
        if connection is None or connection.adapter != step.adapter:
            raise BlockedError()
        params = substitute(step.input, context)
        if step.adapter == 'postgres':
            return await self.postgres(connection, params, step)
        target = urlsplit(connection.endpoint)
        if target.scheme not in ('http', 'https') or target.username or target.password:
            raise BlockedError()
        path = params.get('path', '/')
        url = urljoin(connection.endpoint.rstrip('/') + '/', path)
        if urlsplit(url).netloc != target.netloc or urlsplit(url).scheme != target.scheme:
            raise BlockedError()
        with trusted_outbound_network_scope(allowed_hosts=[target.hostname],
                allowed_ports=[target.port or (443 if target.scheme == 'https' else 80)],
                allow_private_targets=connection.isolated):
            if step.adapter == 'http':
                if params.get('method', 'GET').upper() not in ('GET', 'HEAD') and context['attempt_id'] not in json.dumps(params):
                    raise BlockedError()
                observation = await self.http(connection, params, url)
            else:
                observation = await self.web(connection, params, url, step)
        return redact(observation, tuple(connection.headers.values()))

    async def http(self, connection: Connection, params: dict, url: str) -> dict:
        method = params.get('method', 'GET').upper()
        if method not in ('GET', 'HEAD') and not connection.isolated:
            raise BlockedError()
        if method not in ('GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE'):
            raise BlockedError()
        async with guarded_client_session() as session:  # noqa: SIM117
            async with session.request(method, url, json=params.get('json'),
                    headers=connection.headers, allow_redirects=False) as response:
                body = await response.content.read(65537)
                if len(body) > 65536:
                    raise BlockedError()
                try:
                    data = json.loads(body)
                    text = json.dumps(redact(data, tuple(connection.headers.values())), ensure_ascii=False)
                except (ValueError, UnicodeDecodeError):
                    data = None
                    text = body.decode('utf-8', errors='replace')
                return {'status': response.status, 'body': data,
                        'text': text[:8192],
                        'request': {'method': method, 'path': urlsplit(url).path}}

    async def postgres(self, connection: Connection, params: dict, step: Step) -> dict:
        # Query text is provisioned with the connection by an operator. Users
        # select its ID and bound values; a SELECT prefix is not an SQL sandbox.
        query = connection.queries.get(params.get('query_id', ''))
        if not query or not connection.database_dsn:
            raise BlockedError()
        import asyncpg
        options = database_connection_options(connection)
        conn = await asyncpg.connect(**options, timeout=step.timeout_ms / 1000,
                                     command_timeout=step.timeout_ms / 1000)
        try:
            async with conn.transaction(readonly=True):
                statement = await conn.prepare(query)
                rows = []
                async for record in statement.cursor(*params.get('arguments', []), prefetch=100):
                    rows.append(dict(record))
                    if len(rows) > 100:
                        raise BlockedError()
                return redact({'rows': rows, 'row_count': len(rows), 'query_id': params['query_id'],
                               'transaction_read_only': True}, [connection.database_dsn])
        finally:
            await conn.close(timeout=2)

    async def web(self, connection: Connection, params: dict, url: str, step: Step) -> dict:
        from playwright.async_api import async_playwright

        from core.utils import validate_url_with_env_config
        if params.get('actions') and not connection.isolated:
            raise BlockedError()
        # DNS-named Web targets require a production browser egress proxy.
        if not connection.isolated:
            raise BlockedError()
        try:
            ipaddress.ip_address(urlsplit(url).hostname)
        except ValueError as exc:
            raise BlockedError() from exc
        validate_url_with_env_config(url)
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(service_workers='block', extra_http_headers=connection.headers)
            try:
                async def guard(route):
                    request_url = route.request.url
                    try:
                        if urlsplit(request_url).netloc != urlsplit(url).netloc:
                            raise BlockedError()
                        validate_url_with_env_config(request_url)
                    except Exception:
                        await route.abort()
                    else:
                        await route.continue_()
                await context.route('**/*', guard)
                page = await context.new_page()
                await page.goto(url, wait_until='domcontentloaded', timeout=step.timeout_ms)
                for action in params.get('actions', [])[:20]:
                    locator = page.get_by_role(action['role'], name=action['name'], exact=True)
                    if action['action'] == 'click':
                        await locator.click(timeout=step.timeout_ms)
                    elif action['action'] == 'fill':
                        await locator.fill(action['value'], timeout=step.timeout_ms)
                    else:
                        raise BlockedError()
                locator = page.locator(params.get('selector', 'body'))
                # Poll the observable assertion, not an arbitrary settle delay.
                for _ in range(max(1, step.timeout_ms // 100)):
                    observation = {'text': await locator.inner_text(timeout=step.timeout_ms),
                                   'count': await locator.count(), 'url': page.url}
                    if all(evaluate(a, observation)['outcome'] == 'pass' for a in step.assertions):
                        break
                    await asyncio.sleep(0.1)
                return observation
            finally:
                await context.close()
                await browser.close()
