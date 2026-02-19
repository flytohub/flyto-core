# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
HTTP Health Check Module
Monitor HTTP endpoint availability and performance
"""

import asyncio
import logging
import ssl
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup


logger = logging.getLogger(__name__)


@register_module(
    module_id='monitor.http_check',
    version='1.0.0',
    category='atomic',
    subcategory='monitor',
    tags=['monitor', 'health', 'uptime', 'http', 'devops'],
    label='HTTP Health Check',
    label_key='modules.monitor.http_check.label',
    description='HTTP health check / uptime monitor',
    description_key='modules.monitor.http_check.description',
    icon='Activity',
    color='#10B981',

    input_types=['string', 'object'],
    output_types=['object'],
    can_connect_to=['*'],
    can_receive_from=['*'],

    timeout_ms=30000,
    retryable=True,
    max_retries=3,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['network.connect'],

    params_schema=compose(
        field('url', type='string', label='URL', label_key='modules.monitor.http_check.params.url.label',
              description='URL to check', required=True,
              placeholder='https://api.example.com/health', group=FieldGroup.BASIC),
        field('method', type='select', label='Method', label_key='modules.monitor.http_check.params.method.label',
              description='HTTP method', default='GET',
              options=[
                  {'value': 'GET', 'label': 'GET'},
                  {'value': 'HEAD', 'label': 'HEAD'},
                  {'value': 'POST', 'label': 'POST'},
              ],
              group=FieldGroup.BASIC),
        field('expected_status', type='number', label='Expected Status', label_key='modules.monitor.http_check.params.expected_status.label',
              description='Expected HTTP status code', default=200, min=100, max=599,
              group=FieldGroup.BASIC),
        field('timeout_ms', type='number', label='Timeout (ms)', label_key='modules.monitor.http_check.params.timeout_ms.label',
              description='Request timeout in milliseconds', default=10000,
              min=100, max=60000, group=FieldGroup.OPTIONS),
        field('headers', type='object', label='Headers', label_key='modules.monitor.http_check.params.headers.label',
              description='Custom request headers',
              group=FieldGroup.OPTIONS),
        field('body', type='string', label='Body', label_key='modules.monitor.http_check.params.body.label',
              description='Request body (for POST)', format='multiline',
              showIf={'method': 'POST'},
              group=FieldGroup.OPTIONS),
        field('check_ssl', type='boolean', label='Check SSL', label_key='modules.monitor.http_check.params.check_ssl.label',
              description='Check SSL certificate validity and expiry', default=True,
              group=FieldGroup.OPTIONS),
        field('contains', type='string', label='Contains', label_key='modules.monitor.http_check.params.contains.label',
              description='Response body must contain this string',
              placeholder='ok', group=FieldGroup.OPTIONS),
        field('follow_redirects', type='boolean', label='Follow Redirects', label_key='modules.monitor.http_check.params.follow_redirects.label',
              description='Follow HTTP redirects', default=True,
              group=FieldGroup.ADVANCED),
    ),
    output_schema={
        'ok': {'type': 'boolean', 'description': 'Whether check completed'},
        'data': {
            'type': 'object',
            'properties': {
                'status': {'type': 'string', 'description': 'Health status (healthy/unhealthy)'},
                'status_code': {'type': 'number', 'description': 'HTTP status code'},
                'response_time_ms': {'type': 'number', 'description': 'Response time in milliseconds'},
                'ssl_valid': {'type': 'boolean', 'description': 'SSL certificate valid'},
                'ssl_expires_in_days': {'type': 'number', 'description': 'Days until SSL expiry'},
                'content_match': {'type': 'boolean', 'description': 'Content match result'},
                'url': {'type': 'string', 'description': 'Checked URL'},
            }
        }
    },
    examples=[
        {
            'title': 'Basic health check',
            'title_key': 'modules.monitor.http_check.examples.basic.title',
            'params': {
                'url': 'https://api.example.com/health',
                'expected_status': 200
            }
        },
        {
            'title': 'Check with content validation',
            'title_key': 'modules.monitor.http_check.examples.content.title',
            'params': {
                'url': 'https://api.example.com/health',
                'contains': '"status":"ok"',
                'timeout_ms': 5000
            }
        }
    ],
    author='Flyto Team',
    license='MIT'
)
async def monitor_http_check(context: Dict[str, Any]) -> Dict[str, Any]:
    """HTTP health check / uptime monitor"""
    try:
        import aiohttp
    except ImportError:
        raise ImportError(
            "aiohttp is required for monitor.http_check. "
            "Install with: pip install aiohttp"
        )

    params = context['params']
    url = params['url']
    method = params.get('method', 'GET').upper()
    expected_status = params.get('expected_status', 200)
    timeout_ms = params.get('timeout_ms', 10000)
    headers = params.get('headers', {})
    body = params.get('body')
    check_ssl = params.get('check_ssl', True)
    contains = params.get('contains')
    follow_redirects = params.get('follow_redirects', True)

    timeout_seconds = timeout_ms / 1000.0
    timeout_config = aiohttp.ClientTimeout(total=timeout_seconds)

    ssl_valid: Optional[bool] = None
    ssl_expires_in_days: Optional[int] = None
    content_match: Optional[bool] = None
    is_healthy = True

    request_kwargs: Dict[str, Any] = {
        'headers': dict(headers) if headers else {},
        'allow_redirects': follow_redirects,
    }

    if body and method == 'POST':
        request_kwargs['data'] = body

    start_time = time.time()

    try:
        async with aiohttp.ClientSession(timeout=timeout_config) as session:
            async with session.request(method, url, **request_kwargs) as response:
                response_time_ms = round((time.time() - start_time) * 1000, 2)
                status_code = response.status

                # Check status code
                if status_code != expected_status:
                    is_healthy = False

                # Check content match
                if contains is not None:
                    response_text = await response.text()
                    content_match = contains in response_text
                    if not content_match:
                        is_healthy = False

                # Check SSL certificate
                if check_ssl and url.startswith('https://'):
                    ssl_info = _get_ssl_info(response)
                    if ssl_info:
                        ssl_valid = ssl_info.get('valid')
                        ssl_expires_in_days = ssl_info.get('expires_in_days')
                        if ssl_valid is False:
                            is_healthy = False

                status_str = 'healthy' if is_healthy else 'unhealthy'

                logger.info(
                    f"HTTP check {url}: {status_str} "
                    f"(status={status_code}, time={response_time_ms}ms)"
                )

                return {
                    'ok': True,
                    'data': {
                        'status': status_str,
                        'status_code': status_code,
                        'response_time_ms': response_time_ms,
                        'ssl_valid': ssl_valid,
                        'ssl_expires_in_days': ssl_expires_in_days,
                        'content_match': content_match,
                        'url': url,
                    }
                }

    except asyncio.TimeoutError:
        response_time_ms = round((time.time() - start_time) * 1000, 2)
        logger.warning(f"HTTP check timeout: {url} ({response_time_ms}ms)")
        return {
            'ok': True,
            'data': {
                'status': 'unhealthy',
                'status_code': 0,
                'response_time_ms': response_time_ms,
                'ssl_valid': None,
                'ssl_expires_in_days': None,
                'content_match': None,
                'url': url,
            }
        }

    except aiohttp.ClientSSLError as e:
        response_time_ms = round((time.time() - start_time) * 1000, 2)
        logger.warning(f"HTTP check SSL error: {url} - {e}")
        return {
            'ok': True,
            'data': {
                'status': 'unhealthy',
                'status_code': 0,
                'response_time_ms': response_time_ms,
                'ssl_valid': False,
                'ssl_expires_in_days': None,
                'content_match': None,
                'url': url,
            }
        }

    except aiohttp.ClientError as e:
        response_time_ms = round((time.time() - start_time) * 1000, 2)
        logger.warning(f"HTTP check connection error: {url} - {e}")
        return {
            'ok': True,
            'data': {
                'status': 'unhealthy',
                'status_code': 0,
                'response_time_ms': response_time_ms,
                'ssl_valid': None,
                'ssl_expires_in_days': None,
                'content_match': None,
                'url': url,
            }
        }

    except Exception as e:
        response_time_ms = round((time.time() - start_time) * 1000, 2)
        logger.error(f"HTTP check error: {url} - {e}")
        return {
            'ok': False,
            'error': str(e),
            'error_code': 'CHECK_ERROR',
            'data': {
                'status': 'unhealthy',
                'status_code': 0,
                'response_time_ms': response_time_ms,
                'url': url,
            }
        }


def _get_ssl_info(response) -> Optional[Dict[str, Any]]:
    """Extract SSL certificate info from aiohttp response"""
    try:
        # aiohttp exposes the transport's SSL object
        transport = response.connection and response.connection.transport
        if transport is None:
            return None

        ssl_object = transport.get_extra_info('ssl_object')
        if ssl_object is None:
            return None

        cert = ssl_object.getpeercert()
        if cert is None:
            return {'valid': False, 'expires_in_days': None}

        # Parse expiry date
        not_after = cert.get('notAfter')
        if not_after:
            # SSL date format: "Sep 15 00:00:00 2025 GMT"
            expiry = datetime.strptime(not_after, '%b %d %H:%M:%S %Y %Z')
            expiry = expiry.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            delta = expiry - now
            expires_in_days = delta.days

            return {
                'valid': expires_in_days > 0,
                'expires_in_days': expires_in_days,
            }

        return {'valid': True, 'expires_in_days': None}

    except Exception as e:
        logger.debug(f"Could not extract SSL info: {e}")
        return None
