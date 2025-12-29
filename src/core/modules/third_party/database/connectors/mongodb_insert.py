"""
MongoDB Insert Module
Insert documents into MongoDB collection.
"""
import os

from ....registry import register_module


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
