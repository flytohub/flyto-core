"""
Database Update Module
Update data in database tables
"""
import logging
import os
from typing import Any, Dict, List, Optional

from ...registry import register_module


logger = logging.getLogger(__name__)


@register_module(
    module_id='database.update',
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

    timeout=60,
    retryable=True,
    max_retries=2,
    concurrent_safe=False,

    requires_credentials=True,
    handles_sensitive_data=True,
    required_permissions=['database.write'],

    params_schema={
        'table': {
            'type': 'string',
            'label': 'Table Name',
            'label_key': 'modules.database.update.params.table.label',
            'description': 'Name of the table to update',
            'description_key': 'modules.database.update.params.table.description',
            'required': True
        },
        'data': {
            'type': 'object',
            'label': 'Data',
            'label_key': 'modules.database.update.params.data.label',
            'description': 'Data to update (column: value pairs)',
            'description_key': 'modules.database.update.params.data.description',
            'required': True
        },
        'where': {
            'type': 'object',
            'label': 'Where Conditions',
            'label_key': 'modules.database.update.params.where.label',
            'description': 'WHERE conditions (column: value for equality)',
            'description_key': 'modules.database.update.params.where.description',
            'required': True
        },
        'database_type': {
            'type': 'string',
            'label': 'Database Type',
            'label_key': 'modules.database.update.params.database_type.label',
            'description': 'Type of database',
            'description_key': 'modules.database.update.params.database_type.description',
            'required': False,
            'enum': ['postgresql', 'mysql', 'sqlite'],
            'default': 'postgresql'
        },
        'connection_string': {
            'type': 'string',
            'label': 'Connection String',
            'label_key': 'modules.database.update.params.connection_string.label',
            'description': 'Database connection string',
            'description_key': 'modules.database.update.params.connection_string.description',
            'required': False,
            'secret': True
        },
        'host': {
            'type': 'string',
            'label': 'Host',
            'label_key': 'modules.database.update.params.host.label',
            'description': 'Database host',
            'description_key': 'modules.database.update.params.host.description',
            'required': False
        },
        'port': {
            'type': 'number',
            'label': 'Port',
            'label_key': 'modules.database.update.params.port.label',
            'description': 'Database port',
            'description_key': 'modules.database.update.params.port.description',
            'required': False
        },
        'database': {
            'type': 'string',
            'label': 'Database Name',
            'label_key': 'modules.database.update.params.database.label',
            'description': 'Database name',
            'description_key': 'modules.database.update.params.database.description',
            'required': False
        },
        'user': {
            'type': 'string',
            'label': 'Username',
            'label_key': 'modules.database.update.params.user.label',
            'description': 'Database username',
            'description_key': 'modules.database.update.params.user.description',
            'required': False
        },
        'password': {
            'type': 'string',
            'label': 'Password',
            'label_key': 'modules.database.update.params.password.label',
            'description': 'Database password',
            'description_key': 'modules.database.update.params.password.description',
            'required': False,
            'secret': True
        }
    },
    output_schema={
        'updated_count': {
            'type': 'number',
            'description': 'Number of rows updated'
        }
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

    if not data:
        raise ValueError("No data to update")
    if not where:
        raise ValueError("WHERE conditions required for safety")

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
        host = params.get('host') or os.getenv('POSTGRES_HOST', 'localhost')
        port = params.get('port') or int(os.getenv('POSTGRES_PORT', '5432'))
        database = params.get('database') or os.getenv('POSTGRES_DB')
        user = params.get('user') or os.getenv('POSTGRES_USER')
        password = params.get('password') or os.getenv('POSTGRES_PASSWORD')

        if not all([host, database, user]):
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

    host = params.get('host') or os.getenv('MYSQL_HOST', 'localhost')
    port = params.get('port') or int(os.getenv('MYSQL_PORT', '3306'))
    database = params.get('database') or os.getenv('MYSQL_DATABASE')
    user = params.get('user') or os.getenv('MYSQL_USER')
    password = params.get('password') or os.getenv('MYSQL_PASSWORD')

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
        conn.close()


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
