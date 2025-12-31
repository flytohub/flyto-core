"""
MySQL Database Module
Execute SQL queries on MySQL database.
"""
import os

from ....registry import register_module
from ....schema import compose, presets


@register_module(
    module_id='db.mysql.query',
    version='1.0.0',
    category='database',
    tags=['database', 'mysql', 'sql', 'query', 'db'],
    label='MySQL Query',
    label_key='modules.db.mysql.query.label',
    description='Execute a SQL query on MySQL database and return results',
    description_key='modules.db.mysql.query.description',
    icon='Database',
    color='#00758F',

    # Connection types
    input_types=['json', 'object'],
    output_types=['json', 'array'],
    can_receive_from=['data.*', 'api.*'],
    can_connect_to=['data.*', 'notification.*'],

    # Phase 2: Execution settings
    timeout=60,  # Database queries can take time
    retryable=True,  # Network errors can be retried for read queries
    max_retries=3,
    concurrent_safe=True,  # Multiple queries can run in parallel

    # Phase 2: Security settings
    requires_credentials=True,  # Needs database credentials
    handles_sensitive_data=True,  # Database data is typically sensitive
    required_permissions=['network.access', 'database.read'],

    params_schema=compose(
        presets.DB_HOST(),
        presets.DB_PORT(default=3306),
        presets.DB_USER(),
        presets.DB_PASSWORD(),
        presets.DB_NAME(),
        presets.SQL_QUERY(placeholder='SELECT * FROM users WHERE active = 1'),
        presets.QUERY_PARAMS(),
    ),
    output_schema={
        'rows': {
            'type': 'array',
            'description': 'Array of result rows as objects'
        },
        'row_count': {
            'type': 'number',
            'description': 'Number of rows returned'
        },
        'columns': {
            'type': 'array',
            'description': 'Column names in result set'
        }
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
                'columns': columns
            }
    finally:
        conn.close()
