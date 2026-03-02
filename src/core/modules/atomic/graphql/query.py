# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
GraphQL Query Module
Execute a GraphQL query against an endpoint.
"""
import logging
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError, ModuleError

logger = logging.getLogger(__name__)


def _prepare_graphql_request(params: Dict[str, Any], operation_key: str = 'query'):
    """Validate and prepare GraphQL request components.

    Returns (url, payload, headers).
    """
    url = params.get('url', '').strip()
    operation = params.get(operation_key, '').strip()
    variables = params.get('variables') or None
    headers = dict(params.get('headers') or {})
    auth_token = params.get('auth_token', '').strip()

    if not url:
        raise ValidationError("Missing required parameter: url", field="url")
    if not operation:
        raise ValidationError("Missing required parameter: {}".format(operation_key), field=operation_key)

    headers.setdefault('Content-Type', 'application/json')
    if auth_token:
        headers['Authorization'] = 'Bearer {}'.format(auth_token)

    payload = {'query': operation}
    if variables:
        payload['variables'] = variables

    return url, payload, headers


async def _execute_graphql(url: str, payload: dict, headers: dict, label: str) -> Dict[str, Any]:
    """Send the GraphQL POST and return the parsed response."""
    try:
        import aiohttp
    except ImportError:
        raise ModuleError("aiohttp is required for graphql modules. Install with: pip install aiohttp")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as response:
                status_code = response.status
                try:
                    body = await response.json(content_type=None)
                except Exception:
                    text = await response.text()
                    raise ModuleError(
                        "GraphQL endpoint returned non-JSON response (HTTP {}): {}".format(status_code, text[:500])
                    )
    except aiohttp.ClientError as e:
        raise ModuleError("GraphQL {} request failed: {}".format(label, str(e)))

    data = body.get('data')
    errors = body.get('errors')
    if errors:
        error_msgs = [e.get('message', str(e)) for e in errors]
        logger.warning("GraphQL %s returned errors: %s", label, error_msgs)

    logger.info("GraphQL %s to %s completed (HTTP %d)", label, url, status_code)
    return {'ok': True, 'data': {'data': data, 'errors': errors, 'status_code': status_code}}


@register_module(
    module_id='graphql.query',
    version='1.0.0',
    category='graphql',
    tags=['graphql', 'query', 'api', 'http', 'data'],
    label='GraphQL Query',
    label_key='modules.graphql.query.label',
    description='Execute a GraphQL query against an endpoint',
    description_key='modules.graphql.query.description',
    icon='Code',
    color='#E535AB',
    input_types=['string', 'object'],
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
            'url',
            type='string',
            format='url',
            label='Endpoint URL',
            label_key='modules.graphql.query.params.url.label',
            description='GraphQL endpoint URL',
            description_key='modules.graphql.query.params.url.description',
            required=True,
            placeholder='https://api.example.com/graphql',
            group=FieldGroup.BASIC,
        ),
        field(
            'query',
            type='string',
            label='Query',
            label_key='modules.graphql.query.params.query.label',
            description='GraphQL query string',
            description_key='modules.graphql.query.params.query.description',
            required=True,
            placeholder='{ users { id name email } }',
            format='multiline',
            group=FieldGroup.BASIC,
        ),
        field(
            'variables',
            type='object',
            label='Variables',
            label_key='modules.graphql.query.params.variables.label',
            description='GraphQL query variables as key-value pairs',
            description_key='modules.graphql.query.params.variables.description',
            group=FieldGroup.OPTIONS,
        ),
        field(
            'headers',
            type='object',
            label='Headers',
            label_key='modules.graphql.query.params.headers.label',
            description='Additional HTTP headers to send with the request',
            description_key='modules.graphql.query.params.headers.description',
            group=FieldGroup.OPTIONS,
        ),
        field(
            'auth_token',
            type='string',
            format='password',
            label='Auth Token',
            label_key='modules.graphql.query.params.auth_token.label',
            description='Bearer token for authentication (added as Authorization header)',
            description_key='modules.graphql.query.params.auth_token.description',
            placeholder='your-bearer-token',
            group=FieldGroup.CONNECTION,
        ),
    ),
    output_schema={
        'data': {
            'type': 'object',
            'description': 'GraphQL response data',
            'description_key': 'modules.graphql.query.output.data.description',
        },
        'errors': {
            'type': 'array',
            'description': 'GraphQL errors (null if no errors)',
            'description_key': 'modules.graphql.query.output.errors.description',
        },
        'status_code': {
            'type': 'number',
            'description': 'HTTP status code',
            'description_key': 'modules.graphql.query.output.status_code.description',
        },
    },
    examples=[
        {
            'title': 'Simple query',
            'title_key': 'modules.graphql.query.examples.simple.title',
            'params': {
                'url': 'https://api.example.com/graphql',
                'query': '{ users { id name } }',
            },
        },
        {
            'title': 'Query with variables and auth',
            'title_key': 'modules.graphql.query.examples.variables.title',
            'params': {
                'url': 'https://api.example.com/graphql',
                'query': 'query GetUser($id: ID!) { user(id: $id) { id name email } }',
                'variables': {'id': '123'},
                'auth_token': 'my-token',
            },
        },
    ],
    author='Flyto Team',
    license='MIT',
)
async def graphql_query(context: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a GraphQL query against an endpoint."""
    url, payload, headers = _prepare_graphql_request(context['params'], 'query')
    return await _execute_graphql(url, payload, headers, 'query')
