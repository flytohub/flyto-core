# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
MongoDB Insert Module
Insert documents into MongoDB collection.

HOW FAR THIS MODULE FOLLOWS REALITY

ACCEPTED, and it cannot honestly go higher. The reason is worth stating,
because both numbers this module returns look like evidence and neither is:

  `inserted_count: 1` on the single-document path is a literal written in this
      file. No server contributed to it.

  `inserted_ids` -- and therefore `len(result.inserted_ids)` on the bulk path --
      is generated CLIENT-side. pymongo adds an `_id` to any document that
      lacks one before it goes on the wire, and the result object hands those
      same ids back. `len(result.inserted_ids)` is `len(documents)` by
      construction: it would read identically if the server had stored every
      document, some of them, or none.

That is the `file.write` `bytes_written` shape exactly -- arithmetic on our own
input wearing the name of a measurement -- and a rung resting on either number
would be a false green on the module that writes to Mongo.

What IS measured is `result.acknowledged`: whether the driver waited for the
server's reply under the effective write concern.

    acknowledged=True     ACCEPTED     The server replied and reported no write
        error. That is the peer reporting on its own work, which is taking its
        word -- and taking a peer's word is what ACCEPTED means.
    acknowledged=False    DISPATCHED   Write concern w=0. The driver put the
        bytes on the socket and did not wait. Nobody confirmed receipt, which is
        the definition of the bottom rung.

OBSERVED would need a read-back -- a `find` for the ids afterwards. This module
does not do one, and adding a second round trip to every insert is a change to
what the module costs, not a change to what it reports. The honest answer is the
lower rung with the reason attached.
"""
import os

from .....engine.outcome import ClaimBy, Outcome, envelope
from ....registry import register_module
from ....schema import compose, presets
from ._dsn_target import enforce_dsn_target


def _insert_outcome(result, offered):
    """ACCEPTED when the server acknowledged the write, DISPATCHED when not.

    `offered` always travels, always labelled as the input it is, so a reader
    can see the number reported as `inserted_count` and see beside it that
    nothing on the server contributed to it.
    """
    # `acknowledged` is on every pymongo write result; a driver or stub that
    # does not carry it has told us nothing about receipt, and the honest
    # reading of "we cannot tell whether the peer confirmed" is the rung for
    # nobody having confirmed.
    acknowledged = getattr(result, 'acknowledged', None) is True

    offered_effect = {
        'kind': 'documents_offered',
        'backend': 'mongodb',
        'count': offered,
        'measured_by': 'len() over the documents this module was handed',
        'detail': (
            'How many documents were OFFERED. The _id values in inserted_ids '
            'are generated client-side by pymongo before the write goes on the '
            'wire, so neither this count nor that list is evidence the server '
            'stored anything: both read identically if it stored none.'
        ),
    }

    if acknowledged:
        return envelope(
            Outcome.ACCEPTED,
            claim_by=ClaimBy.NONE,
            effects=[
                offered_effect,
                {
                    'kind': 'write_acknowledged',
                    'backend': 'mongodb',
                    'measured_by': 'result.acknowledged from the driver',
                    'detail': (
                        'The server replied under the effective write concern '
                        'and reported no write error. The peer reporting on its '
                        'own work -- not an observation of the stored documents.'
                    ),
                },
            ],
        )

    return envelope(
        Outcome.DISPATCHED,
        claim_by=ClaimBy.NONE,
        effects=[
            offered_effect,
            {
                'kind': 'write_unacknowledged',
                'backend': 'mongodb',
                'measured_by': 'result.acknowledged from the driver',
                'detail': (
                    'The driver did not report an acknowledgement -- write '
                    'concern w=0 does not wait for the server. The bytes left '
                    'us and nobody confirmed receipt.'
                ),
            },
        ],
    )


@register_module(
    module_id='db.mongodb.insert',
    version='1.0.0',
    category='database',
    tags=['ssrf_protected', 'database', 'mongodb', 'nosql', 'insert', 'db', 'document', 'path_restricted'],
    label='MongoDB Insert',
    label_key='modules.db.mongodb.insert.label',
    description='Insert one or more documents into MongoDB collection',
    description_key='modules.db.mongodb.insert.description',
    icon='Database',
    color='#00ED64',

    # Connection types
    input_types=['json', 'object'],
    output_types=['json', 'array'],
    can_receive_from=['data.*', 'http.*'],
    can_connect_to=['data.*', 'notify.*'],

    # Phase 2: Execution settings
    timeout_ms=30000,  # Insert operations should be faster than queries
    retryable=False,  # Could create duplicate documents if retried
    concurrent_safe=True,  # Multiple inserts can run in parallel

    # Phase 2: Security settings
    requires_credentials=True,
    credential_keys=['MONGODB_URI'],
    handles_sensitive_data=True,  # Database data is typically sensitive
    required_permissions=['database.query'],

    params_schema=compose(
        presets.MONGO_CONNECTION_STRING(),
        presets.MONGO_DATABASE(),
        presets.MONGO_COLLECTION(),
        presets.MONGO_DOCUMENT(),
        presets.MONGO_DOCUMENTS(),
    ),
    output_schema={
        'inserted_count': {
            'type': 'number',
            'description': (
                'Number of documents OFFERED to the driver. Not a measurement '
                'of what the server stored: it reads the same whether every '
                'document landed or none did -- see outcome'
            )
        ,
                'description_key': 'modules.db.mongodb.insert.output.inserted_count.description'},
        'inserted_ids': {
            'type': 'array',
            'description': (
                'The _id of each document offered. Generated CLIENT-side by '
                'pymongo for documents that lack one, so this list is not '
                'evidence the server stored anything'
            )
        ,
                'description_key': 'modules.db.mongodb.insert.output.inserted_ids.description'},
        'outcome': {
            'type': 'object',
            'description': (
                'How far the effect was followed: accepted when the server '
                'acknowledged the write, dispatched under write concern w=0 '
                'where nothing was acknowledged. Never observed -- no document '
                'is read back'
            )
        ,
                'description_key': 'modules.db.mongodb.insert.output.outcome.description'}
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
                    'email': 'dev@flyto2.com',
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
                'inserted_ids': [str(result.inserted_id)],
                'outcome': _insert_outcome(result, 1),
            }
        else:
            # Bulk insert
            result = await collection.insert_many(documents)
            return {
                'inserted_count': len(result.inserted_ids),
                'inserted_ids': [str(id) for id in result.inserted_ids],
                'outcome': _insert_outcome(result, len(result.inserted_ids)),
            }
    finally:
        client.close()
