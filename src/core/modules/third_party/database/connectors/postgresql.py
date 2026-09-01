# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
PostgreSQL Database Module
Execute SQL queries on PostgreSQL database.

HOW FAR THIS MODULE FOLLOWS REALITY

One payload-returning path, two rungs, decided by whether anything came back:

    rows came back      OBSERVED    `len(result_rows)` over Records asyncpg
        materialised from bytes the server sent. Nothing is inferred.
    no rows came back   ACCEPTED    `len([]) == 0` reads identically whether the
        statement matched nothing, changed five rows and returned no result set,
        or was discarded entirely. A value that would be unchanged if the effect
        had not happened is not evidence of it.

The empty case matters more here than it looks, because `conn.fetch` is how this
module runs everything it is given, writes included: an `INSERT INTO t VALUES
(1)` through this module comes back with `rows: []` and `row_count: 0` and is a
committed write, and a `SELECT` matching nothing comes back byte-identical and
changed nothing. The rung does not distinguish those two -- it says of both that
we have no observation, which is the truth. Claiming OBSERVED would say we
watched the world change on a payload that contains no evidence either way.

`conn.execute`'s command tag WOULD carry a count for a write, and this module
does not use it -- `fetch` is the only call here, and its return value is the
result set. That is why the ceiling on the empty path is ACCEPTED and not lower
or higher: the server answered, and the answer says nothing about the data.

Unlike its mysql sibling, this module has no rollback bug. asyncpg runs
statements outside an explicit transaction in autocommit mode, so a write
through `fetch` is durable when `fetch` returns.

VERIFIED is unreachable and no postcondition is declared -- nothing here
evaluates a predicate -- so `ceiling_for(None)` caps this at OBSERVED.
"""
import os

from .....engine.outcome import ClaimBy, Outcome, envelope
from ....registry import register_module
from ....schema import compose, presets
from ._dsn_target import enforce_dsn_target


def _returned_rows_outcome(row_count):
    """OBSERVED for rows the server sent, ACCEPTED for an empty answer."""
    if row_count <= 0:
        return envelope(
            Outcome.ACCEPTED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'no_rows_returned',
                'backend': 'postgresql',
                'measured_by': None,
                'detail': (
                    'The server answered and returned no rows. That is not an '
                    'observation of the data: a statement that returns no '
                    'result set reads the same here whether it changed '
                    'everything or nothing. This module runs whatever SQL it is '
                    'given through conn.fetch, so that includes every write it '
                    'has ever run.'
                ),
            }],
        )
    return envelope(
        Outcome.OBSERVED,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'rows_returned',
            'backend': 'postgresql',
            'count': row_count,
            'measured_by': 'len() over Records asyncpg returned from the server',
        }],
    )


@register_module(
    module_id='db.postgresql.query',
    version='1.0.0',
    category='database',
    tags=['ssrf_protected', 'database', 'postgresql', 'sql', 'query', 'db'],
    label='PostgreSQL Query',
    label_key='modules.db.postgresql.query.label',
    description='Execute a SQL query on PostgreSQL database and return results',
    description_key='modules.db.postgresql.query.description',
    icon='Database',
    color='#336791',

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
    credential_keys=['POSTGRESQL_HOST', 'POSTGRESQL_USER', 'POSTGRESQL_PASSWORD'],
    handles_sensitive_data=True,  # Database data is typically sensitive
    required_permissions=['database.query'],

    params_schema=compose(
        presets.DB_CONNECTION_STRING(),
        presets.SQL_QUERY(),
        presets.DB_QUERY_PARAMS(),
    ),
    output_schema={
        'rows': {
            'type': 'array',
            'description': 'Array of result rows as objects'
        ,
                'description_key': 'modules.db.postgresql.query.output.rows.description'},
        'row_count': {
            'type': 'number',
            'description': (
                'Number of rows RETURNED, never rows affected. A statement that '
                'returns no result set reports 0 here whether it changed every '
                'row or none -- see outcome'
            )
        ,
                'description_key': 'modules.db.postgresql.query.output.row_count.description'},
        'columns': {
            'type': 'array',
            'description': 'Column names in result set'
        ,
                'description_key': 'modules.db.postgresql.query.output.columns.description'},
        'outcome': {
            'type': 'object',
            'description': (
                'How far the effect was followed: observed when rows came back '
                'off the wire, accepted when the server answered with none. '
                'Never higher than observed -- nothing here evaluates a '
                'postcondition'
            )
        ,
                'description_key': 'modules.db.postgresql.query.output.outcome.description'}
    },
    examples=[
        {
            'title': 'Select users',
            'title_key': 'modules.db.postgresql.query.examples.select.title',
            'params': {
                'query': 'SELECT id, email, created_at FROM users WHERE active = true LIMIT 10'
            }
        },
        {
            'title': 'Parameterized query',
            'title_key': 'modules.db.postgresql.query.examples.parameterized.title',
            'params': {
                'query': 'SELECT * FROM orders WHERE user_id = $1 AND status = $2',
                'params': ['${user_id}', 'completed']
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    docs_url='https://www.postgresql.org/docs/current/sql-select.html'
)
async def postgresql_query(context):
    """Execute PostgreSQL query"""
    params = context['params']

    # Get connection string
    conn_string = params.get('connection_string') or os.getenv('POSTGRESQL_URL')
    if not conn_string:
        raise ValueError("Connection string required: provide 'connection_string' param or set POSTGRESQL_URL env variable")

    # SECURITY: a caller-supplied connection_string names a TCP target the same
    # way `host` does in db.mysql.query, but hides it from the name-based
    # outbound sweep — that is how GHSA-9x26-9vhm-2qhw reached internal
    # databases and the metadata endpoint. Guarded before the driver import so
    # a deployment without the driver installed is protected rather than
    # accidentally safe.
    enforce_dsn_target(conn_string, purpose='PostgreSQL')

    try:
        import asyncpg
    except ImportError:
        raise ImportError("asyncpg package required. Install with: pip install asyncpg")

    # Connect and execute query
    conn = await asyncpg.connect(conn_string)
    try:
        query_params = params.get('params', [])
        rows = await conn.fetch(params['query'], *query_params)

        # Convert to list of dicts
        result_rows = [dict(row) for row in rows]
        columns = list(rows[0].keys()) if rows else []

        return {
            'rows': result_rows,
            'row_count': len(result_rows),
            'columns': columns,
            'outcome': _returned_rows_outcome(len(result_rows)),
        }
    finally:
        await conn.close()
