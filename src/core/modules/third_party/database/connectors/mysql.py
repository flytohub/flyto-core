# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
MySQL Database Module
Execute SQL queries on MySQL database.

HOW FAR THIS MODULE FOLLOWS REALITY

One payload-returning path, two rungs, decided by whether anything came back:

    rows came back      OBSERVED    `len(rows)` over row objects aiomysql
        materialised from bytes the server sent. Nothing is inferred.
    no rows came back   ACCEPTED    `len(rows) == 0` reads identically whether
        the statement matched nothing, changed five rows and returned no result
        set, or was discarded entirely. A value that would be unchanged if the
        effect had not happened is not evidence of it, so an empty answer claims
        only that the server answered.

That second rung is the same correction `database.query` needed, and finding it
here surfaced the same bug underneath it. `aiomysql.connect` defaults to
`autocommit=False`, this module accepts arbitrary SQL, and the `finally` below
closed the connection without committing -- so an INSERT / UPDATE / DELETE run
through it executed inside an open transaction, returned a successful payload,
and was rolled back on close. `conn.commit()` before the close closes that; a
commit after a pure read is a no-op, so it costs nothing.

`database.query`'s sqlite branch lost data exactly this way through its own
default fetch mode. This module is the second instance, and it had no fetch mode
to hide behind: every statement it has ever run took this path.

VERIFIED is unreachable and no postcondition is declared -- nothing here
evaluates a predicate -- so `ceiling_for(None)` caps this at OBSERVED.
"""
import os

from .....utils import enforce_outbound_host
from .....engine.outcome import ClaimBy, Outcome, envelope
from ....registry import register_module
from ....schema import compose, presets


def _returned_rows_outcome(row_count):
    """OBSERVED for rows the server sent, ACCEPTED for an empty answer.

    A returned row is an observation of that row. NO returned rows is not an
    observation of anything: the integer is the same for a SELECT that matched
    nothing and for an UPDATE whose result set does not exist. Claiming OBSERVED
    on it would attach "we saw the world change" to a number that would read
    identically if nothing had happened.
    """
    if row_count <= 0:
        return envelope(
            Outcome.ACCEPTED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'no_rows_returned',
                'backend': 'mysql',
                'measured_by': None,
                'detail': (
                    'The server answered and returned no rows. That is not an '
                    'observation of the data: a statement that returns no '
                    'result set reads the same here whether it changed '
                    'everything or nothing. This module runs whatever SQL it is '
                    'given, so that includes every write it has ever run.'
                ),
            }],
        )
    return envelope(
        Outcome.OBSERVED,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'rows_returned',
            'backend': 'mysql',
            'count': row_count,
            'measured_by': 'len() over rows aiomysql returned from the server',
        }],
    )


@register_module(
    module_id='db.mysql.query',
    version='1.0.0',
    category='database',
    tags=['ssrf_protected', 'database', 'mysql', 'sql', 'query', 'db'],
    label='MySQL Query',
    label_key='modules.db.mysql.query.label',
    description='Execute a SQL query on MySQL database and return results',
    description_key='modules.db.mysql.query.description',
    icon='Database',
    color='#00758F',

    # Connection types
    input_types=['json', 'object'],
    output_types=['json', 'array'],
    can_receive_from=['data.*', 'http.*'],
    can_connect_to=['data.*', 'notify.*'],

    # Phase 2: Execution settings
    timeout_ms=60000,  # Database queries can take time
    retryable=True,  # Network errors can be retried for read queries
    max_retries=3,
    concurrent_safe=True,  # Multiple queries can run in parallel

    # Phase 2: Security settings
    requires_credentials=True,
    credential_keys=['MYSQL_HOST', 'MYSQL_USER', 'MYSQL_PASSWORD'],
    handles_sensitive_data=True,  # Database data is typically sensitive
    required_permissions=['database.query'],

    params_schema=compose(
        presets.DB_HOST(),
        presets.DB_PORT(default=3306),
        presets.DB_USER(),
        presets.DB_PASSWORD(),
        presets.DB_NAME(),
        presets.SQL_QUERY(placeholder='SELECT * FROM users WHERE active = 1'),
        presets.DB_QUERY_PARAMS(),
    ),
    output_schema={
        'rows': {
            'type': 'array',
            'description': 'Array of result rows as objects'
        ,
                'description_key': 'modules.db.mysql.query.output.rows.description'},
        'row_count': {
            'type': 'number',
            'description': (
                'Number of rows RETURNED, never rows affected. A statement that '
                'returns no result set reports 0 here whether it changed every '
                'row or none -- see outcome'
            )
        ,
                'description_key': 'modules.db.mysql.query.output.row_count.description'},
        'columns': {
            'type': 'array',
            'description': 'Column names in result set'
        ,
                'description_key': 'modules.db.mysql.query.output.columns.description'},
        'outcome': {
            'type': 'object',
            'description': (
                'How far the effect was followed: observed when rows came back '
                'off the wire, accepted when the server answered with none. '
                'Never higher than observed -- nothing here evaluates a '
                'postcondition'
            )
        ,
                'description_key': 'modules.db.mysql.query.output.outcome.description'}
    },
    examples=[
        {
            'title': 'Select products',
            'title_key': 'modules.db.mysql.query.examples.select.title',
            'params': {
                'query': 'SELECT id, name, price FROM products WHERE stock > 0 ORDER BY price DESC LIMIT 20'
            }
        },
        {
            'title': 'Parameterized query',
            'title_key': 'modules.db.mysql.query.examples.parameterized.title',
            'params': {
                'query': 'SELECT * FROM orders WHERE customer_id = %s AND created_at > %s',
                'params': ['${customer_id}', '2024-01-01']
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    docs_url='https://dev.mysql.com/doc/refman/8.0/en/select.html'
)
async def mysql_query(context):
    """Execute MySQL query"""
    params = context['params']

    try:
        import aiomysql
    except ImportError:
        raise ImportError("aiomysql package required. Install with: pip install aiomysql")

    # Get connection parameters - NO hardcoded defaults
    host = params.get('host') or os.getenv('MYSQL_HOST')
    if not host:
        raise ValueError(
            "Database host not configured. "
            "Set 'host' parameter or MYSQL_HOST environment variable."
        )

    # SECURITY: a caller-supplied `host` makes this module a TCP client aimed
    # anywhere the runner can route, which is SSRF without a URL. A host from
    # MYSQL_HOST is operator configuration and gets the same check — the guard
    # is cheap and the operator can widen it via FLYTO_ALLOWED_HOSTS.
    enforce_outbound_host(host, purpose='MySQL')

    conn_params = {
        'host': host,
        'port': params.get('port', 3306),
        'user': params.get('user') or os.getenv('MYSQL_USER'),
        'password': params.get('password') or os.getenv('MYSQL_PASSWORD'),
        'db': params.get('database') or os.getenv('MYSQL_DATABASE')
    }

    # Connect and execute query
    conn = await aiomysql.connect(**conn_params)
    try:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            query_params = params.get('params', [])
            await cursor.execute(params['query'], query_params)
            rows = await cursor.fetchall()

            columns = [desc[0] for desc in cursor.description] if cursor.description else []

            return {
                'rows': rows,
                'row_count': len(rows),
                'columns': columns,
                'outcome': _returned_rows_outcome(len(rows)),
            }
    finally:
        # DATA LOSS: aiomysql.connect defaults to autocommit=False and this
        # module accepts arbitrary SQL, so every INSERT / UPDATE / DELETE run
        # through it opened a transaction that this close discarded -- the
        # module returned a successful payload and the write was rolled back.
        # A commit after a pure read is a no-op, so this costs nothing.
        await conn.commit()
        conn.close()
