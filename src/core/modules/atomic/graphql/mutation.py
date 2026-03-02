# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
GraphQL Mutation Module
Execute a GraphQL mutation against an endpoint.
"""
import logging
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError, ModuleError

logger = logging.getLogger(__name__)


def _prepare_graphql_request(params: Dict[str, Any], operation_key: str = 'mutation'):
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
    module_id='graphql.mutation',
    version='1.0.0',
    category='graphql',
    tags=['graphql', 'mutation', 'api', 'http', 'data', 'write'],
    label='GraphQL Mutation',
    label_key='modules.graphql.mutation.label',
    description='Execute a GraphQL mutation against an endpoint',
    description_key='modules.graphql.mutation.description',
    icon='Code',
    color='#E535AB',
    input_types=['string', 'object'],
    output_types=['object'],

    can_receive_from=['*'],
    can_connect_to=['*'],

    retryable=False,
    concurrent_safe=True,
    timeout_ms=30000,

    requires_credentials=False,
    handles_sensitive_data=True,
    required_permissions=[],

    params_schema=compose(
        field(
            'url',
            type='string',
            format='url',
            label='Endpoint URL',
            label_key='modules.graphql.mutation.params.url.label',
            description='GraphQL endpoint URL',
            description_key='modules.graphql.mutation.params.url.description',
            required=True,
            placeholder='https://api.example.com/graphql',
            group=FieldGroup.BASIC,
        ),
        field(
            'mutation',
            type='string',
            label='Mutation',
            label_key='modules.graphql.mutation.params.mutation.label',
            description='GraphQL mutation string',
            description_key='modules.graphql.mutation.params.mutation.description',
            required=True,
            placeholder='mutation CreateUser($input: UserInput!) { createUser(input: $input) { id } }',
            format='multiline',
            group=FieldGroup.BASIC,
        ),
        field(
            'variables',
            type='object',
            label='Variables',
            label_key='modules.graphql.mutation.params.variables.label',
            description='GraphQL mutation variables as key-value pairs',
            description_key='modules.graphql.mutation.params.variables.description',
            group=FieldGroup.OPTIONS,
        ),
        field(
            'headers',
            type='object',
            label='Headers',
            label_key='modules.graphql.mutation.params.headers.label',
            description='Additional HTTP headers to send with the request',
            description_key='modules.graphql.mutation.params.headers.description',
            group=FieldGroup.OPTIONS,
        ),
        field(
            'auth_token',
            type='string',
            format='password',
            label='Auth Token',
            label_key='modules.graphql.mutation.params.auth_token.label',
            description='Bearer token for authentication (added as Authorization header)',
            description_key='modules.graphql.mutation.params.auth_token.description',
            placeholder='your-bearer-token',
            group=FieldGroup.CONNECTION,
        ),
    ),
    output_schema={
        'data': {
            'type': 'object',
            'description': 'GraphQL response data',
            'description_key': 'modules.graphql.mutation.output.data.description',
        },
        'errors': {
            'type': 'array',
            'description': 'GraphQL errors (null if no errors)',
            'description_key': 'modules.graphql.mutation.output.errors.description',
        },
        'status_code': {
            'type': 'number',
            'description': 'HTTP status code',
            'description_key': 'modules.graphql.mutation.output.status_code.description',
        },
    },
    examples=[
        {
            'title': 'Create user mutation',
            'title_key': 'modules.graphql.mutation.examples.create.title',
            'params': {
                'url': 'https://api.example.com/graphql',
                'mutation': 'mutation CreateUser($input: UserInput!) { createUser(input: $input) { id name } }',
                'variables': {'input': {'name': 'John', 'email': 'john@example.com'}},
            },
        },
    ],
    author='Flyto Team',
    license='MIT',
)
async def graphql_mutation(context: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a GraphQL mutation against an endpoint."""
    url, payload, headers = _prepare_graphql_request(context['params'], 'mutation')
    return await _execute_graphql(url, payload, headers, 'mutation')
