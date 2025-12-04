"""
Database Integration Modules
Provides integrations with databases like PostgreSQL, MySQL, MongoDB
"""

from ...registry import register_module
import os


@register_module(
    module_id='db.postgresql.query',
    version='1.0.0',
    category='database',
    tags=['database', 'postgresql', 'sql', 'query', 'db'],
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
    timeout=60,  # Database queries can take time
    retryable=True,  # Network errors can be retried for read queries
    max_retries=3,
    concurrent_safe=True,  # Multiple queries can run in parallel

    # Phase 2: Security settings
    requires_credentials=True,  # Needs database credentials
    handles_sensitive_data=True,  # Database data is typically sensitive
    required_permissions=['network.access', 'database.read'],

    params_schema={
        'connection_string': {
            'type': 'string',
            'label': 'Connection String',
            'label_key': 'modules.db.postgresql.query.params.connection_string.label',
            'description': 'PostgreSQL connection string (defaults to env.POSTGRESQL_URL)',
            'description_key': 'modules.db.postgresql.query.params.connection_string.description',
            'placeholder': '${env.POSTGRESQL_URL}',
            'required': False,
            'secret': True,
            'help': 'Format: postgresql://user:password@host:port/database'
        },
        'query': {
            'type': 'string',
            'label': 'SQL Query',
            'label_key': 'modules.db.postgresql.query.params.query.label',
            'description': 'SQL query to execute',
            'description_key': 'modules.db.postgresql.query.params.query.description',
            'required': True,
            'multiline': True,
            'placeholder': 'SELECT * FROM users WHERE active = true'
        },
        'params': {
            'type': 'array',
            'label': 'Query Parameters',
            'label_key': 'modules.db.postgresql.query.params.params.label',
            'description': 'Parameters for parameterized queries (prevents SQL injection)',
            'description_key': 'modules.db.postgresql.query.params.params.description',
            'required': False,
            'help': 'Use $1, $2, etc in query and provide values here'
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
    author='Flyto2 Team',
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
            'description': 'MySQL server host (defaults to env.MYSQL_HOST)',
            'description_key': 'modules.db.mysql.query.params.host.description',
            'placeholder': '${env.MYSQL_HOST}',
            'required': False,
            'default': 'localhost'
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

    # Get connection parameters
    conn_params = {
        'host': params.get('host') or os.getenv('MYSQL_HOST', 'localhost'),
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


@register_module(
    module_id='db.mongodb.find',
    version='1.0.0',
    category='database',
    tags=['database', 'mongodb', 'nosql', 'query', 'db', 'document'],
    label='MongoDB Find',
    label_key='modules.db.mongodb.find.label',
    description='Query documents from MongoDB collection',
    description_key='modules.db.mongodb.find.description',
    icon='Database',
    color='#00ED64',

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
        'connection_string': {
            'type': 'string',
            'label': 'Connection String',
            'label_key': 'modules.db.mongodb.find.params.connection_string.label',
            'description': 'MongoDB connection string (defaults to env.MONGODB_URL)',
            'description_key': 'modules.db.mongodb.find.params.connection_string.description',
            'placeholder': '${env.MONGODB_URL}',
            'required': False,
            'secret': True,
            'help': 'Format: mongodb://user:password@host:port/database or mongodb+srv://...'
        },
        'database': {
            'type': 'string',
            'label': 'Database',
            'label_key': 'modules.db.mongodb.find.params.database.label',
            'description': 'Database name',
            'description_key': 'modules.db.mongodb.find.params.database.description',
            'required': True,
            'placeholder': 'my_database'
        },
        'collection': {
            'type': 'string',
            'label': 'Collection',
            'label_key': 'modules.db.mongodb.find.params.collection.label',
            'description': 'Collection name',
            'description_key': 'modules.db.mongodb.find.params.collection.description',
            'required': True,
            'placeholder': 'users'
        },
        'filter': {
            'type': 'object',
            'label': 'Filter',
            'label_key': 'modules.db.mongodb.find.params.filter.label',
            'description': 'MongoDB query filter (empty object {} returns all)',
            'description_key': 'modules.db.mongodb.find.params.filter.description',
            'required': False,
            'default': {},
            'placeholder': '{"status": "active"}'
        },
        'projection': {
            'type': 'object',
            'label': 'Projection',
            'label_key': 'modules.db.mongodb.find.params.projection.label',
            'description': 'Fields to include/exclude in results',
            'description_key': 'modules.db.mongodb.find.params.projection.description',
            'required': False,
            'placeholder': '{"_id": 0, "name": 1, "email": 1}'
        },
        'limit': {
            'type': 'number',
            'label': 'Limit',
            'label_key': 'modules.db.mongodb.find.params.limit.label',
            'description': 'Maximum number of documents to return',
            'description_key': 'modules.db.mongodb.find.params.limit.description',
            'required': False,
            'default': 100,
            'min': 1,
            'max': 10000
        },
        'sort': {
            'type': 'object',
            'label': 'Sort',
            'label_key': 'modules.db.mongodb.find.params.sort.label',
            'description': 'Sort order (1 for ascending, -1 for descending)',
            'description_key': 'modules.db.mongodb.find.params.sort.description',
            'required': False,
            'placeholder': '{"created_at": -1}'
        }
    },
    output_schema={
        'documents': {
            'type': 'array',
            'description': 'Array of matching documents'
        },
        'count': {
            'type': 'number',
            'description': 'Number of documents returned'
        }
    },
    examples=[
        {
            'title': 'Find all active users',
            'title_key': 'modules.db.mongodb.find.examples.active_users.title',
            'params': {
                'database': 'myapp',
                'collection': 'users',
                'filter': {'status': 'active'},
                'limit': 50
            }
        },
        {
            'title': 'Find with projection and sort',
            'title_key': 'modules.db.mongodb.find.examples.projection_sort.title',
            'params': {
                'database': 'myapp',
                'collection': 'orders',
                'filter': {'total': {'$gt': 100}},
                'projection': {'_id': 0, 'order_id': 1, 'total': 1, 'created_at': 1},
                'sort': {'created_at': -1},
                'limit': 20
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    docs_url='https://www.mongodb.com/docs/drivers/python/'
)
async def mongodb_find(context):
    """Query MongoDB documents"""
    params = context['params']

    try:
        from motor.motor_asyncio import AsyncIOMotorClient
    except ImportError:
        raise ImportError("motor package required. Install with: pip install motor")

    # Get connection string
    conn_string = params.get('connection_string') or os.getenv('MONGODB_URL')
    if not conn_string:
        raise ValueError("Connection string required: provide 'connection_string' param or set MONGODB_URL env variable")

    # Connect to MongoDB
    client = AsyncIOMotorClient(conn_string)
    try:
        db = client[params['database']]
        collection = db[params['collection']]

        # Build query
        filter_query = params.get('filter', {})
        projection = params.get('projection')
        limit = params.get('limit', 100)
        sort = params.get('sort')

        # Execute find
        cursor = collection.find(filter_query, projection)

        if sort:
            cursor = cursor.sort(list(sort.items()))

        cursor = cursor.limit(limit)

        # Fetch results
        documents = await cursor.to_list(length=limit)

        # Convert ObjectId to string for JSON serialization
        for doc in documents:
            if '_id' in doc:
                doc['_id'] = str(doc['_id'])

        return {
            'documents': documents,
            'count': len(documents)
        }
    finally:
        client.close()


@register_module(
    module_id='db.mongodb.insert',
    version='1.0.0',
    category='database',
    tags=['database', 'mongodb', 'nosql', 'insert', 'db', 'document'],
    label='MongoDB Insert',
    label_key='modules.db.mongodb.insert.label',
    description='Insert one or more documents into MongoDB collection',
    description_key='modules.db.mongodb.insert.description',
    icon='Database',
    color='#00ED64',

    # Connection types
    input_types=['json', 'object'],
    output_types=['json', 'array'],
    can_receive_from=['data.*', 'api.*'],
    can_connect_to=['data.*', 'notification.*'],

    # Phase 2: Execution settings
    timeout=30,  # Insert operations should be faster than queries
    retryable=False,  # Could create duplicate documents if retried
    concurrent_safe=True,  # Multiple inserts can run in parallel

    # Phase 2: Security settings
    requires_credentials=True,  # Needs database credentials
    handles_sensitive_data=True,  # Database data is typically sensitive
    required_permissions=['network.access', 'database.write'],

    params_schema={
        'connection_string': {
            'type': 'string',
            'label': 'Connection String',
            'label_key': 'modules.db.mongodb.insert.params.connection_string.label',
            'description': 'MongoDB connection string (defaults to env.MONGODB_URL)',
            'description_key': 'modules.db.mongodb.insert.params.connection_string.description',
            'placeholder': '${env.MONGODB_URL}',
            'required': False,
            'secret': True
        },
        'database': {
            'type': 'string',
            'label': 'Database',
            'label_key': 'modules.db.mongodb.insert.params.database.label',
            'description': 'Database name',
            'description_key': 'modules.db.mongodb.insert.params.database.description',
            'required': True
        },
        'collection': {
            'type': 'string',
            'label': 'Collection',
            'label_key': 'modules.db.mongodb.insert.params.collection.label',
            'description': 'Collection name',
            'description_key': 'modules.db.mongodb.insert.params.collection.description',
            'required': True
        },
        'document': {
            'type': 'object',
            'label': 'Document',
            'label_key': 'modules.db.mongodb.insert.params.document.label',
            'description': 'Document to insert (for single insert)',
            'description_key': 'modules.db.mongodb.insert.params.document.description',
            'required': False
        },
        'documents': {
            'type': 'array',
            'label': 'Documents',
            'label_key': 'modules.db.mongodb.insert.params.documents.label',
            'description': 'Array of documents to insert (for bulk insert)',
            'description_key': 'modules.db.mongodb.insert.params.documents.description',
            'required': False
        }
    },
    output_schema={
        'inserted_count': {
            'type': 'number',
            'description': 'Number of documents inserted'
        },
        'inserted_ids': {
            'type': 'array',
            'description': 'Array of inserted document IDs'
        }
    },
    examples=[
        {
            'title': 'Insert single document',
            'title_key': 'modules.db.mongodb.insert.examples.single.title',
            'params': {
                'database': 'myapp',
                'collection': 'users',
                'document': {
                    'name': 'John Doe',
                    'email': 'john@example.com',
                    'created_at': '${timestamp}'
                }
            }
        },
        {
            'title': 'Insert multiple documents',
            'title_key': 'modules.db.mongodb.insert.examples.multiple.title',
            'params': {
                'database': 'myapp',
                'collection': 'products',
                'documents': [
                    {'name': 'Product A', 'price': 19.99},
                    {'name': 'Product B', 'price': 29.99}
                ]
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    docs_url='https://www.mongodb.com/docs/drivers/python/'
)
async def mongodb_insert(context):
    """Insert documents into MongoDB"""
    params = context['params']

    try:
        from motor.motor_asyncio import AsyncIOMotorClient
    except ImportError:
        raise ImportError("motor package required. Install with: pip install motor")

    # Get connection string
    conn_string = params.get('connection_string') or os.getenv('MONGODB_URL')
    if not conn_string:
        raise ValueError("Connection string required: provide 'connection_string' param or set MONGODB_URL env variable")

    # Determine if single or bulk insert
    document = params.get('document')
    documents = params.get('documents')

    if not document and not documents:
        raise ValueError("Either 'document' or 'documents' must be provided")

    # Connect to MongoDB
    client = AsyncIOMotorClient(conn_string)
    try:
        db = client[params['database']]
        collection = db[params['collection']]

        if document:
            # Single insert
            result = await collection.insert_one(document)
            return {
                'inserted_count': 1,
                'inserted_ids': [str(result.inserted_id)]
            }
        else:
            # Bulk insert
            result = await collection.insert_many(documents)
            return {
                'inserted_count': len(result.inserted_ids),
                'inserted_ids': [str(id) for id in result.inserted_ids]
            }
    finally:
        client.close()
