# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Queue Enqueue Module
Add an item to an in-memory or Redis queue.

HOW FAR THIS MODULE FOLLOWS REALITY

An enqueue is the textbook ACCEPTED: the queue takes the item and nothing
about whether it is ever consumed is knowable here. That is the ceiling for
the shared backend. The in-process backend can say one thing more, and the
difference between them is not which backend is nicer -- it is whether the
number this module reads can be attributed to this module's push.

  memory: the queue grew by exactly one                  OBSERVED
      `qsize()` is read before the put and again after. There is no await
      between them that yields -- an unbounded `asyncio.Queue.put` does not
      suspend -- so a delta of exactly 1 is our item and nobody else's. That
      is a measurement of the store, made here, and attributable.

  memory: the queue did not grow by one                  INDETERMINATE
      A consumer taking the item straight back out is an ordinary correct
      race. Nobody declared a length contract, so the disagreement is this
      module's own inference failing: indeterminate, not failed.

  redis: RPUSH replied with a length                     ACCEPTED
      The reply is the length of the list after the append. That is not a
      count of what this command did -- it is the size of the whole list, on a
      server other producers are writing to, with no baseline taken here. A
      length of 7 is consistent with our push and with a great many other
      histories, so it does not attribute anything to us. What the reply does
      establish is that the server took the write and answered, which is
      exactly what ACCEPTED means.

      No baseline is taken deliberately: an `LLEN` before the `RPUSH` is a
      second round trip AND a race on a shared list, so it would buy a number
      that still could not carry the claim.

      This is the same line `cache.delete` sits on the other side of. A `DEL`
      reply counts the keys the server removed FOR THAT COMMAND, so it is
      attributable and earns OBSERVED; a length is not, and does not.

  redis: RPUSH replied with something that is not a length   INDETERMINATE
      redis-py answers RPUSH with an integer. Anything else means we cannot
      say whether the item was appended.

WHAT NO RUNG HERE MEANS: that the item was processed. The item sitting in a
queue is the whole of the effect this module has; a consumer running is a
different step, and `observed` here must never be read as `handled`.
"""
import asyncio
import json
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


def _memory_enqueue_outcome(*, queue_name: str, size_before: int, size_after: int) -> Dict[str, Any]:
    """The rung an in-process enqueue earned, from the pair of length readings.

    Pure and free of module state, so both branches are reachable in a test
    without having to win a race against the event loop.
    """
    if size_after - size_before == 1:
        return envelope(
            Outcome.OBSERVED,
            # INFERRED: the +1 predicate is this module's own. No caller asked
            # for it, and the branch where it does not hold is attributed to
            # the same author.
            claim_by=ClaimBy.INFERRED,
            effects=[{
                'kind': 'queue_grew_by_one',
                'backend': 'memory',
                'queue': queue_name,
                'size_before': size_before,
                'size_after': size_after,
                'measured_by': 'qsize() read before and after the put',
                'detail': (
                    'The queue holds one more item than it did, and the put is '
                    'the only thing that ran in between. It says the item is '
                    'queued; it says nothing about it being consumed.'
                ),
            }],
        )
    return envelope(
        Outcome.INDETERMINATE,
        claim_by=ClaimBy.INFERRED,
        effects=[{
            'kind': 'queue_length_disagrees',
            'backend': 'memory',
            'queue': queue_name,
            'predicate': 'qsize() after the put is qsize() before it, plus one',
            'size_before': size_before,
            'size_after': size_after,
            'detail': (
                'The queue did not grow by one. A consumer taking the item '
                'straight back out reads the same here as a put that did not '
                'land, so this is indeterminate rather than failed.'
            ),
        }],
    )


def _redis_enqueue_outcome(*, queue_name: str, reply: Any) -> Dict[str, Any]:
    """The rung a Redis enqueue earned, from the RPUSH reply alone.

    ACCEPTED at best, and the reason is in the module docstring: the reply is a
    length, not a count of this command's effect, so it cannot be attributed to
    this push.
    """
    counted = isinstance(reply, int) and not isinstance(reply, bool)
    if counted:
        return envelope(
            Outcome.ACCEPTED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'redis_rpush_acknowledged',
                'backend': 'redis',
                'queue': queue_name,
                'list_length_after': reply,
                'measured_by': 'the RPUSH reply -- the list length the server reports',
                'detail': (
                    'The server took the write and answered with the length of '
                    'the whole list. With no baseline, and other producers free '
                    'to write to it, that length is not attributable to this '
                    'push: it is the peer reporting on its own work.'
                ),
            }],
        )
    return envelope(
        Outcome.INDETERMINATE,
        claim_by=ClaimBy.INFERRED,
        effects=[{
            'kind': 'redis_rpush_not_acknowledged',
            'backend': 'redis',
            'queue': queue_name,
            'reply': repr(reply),
            'detail': (
                'RPUSH answers with an integer length. Without one we cannot '
                'say whether the item was appended.'
            ),
        }],
    )

# Module-level in-memory queue storage
_memory_queues: Dict[str, asyncio.Queue] = {}


def _get_memory_queue(name: str) -> asyncio.Queue:
    """Get or create an in-memory queue by name."""
    if name not in _memory_queues:
        _memory_queues[name] = asyncio.Queue()
    return _memory_queues[name]


@register_module(
    module_id='queue.enqueue',
    version='1.0.0',
    category='queue',
    tags=['queue', 'enqueue', 'push', 'message', 'buffer'],
    label='Enqueue Item',
    label_key='modules.queue.enqueue.label',
    description='Add an item to an in-memory or Redis queue',
    description_key='modules.queue.enqueue.description',
    icon='Layers',
    color='#EC4899',
    input_types=['any'],
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
            label_key='modules.queue.enqueue.params.queue_name.label',
            description='Name of the queue to add the item to',
            description_key='modules.queue.enqueue.params.queue_name.description',
            placeholder='my-queue',
            required=True,
            group=FieldGroup.BASIC,
        ),
        field(
            'data',
            type='string',
            label='Data',
            label_key='modules.queue.enqueue.params.data.label',
            description='Data to enqueue (any JSON-serializable value)',
            description_key='modules.queue.enqueue.params.data.description',
            required=True,
            format='multiline',
            group=FieldGroup.BASIC,
        ),
        field(
            'backend',
            type='string',
            label='Backend',
            label_key='modules.queue.enqueue.params.backend.label',
            description='Queue backend to use',
            description_key='modules.queue.enqueue.params.backend.description',
            default='memory',
            enum=['memory', 'redis'],
            group=FieldGroup.OPTIONS,
        ),
        field(
            'redis_url',
            type='string',
            label='Redis URL',
            label_key='modules.queue.enqueue.params.redis_url.label',
            description='Redis connection URL',
            description_key='modules.queue.enqueue.params.redis_url.description',
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
            'description_key': 'modules.queue.enqueue.output.queue_name.description',
        },
        'position': {
            'type': 'number',
            'description': 'Position of the item in the queue',
            'description_key': 'modules.queue.enqueue.output.position.description',
        },
        'queue_size': {
            'type': 'number',
            'description': 'Current size of the queue after enqueue',
            'description_key': 'modules.queue.enqueue.output.queue_size.description',
        },
        'size_before': {
            'type': 'number',
            'description': (
                'memory backend only: queue length read before the put, so the '
                'growth can be attributed to it. null on the redis backend, '
                'where a baseline would be a second round trip and a race'
            ),
            'description_key': 'modules.queue.enqueue.output.size_before.description',
        },
        'outcome': {
            'type': 'object',
            'description': (
                'How far the enqueue was followed: "observed" when the '
                'in-process queue grew by exactly one, "accepted" when Redis '
                'acknowledged the push. Never a claim that the item was '
                'consumed'
            ),
            'description_key': 'modules.queue.enqueue.output.outcome.description',
        },
    },
    timeout_ms=30000,
)
async def queue_enqueue(context: Dict[str, Any]) -> Dict[str, Any]:
    """Add an item to a queue."""
    params = context['params']
    queue_name = params.get('queue_name')
    data = params.get('data')
    backend = params.get('backend', 'memory')
    redis_url = params.get('redis_url', 'redis://localhost:6379')
    # SECURITY: redis_url is caller-controlled and the client dials whatever
    # host it names. Unguarded that is an internal port prober and a route to
    # the cloud metadata service — the non-HTTP twin of the SSRF advisories.
    # Loopback (the normal self-hosted case) stays allowed.
    enforce_outbound_service_url(redis_url, purpose='Redis')

    if not queue_name:
        raise ValidationError("Missing required parameter: queue_name", field="queue_name")
    if data is None:
        raise ValidationError("Missing required parameter: data", field="data")

    if backend == 'memory':
        q = _get_memory_queue(queue_name)
        # The baseline. Without it, `queue_size` says how long the queue is,
        # not that our item is the reason -- the same gap `file.write` closes
        # by stat-ing before an append.
        size_before = q.qsize()
        await q.put(data)
        queue_size = q.qsize()
        position = queue_size  # position is at the end

        return {
            'ok': True,
            'data': {
                'queue_name': queue_name,
                'position': position,
                'queue_size': queue_size,
                'size_before': size_before,
                'outcome': _memory_enqueue_outcome(
                    queue_name=queue_name,
                    size_before=size_before,
                    size_after=queue_size,
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
                serialized = json.dumps(data)
                queue_size = await client.rpush(queue_name, serialized)
                position = queue_size

                return {
                    'ok': True,
                    'data': {
                        'queue_name': queue_name,
                        'position': position,
                        'queue_size': queue_size,
                        'size_before': None,
                        'outcome': _redis_enqueue_outcome(
                            queue_name=queue_name,
                            reply=queue_size,
                        ),
                    }
                }
            finally:
                await client.aclose()
        except ModuleError:
            raise
        except Exception as e:
            raise ModuleError("Redis enqueue failed: {}".format(str(e)))

    else:
        raise ValidationError(
            "Invalid backend '{}'. Must be 'memory' or 'redis'".format(backend),
            field='backend'
        )
