# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
HTTP Paginate Module
Automatically iterate through paginated API endpoints and collect all results.
Supports cursor-based, offset-based, page-number, and Link header pagination.
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from ....utils import SSRFError, validate_url_with_env_config
from ...registry import register_module
from ...schema import compose, field, presets
from ...schema.constants import FieldGroup

logger = logging.getLogger(__name__)


def _make_result(
    ok: bool,
    all_items: List[Any],
    pages_fetched: int,
    start_time: float,
    error: str = '',
    error_code: str = '',
) -> Dict[str, Any]:
    """Build a standardised paginate result dict."""
    result: Dict[str, Any] = {
        'ok': ok,
        'items': all_items,
        'total_items': len(all_items),
        'pages_fetched': pages_fetched,
        'duration_ms': int((time.time() - start_time) * 1000),
    }
    if not ok:
        result['error'] = error
        result['error_code'] = error_code
    return result


def _merge_query(url: str, params: dict) -> str:
    """Merge query params into URL."""
    parsed = urlparse(url)
    existing = parse_qs(parsed.query)
    existing.update({k: [str(v)] for k, v in params.items()})
    new_query = urlencode(existing, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def _extract_by_path(data: Any, path: str) -> Any:
    """Extract value from nested dict using dot notation. e.g. 'meta.next_cursor'"""
    if not path or data is None:
        return None
    from core.engine.variable_resolver import VariableResolver
    return VariableResolver.get_nested_value(data, path)


def _parse_link_header(link_header: str) -> Optional[str]:
    """Parse RFC 5988 Link header and return the 'next' URL."""
    if not link_header:
        return None
    for part in link_header.split(','):
        part = part.strip()
        if 'rel="next"' in part or "rel='next'" in part:
            url = part.split(';')[0].strip()
            if url.startswith('<') and url.endswith('>'):
                return url[1:-1]
    return None


def _extract_items(data: Any, data_path: str) -> List[Any]:
    """Extract items list from response data."""
    items = _extract_by_path(data, data_path) if data_path else data
    if not isinstance(items, list):
        items = [items] if items is not None else []
    return items


async def _paginate_offset(
    session, method: str, base_url: str, headers: dict, verify_ssl: bool,
    data_path: str, page_size: int, max_pages: int, delay_ms: int,
    params: dict, all_items: List[Any], pages_fetched: int,
) -> tuple:
    """Offset + limit pagination strategy."""
    offset_param = params.get('offset_param', 'offset')
    limit_param = params.get('limit_param', 'limit')
    offset = 0

    for _ in range(max_pages):
        url = _merge_query(base_url, {offset_param: offset, limit_param: page_size})
        async with session.request(method, url, headers=headers, ssl=verify_ssl if verify_ssl else False) as resp:
            data = await resp.json()
            items = _extract_items(data, data_path)

            all_items.extend(items)
            pages_fetched += 1
            logger.info(f"Page {pages_fetched}: {len(items)} items (offset={offset})")

            if len(items) < page_size:
                break
            offset += page_size

        if delay_ms > 0:
            await asyncio.sleep(delay_ms / 1000)

    return all_items, pages_fetched


async def _paginate_page(
    session, method: str, base_url: str, headers: dict, verify_ssl: bool,
    data_path: str, page_size: int, max_pages: int, delay_ms: int,
    params: dict, all_items: List[Any], pages_fetched: int,
) -> tuple:
    """Page number pagination strategy."""
    page_param = params.get('page_param', 'page')
    limit_param = params.get('limit_param', 'limit')
    current_page = params.get('start_page', 1)

    for _ in range(max_pages):
        query = {page_param: current_page}
        if page_size:
            query[limit_param] = page_size
        url = _merge_query(base_url, query)

        async with session.request(method, url, headers=headers, ssl=verify_ssl if verify_ssl else False) as resp:
            data = await resp.json()
            items = _extract_items(data, data_path)

            all_items.extend(items)
            pages_fetched += 1
            logger.info(f"Page {pages_fetched} (page={current_page}): {len(items)} items")

            if len(items) == 0:
                break
            current_page += 1

        if delay_ms > 0:
            await asyncio.sleep(delay_ms / 1000)

    return all_items, pages_fetched


async def _paginate_cursor(
    session, method: str, base_url: str, headers: dict, verify_ssl: bool,
    data_path: str, page_size: int, max_pages: int, delay_ms: int,
    params: dict, all_items: List[Any], pages_fetched: int,
) -> tuple:
    """Cursor / next-token pagination strategy."""
    cursor_param = params.get('cursor_param', 'cursor')
    cursor_path = params.get('cursor_path', '')
    cursor_value = None

    for _ in range(max_pages):
        query = {}
        if cursor_value:
            query[cursor_param] = cursor_value
        if page_size:
            query['limit'] = page_size
        url = _merge_query(base_url, query) if query else base_url

        async with session.request(method, url, headers=headers, ssl=verify_ssl if verify_ssl else False) as resp:
            data = await resp.json()
            items = _extract_items(data, data_path)

            all_items.extend(items)
            pages_fetched += 1

            next_cursor = _extract_by_path(data, cursor_path) if cursor_path else None
            logger.info(f"Page {pages_fetched}: {len(items)} items (cursor={'...' if next_cursor else 'none'})")

            if not next_cursor or len(items) == 0:
                break
            cursor_value = next_cursor

        if delay_ms > 0:
            await asyncio.sleep(delay_ms / 1000)

    return all_items, pages_fetched


async def _paginate_link_header(
    session, method: str, base_url: str, headers: dict, verify_ssl: bool,
    data_path: str, page_size: int, max_pages: int, delay_ms: int,
    params: dict, all_items: List[Any], pages_fetched: int,
) -> tuple:
    """Link header (RFC 5988) pagination strategy."""
    url = base_url
    if page_size:
        url = _merge_query(url, {'per_page': page_size})

    for _ in range(max_pages):
        async with session.request(method, url, headers=headers, ssl=verify_ssl if verify_ssl else False) as resp:
            data = await resp.json()
            items = _extract_items(data, data_path)

            all_items.extend(items)
            pages_fetched += 1

            next_url = _parse_link_header(resp.headers.get('Link', ''))
            logger.info(f"Page {pages_fetched}: {len(items)} items (next={'yes' if next_url else 'none'})")

            if not next_url or len(items) == 0:
                break
            url = next_url

        if delay_ms > 0:
            await asyncio.sleep(delay_ms / 1000)

    return all_items, pages_fetched


_STRATEGY_DISPATCH = {
    'offset': _paginate_offset,
    'page': _paginate_page,
    'cursor': _paginate_cursor,
    'link_header': _paginate_link_header,
}


@register_module(
    module_id='http.paginate',
    version='1.0.0',
    category='atomic',
    subcategory='http',
    tags=['http', 'pagination', 'api', 'rest', 'list', 'iterate', 'atomic'],
    label='HTTP Paginate',
    label_key='modules.http.paginate.label',
    description='Automatically iterate through paginated API endpoints and collect all results',
    description_key='modules.http.paginate.description',
    icon='ListRestart',
    color='#8B5CF6',

    input_types=['string', 'object'],
    output_types=['object'],
    can_connect_to=['*'],
    can_receive_from=['*'],
    can_be_start=True,

    timeout_ms=300000,  # 5 min for full pagination
    retryable=True,
    max_retries=2,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=True,
    required_permissions=['filesystem.read', 'filesystem.write'],

    params_schema=compose(
        presets.URL(required=True, placeholder='https://api.example.com/users'),
        presets.HTTP_METHOD(default='GET'),
        presets.HEADERS(),
        presets.HTTP_AUTH(),
        field(
            'strategy',
            type='string',
            label='Pagination Strategy',
            label_key='modules.http.paginate.strategy',
            description='How the API implements pagination',
            default='offset',
            options=[
                {'value': 'offset', 'label': 'Offset + Limit (skip/take)'},
                {'value': 'page', 'label': 'Page Number (?page=1,2,3...)'},
                {'value': 'cursor', 'label': 'Cursor / Next Token'},
                {'value': 'link_header', 'label': 'Link Header (RFC 5988)'},
            ],
            group=FieldGroup.BASIC,
        ),
        field(
            'data_path',
            type='string',
            label='Data Path',
            label_key='modules.http.paginate.data_path',
            description='Dot-notation path to the array of items in the response (e.g. "data", "results", "items")',
            placeholder='data',
            default='',
            group=FieldGroup.BASIC,
        ),
        # Offset strategy params
        field(
            'offset_param',
            type='string',
            label='Offset Parameter Name',
            label_key='modules.http.paginate.offset_param',
            description='Query parameter name for offset',
            default='offset',
            showIf={'strategy': {'$in': ['offset']}},
            group=FieldGroup.OPTIONS,
        ),
        field(
            'limit_param',
            type='string',
            label='Limit Parameter Name',
            label_key='modules.http.paginate.limit_param',
            description='Query parameter name for page size',
            default='limit',
            showIf={'strategy': {'$in': ['offset', 'page']}},
            group=FieldGroup.OPTIONS,
        ),
        field(
            'page_size',
            type='number',
            label='Page Size',
            label_key='modules.http.paginate.page_size',
            description='Number of items per page',
            default=100,
            min=1,
            max=10000,
            step=1,
            group=FieldGroup.OPTIONS,
        ),
        # Page number strategy params
        field(
            'page_param',
            type='string',
            label='Page Parameter Name',
            label_key='modules.http.paginate.page_param',
            description='Query parameter name for page number',
            default='page',
            showIf={'strategy': {'$in': ['page']}},
            group=FieldGroup.OPTIONS,
        ),
        field(
            'start_page',
            type='number',
            label='Start Page',
            label_key='modules.http.paginate.start_page',
            description='First page number (usually 0 or 1)',
            default=1,
            min=0,
            max=100,
            step=1,
            showIf={'strategy': {'$in': ['page']}},
            group=FieldGroup.OPTIONS,
        ),
        # Cursor strategy params
        field(
            'cursor_param',
            type='string',
            label='Cursor Parameter Name',
            label_key='modules.http.paginate.cursor_param',
            description='Query parameter name for cursor token',
            default='cursor',
            showIf={'strategy': {'$in': ['cursor']}},
            group=FieldGroup.OPTIONS,
        ),
        field(
            'cursor_path',
            type='string',
            label='Next Cursor Path',
            label_key='modules.http.paginate.cursor_path',
            description='Dot-notation path to the next cursor in the response (e.g. "meta.next_cursor", "pagination.next")',
            placeholder='meta.next_cursor',
            default='',
            showIf={'strategy': {'$in': ['cursor']}},
            group=FieldGroup.OPTIONS,
        ),
        # Shared params
        field(
            'max_pages',
            type='number',
            label='Max Pages',
            label_key='modules.http.paginate.max_pages',
            description='Maximum number of pages to fetch (safety limit)',
            default=50,
            min=1,
            max=1000,
            step=1,
            group=FieldGroup.OPTIONS,
        ),
        field(
            'delay_ms',
            type='number',
            label='Delay Between Requests (ms)',
            label_key='modules.http.paginate.delay_ms',
            description='Milliseconds to wait between page requests (rate limiting)',
            default=0,
            min=0,
            max=10000,
            step=100,
            ui={'unit': 'ms'},
            group=FieldGroup.OPTIONS,
        ),
        presets.TIMEOUT_S(default=30),
        presets.VERIFY_SSL(default=True),
        presets.SSRF_PROTECTION(),
    ),
    output_schema={
        'ok': {
            'type': 'boolean',
            'description': 'Whether all pages were fetched successfully',
            'description_key': 'modules.http.paginate.output.ok.description',
        },
        'items': {
            'type': 'array',
            'description': 'All collected items across all pages',
            'description_key': 'modules.http.paginate.output.items.description',
        },
        'total_items': {
            'type': 'number',
            'description': 'Total number of items collected',
            'description_key': 'modules.http.paginate.output.total_items.description',
        },
        'pages_fetched': {
            'type': 'number',
            'description': 'Number of pages fetched',
            'description_key': 'modules.http.paginate.output.pages_fetched.description',
        },
        'duration_ms': {
            'type': 'number',
            'description': 'Total duration in milliseconds',
            'description_key': 'modules.http.paginate.output.duration_ms.description',
        },
    },
    examples=[
        {
            'title': 'Offset pagination (REST API)',
            'title_key': 'modules.http.paginate.examples.offset.title',
            'params': {
                'url': 'https://api.example.com/users',
                'strategy': 'offset',
                'data_path': 'data',
                'page_size': 100,
            },
        },
        {
            'title': 'Page number pagination',
            'title_key': 'modules.http.paginate.examples.page.title',
            'params': {
                'url': 'https://api.example.com/products',
                'strategy': 'page',
                'data_path': 'results',
                'page_param': 'page',
                'page_size': 50,
                'start_page': 1,
            },
        },
        {
            'title': 'Cursor pagination (Slack, Notion)',
            'title_key': 'modules.http.paginate.examples.cursor.title',
            'params': {
                'url': 'https://api.notion.com/v1/databases/{db_id}/query',
                'method': 'POST',
                'strategy': 'cursor',
                'data_path': 'results',
                'cursor_path': 'next_cursor',
                'cursor_param': 'start_cursor',
                'auth': {'type': 'bearer', 'token': '${env.NOTION_TOKEN}'},
            },
        },
        {
            'title': 'Link header pagination (GitHub)',
            'title_key': 'modules.http.paginate.examples.link.title',
            'params': {
                'url': 'https://api.github.com/repos/octocat/hello-world/issues',
                'strategy': 'link_header',
                'page_size': 100,
                'auth': {'type': 'bearer', 'token': '${env.GITHUB_TOKEN}'},
            },
        },
    ],
    author='Flyto Team',
    license='MIT',
)
async def http_paginate(context: Dict[str, Any]) -> Dict[str, Any]:
    """Iterate through paginated API and collect all results."""
    try:
        import aiohttp
    except ImportError as exc:
        raise ImportError("aiohttp is required for http.paginate. Install with: pip install aiohttp") from exc

    import base64

    params = context['params']
    base_url = params['url']
    method = params.get('method', 'GET').upper()
    headers = dict(params.get('headers', {}))
    auth = params.get('auth')
    strategy = params.get('strategy', 'offset')
    data_path = params.get('data_path', '')
    max_pages = params.get('max_pages', 50)
    page_size = params.get('page_size', 100)
    delay_ms = params.get('delay_ms', 0)
    timeout_seconds = params.get('timeout', 30)
    verify_ssl = params.get('verify_ssl', True)

    start_time = time.time()
    all_items: List[Any] = []
    pages_fetched = 0

    try:
        validate_url_with_env_config(base_url)
    except SSRFError as e:
        return _make_result(False, [], 0, start_time, str(e), 'SSRF_BLOCKED')

    # Apply auth
    if auth:
        auth_type = auth.get('type', 'bearer')
        if auth_type == 'bearer':
            headers['Authorization'] = f'Bearer {auth.get("token", "")}'
        elif auth_type == 'basic':
            cred = base64.b64encode(f'{auth.get("username", "")}:{auth.get("password", "")}'.encode()).decode()
            headers['Authorization'] = f'Basic {cred}'
        elif auth_type == 'api_key':
            headers[auth.get('header_name', 'X-API-Key')] = auth.get('api_key', '')

    strategy_fn = _STRATEGY_DISPATCH.get(strategy)
    if not strategy_fn:
        return _make_result(False, [], 0, start_time,
                            f'Unknown pagination strategy: {strategy}', 'INVALID_STRATEGY')

    timeout = aiohttp.ClientTimeout(total=timeout_seconds)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            all_items, pages_fetched = await strategy_fn(
                session, method, base_url, headers, verify_ssl,
                data_path, page_size, max_pages, delay_ms,
                params, all_items, pages_fetched,
            )
    except asyncio.TimeoutError:
        logger.error(f"Pagination timeout after {pages_fetched} pages")
        return _make_result(False, all_items, pages_fetched, start_time,
                            f'Pagination timed out after {pages_fetched} pages', 'TIMEOUT')
    except aiohttp.ClientError as e:
        logger.error(f"Pagination client error on page {pages_fetched + 1}: {e}")
        return _make_result(False, all_items, pages_fetched, start_time, str(e), 'CLIENT_ERROR')
    except Exception as e:
        logger.error(f"Pagination failed: {e}")
        return _make_result(False, all_items, pages_fetched, start_time, str(e), 'PAGINATE_ERROR')

    logger.info(f"Pagination complete: {len(all_items)} items across {pages_fetched} pages")
    return _make_result(True, all_items, pages_fetched, start_time)
