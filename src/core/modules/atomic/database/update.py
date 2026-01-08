"""
Database Update Module
Update data in database tables
"""
import logging
import os
from typing import Any, Dict, List, Optional

from ...registry import register_module
from ...schema import compose, presets
from ....utils import validate_sql_identifier, validate_sql_identifiers, SQLInjectionError


logger = logging.getLogger(__name__)


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
            'description': 'Number of rows updated'
        ,
                'description_key': 'modules.database.update.output.updated_count.description'}
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
        updated_count = int(result.split()[-1])

        logger.info(f"Updated {updated_count} rows in {table}")

        return {
            'ok': True,
            'updated_count': updated_count
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

        logger.info(f"Updated {updated_count} rows in {table}")

        return {
            'ok': True,
            'updated_count': updated_count
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

    logger.info(f"Updated {updated_count} rows in {table}")

    return {
        'ok': True,
        'updated_count': updated_count
    }
