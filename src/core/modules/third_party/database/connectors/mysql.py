"""
MySQL Database Module
Execute SQL queries on MySQL database.
"""
import os

from ....registry import register_module


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

    params_schema={
        'host': {
            'type': 'string',
            'label': 'Host',
            'label_key': 'modules.db.mysql.query.params.host.label',
            'description': 'MySQL server host (from env.MYSQL_HOST or explicit)',
            'description_key': 'modules.db.mysql.query.params.host.description',
            'placeholder': '${env.MYSQL_HOST}',
            'required': False
            # NOTE: NO hardcoded default - require explicit configuration
        },
        'port': {
            'type': 'number',
            'label': 'Port',
            'label_key': 'modules.db.mysql.query.params.port.label',
            'description': 'MySQL server port',
            'description_key': 'modules.db.mysql.query.params.port.description',
            'default': 3306,
            'required': False
        },
        'user': {
            'type': 'string',
            'label': 'Username',
            'label_key': 'modules.db.mysql.query.params.user.label',
            'description': 'MySQL username (defaults to env.MYSQL_USER)',
            'description_key': 'modules.db.mysql.query.params.user.description',
            'placeholder': '${env.MYSQL_USER}',
            'required': False
        },
        'password': {
            'type': 'string',
            'label': 'Password',
            'label_key': 'modules.db.mysql.query.params.password.label',
            'description': 'MySQL password (defaults to env.MYSQL_PASSWORD)',
            'description_key': 'modules.db.mysql.query.params.password.description',
            'placeholder': '${env.MYSQL_PASSWORD}',
            'required': False,
            'secret': True
        },
        'database': {
            'type': 'string',
            'label': 'Database',
            'label_key': 'modules.db.mysql.query.params.database.label',
            'description': 'Database name (defaults to env.MYSQL_DATABASE)',
            'description_key': 'modules.db.mysql.query.params.database.description',
            'placeholder': '${env.MYSQL_DATABASE}',
            'required': False
        },
        'query': {
            'type': 'string',
            'label': 'SQL Query',
            'label_key': 'modules.db.mysql.query.params.query.label',
            'description': 'SQL query to execute',
            'description_key': 'modules.db.mysql.query.params.query.description',
            'required': True,
            'multiline': True,
            'placeholder': 'SELECT * FROM users WHERE active = 1'
        },
        'params': {
            'type': 'array',
            'label': 'Query Parameters',
            'label_key': 'modules.db.mysql.query.params.params.label',
            'description': 'Parameters for parameterized queries (prevents SQL injection)',
            'description_key': 'modules.db.mysql.query.params.params.description',
            'required': False,
            'help': 'Use %s in query and provide values here'
        }
    },
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
