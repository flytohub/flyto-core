"""
MongoDB Find Module
Query documents from MongoDB collection.
"""
import os

from ....registry import register_module
from ....schema import compose, presets


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

    params_schema=compose(
        presets.MONGO_CONNECTION_STRING(),
        presets.MONGO_DATABASE(),
        presets.MONGO_COLLECTION(),
        presets.MONGO_FILTER(),
        presets.MONGO_PROJECTION(),
        presets.MONGO_LIMIT(),
        presets.MONGO_SORT(),
    ),
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
