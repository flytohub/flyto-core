# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Database Query Module
Execute SQL queries on databases (PostgreSQL, MySQL, SQLite)

HOW FAR THIS MODULE FOLLOWS REALITY

There is no single rung for `database.query`, and pretending otherwise is the
whole trap. Nine payload-returning paths across three implemented backends
measure three different things, and one of them measures nothing at all:

  fetch='all' / fetch='one', rows came back           OBSERVED
      `row_count` is `len(rows)` over row objects the driver materialised from
      bytes the server sent. Nothing is inferred. It counts rows RETURNED,
      never rows AFFECTED -- an UPDATE run with fetch='all' reports 0 because
      no result set came back, not because it matched nothing. The effect is
      named `rows_returned` so that distinction survives the integer.

  fetch='all' / fetch='one', no rows came back        ACCEPTED
      `len(rows) == 0` reads identically whether the statement matched nothing,
      changed five rows and returned no result set, or was discarded entirely.
      A value that would be unchanged if the effect had not happened is not
      evidence of the effect, so an empty read claims only that the server
      answered. This path used to claim OBSERVED unconditionally; it was found
      by running a real INSERT through fetch='all' -- the DEFAULT mode -- and
      watching the row get silently rolled back, because `conn.commit()` only
      existed in the fetch='none' branch. The module lost the data and claimed
      to have observed it. Both halves are fixed: the rung here, and the commit
      on every close path below.

  fetch='none', count reported by the backend         OBSERVED
      postgres parses the server's command tag; mysql and sqlite read
      `cursor.rowcount`. In each case a real number crossed the wire.

  fetch='none', no count reported by the backend      ACCEPTED
      A postgres `CREATE TABLE` / `ALTER TABLE` / `MERGE n` tag does not match
      the substring test below, so `row_count` becomes a literal `0` written in
      this file. sqlite returns -1 for every non-DML statement (verified:
      CREATE TABLE, ALTER TABLE, CREATE INDEX, PRAGMA all give -1). Neither is
      an observation. The statement was taken and answered without raising,
      which is exactly ACCEPTED and no more.

A `row_count` of 0 meaning "no rows matched" and a `row_count` of 0 meaning
"this backend reports no count for this statement" are different facts. The
rung is decided at runtime, per return, from whether a number was actually
reported -- never from a per-module constant, which would have to be wrong
about at least one of these paths.

VERIFIED is unreachable here, and not by oversight. It is defined as "a
postcondition was evaluated and it held"; `ceiling_for(None)` therefore caps an
undeclared module at OBSERVED. `register_module` now accepts a `postcondition=`
kwarg, so one COULD be declared -- and this module declares none, because none
of these nine paths evaluates a predicate. The plumbing is not what is holding
this module down; the absence of a read-back is, and adding the declaration
without the read-back would only move the lie one level up.
"""
import logging
import os
from typing import Any, Dict, List, Optional

from ....engine.outcome import ClaimBy, Outcome, envelope
from ...registry import register_module
from ...schema import compose, presets


logger = logging.getLogger(__name__)


# Supported database types.
#
# WARNING: this constant is dead -- nothing in src/ or tests/ reads it -- and it
# lies. 'mssql' has no branch in the dispatch below (it falls through to
# `raise ValueError`), and no 'mssql' option in the `DB_TYPE()` select the UI
# renders. `database.insert` lists the three that exist. Do not build a
# per-backend table from this list without checking each entry against the
# dispatch; it advertises a backend that does not exist.
SUPPORTED_DATABASES = ['postgresql', 'mysql', 'sqlite', 'mssql']


def _returned_rows(backend: str, fetch_mode: str, row_count: int) -> Dict[str, Any]:
    """The envelope for `fetch='all'` and `fetch='one'`.

    Two rungs, decided by whether anything actually came back. OBSERVED is
    earned by one line: `row_count` is `len()` over rows the driver built from
    the server's response. There is no branch in which that number is invented.
    An empty result set earns ACCEPTED instead, for the reason below.

    What it is a count OF is the part worth carrying: rows returned. Under
    fetch='one' it is additionally capped at 1 by `rows = [row] if row else []`,
    so it answers "did at least one row come back", not "how many matched".
    `fetch` rides in the effect so a consumer can tell which question was asked.
    """
    # A returned row is an observation of that row. NO returned rows is not an
    # observation of anything: `len(rows) == 0` reads identically whether a
    # statement matched nothing, changed five rows and returned no result set,
    # or was discarded entirely. That is the same shape as `file.write`'s
    # `bytes_written` -- a value that would be unchanged if the effect had not
    # happened -- and claiming OBSERVED on it is the exact failure this contract
    # exists to stop, on the module that runs every write in the product.
    #
    # An empty read is therefore ACCEPTED: the server answered, and nothing in
    # the answer says what happened to the data.
    if row_count <= 0:
        return envelope(
            Outcome.ACCEPTED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'no_rows_returned',
                'backend': backend,
                'fetch': fetch_mode,
                'measured_by': None,
                'detail': (
                    'The server answered and returned no rows. That is not an '
                    'observation of the data: a statement that returns no '
                    'result set reads the same here whether it changed '
                    'everything or nothing.'
                ),
            }],
        )
    return envelope(
        Outcome.OBSERVED,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'rows_returned',
            'backend': backend,
            'fetch': fetch_mode,
            'count': row_count,
            'measured_by': 'len() over rows the driver returned from the server',
        }],
    )


def _write_outcome(
    *,
    backend: str,
    counted: bool,
    row_count: Any,
    measured_by: str,
    detail: str,
) -> Dict[str, Any]:
    """The envelope for `fetch='none'` -- the mode every write goes through.

    `counted` is the whole decision, and it is a runtime fact, not a property of
    the backend: the same postgres connection yields a parsed count for an
    UPDATE and an unparsed literal 0 for the CREATE TABLE that preceded it.

        counted=True    a number crossed the wire            -> OBSERVED
        counted=False   no number was reported for this one  -> ACCEPTED

    ACCEPTED rather than OBSERVED for the second because no line measured
    anything about rows. What is known is that the server took the statement and
    answered without raising -- "the other side acknowledged taking it". Putting
    a fabricated `row_count` beside a rung that claims we watched the world
    change is precisely the false green this contract exists to stop.

    Note on the OBSERVED case: `count: 0` means the statement affected no rows.
    It does not mean the statement had no effect. DDL affects zero rows by
    definition and still changes the schema, which is why `kind` says
    `rows_affected` and not `statement_effect`.
    """
    if counted:
        return envelope(
            Outcome.OBSERVED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'rows_affected',
                'backend': backend,
                'count': row_count,
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
            'detail': detail,
        }],
    )


@register_module(
    module_id='database.query',
    stability="beta",
    version='1.0.0',
    category='database',
    subcategory='query',
    tags=['database', 'sql', 'query', 'postgresql', 'mysql', 'sqlite'],
    label='Database Query',
    label_key='modules.database.query.label',
    description='Execute SQL queries on PostgreSQL, MySQL, or SQLite databases',
    description_key='modules.database.query.description',
    icon='Database',
    color='#336791',

    # Connection types
    input_types=['text', 'object'],
    output_types=['array', 'object'],
    can_connect_to=['database.*', 'data.*', 'array.*', 'object.*', 'file.*', 'http.*', 'notify.*', 'flow.*'],
    can_receive_from=['*'],

    # Execution settings
    timeout_ms=120000,
    retryable=True,
    max_retries=2,
    concurrent_safe=False,  # Database connections may not be thread-safe

    # Security settings
    requires_credentials=True,
    credential_keys=['API_KEY'],
    handles_sensitive_data=True,
    required_permissions=['filesystem.read', 'filesystem.write'],

    params_schema=compose(
        presets.SQL_QUERY(),
        presets.DB_QUERY_PARAMS(),
        presets.DB_TYPE(),
        presets.DB_CONNECTION_STRING(),
        presets.DB_HOST(),
        presets.DB_PORT(),
        presets.DB_NAME(),
        presets.DB_USER(),
        presets.DB_PASSWORD(),
        presets.FETCH_MODE(),
    ),
    output_schema={
        'rows': {
            'type': 'array',
            'description': 'Query result rows'
        ,
                'description_key': 'modules.database.query.output.rows.description'},
        'row_count': {
            'type': 'number',
            'description': 'Number of rows returned/affected'
        ,
                'description_key': 'modules.database.query.output.row_count.description'},
        'columns': {
            'type': 'array',
            'description': 'Column names'
        ,
                'description_key': 'modules.database.query.output.columns.description'},
        'outcome': {
            'type': 'object',
            'description': (
                'How far the effect was followed: rung, claim_by, postcondition, '
                'effects, evidence_ref. Decided per return, not per module: '
                '"observed" when a row count crossed the wire, "accepted" when '
                'the backend reported none for this statement. Never higher '
                'than "observed" -- nothing here evaluates a postcondition.'
            ),
            'description_key': 'modules.database.query.output.outcome.description'}
    },
    examples=[
        {
            'title': 'Select with parameters',
            'title_key': 'modules.database.query.examples.select.title',
            'params': {
                'query': 'SELECT * FROM users WHERE status = $1',
                'params': ['active'],
                'database_type': 'postgresql'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def database_query(context: Dict[str, Any]) -> Dict[str, Any]:
    """Execute SQL query on database"""
    params = context['params']

    # SECURITY: reject client-supplied connection targets (connection_string OR
    # host/port/credentials) unless FLYTO_ALLOW_CLIENT_DB_DSN is set, and when
    # allowed, refuse SSRF-sensitive hosts (RFC1918/loopback/metadata). Closes
    # both the connection_string vector AND the host/port bypass below.
    from ._dsn_guard import guard_client_dsn
    guard_client_dsn(params)

    query = params['query']
    query_params = params.get('params', [])
    db_type = params.get('database_type', 'postgresql')
    connection_string = params.get('connection_string') or os.getenv('DATABASE_URL')
    fetch_mode = params.get('fetch', 'all')

    # Validate query (basic security check)
    if not query.strip():
        raise ValueError("Query cannot be empty")

    # Execute based on database type
    if db_type == 'postgresql':
        return await _execute_postgresql(query, query_params, connection_string, params, fetch_mode)
    elif db_type == 'mysql':
        return await _execute_mysql(query, query_params, connection_string, params, fetch_mode)
    elif db_type == 'sqlite':
        return await _execute_sqlite(query, query_params, params, fetch_mode)
    else:
        raise ValueError(f"Unsupported database type: {db_type}")


async def _execute_postgresql(
    query: str,
    query_params: List[Any],
    connection_string: Optional[str],
    params: Dict[str, Any],
    fetch_mode: str
) -> Dict[str, Any]:
    """Execute PostgreSQL query"""
    try:
        import asyncpg
    except ImportError:
        raise ImportError("asyncpg is required for PostgreSQL. Install with: pip install asyncpg")

    # Build connection string if not provided
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

    # Execute query
    conn = await asyncpg.connect(connection_string)
    try:
        if fetch_mode == 'none':
            result = await conn.execute(query, *query_params)
            # asyncpg hands back the server's command tag: 'INSERT 0 3',
            # 'UPDATE 5', 'DELETE 2' carry a count in the last token -- but
            # 'CREATE TABLE', 'ALTER TABLE', 'TRUNCATE TABLE' and 'MERGE 4'
            # match none of these substrings, and for those the 0 below is a
            # literal written here, not a number the server sent. `counted`
            # carries that distinction into the envelope instead of losing it.
            # (The test is on the tag, not the SQL, so it cannot false-positive:
            # no non-DML postgres tag contains UPDATE/DELETE/INSERT.)
            counted = 'UPDATE' in result or 'DELETE' in result or 'INSERT' in result
            row_count = int(result.split()[-1]) if counted else 0
            return {
                'ok': True,
                'rows': [],
                'row_count': row_count,
                'columns': [],
                'outcome': _write_outcome(
                    backend='postgresql',
                    counted=counted,
                    row_count=row_count,
                    measured_by='row count parsed from the postgres command tag',
                    detail=f'postgres command tag {result!r} carries no row count',
                ),
            }
        elif fetch_mode == 'one':
            row = await conn.fetchrow(query, *query_params)
            rows = [dict(row)] if row else []
            columns = list(row.keys()) if row else []
            return {
                'ok': True,
                'rows': rows,
                'row_count': len(rows),
                'columns': columns,
                'outcome': _returned_rows('postgresql', 'one', len(rows)),
            }
        else:  # all
            records = await conn.fetch(query, *query_params)
            rows = [dict(r) for r in records]
            columns = list(records[0].keys()) if records else []
            return {
                'ok': True,
                'rows': rows,
                'row_count': len(rows),
                'columns': columns,
                'outcome': _returned_rows('postgresql', 'all', len(rows)),
            }
    finally:
        await conn.close()


async def _execute_mysql(
    query: str,
    query_params: List[Any],
    connection_string: Optional[str],
    params: Dict[str, Any],
    fetch_mode: str
) -> Dict[str, Any]:
    """Execute MySQL query"""
    try:
        import aiomysql
    except ImportError:
        raise ImportError("aiomysql is required for MySQL. Install with: pip install aiomysql")

    # Get connection params - NO hardcoded defaults
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

    # Execute query
    conn = await aiomysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        db=database
    )
    try:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(query, query_params)

            if fetch_mode == 'none':
                await conn.commit()
                row_count = cursor.rowcount
                # PEP 249 defines rowcount as the number of rows the statement
                # affected, or -1 when the driver cannot determine one. MySQL's
                # OK packet carries affected_rows for every statement, so a 0
                # here is the server's number rather than a fallback -- but only
                # a value >= 0 is a number at all, and the guard is on the value
                # because that is the only thing this code can actually check.
                #
                # Caveat kept out of the rung because it is a different question:
                # MySQL reports CHANGED rows for an UPDATE, not MATCHED rows,
                # unless the connection sets CLIENT_FOUND_ROWS. An UPDATE that
                # matched five rows and altered none reports 0, truthfully.
                counted = isinstance(row_count, int) and row_count >= 0
                return {
                    'ok': True,
                    'rows': [],
                    'row_count': row_count,
                    'columns': [],
                    'outcome': _write_outcome(
                        backend='mysql',
                        counted=counted,
                        row_count=row_count,
                        measured_by='cursor.rowcount from the MySQL OK packet',
                        detail=(
                            f'cursor.rowcount was {row_count!r}; MySQL reported '
                            'no determinable row count for this statement'
                        ),
                    ),
                }
            elif fetch_mode == 'one':
                row = await cursor.fetchone()
                rows = [row] if row else []
                columns = list(row.keys()) if row else []
                return {
                    'ok': True,
                    'rows': rows,
                    'row_count': len(rows),
                    'columns': columns,
                    'outcome': _returned_rows('mysql', 'one', len(rows)),
                }
            else:  # all
                rows = await cursor.fetchall()
                columns = [desc[0] for desc in cursor.description] if cursor.description else []
                return {
                    'ok': True,
                    'rows': list(rows),
                    'row_count': len(rows),
                    'columns': columns,
                    'outcome': _returned_rows('mysql', 'all', len(rows)),
                }
    finally:
        # Commit before closing, on every path -- see the sqlite branch for the
        # measured data loss this closes. A commit after a pure read is a no-op.
        await conn.commit()
        # RELIABILITY: Properly close async MySQL connection
        conn.close()
        await conn.ensure_closed()


async def _execute_sqlite(
    query: str,
    query_params: List[Any],
    params: Dict[str, Any],
    fetch_mode: str
) -> Dict[str, Any]:
    """Execute SQLite query"""
    import sqlite3
    import asyncio

    database = params.get('database') or os.getenv('SQLITE_DATABASE', ':memory:')

    def _run_query():
        conn = sqlite3.connect(database)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            cursor.execute(query, query_params)

            if fetch_mode == 'none':
                conn.commit()
                row_count = cursor.rowcount
                # sqlite3 sets rowcount from sqlite3_changes() for INSERT /
                # UPDATE / DELETE and leaves it at -1 for everything else.
                # Measured on this interpreter (CPython 3.12 / SQLite 3.53):
                # CREATE TABLE, ALTER TABLE, CREATE INDEX and PRAGMA all give
                # -1, while 'DELETE ... WHERE a = 99' matching nothing gives 0.
                # So -1 and 0 are genuinely different answers here, and unlike
                # postgres this backend never disguises the first as the second.
                counted = isinstance(row_count, int) and row_count >= 0
                return {
                    'ok': True,
                    'rows': [],
                    'row_count': row_count,
                    'columns': [],
                    'outcome': _write_outcome(
                        backend='sqlite',
                        counted=counted,
                        row_count=row_count,
                        measured_by='cursor.rowcount from sqlite3_changes()',
                        detail=(
                            f'cursor.rowcount was {row_count!r}; sqlite reports no '
                            'row count for non-DML statements'
                        ),
                    ),
                }
            elif fetch_mode == 'one':
                row = cursor.fetchone()
                if row:
                    columns = row.keys()
                    rows = [dict(row)]
                else:
                    columns = []
                    rows = []
                return {
                    'ok': True,
                    'rows': rows,
                    'row_count': len(rows),
                    'columns': list(columns),
                    'outcome': _returned_rows('sqlite', 'one', len(rows)),
                }
            else:  # all
                rows_raw = cursor.fetchall()
                if rows_raw:
                    columns = rows_raw[0].keys()
                    rows = [dict(r) for r in rows_raw]
                else:
                    columns = []
                    rows = []
                return {
                    'ok': True,
                    'rows': rows,
                    'row_count': len(rows),
                    'columns': list(columns),
                    'outcome': _returned_rows('sqlite', 'all', len(rows)),
                }
        finally:
            # Commit before closing, on every path.
            #
            # `conn.commit()` used to exist only in the fetch='none' branch, and
            # `fetch` defaults to 'all'. So an INSERT / UPDATE / DELETE run through
            # the default mode opened sqlite's implicit DML transaction, returned
            # ok=True, and was rolled back by this close. Measured on a real
            # file-backed db: `INSERT INTO t VALUES (42)` with fetch='all' reported
            # success and left the table empty.
            #
            # A commit after a pure read is a no-op, so this costs nothing and
            # closes a silent data loss. Found by giving this module an outcome
            # rung and then asking what the rung was measuring.
            conn.commit()
            conn.close()

    return await asyncio.to_thread(_run_query)
