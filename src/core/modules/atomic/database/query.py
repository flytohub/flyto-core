"""
Database Query Module
Execute SQL queries on databases (PostgreSQL, MySQL, SQLite)
"""
import logging
import os
from typing import Any, Dict, List, Optional

from ...registry import register_module
from ...schema import compose, presets


logger = logging.getLogger(__name__)


# Supported database types
SUPPORTED_DATABASES = ['postgresql', 'mysql', 'sqlite', 'mssql']


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
    can_connect_to=['data.*', 'array.*'],
    can_receive_from=['data.*', 'api.*', 'http.*', 'flow.*', 'start'],

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
                'description_key': 'modules.database.query.output.columns.description'}
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
    author='Flyto Team',
    license='MIT'
)
async def database_query(context: Dict[str, Any]) -> Dict[str, Any]:
    """Execute SQL query on database"""
    params = context['params']

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
            return {
                'ok': True,
                'rows': [],
                'row_count': int(result.split()[-1]) if 'UPDATE' in result or 'DELETE' in result or 'INSERT' in result else 0,
                'columns': []
            }
        elif fetch_mode == 'one':
            row = await conn.fetchrow(query, *query_params)
            rows = [dict(row)] if row else []
            columns = list(row.keys()) if row else []
            return {
                'ok': True,
                'rows': rows,
                'row_count': len(rows),
                'columns': columns
            }
        else:  # all
            records = await conn.fetch(query, *query_params)
            rows = [dict(r) for r in records]
            columns = list(records[0].keys()) if records else []
            return {
                'ok': True,
                'rows': rows,
                'row_count': len(rows),
                'columns': columns
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
                return {
                    'ok': True,
                    'rows': [],
                    'row_count': cursor.rowcount,
                    'columns': []
                }
            elif fetch_mode == 'one':
                row = await cursor.fetchone()
                rows = [row] if row else []
                columns = list(row.keys()) if row else []
                return {
                    'ok': True,
                    'rows': rows,
                    'row_count': len(rows),
                    'columns': columns
                }
            else:  # all
                rows = await cursor.fetchall()
                columns = [desc[0] for desc in cursor.description] if cursor.description else []
                return {
                    'ok': True,
                    'rows': list(rows),
                    'row_count': len(rows),
                    'columns': columns
                }
    finally:
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
                return {
                    'ok': True,
                    'rows': [],
                    'row_count': cursor.rowcount,
                    'columns': []
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
                    'columns': list(columns)
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
                    'columns': list(columns)
                }
        finally:
            conn.close()

    return await asyncio.to_thread(_run_query)
