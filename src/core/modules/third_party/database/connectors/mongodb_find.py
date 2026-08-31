# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
MongoDB Find Module
Query documents from MongoDB collection.

HOW FAR THIS MODULE FOLLOWS REALITY

One payload-returning path, two rungs:

    documents came back    OBSERVED    `len(documents)` over dicts motor decoded
        from BSON the server sent, after `to_list` drained the cursor. Nothing
        is inferred; each document is state read out of the database.
    none came back         ACCEPTED    `len([]) == 0` is not an observation of
        anything. The server answered, and the answer contains no document.

The empty case is held to ACCEPTED for the same reason as in `database.query`,
and it is worth saying why the softer reading was refused. Unlike a SQL result
set, `collection.find` cannot be a write, so it is tempting to read an empty
result as a positive observation that nothing matches the filter. That reading
needs the filter to be the whole story, and it is not: `limit` is applied to
this cursor, a projection can be malformed, and a collection or database name
that does not exist returns an empty cursor rather than an error -- a typo in
`params['collection']` produces exactly the payload a correct query over an
empty collection produces. `count == 0` therefore does not distinguish "nothing
matches" from "we asked the wrong place", and a rung that said OBSERVED would be
asserting the first.

`count` is also NOT the number of documents matching the filter. It is the
number returned, capped by `limit` (default 100). The effect says so, because an
integer that is silently a page size and not a total is how a workflow comes to
believe a collection has exactly 100 documents in it.

VERIFIED is unreachable and no postcondition is declared -- nothing here
evaluates a predicate -- so `ceiling_for(None)` caps this at OBSERVED.
"""
import os

from .....engine.outcome import ClaimBy, Outcome, envelope
from ....registry import register_module
from ....schema import compose, presets
from ._dsn_target import enforce_dsn_target


def _found_documents_outcome(count, limit):
    """OBSERVED for documents the server sent, ACCEPTED for an empty answer."""
    if count <= 0:
        return envelope(
            Outcome.ACCEPTED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'no_documents_returned',
                'backend': 'mongodb',
                'measured_by': None,
                'detail': (
                    'The server answered and returned no documents. That is not '
                    'an observation that nothing matches: a database or '
                    'collection name that does not exist returns an empty '
                    'cursor rather than an error, so this payload is identical '
                    'to the one a typo in the collection name produces.'
                ),
            }],
        )
    return envelope(
        Outcome.OBSERVED,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'documents_returned',
            'backend': 'mongodb',
            'count': count,
            'limit': limit,
            'measured_by': 'len() over documents motor decoded from the server',
            'detail': (
                'Documents RETURNED, capped by limit. Not the number of '
                'documents matching the filter: a count equal to limit means '
                'the page was full, not that the collection holds that many.'
            ),
        }],
    )


@register_module(
    module_id='db.mongodb.find',
    version='1.0.0',
    category='database',
    tags=['ssrf_protected', 'database', 'mongodb', 'nosql', 'query', 'db', 'document', 'path_restricted'],
    label='MongoDB Find',
    label_key='modules.db.mongodb.find.label',
    description='Query documents from MongoDB collection',
    description_key='modules.db.mongodb.find.description',
    icon='Database',
    color='#00ED64',

    # Connection types
    input_types=['json', 'object'],
    output_types=['json', 'array'],
    can_receive_from=['data.*', 'http.*'],
    can_connect_to=['data.*', 'notify.*'],

    # Phase 2: Execution settings
    timeout_ms=60000,  # Database queries can take time
    retryable=True,  # Network errors can be retried for read queries
    max_retries=3,
    concurrent_safe=True,  # Multiple queries can run in parallel

    # Phase 2: Security settings
    requires_credentials=True,
    credential_keys=['MONGODB_URI'],
    handles_sensitive_data=True,  # Database data is typically sensitive
    required_permissions=['database.query'],

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
        ,
                'description_key': 'modules.db.mongodb.find.output.documents.description'},
        'count': {
            'type': 'number',
            'description': (
                'Number of documents RETURNED, capped by limit. Not the number '
                'matching the filter -- a count equal to limit means the page '
                'was full, not that the collection holds that many'
            )
        ,
                'description_key': 'modules.db.mongodb.find.output.count.description'},
        'outcome': {
            'type': 'object',
            'description': (
                'How far the effect was followed: observed when documents came '
                'back off the wire, accepted when the server answered with none. '
                'Never higher than observed -- nothing here evaluates a '
                'postcondition'
            )
        ,
                'description_key': 'modules.db.mongodb.find.output.outcome.description'}
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

    # Get connection string
    conn_string = params.get('connection_string') or os.getenv('MONGODB_URL')
    if not conn_string:
        raise ValueError("Connection string required: provide 'connection_string' param or set MONGODB_URL env variable")

    # SECURITY: a caller-supplied connection_string names a TCP target the same
    # way `host` does in db.mysql.query, but hides it from the name-based
    # outbound sweep — that is how GHSA-9x26-9vhm-2qhw reached internal
    # databases and the metadata endpoint. Guarded before the driver import so
    # a deployment without the driver installed is protected rather than
    # accidentally safe.
    enforce_dsn_target(conn_string, purpose='MongoDB')

    try:
        from motor.motor_asyncio import AsyncIOMotorClient
    except ImportError:
        raise ImportError("motor package required. Install with: pip install motor")

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
            'count': len(documents),
            'outcome': _found_documents_outcome(len(documents), limit),
        }
    finally:
        client.close()
