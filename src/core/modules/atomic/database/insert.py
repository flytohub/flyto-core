"""
Database Insert Module
Insert data into database tables
"""
import logging
import os
from typing import Any, Dict, List, Optional

from ...registry import register_module
from ...schema import compose, presets
from ....utils import validate_sql_identifier, validate_sql_identifiers, SQLInjectionError


logger = logging.getLogger(__name__)


SUPPORTED_DATABASES = ['postgresql', 'mysql', 'sqlite']


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
    can_connect_to=['data.*'],
    can_receive_from=['data.*', 'api.*', 'http.*', 'flow.*', 'start'],

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
            'description': 'Number of rows inserted'
        ,
                'description_key': 'modules.database.insert.output.inserted_count.description'},
        'returning_data': {
            'type': 'array',
            'description': 'Returned data from insert'
        ,
                'description_key': 'modules.database.insert.output.returning_data.description'}
    },
    examples=[
        {
            'title': 'Insert single row',
            'title_key': 'modules.database.insert.examples.single.title',
            'params': {
                'table': 'users',
                'data': {'name': 'John', 'email': 'john@example.com'},
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
        for row in rows:
            values = [row[col] for col in columns]
            if returning:
                result = await conn.fetchrow(query, *values)
                returning_data.append(dict(result))
            else:
                await conn.execute(query, *values)

        logger.info(f"Inserted {len(rows)} rows into {table}")

        return {
            'ok': True,
            'inserted_count': len(rows),
            'returning_data': returning_data
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

        async with conn.cursor() as cursor:
            for row in rows:
                values = [row[col] for col in columns]
                await cursor.execute(query, values)
            await conn.commit()

        logger.info(f"Inserted {len(rows)} rows into {table}")

        return {
            'ok': True,
            'inserted_count': len(rows),
            'returning_data': []
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

            for row in rows:
                values = [row[col] for col in columns]
                cursor.execute(query, values)

            conn.commit()
            return len(rows)
        finally:
            conn.close()

    count = await asyncio.to_thread(_run_insert)

    logger.info(f"Inserted {count} rows into {table}")

    return {
        'ok': True,
        'inserted_count': count,
        'returning_data': []
    }
