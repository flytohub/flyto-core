# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Database Update Module
Update data in database tables

HOW FAR THIS MODULE FOLLOWS REALITY

Unlike its sibling `database.insert`, this module was already reading a real
number on every path -- `updated_count` has never been arithmetic on the input.
What it lacked was a way to say so, and a way to distinguish the one case where
the number is not a measurement:

  postgresql       `int(result.split()[-1])` over the server's command tag. The
      only statement this module issues is an UPDATE, and the postgres UPDATE
      tag is always 'UPDATE <count>', so a number always crossed the wire here.
      OBSERVED unconditionally, and the tag itself travels in the effect.

  mysql / sqlite   `cursor.rowcount`. PEP 249 allows -1 for "the driver cannot
      determine a count", and -1 is not a count of anything: that path is
      ACCEPTED. A rowcount of 0 is a different fact -- the backend saying no
      rows changed -- and stays OBSERVED. Collapsing the two would be the same
      defect `database.query` had, where a literal 0 and a counted 0 were
      indistinguishable downstream.

One caveat is carried in the effect rather than in the rung, because it is a
different question from how far we followed the effect: MySQL reports CHANGED
rows for an UPDATE, not MATCHED rows, unless the connection sets
CLIENT_FOUND_ROWS. An UPDATE that matched five rows and altered none reports 0,
truthfully. postgres and sqlite report matched rows.

VERIFIED is unreachable and no postcondition is declared: a count of changed
rows is not a predicate evaluated against the stored values. `ceiling_for(None)`
caps this at OBSERVED, which is where it belongs.
"""
import logging
import os
from typing import Any, Dict, List, Optional

from ....engine.outcome import ClaimBy, Outcome, envelope
from ...registry import register_module
from ...schema import compose, presets
from ....utils import validate_sql_identifier, validate_sql_identifiers, SQLInjectionError


logger = logging.getLogger(__name__)


def _update_outcome(
    *,
    backend: str,
    counted: bool,
    updated_count: Any,
    measured_by: str,
    detail: str,
    counts: str,
) -> Dict[str, Any]:
    """The rung this UPDATE earned.

    `counted` is a runtime fact about this one statement, never a property of
    the backend: the same mysql connection answers with a rowcount for one
    statement and -1 for the next.

        counted=True    a number crossed the wire            -> OBSERVED
        counted=False   no number was reported for this one  -> ACCEPTED

    `counts` names what the number is a count OF -- 'rows changed' on mysql,
    'rows matched' elsewhere -- because an integer that means two different
    things on two backends is worth less than one that says which it is.
    """
    if counted:
        return envelope(
            Outcome.OBSERVED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'rows_updated',
                'backend': backend,
                'count': updated_count,
                'counts': counts,
                'measured_by': measured_by,
            }],
        )
    return envelope(
        Outcome.ACCEPTED,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'statement_accepted',
            'backend': backend,
            'count_reported': False,
            'measured_by': None,
            'detail': detail,
        }],
    )


@register_module(
    module_id='database.update',
    stability="beta",
    version='1.0.0',
    category='database',
    subcategory='write',
    tags=['database', 'sql', 'update', 'postgresql', 'mysql', 'sqlite'],
    label='Database Update',
    label_key='modules.database.update.label',
    description='Update data in database tables',
    description_key='modules.database.update.description',
    icon='Database',
    color='#FB8C00',

    input_types=['object'],
    output_types=['object'],
    can_connect_to=['database.*', 'data.*', 'array.*', 'object.*', 'file.*', 'http.*', 'notify.*', 'flow.*'],
    can_receive_from=['*'],

    timeout_ms=60000,
    retryable=True,
    max_retries=2,
    concurrent_safe=False,

    requires_credentials=True,
    credential_keys=['API_KEY'],
    handles_sensitive_data=True,
    required_permissions=['filesystem.read', 'filesystem.write'],

    params_schema=compose(
        presets.DB_TABLE(),
        presets.DB_DATA(),
        presets.WHERE_CONDITIONS(),
        presets.DB_TYPE(),
        presets.DB_CONNECTION_STRING(),
        presets.DB_HOST(),
        presets.DB_PORT(),
        presets.DB_NAME(),
        presets.DB_USER(),
        presets.DB_PASSWORD(),
    ),
    output_schema={
        'updated_count': {
            'type': 'number',
            'description': (
                'Number of rows the backend reported for this UPDATE: matched '
                'rows on postgresql and sqlite, CHANGED rows on mysql. -1 on '
                'mysql/sqlite means the driver reported no count -- see outcome'
            )
        ,
                'description_key': 'modules.database.update.output.updated_count.description'},
        'outcome': {
            'type': 'object',
            'description': (
                'How far this update was followed into reality: observed when a '
                'row count crossed the wire, accepted when the driver reported '
                'none for this statement. Never higher than observed -- nothing '
                'here evaluates a postcondition'
            )
        ,
                'description_key': 'modules.database.update.output.outcome.description'}
    },
    examples=[
        {
            'title': 'Update user status',
            'title_key': 'modules.database.update.examples.status.title',
            'params': {
                'table': 'users',
                'data': {'status': 'active'},
                'where': {'id': 123},
                'database_type': 'postgresql'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def database_update(context: Dict[str, Any]) -> Dict[str, Any]:
    """Update data in database"""
    params = context['params']

    # SECURITY: reject client-supplied connection targets (connection_string OR
    # host/port/credentials) unless FLYTO_ALLOW_CLIENT_DB_DSN is set; refuse
    # SSRF-sensitive hosts when allowed. See database/_dsn_guard.py.
    from ._dsn_guard import guard_client_dsn
    guard_client_dsn(params)

    table = params['table']
    data = params['data']
    where = params['where']
    db_type = params.get('database_type', 'postgresql')
    connection_string = params.get('connection_string') or os.getenv('DATABASE_URL')

    # SECURITY: Validate table name to prevent SQL injection
    try:
        table = validate_sql_identifier(table, 'table')
    except SQLInjectionError as e:
        return {
            'ok': False,
            'error': str(e),
            'error_code': 'SQL_INJECTION'
        }

    if not data:
        raise ValueError("No data to update")
    if not where:
        raise ValueError("WHERE conditions required for safety")

    # SECURITY: Validate column names in data and where clauses
    try:
        validate_sql_identifiers(list(data.keys()), 'column')
        validate_sql_identifiers(list(where.keys()), 'where column')
    except SQLInjectionError as e:
        return {
            'ok': False,
            'error': str(e),
            'error_code': 'SQL_INJECTION'
        }

    if db_type == 'postgresql':
        return await _update_postgresql(table, data, where, connection_string, params)
    elif db_type == 'mysql':
        return await _update_mysql(table, data, where, connection_string, params)
    elif db_type == 'sqlite':
        return await _update_sqlite(table, data, where, params)
    else:
        raise ValueError(f"Unsupported database type: {db_type}")


async def _update_postgresql(
    table: str,
    data: Dict[str, Any],
    where: Dict[str, Any],
    connection_string: Optional[str],
    params: Dict[str, Any]
) -> Dict[str, Any]:
    """Update PostgreSQL"""
    try:
        import asyncpg
    except ImportError:
        raise ImportError("asyncpg is required for PostgreSQL. Install with: pip install asyncpg")

    if not connection_string:
        # NO hardcoded defaults - require explicit configuration
        host = params.get('host') or os.getenv('POSTGRES_HOST')
        port = params.get('port') or int(os.getenv('POSTGRES_PORT', '5432'))
        database = params.get('database') or os.getenv('POSTGRES_DB')
        user = params.get('user') or os.getenv('POSTGRES_USER')
        password = params.get('password') or os.getenv('POSTGRES_PASSWORD')

        if not host:
            raise ValueError(
                "Database host not configured. "
                "Set 'host' parameter or POSTGRES_HOST environment variable."
            )
        if not all([database, user]):
            raise ValueError("Database connection not configured")

        connection_string = f"postgresql://{user}:{password}@{host}:{port}/{database}"

    conn = await asyncpg.connect(connection_string)
    try:
        set_columns = list(data.keys())
        where_columns = list(where.keys())

        param_idx = 1
        set_parts = []
        for col in set_columns:
            set_parts.append(f"{col} = ${param_idx}")
            param_idx += 1

        where_parts = []
        for col in where_columns:
            where_parts.append(f"{col} = ${param_idx}")
            param_idx += 1

        query = f"UPDATE {table} SET {', '.join(set_parts)} WHERE {' AND '.join(where_parts)}"

        values = [data[col] for col in set_columns] + [where[col] for col in where_columns]

        result = await conn.execute(query, *values)
        # The only statement this module builds is an UPDATE, and the postgres
        # UPDATE tag is always 'UPDATE <count>'. The parse is left exactly as it
        # was -- including raising on a tag that carries no integer -- because a
        # fabricated 0 next to a rung is worse than an error. `counted` is
        # therefore unconditionally True on this return, and the tag rides in
        # the effect so the claim can be checked against what the server said.
        updated_count = int(result.split()[-1])

        logger.info(f"Updated {updated_count} rows in {table}")

        return {
            'ok': True,
            'updated_count': updated_count,
            'outcome': _update_outcome(
                backend='postgresql',
                counted=True,
                updated_count=updated_count,
                measured_by=f'row count parsed from the postgres command tag {result!r}',
                detail='',
                counts='rows matched by the WHERE clause',
            ),
        }
    finally:
        await conn.close()


async def _update_mysql(
    table: str,
    data: Dict[str, Any],
    where: Dict[str, Any],
    connection_string: Optional[str],
    params: Dict[str, Any]
) -> Dict[str, Any]:
    """Update MySQL"""
    try:
        import aiomysql
    except ImportError:
        raise ImportError("aiomysql is required for MySQL. Install with: pip install aiomysql")

    # NO hardcoded defaults - require explicit configuration
    host = params.get('host') or os.getenv('MYSQL_HOST')
    port = params.get('port') or int(os.getenv('MYSQL_PORT', '3306'))
    database = params.get('database') or os.getenv('MYSQL_DATABASE')
    user = params.get('user') or os.getenv('MYSQL_USER')
    password = params.get('password') or os.getenv('MYSQL_PASSWORD')

    if not host:
        raise ValueError(
            "Database host not configured. "
            "Set 'host' parameter or MYSQL_HOST environment variable."
        )

    conn = await aiomysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        db=database
    )
    try:
        set_parts = [f"{col} = %s" for col in data.keys()]
        where_parts = [f"{col} = %s" for col in where.keys()]

        query = f"UPDATE {table} SET {', '.join(set_parts)} WHERE {' AND '.join(where_parts)}"

        values = list(data.values()) + list(where.values())

        async with conn.cursor() as cursor:
            await cursor.execute(query, values)
            updated_count = cursor.rowcount
            await conn.commit()

        counted = isinstance(updated_count, int) and updated_count >= 0

        logger.info(f"Updated {updated_count} rows in {table}")

        return {
            'ok': True,
            'updated_count': updated_count,
            'outcome': _update_outcome(
                backend='mysql',
                counted=counted,
                updated_count=updated_count,
                measured_by='cursor.rowcount from the MySQL OK packet',
                detail=(
                    f'cursor.rowcount was {updated_count!r}; MySQL reported no '
                    'determinable row count for this statement'
                ),
                counts=(
                    'rows CHANGED, not rows matched -- an UPDATE that matched '
                    'rows and altered none reports 0 unless the connection sets '
                    'CLIENT_FOUND_ROWS'
                ),
            ),
        }
    finally:
        # RELIABILITY: Properly close async MySQL connection
        conn.close()
        await conn.ensure_closed()


async def _update_sqlite(
    table: str,
    data: Dict[str, Any],
    where: Dict[str, Any],
    params: Dict[str, Any]
) -> Dict[str, Any]:
    """Update SQLite"""
    import sqlite3
    import asyncio

    database = params.get('database') or os.getenv('SQLITE_DATABASE', ':memory:')

    def _run_update():
        conn = sqlite3.connect(database)
        try:
            cursor = conn.cursor()

            set_parts = [f"{col} = ?" for col in data.keys()]
            where_parts = [f"{col} = ?" for col in where.keys()]

            query = f"UPDATE {table} SET {', '.join(set_parts)} WHERE {' AND '.join(where_parts)}"

            values = list(data.values()) + list(where.values())

            cursor.execute(query, values)
            updated_count = cursor.rowcount
            conn.commit()

            return updated_count
        finally:
            conn.close()

    updated_count = await asyncio.to_thread(_run_update)

    counted = isinstance(updated_count, int) and updated_count >= 0

    logger.info(f"Updated {updated_count} rows in {table}")

    return {
        'ok': True,
        'updated_count': updated_count,
        'outcome': _update_outcome(
            backend='sqlite',
            counted=counted,
            updated_count=updated_count,
            measured_by='cursor.rowcount from sqlite3_changes()',
            detail=(
                f'cursor.rowcount was {updated_count!r}; sqlite reports no row '
                'count for statements that are not DML'
            ),
            counts='rows matched by the WHERE clause',
        ),
    }
