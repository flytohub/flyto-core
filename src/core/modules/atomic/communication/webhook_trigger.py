"""
Webhook Trigger Module
Send HTTP requests to webhook endpoints
"""
import logging
import os
from typing import Any, Dict, List, Optional

from ...registry import register_module


logger = logging.getLogger(__name__)


@register_module(
    module_id='webhook.trigger',
    version='1.0.0',
    category='communication',
    subcategory='webhook',
    tags=['webhook', 'http', 'trigger', 'api', 'notification'],
    label='Trigger Webhook',
    label_key='modules.webhook.trigger.label',
    description='Send HTTP POST request to a webhook URL',
    description_key='modules.webhook.trigger.description',
    icon='Webhook',
    color='#FF6B6B',

    input_types=['object', 'text'],
    output_types=['object'],
    can_connect_to=['notification.*', 'api.*'],

    timeout=30,
    retryable=True,
    max_retries=3,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['network.http'],

    params_schema={
        'url': {
            'type': 'string',
            'label': 'Webhook URL',
            'label_key': 'modules.webhook.trigger.params.url.label',
            'description': 'Target webhook URL',
            'description_key': 'modules.webhook.trigger.params.url.description',
            'required': True
        },
        'method': {
            'type': 'string',
            'label': 'HTTP Method',
            'label_key': 'modules.webhook.trigger.params.method.label',
            'description': 'HTTP method to use',
            'description_key': 'modules.webhook.trigger.params.method.description',
            'required': False,
            'enum': ['POST', 'GET', 'PUT', 'PATCH', 'DELETE'],
            'default': 'POST'
        },
        'payload': {
            'type': 'object',
            'label': 'Payload',
            'label_key': 'modules.webhook.trigger.params.payload.label',
            'description': 'JSON payload to send',
            'description_key': 'modules.webhook.trigger.params.payload.description',
            'required': False
        },
        'headers': {
            'type': 'object',
            'label': 'Headers',
            'label_key': 'modules.webhook.trigger.params.headers.label',
            'description': 'Custom HTTP headers',
            'description_key': 'modules.webhook.trigger.params.headers.description',
            'required': False
        },
        'content_type': {
            'type': 'string',
            'label': 'Content Type',
            'label_key': 'modules.webhook.trigger.params.content_type.label',
            'description': 'Content-Type header',
            'description_key': 'modules.webhook.trigger.params.content_type.description',
            'required': False,
            'enum': ['application/json', 'application/x-www-form-urlencoded', 'text/plain'],
            'default': 'application/json'
        },
        'auth_token': {
            'type': 'string',
            'label': 'Auth Token',
            'label_key': 'modules.webhook.trigger.params.auth_token.label',
            'description': 'Bearer token for authorization',
            'description_key': 'modules.webhook.trigger.params.auth_token.description',
            'required': False,
            'secret': True
        },
        'timeout': {
            'type': 'number',
            'label': 'Timeout (seconds)',
            'label_key': 'modules.webhook.trigger.params.timeout.label',
            'description': 'Request timeout in seconds',
            'description_key': 'modules.webhook.trigger.params.timeout.description',
            'required': False,
            'default': 30
        }
    },
    output_schema={
        'status_code': {
            'type': 'number',
            'description': 'HTTP response status code'
        },
        'response': {
            'type': 'object',
            'description': 'Response body (if JSON)'
        },
        'headers': {
            'type': 'object',
            'description': 'Response headers'
        }
    },
    examples=[
        {
            'title': 'Simple POST webhook',
            'title_key': 'modules.webhook.trigger.examples.simple.title',
            'params': {
                'url': 'https://example.com/webhook',
                'payload': {'event': 'task_completed', 'data': {}}
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def webhook_trigger(context: Dict[str, Any]) -> Dict[str, Any]:
    """Trigger a webhook endpoint"""
    try:
        import aiohttp
    except ImportError:
        raise ImportError("aiohttp is required for webhook.trigger. Install with: pip install aiohttp")

    params = context['params']
    url = params['url']
    method = params.get('method', 'POST').upper()
    payload = params.get('payload')
    custom_headers = params.get('headers', {})
    content_type = params.get('content_type', 'application/json')
    auth_token = params.get('auth_token')
    timeout_seconds = params.get('timeout', 30)

    headers = {'Content-Type': content_type}
    headers.update(custom_headers)

    if auth_token:
        headers['Authorization'] = f'Bearer {auth_token}'

    timeout = aiohttp.ClientTimeout(total=timeout_seconds)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        request_kwargs = {'headers': headers}

        if method in ('POST', 'PUT', 'PATCH') and payload:
            if content_type == 'application/json':
                request_kwargs['json'] = payload
            elif content_type == 'application/x-www-form-urlencoded':
                request_kwargs['data'] = payload
            else:
                request_kwargs['data'] = str(payload)

        async with session.request(method, url, **request_kwargs) as response:
            status_code = response.status
            response_headers = dict(response.headers)

            try:
                response_body = await response.json()
            except Exception:
                response_body = await response.text()

            logger.info(f"Webhook triggered: {method} {url} -> {status_code}")

            return {
                'ok': status_code < 400,
                'status_code': status_code,
                'response': response_body,
                'headers': response_headers
            }
