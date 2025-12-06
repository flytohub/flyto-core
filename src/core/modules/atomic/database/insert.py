"""
Database Insert Module
Insert data into database tables
"""
import logging
import os
from typing import Any, Dict, List, Optional

from ...registry import register_module


logger = logging.getLogger(__name__)


SUPPORTED_DATABASES = ['postgresql', 'mysql', 'sqlite']


@register_module(
    module_id='database.insert',
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
            'label_key': 'modules.database.insert.params.table.label',
            'description': 'Name of the table to insert into',
            'description_key': 'modules.database.insert.params.table.description',
            'required': True
        },
        'data': {
            'type': 'object',
            'label': 'Data',
            'label_key': 'modules.database.insert.params.data.label',
            'description': 'Data to insert (object for single row, array for multiple)',
            'description_key': 'modules.database.insert.params.data.description',
            'required': True
        },
        'database_type': {
            'type': 'string',
            'label': 'Database Type',
            'label_key': 'modules.database.insert.params.database_type.label',
            'description': 'Type of database',
            'description_key': 'modules.database.insert.params.database_type.description',
            'required': False,
            'enum': ['postgresql', 'mysql', 'sqlite'],
            'default': 'postgresql'
        },
        'connection_string': {
            'type': 'string',
            'label': 'Connection String',
            'label_key': 'modules.database.insert.params.connection_string.label',
            'description': 'Database connection string',
            'description_key': 'modules.database.insert.params.connection_string.description',
            'required': False,
            'secret': True
        },
        'host': {
            'type': 'string',
            'label': 'Host',
            'label_key': 'modules.database.insert.params.host.label',
            'description': 'Database host',
            'description_key': 'modules.database.insert.params.host.description',
            'required': False
        },
        'port': {
            'type': 'number',
            'label': 'Port',
            'label_key': 'modules.database.insert.params.port.label',
            'description': 'Database port',
            'description_key': 'modules.database.insert.params.port.description',
            'required': False
        },
        'database': {
            'type': 'string',
            'label': 'Database Name',
            'label_key': 'modules.database.insert.params.database.label',
            'description': 'Database name',
            'description_key': 'modules.database.insert.params.database.description',
            'required': False
        },
        'user': {
            'type': 'string',
            'label': 'Username',
            'label_key': 'modules.database.insert.params.user.label',
            'description': 'Database username',
            'description_key': 'modules.database.insert.params.user.description',
            'required': False
        },
        'password': {
            'type': 'string',
            'label': 'Password',
            'label_key': 'modules.database.insert.params.password.label',
            'description': 'Database password',
            'description_key': 'modules.database.insert.params.password.description',
            'required': False,
            'secret': True
        },
        'returning': {
            'type': 'array',
            'label': 'Returning Columns',
            'label_key': 'modules.database.insert.params.returning.label',
            'description': 'Columns to return after insert (PostgreSQL)',
            'description_key': 'modules.database.insert.params.returning.description',
            'required': False
        }
    },
    output_schema={
        'inserted_count': {
            'type': 'number',
            'description': 'Number of rows inserted'
        },
        'returning_data': {
            'type': 'array',
            'description': 'Returned data from insert'
        }
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

    rows = [data] if isinstance(data, dict) else data
    if not rows:
        raise ValueError("No data to insert")

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
        conn.close()


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
