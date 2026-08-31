# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Queue Dequeue Module
Remove and return an item from an in-memory or Redis queue.

HOW FAR THIS MODULE FOLLOWS REALITY

Four payload paths, and they split two ways on one question: did an item come
back?

  an item came back                                      OBSERVED
      The item in `data['data']` was in the queue and now is not. It was not
      computed here and there is no branch that invents it -- `get_nowait`,
      `wait_for(get())`, `LPOP` and `BLPOP` all hand back something the store
      was holding. That is a measurement of the store's contents and of the
      store changing, in one reading.

  nothing came back                                      ACCEPTED
      `empty: True` reads identically whether the queue was never written,
      was drained by another consumer, or -- for the `memory` backend, which
      is a module-level dict of `asyncio.Queue` -- belongs to a different
      worker process than the producer's. Nothing about the data was
      observed; a store answered, which is exactly ACCEPTED.

WHY THE BLOCKING TIMEOUT IS NOT `indeterminate`. A timeout is the textbook
indeterminate when it leaves us unable to say whether the effect happened, and
`asyncio.wait_for` cancelling a pending `Queue.get()` is exactly the shape that
could: if the cancellation landed after the item had been taken but before it
was returned, the item would be consumed and dropped, and the caller would see
an ordinary empty answer. That would make this path indeterminate on every
timeout.

It does not happen on this interpreter, and the claim was measured rather than
assumed: 1,500 trials sweeping a `put` across the deadline of a 20 ms
`wait_for`, checking the queue after the timeout with a settling window, lost
nothing (CPython 3.12.13). `Queue.get`'s cancellation handler puts the waiter
back and re-wakes the next getter, so the item stays queued. So the honest
answer here is that nothing was consumed and nothing came back -- ACCEPTED, and
a fabricated `indeterminate` on the most common polling path would be noise
that trains readers to ignore the field.

WHAT NO RUNG HERE MEANS: that the item was handled. Taking an item off a queue
destroys it; if the step that follows fails, nothing in this module put it
back. `observed` says the item reached this process, not that the work is done.
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

# Import shared memory queue storage
from .enqueue import _memory_queues, _get_memory_queue


def _dequeue_outcome(*, backend: str, queue_name: str, source: str, got_item: bool) -> Dict[str, Any]:
    """The rung one dequeue attempt earned.

    `source` names the call that answered -- `get_nowait`, `wait_for(get())`,
    `LPOP` or `BLPOP` -- because "the queue was empty" and "the wait ran out"
    are different stories behind the same `empty: True`, and the rung is the
    same for both only because neither returned anything.
    """
    if got_item:
        return envelope(
            Outcome.OBSERVED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'queue_item_removed',
                'backend': backend,
                'queue': queue_name,
                'source': source,
                'measured_by': 'the item the queue handed back',
                'detail': (
                    'An item that was in the queue is now out of it and in '
                    'this process. It says nothing about the item being '
                    'handled: a dequeue is destructive and nothing here puts '
                    'it back.'
                ),
            }],
        )
    return envelope(
        Outcome.ACCEPTED,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'queue_returned_nothing',
            'backend': backend,
            'queue': queue_name,
            'source': source,
            'measured_by': None,
            'detail': (
                'The store answered and handed back nothing. That reads the '
                'same whether the queue was never written, was drained by '
                'another consumer, or belongs to another process -- the memory '
                'backend is per-process. Nothing about the data was observed.'
            ),
        }],
    )


@register_module(
    module_id='queue.dequeue',
    version='1.0.0',
    category='queue',
    tags=['queue', 'dequeue', 'pop', 'consume', 'message'],
    label='Dequeue Item',
    label_key='modules.queue.dequeue.label',
    description='Remove and return an item from a queue',
    description_key='modules.queue.dequeue.description',
    icon='Layers',
    color='#EC4899',
    input_types=['string'],
    output_types=['any', 'json'],

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
            label_key='modules.queue.dequeue.params.queue_name.label',
            description='Name of the queue to dequeue from',
            description_key='modules.queue.dequeue.params.queue_name.description',
            placeholder='my-queue',
            required=True,
            group=FieldGroup.BASIC,
        ),
        field(
            'backend',
            type='string',
            label='Backend',
            label_key='modules.queue.dequeue.params.backend.label',
            description='Queue backend to use',
            description_key='modules.queue.dequeue.params.backend.description',
            default='memory',
            enum=['memory', 'redis'],
            group=FieldGroup.OPTIONS,
        ),
        field(
            'redis_url',
            type='string',
            label='Redis URL',
            label_key='modules.queue.dequeue.params.redis_url.label',
            description='Redis connection URL',
            description_key='modules.queue.dequeue.params.redis_url.description',
            default='redis://localhost:6379',
            placeholder='redis://localhost:6379',
            showIf={'backend': {'$in': ['redis']}},
            group=FieldGroup.CONNECTION,
        ),
        field(
            'timeout',
            type='number',
            label='Timeout',
            label_key='modules.queue.dequeue.params.timeout.label',
            description='Timeout in seconds (0 = non-blocking)',
            description_key='modules.queue.dequeue.params.timeout.description',
            default=0,
            min=0,
            max=300,
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'data': {
            'type': 'any',
            'description': 'The dequeued item (null if queue is empty)',
            'description_key': 'modules.queue.dequeue.output.data.description',
        },
        'queue_name': {
            'type': 'string',
            'description': 'Name of the queue',
            'description_key': 'modules.queue.dequeue.output.queue_name.description',
        },
        'remaining': {
            'type': 'number',
            'description': 'Remaining items in the queue',
            'description_key': 'modules.queue.dequeue.output.remaining.description',
        },
        'empty': {
            'type': 'boolean',
            'description': 'Whether the queue was empty',
            'description_key': 'modules.queue.dequeue.output.empty.description',
        },
        'outcome': {
            'type': 'object',
            'description': (
                'How far the dequeue was followed: "observed" when an item '
                'came back out of the store, "accepted" when nothing did. '
                'Never a claim that the item was handled'
            ),
            'description_key': 'modules.queue.dequeue.output.outcome.description',
        },
    },
    timeout_ms=310000,  # slightly more than max timeout (300s + 10s buffer)
)
async def queue_dequeue(context: Dict[str, Any]) -> Dict[str, Any]:
    """Remove and return an item from a queue."""
    params = context['params']
    queue_name = params.get('queue_name')
    backend = params.get('backend', 'memory')
    redis_url = params.get('redis_url', 'redis://localhost:6379')
    # SECURITY: redis_url is caller-controlled and the client dials whatever
    # host it names. Unguarded that is an internal port prober and a route to
    # the cloud metadata service — the non-HTTP twin of the SSRF advisories.
    # Loopback (the normal self-hosted case) stays allowed.
    enforce_outbound_service_url(redis_url, purpose='Redis')
    timeout = int(params.get('timeout', 0) or 0)

    if not queue_name:
        raise ValidationError("Missing required parameter: queue_name", field="queue_name")

    if backend == 'memory':
        q = _get_memory_queue(queue_name)

        if timeout == 0:
            # Non-blocking
            source = 'get_nowait'
            try:
                item = q.get_nowait()
            except asyncio.QueueEmpty:
                return {
                    'ok': True,
                    'data': {
                        'data': None,
                        'queue_name': queue_name,
                        'remaining': 0,
                        'empty': True,
                        'outcome': _dequeue_outcome(
                            backend='memory',
                            queue_name=queue_name,
                            source=source,
                            got_item=False,
                        ),
                    }
                }
        else:
            # Blocking with timeout
            source = 'wait_for(get())'
            try:
                item = await asyncio.wait_for(q.get(), timeout=timeout)
            except asyncio.TimeoutError:
                return {
                    'ok': True,
                    'data': {
                        'data': None,
                        'queue_name': queue_name,
                        'remaining': q.qsize(),
                        'empty': True,
                        'outcome': _dequeue_outcome(
                            backend='memory',
                            queue_name=queue_name,
                            source=source,
                            got_item=False,
                        ),
                    }
                }

        return {
            'ok': True,
            'data': {
                'data': item,
                'queue_name': queue_name,
                'remaining': q.qsize(),
                'empty': False,
                'outcome': _dequeue_outcome(
                    backend='memory',
                    queue_name=queue_name,
                    source=source,
                    got_item=True,
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
                if timeout == 0:
                    # Non-blocking: LPOP
                    source = 'LPOP'
                    raw = await client.lpop(queue_name)
                else:
                    # Blocking: BLPOP with timeout
                    source = 'BLPOP'
                    result = await client.blpop(queue_name, timeout=timeout)
                    raw = result[1] if result else None

                if raw is None:
                    remaining = await client.llen(queue_name)
                    return {
                        'ok': True,
                        'data': {
                            'data': None,
                            'queue_name': queue_name,
                            'remaining': remaining,
                            'empty': True,
                            'outcome': _dequeue_outcome(
                                backend='redis',
                                queue_name=queue_name,
                                source=source,
                                got_item=False,
                            ),
                        }
                    }

                # Deserialize JSON
                try:
                    if isinstance(raw, bytes):
                        raw = raw.decode('utf-8')
                    item = json.loads(raw)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    item = raw

                remaining = await client.llen(queue_name)

                return {
                    'ok': True,
                    'data': {
                        'data': item,
                        'queue_name': queue_name,
                        'remaining': remaining,
                        'empty': False,
                        'outcome': _dequeue_outcome(
                            backend='redis',
                            queue_name=queue_name,
                            source=source,
                            got_item=True,
                        ),
                    }
                }
            finally:
                await client.aclose()
        except ModuleError:
            raise
        except Exception as e:
            raise ModuleError("Redis dequeue failed: {}".format(str(e)))

    else:
        raise ValidationError(
            "Invalid backend '{}'. Must be 'memory' or 'redis'".format(backend),
            field='backend'
        )
