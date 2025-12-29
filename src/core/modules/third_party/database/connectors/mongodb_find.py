"""
MongoDB Find Module
Query documents from MongoDB collection.
"""
import os

from ....registry import register_module


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
