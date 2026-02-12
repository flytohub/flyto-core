"""
PostgreSQL Database Module
Execute SQL queries on PostgreSQL database.
"""
import os

from ....registry import register_module
from ....schema import compose, presets


@register_module(
    module_id='db.postgresql.query',
    version='1.0.0',
    category='database',
    tags=['ssrf_protected', 'database', 'postgresql', 'sql', 'query', 'db'],
    label='PostgreSQL Query',
    label_key='modules.db.postgresql.query.label',
    description='Execute a SQL query on PostgreSQL database and return results',
    description_key='modules.db.postgresql.query.description',
    icon='Database',
    color='#336791',

    # Connection types
    input_types=['json', 'object'],
    output_types=['json', 'array'],
    can_receive_from=['data.*', 'api.*'],
    can_connect_to=['data.*', 'notification.*'],

    # Phase 2: Execution settings
    timeout_ms=60000,  # Database queries can take time
    retryable=True,  # Network errors can be retried for read queries
    max_retries=3,
    concurrent_safe=True,  # Multiple queries can run in parallel

    # Phase 2: Security settings
    requires_credentials=True,
    credential_keys=['POSTGRESQL_HOST', 'POSTGRESQL_USER', 'POSTGRESQL_PASSWORD'],
    handles_sensitive_data=True,  # Database data is typically sensitive
    required_permissions=['database.query'],

    params_schema=compose(
        presets.DB_CONNECTION_STRING(),
        presets.SQL_QUERY(),
        presets.DB_QUERY_PARAMS(),
    ),
    output_schema={
        'rows': {
            'type': 'array',
            'description': 'Array of result rows as objects'
        ,
                'description_key': 'modules.db.postgresql.query.output.rows.description'},
        'row_count': {
            'type': 'number',
            'description': 'Number of rows returned'
        ,
                'description_key': 'modules.db.postgresql.query.output.row_count.description'},
        'columns': {
            'type': 'array',
            'description': 'Column names in result set'
        ,
                'description_key': 'modules.db.postgresql.query.output.columns.description'}
    },
    examples=[
        {
            'title': 'Select users',
            'title_key': 'modules.db.postgresql.query.examples.select.title',
            'params': {
                'query': 'SELECT id, email, created_at FROM users WHERE active = true LIMIT 10'
            }
        },
        {
            'title': 'Parameterized query',
            'title_key': 'modules.db.postgresql.query.examples.parameterized.title',
            'params': {
                'query': 'SELECT * FROM orders WHERE user_id = $1 AND status = $2',
                'params': ['${user_id}', 'completed']
            }
        }
    ],
    author='Flyto Team',
    license='MIT',
    docs_url='https://www.postgresql.org/docs/current/sql-select.html'
)
async def postgresql_query(context):
    """Execute PostgreSQL query"""
    params = context['params']

    try:
        import asyncpg
    except ImportError:
        raise ImportError("asyncpg package required. Install with: pip install asyncpg")

    # Get connection string
    conn_string = params.get('connection_string') or os.getenv('POSTGRESQL_URL')
    if not conn_string:
        raise ValueError("Connection string required: provide 'connection_string' param or set POSTGRESQL_URL env variable")

    # Connect and execute query
    conn = await asyncpg.connect(conn_string)
    try:
        query_params = params.get('params', [])
        rows = await conn.fetch(params['query'], *query_params)

        # Convert to list of dicts
        result_rows = [dict(row) for row in rows]
        columns = list(rows[0].keys()) if rows else []

        return {
            'rows': result_rows,
            'row_count': len(result_rows),
            'columns': columns
        }
    finally:
        await conn.close()
