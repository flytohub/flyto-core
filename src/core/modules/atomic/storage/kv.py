# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Key-Value Storage Module
Simple persistent key-value storage for workflow state.
Uses file-based JSON storage for portability and simplicity.

HOW FAR THESE MODULES FOLLOW REALITY

Three modules over one JSON file per namespace. All three used to report `ok:
True` and nothing else, and `ok` here means only "no exception escaped the
`try`" -- which is a statement about this process, never about the file.

What is measurable is the file, so all three now read it back:

  storage.set     reload the namespace, find the key, and match `_stored_at`
                  against the float this call generated       -> OBSERVED
  storage.get     the value came out of the file              -> OBSERVED
  storage.delete  reload the namespace and find the key gone  -> OBSERVED

`_stored_at` is what makes `set`'s read-back evidence rather than a coincidence.
A reload that merely finds the key present would be satisfied by a value written
by some earlier run; the timestamp is generated in this call, and finding that
exact float under that exact key is a fact that could not have been true before
it. (Floats round-trip exactly through `json` in CPython, which is what makes
the equality safe to lean on.)

THE ABSENCE THAT WAS NOT AN OBSERVATION

`_load_storage` used to swallow `JSONDecodeError` and `IOError`, log a warning
and return `{}`. Every caller then read that empty dict as fact:

  * `storage.get` returned the caller's default and `found: False`, so a
    corrupted namespace file was indistinguishable from a key that was never
    set -- silently, for as long as the corruption lasted;
  * `storage.delete` reported `deleted: False` for keys that were really there;
  * `storage.set` wrote the `{}` back with one key in it, DISCARDING every other
    key in the namespace.

This is the `database.query` empty-result trap in another costume: a `{}` that
reads identically whether the namespace is empty or unreadable is not evidence
of either. `_load_storage` now returns a status beside the data -- `loaded`,
`absent`, `unreadable` -- and `unreadable` produces INDETERMINATE rather than a
confident `found: False`. `absent` stays OBSERVED: an ENOENT on the namespace
file is the filesystem answering that nothing was ever stored here.

THE TRUNCATION, which is the bug this exercise actually found

`_save_storage` opened the namespace file with `'w'` and handed the handle
straight to `json.dump`. `'w'` truncates at open. `json.dump` serialises
incrementally, straight into the file. So a value `json` cannot represent -- a
`set`, a `datetime`, a numpy scalar, anything a workflow might pass through
`value` -- truncated the file to zero and then raised partway through rewriting
it, destroying every OTHER key in the namespace. The module caught the exception
and returned `ok: False`, which reads as "nothing happened".

Measured before the fix: a namespace holding `keep` is left as invalid JSON
containing a partial object after one `storage.set(key='bad', value={1, 2})`,
and the next `storage.get(key='keep')` returns the default. The data is gone and
nothing in the result says so.

Two changes close it, in this order:

  * serialise to a string FIRST, so an unrepresentable value raises before any
    file is opened and the stored data is never touched; and
  * write the string to a temporary file in the same directory and `os.replace`
    it into place, so a reader never sees a partial file and a crash mid-write
    leaves the previous version intact rather than a truncated one.

Found by giving these modules an outcome rung and then asking what the rung was
measuring -- the same way the `fetch='all'` rollback was found in
`database.query`.
"""
import json
import logging
import os
import stat
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from ....engine.outcome import ClaimBy, Outcome, envelope
from ...registry import register_module

logger = logging.getLogger(__name__)

# Default storage directory
DEFAULT_STORAGE_DIR = os.path.expanduser("~/.flyto/storage")

#: How a namespace read turned out. The distinction `_load_storage` used to
#: throw away: `{}` from a namespace that has never been written and `{}` from
#: one that could not be parsed are different facts, and only the first is
#: evidence that a key is not set.
LOADED = "loaded"
ABSENT = "absent"
UNREADABLE = "unreadable"


def _get_storage_path(namespace: str) -> Path:
    """Get storage file path for namespace"""
    storage_dir = Path(os.environ.get("FLYTO_STORAGE_DIR", DEFAULT_STORAGE_DIR))
    storage_dir.mkdir(parents=True, exist_ok=True)
    # Sanitize namespace for filename
    safe_namespace = "".join(c if c.isalnum() or c in "-_" else "_" for c in namespace)
    return storage_dir / f"{safe_namespace}.json"


def _load_storage(namespace: str) -> Tuple[Dict[str, Any], str, Optional[str]]:
    """``(data, status, reason)`` -- the namespace, and how confidently.

    Returns the same `{}` it always did for both empty cases, so no caller has
    to change how it reads the data. What is new is the second element: an
    empty dict from `ABSENT` supports a claim that a key is not set, and an
    empty dict from `UNREADABLE` supports nothing at all. See the module
    docstring for what reading them as the same thing cost.
    """
    path = _get_storage_path(namespace)
    if not path.exists():
        return {}, ABSENT, None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            loaded = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to load storage {namespace}: {e}")
        return {}, UNREADABLE, f"{type(e).__name__}: {e}"
    if not isinstance(loaded, dict):
        # A namespace file holding a list or a scalar is not a key-value store.
        # `.get(key)` on it would raise or lie depending on the type, so it is
        # the same kind of "cannot read this" as a syntax error.
        return {}, UNREADABLE, f"namespace file holds {type(loaded).__name__}, not an object"
    return loaded, LOADED, None


def _save_storage(namespace: str, data: Dict[str, Any]) -> None:
    """Write the namespace, atomically, or leave the previous one untouched.

    Two properties, both of which the `open('w')` + `json.dump` this replaces
    lacked. See the module docstring for the measured data loss.

    * Serialised BEFORE anything is opened. An unrepresentable value raises here
      with no file touched, instead of after `'w'` has already truncated it.
    * Published with `os.replace`, which is atomic within a filesystem. A reader
      sees either the whole previous namespace or the whole new one, never the
      middle of a write, and a crash cannot leave a half-written file behind.

    One consequence of writing through a temporary file is worth handling rather
    than inheriting: `mkstemp` creates at 0600, while the `open('w')` this
    replaces created at 0666 minus the umask, normally 0644. Replacing an
    existing namespace would therefore silently tighten its permissions, so an
    existing file's mode is carried over. A namespace created fresh keeps
    mkstemp's 0600, which is the better default for a state store and breaks
    nothing that was not already there.
    """
    path = _get_storage_path(namespace)
    # Raises on an unrepresentable value while the stored file is still intact.
    payload = json.dumps(data, ensure_ascii=False, indent=2)

    # Same directory as the target: os.replace is only atomic within one
    # filesystem, and a temp dir elsewhere would silently become a copy.
    handle, temp_path = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(handle, 'w', encoding='utf-8') as f:
            f.write(payload)
        try:
            os.chmod(temp_path, stat.S_IMODE(os.stat(path).st_mode))
        except OSError:
            # No previous namespace, or its mode cannot be read. mkstemp's 0600
            # stands; this is a permissions nicety and never a reason to lose
            # the write.
            pass
        os.replace(temp_path, path)
    except BaseException:
        # The previous namespace is still in place; drop the partial temp file
        # rather than leaving it to accumulate in the storage directory.
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def _is_expired(entry: Dict[str, Any]) -> bool:
    """Check if entry has expired"""
    expires_at = entry.get("_expires_at")
    if expires_at is None:
        return False
    return time.time() > expires_at


def _unreadable_envelope(*, operation: str, namespace: str, reason: Optional[str]) -> Dict[str, Any]:
    """The rung when the namespace file could not be parsed.

    INDETERMINATE, and this is the whole point of tracking the status: the `{}`
    these modules go on to report a result from is a fallback, not a reading.
    Whether the key is set, and what it was set to, is not known.
    """
    return envelope(
        Outcome.INDETERMINATE,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'namespace_unreadable',
            'operation': operation,
            'namespace': namespace,
            'measured_by': None,
            'reason': reason,
            'detail': (
                'The namespace file exists and could not be parsed, so it was '
                'treated as empty. Any found/deleted flag on this result is that '
                'fallback and not an observation -- the keys really in this '
                'namespace are unknown.'
            ),
        }],
    )


def _error_envelope(*, operation: str, namespace: str, error: str) -> Dict[str, Any]:
    """The rung for the `except Exception` path every one of these modules has.

    INDETERMINATE rather than FAILED. For a read there is nothing to have
    failed; for a write, the exception may have come from serialising (nothing
    was touched -- `_save_storage` fails before opening anything) or from the
    replace, and this handler cannot tell which. "We cannot say" is exactly what
    the off-ladder `indeterminate` is for.

    NOTE for consumers: on this path the module returns `ok: False`, and
    `wrap_legacy_result` turns that into an ERROR whose `to_legacy_dict` keeps
    only ok/error/error_code. This envelope therefore reaches a direct caller of
    the module but is dropped on the way out of a step. It is attached anyway,
    because the alternative is a result shape that has the field on some returns
    and not others.
    """
    return envelope(
        Outcome.INDETERMINATE,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'storage_error',
            'operation': operation,
            'namespace': namespace,
            'measured_by': None,
            'reason': error,
            'detail': (
                'The operation raised. Nothing was read back, so whether the '
                'stored state changed is unknown. A serialisation failure leaves '
                'the previous namespace intact by construction; a failure during '
                'the atomic replace does not say which side it landed on.'
            ),
        }],
    )


@register_module(
    module_id='storage.get',
    stability='stable',
    version='1.0.0',
    category='storage',
    subcategory='kv',
    tags=['storage', 'cache', 'state', 'kv', 'memory', 'persist'],
    label='Get Stored Value',
    label_key='modules.storage.get.label',
    description='Retrieve a value from persistent key-value storage',
    description_key='modules.storage.get.description',
    icon='Database',
    color='#10B981',

    input_types=['text', 'object'],
    output_types=['object', 'text', 'number'],
    can_connect_to=['*'],
    can_receive_from=['*'],

    timeout_ms=5000,
    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema={
        'namespace': {
            'type': 'string',
            'label': 'Namespace',
            'label_key': 'modules.storage.get.params.namespace.label',
            'description': 'Storage namespace (e.g., workflow name or project)',
            'description_key': 'modules.storage.get.params.namespace.description',
            'required': True,
            'placeholder': 'my-workflow',
            'default': 'default'
        },
        'key': {
            'type': 'string',
            'label': 'Key',
            'label_key': 'modules.storage.get.params.key.label',
            'description': 'Key to retrieve',
            'description_key': 'modules.storage.get.params.key.description',
            'required': True,
            'placeholder': 'last_price'
        },
        'default': {
            'type': 'any',
            'label': 'Default Value',
            'label_key': 'modules.storage.get.params.default.label',
            'description': 'Value to return if key does not exist',
            'description_key': 'modules.storage.get.params.default.description',
            'required': False,
            'placeholder': '0'
        }
    },
    output_schema={
        'ok': {
            'type': 'boolean',
            'description': 'Whether the operation succeeded',
            'description_key': 'modules.storage.get.output.ok.description'
        },
        'found': {
            'type': 'boolean',
            'description': (
                'Whether the key was found (not expired). False is also the '
                'fallback when the namespace could not be parsed -- read '
                'outcome.rung to tell a finding from a fallback'
            ),
            'description_key': 'modules.storage.get.output.found.description'
        },
        'value': {
            'type': 'any',
            'description': 'The stored value or default',
            'description_key': 'modules.storage.get.output.value.description'
        },
        'key': {
            'type': 'string',
            'description': 'The key that was queried',
            'description_key': 'modules.storage.get.output.key.description'
        },
        'outcome': {
            'type': 'object',
            'description': (
                'How far this lookup was followed into reality: observed when '
                'the namespace was read (including a clean miss), indeterminate '
                'when it could not be parsed'
            ),
            'description_key': 'modules.storage.get.output.outcome.description'
        }
    },
    examples=[
        {
            'title': 'Get last BTC price',
            'title_key': 'modules.storage.get.examples.btc.title',
            'params': {
                'namespace': 'crypto-alerts',
                'key': 'btc_last_price',
                'default': 0
            }
        },
        {
            'title': 'Get workflow state',
            'title_key': 'modules.storage.get.examples.state.title',
            'params': {
                'namespace': 'my-workflow',
                'key': 'last_run_status'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def storage_get(context: Dict[str, Any]) -> Dict[str, Any]:
    """Get value from key-value storage"""
    params = context['params']
    namespace = params.get('namespace', 'default')
    key = params['key']
    default_value = params.get('default')

    try:
        storage, status, reason = _load_storage(namespace)

        # A miss over a namespace we could not parse is not a miss. Reported
        # first, because every return below it would otherwise describe the
        # fallback `{}` as though it were the stored data.
        if status == UNREADABLE:
            return {
                'ok': True,
                'found': False,
                'value': default_value,
                'key': key,
                'outcome': _unreadable_envelope(
                    operation='get', namespace=namespace, reason=reason
                ),
            }

        entry = storage.get(key)

        if entry is None:
            return {
                'ok': True,
                'found': False,
                'value': default_value,
                'key': key,
                # A clean read of the namespace that does not contain the key is
                # evidence the key is not set -- unlike `database.query`'s empty
                # result set, the whole mapping was in hand and searched. `absent`
                # is the same finding by way of ENOENT on the file.
                'outcome': envelope(
                    Outcome.OBSERVED,
                    claim_by=ClaimBy.NONE,
                    effects=[{
                        'kind': 'key_absent',
                        'namespace': namespace,
                        'key': key,
                        'namespace_status': status,
                        'measured_by': (
                            'the parsed namespace file, searched for the key'
                            if status == LOADED else
                            'os.path.exists on the namespace file: it is not there'
                        ),
                        'detail': (
                            'The namespace was read and does not hold this key. '
                            'The returned value is the caller\'s default.'
                        ),
                    }],
                ),
            }

        # Check expiration
        if _is_expired(entry):
            # Clean up expired entry
            del storage[key]
            _save_storage(namespace, storage)
            # The eviction is a write, and a write nobody looks at is only
            # dispatched. One reload settles both halves of this return: the
            # entry that expired was read from the file, and the entry is gone
            # from it now.
            evicted, evicted_status, evicted_reason = _load_storage(namespace)
            eviction_confirmed = evicted_status != UNREADABLE and key not in evicted
            return {
                'ok': True,
                'found': False,
                'value': default_value,
                'key': key,
                'expired': True,
                'outcome': envelope(
                    Outcome.OBSERVED if eviction_confirmed else Outcome.INDETERMINATE,
                    claim_by=ClaimBy.INFERRED,
                    effects=[{
                        'kind': 'entry_expired',
                        'namespace': namespace,
                        'key': key,
                        'expires_at': entry.get('_expires_at'),
                        'eviction_confirmed': eviction_confirmed,
                        'measured_by': (
                            'the entry read from the namespace file, its '
                            '_expires_at compared against time.time(); then the '
                            'namespace reloaded to confirm the entry is gone'
                        ),
                        'reason': evicted_reason,
                        'detail': (
                            'The stored entry was read and had passed its '
                            'expiry, and the reload confirms the eviction '
                            'landed.'
                            if eviction_confirmed else
                            'The stored entry was read and had passed its '
                            'expiry. The eviction write could not be confirmed '
                            'by the reload, so whether the entry is still on '
                            'disk is unknown.'
                        ),
                    }],
                ),
            }

        return {
            'ok': True,
            'found': True,
            'value': entry.get('value'),
            'key': key,
            'stored_at': entry.get('_stored_at'),
            'outcome': envelope(
                Outcome.OBSERVED,
                claim_by=ClaimBy.NONE,
                effects=[{
                    'kind': 'value_read',
                    'namespace': namespace,
                    'key': key,
                    'stored_at': entry.get('_stored_at'),
                    'measured_by': 'the value parsed out of the namespace file',
                    'detail': (
                        'The returned value came off the filesystem. Not a '
                        'restatement of any parameter -- the caller\'s default '
                        'was not used.'
                    ),
                }],
            ),
        }

    except Exception as e:
        logger.error(f"Storage get error: {e}")
        return {
            'ok': False,
            'error': str(e),
            'error_code': 'STORAGE_ERROR',
            'key': key,
            'outcome': _error_envelope(operation='get', namespace=namespace, error=str(e)),
        }


@register_module(
    module_id='storage.set',
    stability='stable',
    version='1.0.0',
    category='storage',
    subcategory='kv',
    tags=['storage', 'cache', 'state', 'kv', 'memory', 'persist'],
    label='Store Value',
    label_key='modules.storage.set.label',
    description='Store a value in persistent key-value storage',
    description_key='modules.storage.set.description',
    icon='DatabaseBackup',
    color='#10B981',

    input_types=['object', 'text', 'number'],
    output_types=['object'],
    can_connect_to=['*'],
    can_receive_from=['*'],

    timeout_ms=5000,
    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema={
        'namespace': {
            'type': 'string',
            'label': 'Namespace',
            'label_key': 'modules.storage.set.params.namespace.label',
            'description': 'Storage namespace (e.g., workflow name or project)',
            'description_key': 'modules.storage.set.params.namespace.description',
            'required': True,
            'placeholder': 'my-workflow',
            'default': 'default'
        },
        'key': {
            'type': 'string',
            'label': 'Key',
            'label_key': 'modules.storage.set.params.key.label',
            'description': 'Key to store value under',
            'description_key': 'modules.storage.set.params.key.description',
            'required': True,
            'placeholder': 'last_price'
        },
        'value': {
            'type': 'any',
            'label': 'Value',
            'label_key': 'modules.storage.set.params.value.label',
            'description': 'Value to store (string, number, or object)',
            'description_key': 'modules.storage.set.params.value.description',
            'required': True,
            'placeholder': '42350.50'
        },
        'ttl_seconds': {
            'type': 'number',
            'label': 'TTL (seconds)',
            'label_key': 'modules.storage.set.params.ttl.label',
            'description': 'Time to live in seconds (optional, 0 = no expiration)',
            'description_key': 'modules.storage.set.params.ttl.description',
            'required': False,
            'default': 0,
            'min': 0,
            'max': 31536000,
            'placeholder': '3600'
        }
    },
    output_schema={
        'ok': {
            'type': 'boolean',
            'description': 'Whether the operation succeeded',
            'description_key': 'modules.storage.set.output.ok.description'
        },
        'key': {
            'type': 'string',
            'description': 'The key that was stored',
            'description_key': 'modules.storage.set.output.key.description'
        },
        'stored_at': {
            'type': 'number',
            'description': 'Unix timestamp when value was stored',
            'description_key': 'modules.storage.set.output.stored_at.description'
        },
        'expires_at': {
            'type': 'number',
            'description': 'Unix timestamp when value expires (if TTL set)',
            'description_key': 'modules.storage.set.output.expires_at.description'
        },
        'outcome': {
            'type': 'object',
            'description': (
                'How far this write was followed into reality: observed when a '
                'reload finds the key carrying this call\'s timestamp, '
                'indeterminate when it does not'
            ),
            'description_key': 'modules.storage.set.output.outcome.description'
        }
    },
    examples=[
        {
            'title': 'Store BTC price',
            'title_key': 'modules.storage.set.examples.btc.title',
            'params': {
                'namespace': 'crypto-alerts',
                'key': 'btc_last_price',
                'value': 42350.50
            }
        },
        {
            'title': 'Store with expiration',
            'title_key': 'modules.storage.set.examples.ttl.title',
            'params': {
                'namespace': 'cache',
                'key': 'api_response',
                'value': {'data': 'cached'},
                'ttl_seconds': 3600
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def storage_set(context: Dict[str, Any]) -> Dict[str, Any]:
    """Store value in key-value storage"""
    params = context['params']
    namespace = params.get('namespace', 'default')
    key = params['key']
    value = params['value']
    ttl_seconds = params.get('ttl_seconds', 0)

    try:
        storage, prior_status, prior_reason = _load_storage(namespace)

        now = time.time()
        entry = {
            'value': value,
            '_stored_at': now
        }

        if ttl_seconds and ttl_seconds > 0:
            entry['_expires_at'] = now + ttl_seconds

        storage[key] = entry
        _save_storage(namespace, storage)

        # The read-back. `_stored_at` is a float generated in THIS call, so
        # finding it under this key is a fact that could not have been true
        # before the write -- which is what separates evidence from a
        # coincidence a previous run left behind.
        reloaded, reload_status, reload_reason = _load_storage(namespace)
        stored = reloaded.get(key) if reload_status != UNREADABLE else None
        landed = isinstance(stored, dict) and stored.get('_stored_at') == now

        result = {
            'ok': True,
            'key': key,
            'stored_at': now,
            'outcome': _set_outcome(
                namespace=namespace,
                key=key,
                landed=landed,
                stored=stored,
                value=value,
                reload_status=reload_status,
                reload_reason=reload_reason,
                prior_status=prior_status,
                prior_reason=prior_reason,
            ),
        }

        if ttl_seconds and ttl_seconds > 0:
            result['expires_at'] = entry['_expires_at']

        return result

    except Exception as e:
        logger.error(f"Storage set error: {e}")
        return {
            'ok': False,
            'error': str(e),
            'error_code': 'STORAGE_ERROR',
            'key': key,
            'outcome': _error_envelope(operation='set', namespace=namespace, error=str(e)),
        }


def _set_outcome(
    *,
    namespace: str,
    key: str,
    landed: bool,
    stored: Optional[Dict[str, Any]],
    value: Any,
    reload_status: str,
    reload_reason: Optional[str],
    prior_status: str,
    prior_reason: Optional[str],
) -> Dict[str, Any]:
    """The rung this write earned, from the reload.

    OBSERVED needs the reload to find the key carrying this call's timestamp.
    Anything else is INDETERMINATE: a namespace that will not parse after we
    wrote it, or a key that is not there, are both states in which what happened
    to the data is genuinely unknown.

    `value_round_tripped` is reported but deliberately does NOT gate the rung.
    JSON is lossy in ways that are nobody's fault -- a tuple returns as a list,
    an integer dict key returns as a string -- so an inequality there is not
    evidence the write went wrong, and gating on it would mark correct writes
    indeterminate.
    """
    effects = []

    # Reported whether or not the write landed: a namespace that could not be
    # parsed before this call has just been REPLACED by one holding a single
    # key, and the keys that were in it are gone. The rung is about the effect
    # this call performed, so it stays OBSERVED when the read-back succeeds --
    # but the collateral belongs in the payload, not nowhere.
    if prior_status == UNREADABLE:
        effects.append({
            'kind': 'prior_namespace_discarded',
            'namespace': namespace,
            'measured_by': None,
            'reason': prior_reason,
            'detail': (
                'The namespace file could not be parsed before this write, so '
                'it was treated as empty and has now been overwritten. Any keys '
                'it held are gone. This says nothing about the key just '
                'written, which is what the rung is about.'
            ),
        })

    if landed:
        effects.append({
            'kind': 'value_stored',
            'namespace': namespace,
            'key': key,
            'stored_at': stored.get('_stored_at') if stored else None,
            'value_round_tripped': bool(stored) and stored.get('value') == value,
            'measured_by': (
                'the namespace reloaded from disk after the write, matched on '
                'the _stored_at timestamp generated by this call'
            ),
            'detail': (
                'The key is in the file with this call\'s timestamp, which no '
                'earlier run could have written. value_round_tripped reports '
                'whether the parsed value also compares equal; it does not gate '
                'the rung, because JSON turns tuples into lists and integer keys '
                'into strings without anything being wrong.'
            ),
        })
        return envelope(Outcome.OBSERVED, claim_by=ClaimBy.INFERRED, effects=effects)

    effects.append({
        'kind': 'value_not_confirmed',
        'namespace': namespace,
        'key': key,
        'predicate': "reloaded[key]['_stored_at'] == the timestamp this call generated",
        'namespace_status': reload_status,
        'measured_by': 'the namespace reloaded from disk after the write',
        'reason': reload_reason,
        'detail': (
            'The write returned without raising and the reload does not confirm '
            'it. Indeterminate rather than failed: a concurrent writer to the '
            'same namespace replaces the file between the write and the reload '
            'and reads identically here to a write that never landed.'
        ),
    })
    return envelope(Outcome.INDETERMINATE, claim_by=ClaimBy.INFERRED, effects=effects)


@register_module(
    module_id='storage.delete',
    stability='stable',
    version='1.0.0',
    category='storage',
    subcategory='kv',
    tags=['storage', 'cache', 'state', 'kv', 'memory', 'persist'],
    label='Delete Stored Value',
    label_key='modules.storage.delete.label',
    description='Delete a value from persistent key-value storage',
    description_key='modules.storage.delete.description',
    icon='Trash2',
    color='#EF4444',

    input_types=['text', 'object'],
    output_types=['object'],
    can_connect_to=['*'],
    can_receive_from=['*'],

    timeout_ms=5000,
    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema={
        'namespace': {
            'type': 'string',
            'label': 'Namespace',
            'label_key': 'modules.storage.delete.params.namespace.label',
            'description': 'Storage namespace',
            'description_key': 'modules.storage.delete.params.namespace.description',
            'required': True,
            'placeholder': 'my-workflow',
            'default': 'default'
        },
        'key': {
            'type': 'string',
            'label': 'Key',
            'label_key': 'modules.storage.delete.params.key.label',
            'description': 'Key to delete',
            'description_key': 'modules.storage.delete.params.key.description',
            'required': True,
            'placeholder': 'last_price'
        }
    },
    output_schema={
        'ok': {
            'type': 'boolean',
            'description': 'Whether the operation succeeded',
            'description_key': 'modules.storage.delete.output.ok.description'
        },
        'deleted': {
            'type': 'boolean',
            'description': (
                'Whether the key existed and was deleted. False is also the '
                'fallback when the namespace could not be parsed -- read '
                'outcome.rung to tell a finding from a fallback'
            ),
            'description_key': 'modules.storage.delete.output.deleted.description'
        },
        'key': {
            'type': 'string',
            'description': 'The key that was deleted',
            'description_key': 'modules.storage.delete.output.key.description'
        },
        'outcome': {
            'type': 'object',
            'description': (
                'How far this delete was followed into reality: observed when a '
                'reload finds the key gone, indeterminate when the namespace '
                'could not be parsed'
            ),
            'description_key': 'modules.storage.delete.output.outcome.description'
        }
    },
    examples=[
        {
            'title': 'Delete cached value',
            'title_key': 'modules.storage.delete.examples.cache.title',
            'params': {
                'namespace': 'cache',
                'key': 'api_response'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def storage_delete(context: Dict[str, Any]) -> Dict[str, Any]:
    """Delete value from key-value storage"""
    params = context['params']
    namespace = params.get('namespace', 'default')
    key = params['key']

    try:
        storage, status, reason = _load_storage(namespace)

        # Nothing is written on this path, so the stored data is intact -- but
        # `deleted: False` here means "we could not read the namespace", not
        # "the key was not there", and only the envelope can say which.
        if status == UNREADABLE:
            return {
                'ok': True,
                'deleted': False,
                'key': key,
                'outcome': _unreadable_envelope(
                    operation='delete', namespace=namespace, reason=reason
                ),
            }

        deleted = key in storage
        if deleted:
            del storage[key]
            _save_storage(namespace, storage)
            reloaded, reload_status, reload_reason = _load_storage(namespace)
            gone = reload_status != UNREADABLE and key not in reloaded
            outcome = envelope(
                Outcome.OBSERVED if gone else Outcome.INDETERMINATE,
                claim_by=ClaimBy.INFERRED,
                effects=[{
                    'kind': 'key_removed' if gone else 'key_removal_not_confirmed',
                    'namespace': namespace,
                    'key': key,
                    'predicate': 'key not in the namespace reloaded from disk',
                    'measured_by': 'the namespace reloaded from disk after the write',
                    'reason': reload_reason,
                    'detail': (
                        'The key was in the namespace, was removed, and a reload '
                        'confirms it is gone.'
                        if gone else
                        'The write returned without raising and the reload does '
                        'not confirm the removal. Indeterminate rather than '
                        'failed: a concurrent writer restoring the key reads '
                        'identically here to a delete that never landed.'
                    ),
                }],
            )
        else:
            # A clean read of the whole namespace that does not contain the key.
            # Nothing was written and nothing changed; what is observed is the
            # state the caller wanted, and `unlink_issued`-style honesty about
            # that lives in `write_issued` below.
            outcome = envelope(
                Outcome.OBSERVED,
                claim_by=ClaimBy.NONE,
                effects=[{
                    'kind': 'key_already_absent',
                    'namespace': namespace,
                    'key': key,
                    'namespace_status': status,
                    'write_issued': False,
                    'measured_by': (
                        'the parsed namespace file, searched for the key'
                        if status == LOADED else
                        'os.path.exists on the namespace file: it is not there'
                    ),
                    'detail': (
                        'The namespace was read and does not hold this key. No '
                        'write was issued -- nothing changed, and what is '
                        'observed is that the desired end state already held.'
                    ),
                }],
            )

        return {
            'ok': True,
            'deleted': deleted,
            'key': key,
            'outcome': outcome,
        }

    except Exception as e:
        logger.error(f"Storage delete error: {e}")
        return {
            'ok': False,
            'error': str(e),
            'error_code': 'STORAGE_ERROR',
            'key': key,
            'outcome': _error_envelope(operation='delete', namespace=namespace, error=str(e)),
        }
