# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
HTTP Webhook Wait Module
Start a temporary HTTP server, optionally create a public tunnel via ngrok,
and wait for an incoming webhook callback.
"""

import asyncio
import logging
import time
import json
import socket
from typing import Any, Dict, Optional

from ...registry import register_module
from ...schema import compose, field
from ...schema.constants import Visibility, FieldGroup


logger = logging.getLogger(__name__)


def _find_free_port() -> int:
    """Find a free port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


async def _start_ngrok(port: int, ngrok_token: Optional[str] = None) -> Optional[str]:
    """Try to create an ngrok tunnel. Returns public URL or None."""
    try:
        from pyngrok import ngrok, conf
        if ngrok_token:
            conf.get_default().auth_token = ngrok_token
        tunnel = ngrok.connect(port, "http")
        public_url = tunnel.public_url
        logger.info(f"ngrok tunnel created: {public_url}")
        return public_url
    except ImportError:
        logger.info("pyngrok not installed, skipping ngrok tunnel")
        return None
    except Exception as e:
        logger.warning(f"ngrok tunnel failed: {e}")
        return None


async def _stop_ngrok(port: int) -> None:
    """Stop ngrok tunnel for the given port."""
    try:
        from pyngrok import ngrok
        tunnels = ngrok.get_tunnels()
        for tunnel in tunnels:
            if str(port) in tunnel.config.get('addr', ''):
                ngrok.disconnect(tunnel.public_url)
    except Exception:
        pass


@register_module(
    module_id='http.webhook_wait',
    version='1.0.0',
    category='atomic',
    subcategory='http',
    tags=['http', 'webhook', 'callback', 'server', 'listen', 'inbound', 'atomic'],
    label='Webhook Wait',
    label_key='modules.http.webhook_wait.label',
    description='Start a temporary server and wait for an incoming webhook callback',
    description_key='modules.http.webhook_wait.description',
    icon='Webhook',
    color='#F97316',

    input_types=['string', 'object'],
    output_types=['object'],
    can_connect_to=['*'],
    can_receive_from=['*'],
    can_be_start=True,

    timeout_ms=600000,  # 10 min max
    retryable=False,
    concurrent_safe=False,

    requires_credentials=False,
    handles_sensitive_data=True,
    required_permissions=['filesystem.read', 'filesystem.write'],

    params_schema=compose(
        field(
            'path',
            type='string',
            label='Webhook Path',
            label_key='modules.http.webhook_wait.path',
            description='URL path to listen on (e.g. /webhook, /callback)',
            default='/webhook',
            placeholder='/webhook',
            group=FieldGroup.BASIC,
        ),
        field(
            'port',
            type='number',
            label='Port',
            label_key='modules.http.webhook_wait.port',
            description='Port to listen on (0 = auto-assign)',
            default=0,
            min=0,
            max=65535,
            step=1,
            group=FieldGroup.BASIC,
        ),
        field(
            'timeout',
            type='number',
            label='Wait Timeout (seconds)',
            label_key='schema.field.timeout_s',
            description='Maximum time to wait for the webhook callback',
            default=300,
            min=5,
            max=600,
            step=1,
            ui={'unit': 's'},
            group=FieldGroup.BASIC,
        ),
        field(
            'use_ngrok',
            type='boolean',
            label='Create Public URL (ngrok)',
            label_key='modules.http.webhook_wait.use_ngrok',
            description='Create an ngrok tunnel for public access (requires pyngrok)',
            default=False,
            group=FieldGroup.OPTIONS,
        ),
        field(
            'ngrok_token',
            type='string',
            label='ngrok Auth Token',
            label_key='modules.http.webhook_wait.ngrok_token',
            description='ngrok authentication token (free at ngrok.com)',
            placeholder='${env.NGROK_AUTH_TOKEN}',
            format='password',
            showIf={'use_ngrok': {'$in': [True]}},
            group=FieldGroup.CONNECTION,
        ),
        field(
            'expected_method',
            type='string',
            label='Expected HTTP Method',
            label_key='modules.http.webhook_wait.expected_method',
            description='Only accept this HTTP method (empty = accept any)',
            default='POST',
            options=[
                {'value': '', 'label': 'Any method'},
                {'value': 'POST', 'label': 'POST only'},
                {'value': 'GET', 'label': 'GET only'},
                {'value': 'PUT', 'label': 'PUT only'},
            ],
            visibility=Visibility.EXPERT,
            group=FieldGroup.ADVANCED,
        ),
        field(
            'response_status',
            type='number',
            label='Response Status Code',
            label_key='modules.http.webhook_wait.response_status',
            description='HTTP status code to respond with when webhook is received',
            default=200,
            min=200,
            max=299,
            step=1,
            visibility=Visibility.EXPERT,
            group=FieldGroup.ADVANCED,
        ),
        field(
            'response_body',
            type='string',
            label='Response Body',
            label_key='modules.http.webhook_wait.response_body',
            description='Response body to send back to the webhook caller',
            default='{"ok": true}',
            visibility=Visibility.EXPERT,
            group=FieldGroup.ADVANCED,
        ),
    ),
    output_schema={
        'ok': {
            'type': 'boolean',
            'description': 'Whether webhook was received before timeout',
            'description_key': 'modules.http.webhook_wait.output.ok.description',
        },
        'webhook_url': {
            'type': 'string',
            'description': 'The URL to send webhooks to (public if ngrok enabled)',
            'description_key': 'modules.http.webhook_wait.output.webhook_url.description',
        },
        'method': {
            'type': 'string',
            'description': 'HTTP method of the received webhook',
            'description_key': 'modules.http.webhook_wait.output.method.description',
        },
        'headers': {
            'type': 'object',
            'description': 'Headers from the received webhook',
            'description_key': 'modules.http.webhook_wait.output.headers.description',
        },
        'body': {
            'type': 'any',
            'description': 'Body from the received webhook (parsed JSON or raw text)',
            'description_key': 'modules.http.webhook_wait.output.body.description',
        },
        'query': {
            'type': 'object',
            'description': 'Query parameters from the received webhook',
            'description_key': 'modules.http.webhook_wait.output.query.description',
        },
        'duration_ms': {
            'type': 'number',
            'description': 'Time waited for the webhook in milliseconds',
            'description_key': 'modules.http.webhook_wait.output.duration_ms.description',
        },
    },
    examples=[
        {
            'title': 'Wait for Stripe webhook (local)',
            'title_key': 'modules.http.webhook_wait.examples.local.title',
            'params': {
                'path': '/webhook/stripe',
                'port': 8765,
                'timeout': 120,
                'use_ngrok': False,
            },
        },
        {
            'title': 'Wait for webhook with ngrok tunnel',
            'title_key': 'modules.http.webhook_wait.examples.ngrok.title',
            'params': {
                'path': '/webhook',
                'timeout': 300,
                'use_ngrok': True,
                'ngrok_token': '${env.NGROK_AUTH_TOKEN}',
            },
        },
    ],
    author='Flyto Team',
    license='MIT',
)
async def http_webhook_wait(context: Dict[str, Any]) -> Dict[str, Any]:
    """Start a temporary HTTP server and wait for an incoming webhook."""
    from aiohttp import web

    params = context['params']
    path = params.get('path', '/webhook')
    port = int(params.get('port', 0))
    timeout_seconds = int(params.get('timeout', 300))
    use_ngrok = params.get('use_ngrok', False)
    ngrok_token = params.get('ngrok_token')
    expected_method = params.get('expected_method', 'POST')
    response_status = int(params.get('response_status', 200))
    response_body = params.get('response_body', '{"ok": true}')

    if port == 0:
        port = _find_free_port()

    # Ensure path starts with /
    if not path.startswith('/'):
        path = '/' + path

    received = asyncio.Event()
    webhook_data: Dict[str, Any] = {}
    start_time = time.time()

    async def handle_webhook(request: web.Request) -> web.Response:
        """Handle incoming webhook request."""
        # Check method if specified
        if expected_method and request.method != expected_method:
            return web.Response(
                status=405,
                text=json.dumps({'error': f'Expected {expected_method}, got {request.method}'}),
                content_type='application/json',
            )

        # Read body
        body_text = await request.text()
        try:
            body_parsed = json.loads(body_text) if body_text else None
        except (json.JSONDecodeError, ValueError):
            body_parsed = body_text

        # Extract query params
        query_params = dict(request.query)

        webhook_data['method'] = request.method
        webhook_data['headers'] = dict(request.headers)
        webhook_data['body'] = body_parsed
        webhook_data['query'] = query_params
        webhook_data['path'] = str(request.path)

        logger.info(f"Webhook received: {request.method} {request.path}")
        received.set()

        return web.Response(
            status=response_status,
            text=response_body,
            content_type='application/json',
        )

    # Health check endpoint
    async def handle_health(request: web.Request) -> web.Response:
        return web.Response(text='{"status": "waiting"}', content_type='application/json')

    app = web.Application()
    app.router.add_route('*', path, handle_webhook)
    app.router.add_get('/health', handle_health)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', port)

    public_url = None
    try:
        await site.start()
        local_url = f'http://localhost:{port}{path}'
        logger.info(f"Webhook server started at {local_url}")

        # Create ngrok tunnel if requested
        if use_ngrok:
            public_url = await _start_ngrok(port, ngrok_token)

        webhook_url = f'{public_url}{path}' if public_url else local_url

        logger.info(f"Waiting for webhook at: {webhook_url} (timeout: {timeout_seconds}s)")

        # Wait for webhook or timeout
        try:
            await asyncio.wait_for(received.wait(), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.warning(f"Webhook wait timed out after {timeout_seconds}s")
            return {
                'ok': False,
                'error': f'No webhook received within {timeout_seconds} seconds',
                'error_code': 'TIMEOUT',
                'webhook_url': webhook_url,
                'duration_ms': duration_ms,
            }

        duration_ms = int((time.time() - start_time) * 1000)
        return {
            'ok': True,
            'webhook_url': webhook_url,
            'method': webhook_data.get('method', ''),
            'headers': webhook_data.get('headers', {}),
            'body': webhook_data.get('body'),
            'query': webhook_data.get('query', {}),
            'duration_ms': duration_ms,
        }

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(f"Webhook server error: {e}")
        return {
            'ok': False,
            'error': str(e),
            'error_code': 'SERVER_ERROR',
            'duration_ms': duration_ms,
        }

    finally:
        # Cleanup
        if use_ngrok:
            await _stop_ngrok(port)
        await runner.cleanup()
        logger.info("Webhook server stopped")
