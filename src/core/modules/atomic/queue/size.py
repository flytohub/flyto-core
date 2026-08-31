# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Queue Size Module
Get the current size of a queue.

HOW FAR THIS MODULE FOLLOWS REALITY

Two of the three `size` values this module can return are numbers something
counted. One of them is a literal, and telling them apart is the entire
contract here.

  memory, and a queue by that name exists               OBSERVED
      `qsize()` over the live `asyncio.Queue`. A real length, read from the
      store.

  memory, and no queue by that name exists              ACCEPTED
      `size = 0` in that branch is written in this file. Nothing was counted:
      `_memory_queues` has no entry, and this module -- unlike `enqueue` and
      `dequeue` -- does not create one. The zero is a stand-in for "there is
      no queue here", and it is indistinguishable from the zero an existing,
      empty queue returns. That is the postgres `CREATE TABLE` shape from
      `database.query`: a count that did not come from a count.

  redis                                                 OBSERVED
      `LLEN` is answered by the server from the list itself. Its zero for a
      missing key is a real answer and not a stand-in, because Redis draws no
      distinction between an empty list and an absent one -- there is nothing
      for the reply to be hiding.

`queue_exists` is in the output so a consumer can tell the two zeros apart
without parsing the envelope, which is the distinction `size` alone destroys.
"""
import logging
from typing import Any, Dict

from ....engine.outcome import ClaimBy, Outcome, envelope
from ....utils import enforce_outbound_service_url
from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError, ModuleError

logger = logging.getLogger(__name__)

# Import shared memory queue storage
from .enqueue import _memory_queues


def _size_outcome(*, backend: str, queue_name: str, counted: bool, size: Any) -> Dict[str, Any]:
    """The rung one size reading earned, decided by whether anything counted it.

    `counted` is a runtime fact, not a property of the backend: the same
    process answers an existing queue with a real length and an unknown name
    with a literal. Deciding this per return rather than per module is the
    point -- a per-module constant would have to be wrong about one of them.
    """
    if counted:
        return envelope(
            Outcome.OBSERVED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'queue_length_read',
                'backend': backend,
                'queue': queue_name,
                'size': size,
                'measured_by': (
                    'qsize() over the live asyncio.Queue' if backend == 'memory'
                    else 'the LLEN reply, which the server answers from the list'
                ),
            }],
        )
    return envelope(
        Outcome.ACCEPTED,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'no_queue_to_measure',
            'backend': backend,
            'queue': queue_name,
            'count_reported': False,
            'measured_by': None,
            'detail': (
                'No queue by that name exists in this process, and this module '
                'does not create one. The reported 0 is a literal written in '
                'this file, not a length: it reads identically to the 0 an '
                'existing empty queue would return.'
                if backend == 'memory' else
                'LLEN did not answer with a length, so nothing counted the '
                'list and the reported size is not a measurement of it.'
            ),
        }],
    )


@register_module(
    module_id='queue.size',
    version='1.0.0',
    category='queue',
    tags=['queue', 'size', 'length', 'count', 'status'],
    label='Queue Size',
    label_key='modules.queue.size.label',
    description='Get the current size of a queue',
    description_key='modules.queue.size.description',
    icon='Layers',
    color='#EC4899',
    input_types=['string'],
    output_types=['json'],

    can_receive_from=['*'],
    can_connect_to=['*'],

    retryable=True,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema=compose(
        field(
            'queue_name',
            type='string',
            label='Queue Name',
            label_key='modules.queue.size.params.queue_name.label',
            description='Name of the queue to check',
            description_key='modules.queue.size.params.queue_name.description',
            placeholder='my-queue',
            required=True,
            group=FieldGroup.BASIC,
        ),
        field(
            'backend',
            type='string',
            label='Backend',
            label_key='modules.queue.size.params.backend.label',
            description='Queue backend to use',
            description_key='modules.queue.size.params.backend.description',
            default='memory',
            enum=['memory', 'redis'],
            group=FieldGroup.OPTIONS,
        ),
        field(
            'redis_url',
            type='string',
            label='Redis URL',
            label_key='modules.queue.size.params.redis_url.label',
            description='Redis connection URL',
            description_key='modules.queue.size.params.redis_url.description',
            default='redis://localhost:6379',
            placeholder='redis://localhost:6379',
            showIf={'backend': {'$in': ['redis']}},
            group=FieldGroup.CONNECTION,
        ),
    ),
    output_schema={
        'queue_name': {
            'type': 'string',
            'description': 'Name of the queue',
            'description_key': 'modules.queue.size.output.queue_name.description',
        },
        'size': {
            'type': 'number',
            'description': (
                'Current number of items in the queue. On the memory backend a '
                'name with no queue behind it reports 0 without counting '
                'anything -- see queue_exists'
            ),
            'description_key': 'modules.queue.size.output.size.description',
        },
        'queue_exists': {
            'type': 'boolean',
            'description': (
                'memory backend only: whether a queue by this name exists in '
                'this process, which is what separates a counted 0 from a '
                'literal one. null on the redis backend, where LLEN answers '
                'for a missing list the same way it answers for an empty one'
            ),
            'description_key': 'modules.queue.size.output.queue_exists.description',
        },
        'outcome': {
            'type': 'object',
            'description': (
                'How far the reading was followed: "observed" when a length '
                'was counted, "accepted" when the 0 is a stand-in for a queue '
                'that does not exist'
            ),
            'description_key': 'modules.queue.size.output.outcome.description',
        },
    },
    timeout_ms=10000,
)
async def queue_size(context: Dict[str, Any]) -> Dict[str, Any]:
    """Get the current size of a queue."""
    params = context['params']
    queue_name = params.get('queue_name')
    backend = params.get('backend', 'memory')
    redis_url = params.get('redis_url', 'redis://localhost:6379')
    # SECURITY: redis_url is caller-controlled and the client dials whatever
    # host it names. Unguarded that is an internal port prober and a route to
    # the cloud metadata service — the non-HTTP twin of the SSRF advisories.
    # Loopback (the normal self-hosted case) stays allowed.
    enforce_outbound_service_url(redis_url, purpose='Redis')

    if not queue_name:
        raise ValidationError("Missing required parameter: queue_name", field="queue_name")

    if backend == 'memory':
        queue_exists = queue_name in _memory_queues
        if queue_exists:
            size = _memory_queues[queue_name].qsize()
        else:
            # A literal, not a length. Carried into the envelope as
            # `counted=False` rather than lost behind an integer that looks
            # exactly like a counted one.
            size = 0

        return {
            'ok': True,
            'data': {
                'queue_name': queue_name,
                'size': size,
                'queue_exists': queue_exists,
                'outcome': _size_outcome(
                    backend='memory',
                    queue_name=queue_name,
                    counted=queue_exists,
                    size=size,
                ),
            }
        }

    elif backend == 'redis':
        try:
            import redis.asyncio as aioredis
        except ImportError:
            raise ModuleError(
                "Redis backend requires the 'redis' package. Install with: pip install redis",
                hint="pip install redis"
            )

        try:
            client = aioredis.from_url(redis_url)
            try:
                size = await client.llen(queue_name)
                return {
                    'ok': True,
                    'data': {
                        'queue_name': queue_name,
                        'size': size,
                        'queue_exists': None,
                        'outcome': _size_outcome(
                            backend='redis',
                            queue_name=queue_name,
                            counted=isinstance(size, int) and not isinstance(size, bool),
                            size=size,
                        ),
                    }
                }
            finally:
                await client.aclose()
        except ModuleError:
            raise
        except Exception as e:
            raise ModuleError("Redis queue size check failed: {}".format(str(e)))

    else:
        raise ValidationError(
            "Invalid backend '{}'. Must be 'memory' or 'redis'".format(backend),
            field='backend'
        )
