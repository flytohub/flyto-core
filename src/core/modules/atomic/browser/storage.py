# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Storage Module

Access localStorage and sessionStorage.

SIX ACTIONS, AND THREE OF THEM USED TO REPORT A CONSTANT

There is no single rung for this module, for the same reason `database.query`
has none: the six actions measure different amounts, and three of them measured
nothing at all before this change.

  get / keys / length      OBSERVED
      The value, the key list and the count all cross back from the page's
      storage object. Nothing is inferred.

      ``get`` is OBSERVED even when it returns null, and that is a real
      difference from `database.query`, where an empty result set is only
      ACCEPTED. ``getItem`` answers about ONE key and returns null for exactly
      one reason -- that key is not in the store. An empty SQL result set has
      several possible reasons and cannot say which. Absence measured is an
      observation; absence that might be silence is not.

  set                      OBSERVED / INDETERMINATE
      It returned ``"value": self.value`` -- the caller's own parameter,
      unchanged, whatever the store did with it. Now the key is read back and
      compared. Note the store is a string store: ``setItem(k, 5)`` and
      ``getItem(k) == '5'``, so the comparison is against ``str(value)``, which
      is the same coercion the write already applied.

  remove                   OBSERVED / INDETERMINATE
      It returned ``"removed": True``. A literal. It was True when the key was
      removed, True when the key never existed, and True if the store had
      rejected the call. Now: the key is read back, and gone means gone.

  clear                    OBSERVED / INDETERMINATE
      It returned ``"cleared": True``. Same literal, same problem. Now:
      ``length`` is read back and zero means empty.

The failing read-backs are INDETERMINATE and not FAILED because nobody declared
a postcondition here, the comparison is this module's own inference, and a page
script that writes the key back between the two evaluates would produce it
without anything being broken.
"""
from typing import Any, Dict, List, Optional

from ....engine.outcome import ClaimBy, Outcome, envelope
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets


def _read_outcome(*, action: str, storage_name: str, measured: str, value: Any) -> Dict[str, Any]:
    """OBSERVED for the three actions that only look.

    A value that came out of the page's storage object is a measurement of it,
    including ``None`` from ``getItem``: that answers about one key and means
    that key is absent, which is a fact rather than a silence.
    """
    return envelope(
        Outcome.OBSERVED,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'storage_read',
            'action': action,
            'storage': storage_name,
            'measured_by': measured,
            'result_type': type(value).__name__,
            'detail': (
                'Read out of the page\'s storage object. null from getItem is '
                'itself an observation: it means this key is not in the store.'
            ),
        }],
    )


def _write_outcome(
    *,
    action: str,
    storage_name: str,
    holds: bool,
    predicate: str,
    measured: str,
    observed_detail: str,
    unmet_detail: str,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """OBSERVED / INDETERMINATE for the three actions that change the store.

    `holds` is always the result of an evaluate that ran AFTER the write, never
    a constant. That is the whole of the difference from what these three
    actions reported before.
    """
    effect = {
        'kind': 'storage_write_observed' if holds else 'storage_write_unconfirmed',
        'action': action,
        'storage': storage_name,
        'predicate': predicate,
        'measured_by': measured,
        'detail': observed_detail if holds else unmet_detail,
    }
    effect.update(extra or {})
    if holds:
        return envelope(Outcome.OBSERVED, claim_by=ClaimBy.INFERRED, effects=[effect])
    return envelope(Outcome.INDETERMINATE, claim_by=ClaimBy.INFERRED, effects=[effect])


@register_module(
    module_id='browser.storage',
    version='1.0.0',
    category='browser',
    tags=['browser', 'storage', 'localStorage', 'sessionStorage', 'ssrf_protected', 'path_restricted'],
    label='Browser Storage',
    label_key='modules.browser.storage.label',
    description='Access localStorage and sessionStorage',
    description_key='modules.browser.storage.description',
    icon='Database',
    color='#6610F2',

    # Connection types
    input_types=['page'],
    output_types=['string', 'json'],


    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*', 'ai.*', 'llm.*', 'agent.*'],    params_schema=compose(
        presets.BROWSER_ACTION(options=['get', 'set', 'remove', 'clear', 'keys', 'length']),
        presets.STORAGE_TYPE(),
        presets.STORAGE_KEY(),
        presets.STORAGE_VALUE(),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.browser.storage.output.status.description'},
        'value': {'type': 'any', 'description': 'The returned value',
                'description_key': 'modules.browser.storage.output.value.description'},
        'keys': {'type': 'array', 'description': 'List of keys',
                'description_key': 'modules.browser.storage.output.keys.description'},
        'length': {'type': 'number', 'description': 'Length of data',
                'description_key': 'modules.browser.storage.output.length.description'},
        'stored_value': {'type': 'string', 'description': (
                    'For the set action: what the store returns for the key '
                    'afterwards. `value` is the parameter that was sent'
                ),
                'description_key': 'modules.browser.storage.output.stored_value.description'},
        'removed': {'type': 'boolean', 'description': (
                    'For the remove action: whether the key is absent from the '
                    'store afterwards, read back rather than asserted'
                ),
                'description_key': 'modules.browser.storage.output.removed.description'},
        'cleared': {'type': 'boolean', 'description': (
                    'For the clear action: whether the store is empty '
                    'afterwards, read back rather than asserted'
                ),
                'description_key': 'modules.browser.storage.output.cleared.description'},
        'remaining': {'type': 'number', 'description': (
                    'For the clear action: how many entries the store still '
                    'reports'
                ),
                'description_key': 'modules.browser.storage.output.remaining.description'},
        'outcome': {'type': 'object', 'description': (
                    'How far this action was followed, decided per action: '
                    'observed for the reads and for a write the store confirms, '
                    'indeterminate when the read-back disagrees'
                ),
                'description_key': 'modules.browser.storage.output.outcome.description'}
    },
    examples=[
        {
            'name': 'Get value from localStorage',
            'params': {'action': 'get', 'type': 'local', 'key': 'user_token'}
        },
        {
            'name': 'Set value in sessionStorage',
            'params': {'action': 'set', 'type': 'session', 'key': 'temp_data', 'value': '{"id": 123}'}
        },
        {
            'name': 'Clear localStorage',
            'params': {'action': 'clear', 'type': 'local'}
        },
        {
            'name': 'Get all keys',
            'params': {'action': 'keys', 'type': 'local'}
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=30000,
    required_permissions=["browser.automation"],
)
class BrowserStorageModule(BaseModule):
    """Browser Storage Module"""

    module_name = "Browser Storage"
    module_description = "Access localStorage and sessionStorage"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        if 'action' not in self.params:
            raise ValueError("Missing required parameter: action")

        self.action = self.params['action']
        if self.action not in ['get', 'set', 'remove', 'clear', 'keys', 'length']:
            raise ValueError(f"Invalid action: {self.action}")

        self.storage_type = self.params.get('type', 'local')
        if self.storage_type not in ['local', 'session']:
            raise ValueError(f"Invalid storage type: {self.storage_type}")

        self.key = self.params.get('key')
        self.value = self.params.get('value')

        if self.action in ['get', 'remove'] and not self.key:
            raise ValueError(f"{self.action} action requires key")
        if self.action == 'set' and (not self.key or self.value is None):
            raise ValueError("set action requires key and value")

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        page = browser.page
        storage_name = 'localStorage' if self.storage_type == 'local' else 'sessionStorage'

        if self.action == 'get':
            value = await page.evaluate(
                '([storageName, key]) => window[storageName].getItem(key)',
                [storage_name, self.key]
            )
            return {
                "status": "success",
                "key": self.key,
                "value": value,
                "outcome": _read_outcome(
                    action='get', storage_name=storage_name,
                    measured=f'{storage_name}.getItem(key) evaluated in the page',
                    value=value,
                ),
            }

        elif self.action == 'set':
            # The store coerces to string, so the write and the read-back are
            # compared on the same side of that coercion.
            written = str(self.value)
            await page.evaluate(
                '([storageName, key, value]) => window[storageName].setItem(key, value)',
                [storage_name, self.key, written]
            )
            stored = await page.evaluate(
                '([storageName, key]) => window[storageName].getItem(key)',
                [storage_name, self.key]
            )
            return {
                "status": "success",
                "key": self.key,
                "value": self.value,
                "stored_value": stored,
                "outcome": _write_outcome(
                    action='set', storage_name=storage_name,
                    holds=stored == written,
                    predicate='getItem(key) == str(value) after the write',
                    measured=f'{storage_name}.getItem(key) evaluated after the write',
                    observed_detail=(
                        'The store returns the value that was written. '
                        '`value` in this result is the parameter; `stored_value` '
                        'is what the page holds.'
                    ),
                    unmet_detail=(
                        'The store does not return what was written. A page '
                        'script may have overwritten the key between the two '
                        'evaluates, so this is indeterminate rather than failed.'
                    ),
                ),
            }

        elif self.action == 'remove':
            await page.evaluate(
                '([storageName, key]) => window[storageName].removeItem(key)',
                [storage_name, self.key]
            )
            still_present = await page.evaluate(
                '([storageName, key]) => window[storageName].getItem(key) !== null',
                [storage_name, self.key]
            )
            return {
                "status": "success",
                "key": self.key,
                # Read back, not asserted. This used to be a literal True.
                "removed": not still_present,
                "outcome": _write_outcome(
                    action='remove', storage_name=storage_name,
                    holds=not still_present,
                    predicate='getItem(key) is null after the removal',
                    measured=f'{storage_name}.getItem(key) evaluated after the removal',
                    observed_detail=(
                        'The key is not in the store. Removing a key that was '
                        'never there lands here too, and truthfully: the '
                        'postcondition is about the store, not about a delta.'
                    ),
                    unmet_detail=(
                        'The key is still in the store after removeItem. A page '
                        'script writing it back would do this, so this is '
                        'indeterminate rather than failed.'
                    ),
                ),
            }

        elif self.action == 'clear':
            await page.evaluate(
                '(storageName) => window[storageName].clear()',
                storage_name
            )
            remaining = await page.evaluate(
                '(storageName) => window[storageName].length',
                storage_name
            )
            return {
                "status": "success",
                # Read back, not asserted. This used to be a literal True.
                "cleared": remaining == 0,
                "remaining": remaining,
                "outcome": _write_outcome(
                    action='clear', storage_name=storage_name,
                    holds=remaining == 0,
                    predicate='length == 0 after the clear',
                    measured=f'{storage_name}.length evaluated after the clear',
                    observed_detail='The store is empty.',
                    unmet_detail=(
                        'The store is not empty after clear(). A page script '
                        'writing during the call would do this, so this is '
                        'indeterminate rather than failed.'
                    ),
                    extra={'remaining': remaining},
                ),
            }

        elif self.action == 'keys':
            keys = await page.evaluate('''
                (storageName) => {
                    const storage = window[storageName];
                    const keys = [];
                    for (let i = 0; i < storage.length; i++) {
                        keys.push(storage.key(i));
                    }
                    return keys;
                }
            ''', storage_name)
            return {
                "status": "success",
                "keys": keys,
                "count": len(keys),
                "outcome": _read_outcome(
                    action='keys', storage_name=storage_name,
                    measured=f'a walk of {storage_name}.key(i) evaluated in the page',
                    value=keys,
                ),
            }

        elif self.action == 'length':
            length = await page.evaluate(
                '(storageName) => window[storageName].length',
                storage_name
            )
            return {
                "status": "success",
                "length": length,
                "outcome": _read_outcome(
                    action='length', storage_name=storage_name,
                    measured=f'{storage_name}.length evaluated in the page',
                    value=length,
                ),
            }
