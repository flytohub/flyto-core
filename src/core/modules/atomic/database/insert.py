# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Database Insert Module
Insert data into database tables

HOW FAR THIS MODULE FOLLOWS REALITY

`inserted_count` was `len(rows)` on all four payload-returning paths -- the
length of the caller's own list. That number is identical whether the server
stored every row, some of them, or none: it is arithmetic on the input, exactly
the shape `file.write`'s `bytes_written` had before an `os.stat` read-back was
added. Nothing here read it back either, so the honest ceiling was ACCEPTED and
the field's own schema description ("Number of rows inserted") was a claim the
code could not support.

Every backend was already being handed a real count and throwing it away:

  postgresql, no RETURNING          asyncpg returns the server's command tag
      from `conn.execute` -- 'INSERT 0 1' -- and the return value was discarded.
      Parsed per row and totalled, that is a number the server sent.

  postgresql, with RETURNING        `conn.fetchrow` gives back the row the
      server actually stored. Rows returned is the strongest evidence available
      here: the driver materialised them from the server's response.

  mysql / sqlite                    `cursor.rowcount` after each execute is
      affected_rows off the MySQL OK packet and sqlite3_changes() respectively.

So the rung is now decided per return from whether a count was reported, and by
whether that count agrees with the number of rows offered:

    total reported == rows offered      OBSERVED      (claim_by inferred)
    total reported != rows offered      INDETERMINATE (claim_by inferred)
    no count reported for some row      ACCEPTED

INDETERMINATE rather than FAILED for the mismatch, for the reason `file.write`
gives: nobody declared a row-count contract, the equality is this module's own
inference, and there are ordinary correct inserts it is false for -- a BEFORE
INSERT trigger returning NULL suppresses the row and reports zero, and the
insert is still behaving as the schema author intended. A caller's broken
contract is FAILED; an inference of ours that may be wrong is INDETERMINATE.

`inserted_count` is left alone for compatibility and its description now says
what it is. `observed_count` is the new field that carries the measurement.

VERIFIED is unreachable and no postcondition is declared: nothing here evaluates
a predicate against the stored rows. `ceiling_for(None)` caps this at OBSERVED,
which is where it belongs.
"""
import logging
import os
from typing import Any, Dict, List, Optional

from ....engine.outcome import ClaimBy, Outcome, envelope
from ...registry import register_module
from ...schema import compose, presets
from ....utils import validate_sql_identifier, validate_sql_identifiers, SQLInjectionError


logger = logging.getLogger(__name__)


SUPPORTED_DATABASES = ['postgresql', 'mysql', 'sqlite']


def _postgres_tag_count(tag: Any) -> Optional[int]:
    """Rows the server said it inserted, or ``None`` when the tag carries none.

    An asyncpg INSERT command tag is ``'INSERT <oid> <count>'`` -- three tokens,
    the last a decimal. The check is on the tag rather than on the SQL, so no
    query text can fake a count, and it is stricter than the substring test in
    `query.py` because this module only ever issues INSERT and can afford to
    demand the exact shape. Anything else means no number crossed the wire.
    """
    parts = str(tag).split()
    if len(parts) != 3 or parts[0].upper() != 'INSERT' or not parts[2].isdigit():
        return None
    return int(parts[2])


def _total_reported(counts: List[Optional[int]]) -> Optional[int]:
    """The sum of per-statement counts, or ``None`` if any one was not reported.

    Partial totals are refused deliberately. Summing the rows we did get a
    number for and presenting it as the total would put a smaller-than-offered
    integer next to a rung, and the reader could not tell a genuine short insert
    from a backend that stayed silent about one statement. `None` says "not
    measured", which is a different fact and the true one.
    """
    if any(count is None or count < 0 for count in counts):
        return None
    return sum(counts)


def _insert_outcome(
    *,
    backend: str,
    offered: int,
    observed: Optional[int],
    measured_by: str,
    detail: str,
) -> Dict[str, Any]:
    """The rung this insert earned, and the measurements that earned it.

    `offered` is always carried, and always labelled as the input it is, so a
    consumer can see the number that used to be reported as `inserted_count` and
    see beside it that no syscall and no server contributed to it.
    """
    offered_effect = {
        'kind': 'rows_offered',
        'backend': backend,
        'count': offered,
        'measured_by': 'len(rows) -- the list this module was handed',
        'detail': (
            'How many rows were OFFERED to the backend. Arithmetic on the '
            'caller\'s own input: it reads identically whether the server '
            'stored every row, some of them, or none.'
        ),
    }

    if observed is None:
        return envelope(
            Outcome.ACCEPTED,
            claim_by=ClaimBy.NONE,
            effects=[
                offered_effect,
                {
                    'kind': 'rows_not_counted',
                    'backend': backend,
                    'count_reported': False,
                    'measured_by': None,
                    'detail': detail,
                },
            ],
        )

    observed_effect = {
        'kind': 'rows_reported_inserted',
        'backend': backend,
        'count': observed,
        'measured_by': measured_by,
    }

    if observed == offered:
        return envelope(
            Outcome.OBSERVED,
            # INFERRED: a predicate was evaluated and it was ours. No caller
            # asked that the totals match; recording who did keeps the matching
            # and the mismatching case attributable to the same author.
            claim_by=ClaimBy.INFERRED,
            effects=[offered_effect, observed_effect],
        )

    return envelope(
        Outcome.INDETERMINATE,
        claim_by=ClaimBy.INFERRED,
        effects=[
            offered_effect,
            observed_effect,
            {
                'kind': 'row_count_disagrees',
                'backend': backend,
                'predicate': 'sum(rows reported by the backend) == len(rows offered)',
                'expected_count': offered,
                'actual_count': observed,
                'detail': (
                    'The backend did not report one stored row per row offered. '
                    'That may be a partial insert, or it may be this module\'s '
                    'inference being wrong -- a BEFORE INSERT trigger returning '
                    'NULL suppresses a row and reports zero for it, with nothing '
                    'broken. We cannot say which, so this is indeterminate '
                    'rather than failed.'
                ),
            },
        ],
    )


@register_module(
    module_id='database.insert',
    stability="beta",
    version='1.0.0',
    category='database',
    subcategory='write',
    tags=['database', 'sql', 'insert', 'postgresql', 'mysql', 'sqlite'],
    label='Database Insert',
    label_key='modules.database.insert.label',
    description='Insert data into database tables',
    description_key='modules.database.insert.description',
    icon='Database',
    color='#43A047',

    input_types=['object', 'array'],
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
        presets.DB_TYPE(),
        presets.DB_CONNECTION_STRING(),
        presets.DB_HOST(),
        presets.DB_PORT(),
        presets.DB_NAME(),
        presets.DB_USER(),
        presets.DB_PASSWORD(),
        presets.RETURNING_COLUMNS(),
    ),
    output_schema={
        'inserted_count': {
            'type': 'number',
            'description': (
                'Number of rows OFFERED to the backend: the length of the data '
                'parameter. Not a measurement of what was stored -- it reads the '
                'same whether every row landed or none did. See observed_count'
            )
        ,
                'description_key': 'modules.database.insert.output.inserted_count.description'},
        'observed_count': {
            'type': 'number',
            'description': (
                'Rows the backend reported storing, totalled across the '
                'statements: parsed from the postgres command tag, counted from '
                'the rows RETURNING sent back, or read from cursor.rowcount. '
                'null when the backend reported no count for some statement'
            )
        ,
                'description_key': 'modules.database.insert.output.observed_count.description'},
        'returning_data': {
            'type': 'array',
            'description': 'Returned data from insert'
        ,
                'description_key': 'modules.database.insert.output.returning_data.description'},
        'outcome': {
            'type': 'object',
            'description': (
                'How far this insert was followed into reality: observed when '
                'the backend reported one stored row per row offered, accepted '
                'when it reported no count, indeterminate when the totals '
                'disagreed. Never higher than observed -- nothing here evaluates '
                'a postcondition'
            )
        ,
                'description_key': 'modules.database.insert.output.outcome.description'}
    },
    examples=[
        {
            'title': 'Insert single row',
            'title_key': 'modules.database.insert.examples.single.title',
            'params': {
                'table': 'users',
                'data': {'name': 'John', 'email': 'dev@flyto2.com'},
                'database_type': 'postgresql'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def database_insert(context: Dict[str, Any]) -> Dict[str, Any]:
    """Insert data into database"""
    params = context['params']

    # SECURITY: reject client-supplied connection targets (connection_string OR
    # host/port/credentials) unless FLYTO_ALLOW_CLIENT_DB_DSN is set; refuse
    # SSRF-sensitive hosts when allowed. See database/_dsn_guard.py.
    from ._dsn_guard import guard_client_dsn
    guard_client_dsn(params)

    table = params['table']
    data = params['data']
    db_type = params.get('database_type', 'postgresql')
    connection_string = params.get('connection_string') or os.getenv('DATABASE_URL')
    returning = params.get('returning', [])

    # SECURITY: Validate table name to prevent SQL injection
    try:
        table = validate_sql_identifier(table, 'table')
    except SQLInjectionError as e:
        return {
            'ok': False,
            'error': str(e),
            'error_code': 'SQL_INJECTION'
        }

    rows = [data] if isinstance(data, dict) else data
    if not rows:
        raise ValueError("No data to insert")

    # SECURITY: Validate column names
    try:
        columns = list(rows[0].keys())
        validate_sql_identifiers(columns, 'column')
        if returning:
            validate_sql_identifiers(returning, 'returning column')
    except SQLInjectionError as e:
        return {
            'ok': False,
            'error': str(e),
            'error_code': 'SQL_INJECTION'
        }

    if db_type == 'postgresql':
        return await _insert_postgresql(table, rows, connection_string, params, returning)
    elif db_type == 'mysql':
        return await _insert_mysql(table, rows, connection_string, params)
    elif db_type == 'sqlite':
        return await _insert_sqlite(table, rows, params)
    else:
        raise ValueError(f"Unsupported database type: {db_type}")


async def _insert_postgresql(
    table: str,
    rows: List[Dict],
    connection_string: Optional[str],
    params: Dict[str, Any],
    returning: List[str]
) -> Dict[str, Any]:
    """Insert into PostgreSQL"""
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
        columns = list(rows[0].keys())
        placeholders = ', '.join(f'${i+1}' for i in range(len(columns)))
        columns_str = ', '.join(columns)

        query = f"INSERT INTO {table} ({columns_str}) VALUES ({placeholders})"
        if returning:
            query += f" RETURNING {', '.join(returning)}"

        returning_data = []
        tag_counts: List[Optional[int]] = []
        for row in rows:
            values = [row[col] for col in columns]
            if returning:
                result = await conn.fetchrow(query, *values)
                # `fetchrow` gives None when the statement stored no row, which
                # a BEFORE INSERT trigger returning NULL does. `dict(None)`
                # raised TypeError there; skipping instead lets the row simply
                # be absent from the count, which is the fact, and the totals
                # then disagree and the rung says INDETERMINATE.
                if result is not None:
                    returning_data.append(dict(result))
            else:
                # The command tag asyncpg returns here was discarded. It is the
                # server's own count, and it is the only measurement available
                # on this path.
                tag_counts.append(_postgres_tag_count(await conn.execute(query, *values)))

        if returning:
            observed = len(returning_data)
            measured_by = 'len() over the rows the server returned from INSERT ... RETURNING'
            detail = ''
        else:
            observed = _total_reported(tag_counts)
            measured_by = 'row counts parsed from the postgres INSERT command tags'
            detail = (
                'At least one postgres command tag was not of the form '
                "'INSERT <oid> <count>', so no row count crossed the wire for it."
            )

        logger.info(f"Offered {len(rows)} rows to {table}")

        return {
            'ok': True,
            'inserted_count': len(rows),
            'observed_count': observed,
            'returning_data': returning_data,
            'outcome': _insert_outcome(
                backend='postgresql',
                offered=len(rows),
                observed=observed,
                measured_by=measured_by,
                detail=detail,
            ),
        }
    finally:
        await conn.close()


async def _insert_mysql(
    table: str,
    rows: List[Dict],
    connection_string: Optional[str],
    params: Dict[str, Any]
) -> Dict[str, Any]:
    """Insert into MySQL"""
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
        columns = list(rows[0].keys())
        placeholders = ', '.join(['%s'] * len(columns))
        columns_str = ', '.join(columns)

        query = f"INSERT INTO {table} ({columns_str}) VALUES ({placeholders})"

        row_counts: List[Optional[int]] = []
        async with conn.cursor() as cursor:
            for row in rows:
                values = [row[col] for col in columns]
                await cursor.execute(query, values)
                # affected_rows off the MySQL OK packet. PEP 249 allows -1 for
                # "cannot determine", and `_total_reported` treats a negative as
                # not reported rather than subtracting it from the total.
                row_counts.append(cursor.rowcount)
            await conn.commit()

        observed = _total_reported(row_counts)

        logger.info(f"Offered {len(rows)} rows to {table}")

        return {
            'ok': True,
            'inserted_count': len(rows),
            'observed_count': observed,
            'returning_data': [],
            'outcome': _insert_outcome(
                backend='mysql',
                offered=len(rows),
                observed=observed,
                measured_by='cursor.rowcount from the MySQL OK packet, per statement',
                detail=(
                    f'cursor.rowcount was {row_counts!r}; MySQL reported no '
                    'determinable row count for at least one statement'
                ),
            ),
        }
    finally:
        # RELIABILITY: Properly close async MySQL connection
        conn.close()
        await conn.ensure_closed()


async def _insert_sqlite(
    table: str,
    rows: List[Dict],
    params: Dict[str, Any]
) -> Dict[str, Any]:
    """Insert into SQLite"""
    import sqlite3
    import asyncio

    database = params.get('database') or os.getenv('SQLITE_DATABASE', ':memory:')

    def _run_insert():
        conn = sqlite3.connect(database)
        try:
            cursor = conn.cursor()
            columns = list(rows[0].keys())
            placeholders = ', '.join(['?'] * len(columns))
            columns_str = ', '.join(columns)

            query = f"INSERT INTO {table} ({columns_str}) VALUES ({placeholders})"

            row_counts: List[Optional[int]] = []
            for row in rows:
                values = [row[col] for col in columns]
                cursor.execute(query, values)
                # sqlite3 sets rowcount from sqlite3_changes(); for INSERT it is
                # the number of rows the statement stored, and -1 only where the
                # engine reports no count at all.
                row_counts.append(cursor.rowcount)

            conn.commit()
            return _total_reported(row_counts)
        finally:
            conn.close()

    observed = await asyncio.to_thread(_run_insert)

    logger.info(f"Offered {len(rows)} rows to {table}")

    return {
        'ok': True,
        'inserted_count': len(rows),
        'observed_count': observed,
        'returning_data': [],
        'outcome': _insert_outcome(
            backend='sqlite',
            offered=len(rows),
            observed=observed,
            measured_by='cursor.rowcount from sqlite3_changes(), per statement',
            detail=(
                'sqlite reported no row count for at least one statement '
                '(cursor.rowcount was negative)'
            ),
        ),
    }
