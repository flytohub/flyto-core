# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

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
            type='text',
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
            type='password',
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
    try:
        import aiohttp
    except ImportError:
        raise ModuleError(
            "aiohttp is required for graphql.mutation. "
            "Install with: pip install aiohttp"
        )

    params = context['params']
    url = params.get('url', '').strip()
    mutation = params.get('mutation', '').strip()
    variables = params.get('variables') or None
    headers = dict(params.get('headers') or {})
    auth_token = params.get('auth_token', '').strip()

    if not url:
        raise ValidationError("Missing required parameter: url", field="url")
    if not mutation:
        raise ValidationError("Missing required parameter: mutation", field="mutation")

    # Set default content type
    headers.setdefault('Content-Type', 'application/json')

    # Add Bearer token if provided
    if auth_token:
        headers['Authorization'] = 'Bearer {}'.format(auth_token)

    # Build request payload — GraphQL uses 'query' key for both queries and mutations
    payload = {'query': mutation}
    if variables:
        payload['variables'] = variables

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as response:
                status_code = response.status
                try:
                    body = await response.json(content_type=None)
                except Exception:
                    text = await response.text()
                    raise ModuleError(
                        "GraphQL endpoint returned non-JSON response (HTTP {}): {}".format(
                            status_code, text[:500]
                        )
                    )
    except aiohttp.ClientError as e:
        raise ModuleError("GraphQL mutation request failed: {}".format(str(e)))

    data = body.get('data')
    errors = body.get('errors')

    if errors:
        error_msgs = [e.get('message', str(e)) for e in errors]
        logger.warning("GraphQL mutation returned errors: %s", error_msgs)

    logger.info("GraphQL mutation to %s completed (HTTP %d)", url, status_code)

    return {
        'ok': True,
        'data': {
            'data': data,
            'errors': errors,
            'status_code': status_code,
        },
    }
