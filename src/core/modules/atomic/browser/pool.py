# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Pool Module — Manage multiple browser instances

Create named browser instances for parallel automation.
Each instance has its own context (cookies, storage, profile).

Usage:
  browser.pool(action='create', name='scraper1') → creates new browser
  browser.pool(action='switch', name='scraper1') → switches active browser
  browser.pool(action='close', name='scraper1') → closes specific instance
  browser.pool(action='list') → list all active instances
  browser.pool(action='close_all') → close all instances

FIVE ACTIONS, THREE OF WHICH NEVER TOUCH A BROWSER

``count`` was this module's only number and it is ``len(_browser_pool)`` — the
size of the dictionary two lines above. It is identical whether every driver in
it is running, hung, or was killed by the OS an hour ago, so it is evidence of
nothing at all. Only the actions that actually reach a browser can say more:

    create      OBSERVED when the started process reports its version,
                ACCEPTED when there is no Browser object to ask.
    close       OBSERVED when the Browser held across close() reports its
                connection gone, INDETERMINATE while it is still live,
                ACCEPTED when there was none to ask.
    close_all   the same, aggregated: OBSERVED only when every driver that
                could be asked reported the connection gone.

    switch      no envelope. It rebinds ``self.context['browser']`` and reaches
                nothing; see the defect note below.
    list        no envelope. It reads the dictionary and stops.

    close on a name that is not in the pool also writes no envelope: nothing was
    attempted, and the ladder has no rung meaning "no instruction was issued".

KNOWN DEFECT, NOT FIXED HERE: CROSS-EXECUTION DRIVER ADOPTION

``_browser_pool`` is a module-global keyed only by a caller-supplied string, and
it lives as long as the process. Nothing in it is scoped to a workflow, a run,
or a tenant. So in any host that runs more than one execution per process:

  * ``switch`` with a guessed or shared name adopts ANOTHER execution's live
    driver into this execution's context — with that execution's cookies,
    storage and logged-in sessions — and reports ``status: success``;
  * ``create`` with a name another execution is using closes that execution's
    browser out from under it (``_create`` closes the incumbent first);
  * ``close_all`` closes every browser in the process, including ones this
    workflow never opened, and then reports ``count: 0``.

This is a scoping bug in the pool key, not something an outcome rung can repair:
the driver really is adopted, so a truthful envelope on ``switch`` would confirm
a session was taken over rather than warn about it. Reported, not fixed — the
fix is a per-execution namespace on the pool, and it changes behaviour that
existing workflows may lean on.
"""
import logging
from typing import Any, Dict, List, Optional

from ....engine.outcome import envelope
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field
from ._session_outcome import (
    browser_object,
    closed_claim,
    observe_disconnected,
    read_engine,
    started_claim,
)

logger = logging.getLogger(__name__)

# Module-level pool storage (shared across all executions in same process)
#
# SCOPING DEFECT: see the module docstring. The key is a caller-supplied string
# with no execution, run or tenant component, so two workflows in one process
# share this dictionary and can adopt or close each other's browsers.
_browser_pool: Dict[str, Any] = {}


def _close_all_outcome(readings: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The rung a close_all earned, from every driver it could ask.

    Aggregation is by the weakest reading, not the average and not the majority:
    one browser still holding a live connection means "all closed" is not
    established, whatever the other four say. An empty pool gets no envelope —
    nothing was attempted.
    """
    if not readings:
        return None

    still_connected = [r['name'] for r in readings if r['disconnected'] is False]
    not_observed = [r['name'] for r in readings if r['disconnected'] is None]
    disconnected = [r['name'] for r in readings if r['disconnected'] is True]

    shared = {
        'browsers_asked': len(readings),
        'browsers_disconnected': len(disconnected),
        'browsers_still_connected': len(still_connected),
        'browsers_not_observed': len(not_observed),
    }

    if still_connected:
        rung, claim_by, reading = closed_claim(
            disconnected=False, reason=None, extra=shared
        )
    elif not disconnected:
        rung, claim_by, reading = closed_claim(
            disconnected=None,
            reason='no Browser object to ask for any driver in the pool',
            extra=shared,
        )
    else:
        rung, claim_by, reading = closed_claim(
            disconnected=True, reason=None, extra=shared
        )
    return envelope(rung, claim_by=claim_by, effects=[reading])


@register_module(
    module_id='browser.pool',
    version='1.0.0',
    category='browser',
    tags=['browser', 'parallel', 'pool', 'multi', 'concurrent'],
    label='Browser Pool',
    label_key='modules.browser.pool.label',
    description='Manage multiple named browser instances for parallel automation.',
    description_key='modules.browser.pool.description',
    icon='Layers',
    color='#6366F1',
    input_types=['page', 'browser'],
    output_types=['browser', 'page'],
    can_receive_from=['browser.*', 'flow.*', 'start'],
    can_connect_to=['browser.*', 'flow.*', 'ai.*', 'llm.*', 'agent.*'],
    params_schema=compose(
        field('action', type='select', label='Action',
              required=True, default='create',
              options=[
                  {'value': 'create', 'label': 'Create new browser'},
                  {'value': 'switch', 'label': 'Switch to existing browser'},
                  {'value': 'close', 'label': 'Close specific browser'},
                  {'value': 'list', 'label': 'List all browsers'},
                  {'value': 'close_all', 'label': 'Close all browsers'},
              ],
              group='basic'),
        field('name', type='string', label='Browser name',
              description='Unique name for this browser instance.',
              required=False, default='default', placeholder='scraper1',
              group='basic'),
        field('headless', type='boolean', label='Headless',
              description='Run in headless mode (for create action).',
              default=True, required=False,
              group='basic'),
        field('stealth', type='boolean', label='Stealth mode',
              description='Apply anti-detection patches (for create action).',
              default=True, required=False,
              group='basic'),
    ),
    output_schema={
        'action':   {'type': 'string',  'description': 'Action performed'},
        'name':     {'type': 'string',  'description': 'Browser name'},
        'pool':     {'type': 'array',   'description': 'All active browser names (for list action)'},
        'count':    {'type': 'number',  'description': 'Number of active browsers, as this module tracks them — the size of its own dictionary, not a count of live processes'},
        'outcome':  {'type': 'object',  'description': (
            'How far the effect was followed, decided per action: observed when '
            'a created process reported its version or a closed one reported '
            'its connection gone, indeterminate while a closed browser is still '
            'connected, accepted when there was nothing to ask. Absent for '
            'switch and list, which reach no browser.'
        )},
    },
    examples=[
        {'name': 'Create named browser', 'params': {'action': 'create', 'name': 'scraper1'}},
        {'name': 'Switch to browser', 'params': {'action': 'switch', 'name': 'scraper1'}},
        {'name': 'List all browsers', 'params': {'action': 'list'}},
    ],
    author='Flyto2 Team', license='MIT', timeout_ms=30000,
    required_permissions=["browser.read", "browser.write"],
)
class BrowserPoolModule(BaseModule):
    module_name = "Browser Pool"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        self.action = self.params.get('action', 'create')
        self.name = self.params.get('name', 'default')
        self.headless = self.params.get('headless', True)
        self.stealth = self.params.get('stealth', True)

    async def execute(self) -> Any:
        global _browser_pool

        if self.action == 'create':
            return await self._create()
        elif self.action == 'switch':
            return self._switch()
        elif self.action == 'close':
            return await self._close()
        elif self.action == 'list':
            return self._list()
        elif self.action == 'close_all':
            return await self._close_all()
        else:
            raise ValueError(f"Unknown action: {self.action}")

    async def _create(self) -> dict:
        from core.browser.driver import BrowserDriver

        # Close existing if same name
        if self.name in _browser_pool:
            try:
                await _browser_pool[self.name].close()
            except Exception:
                pass

        driver = BrowserDriver(headless=self.headless)
        await driver.launch(stealth=self.stealth)

        _browser_pool[self.name] = driver
        self.context['browser'] = driver
        self.context['browser_pool_active'] = self.name

        logger.info("Created browser '%s' (pool size: %d)", self.name, len(_browser_pool))

        engine, version, reason = read_engine(driver)
        rung, claim_by, reading = started_claim(
            engine=engine,
            version=version,
            requested_engine=getattr(driver, 'browser_type', None),
            reason=reason,
        )

        return {
            "status": "success",
            "action": "create",
            "name": self.name,
            "pool": list(_browser_pool.keys()),
            "count": len(_browser_pool),
            "engine_version": version,
            "outcome": envelope(rung, claim_by=claim_by, effects=[reading]),
        }

    def _switch(self) -> dict:
        # No envelope, and not for want of a value to report. This action
        # rebinds a dictionary entry into self.context and reaches no browser at
        # all: the only thing it could measure is is_connected(), which is born
        # True and says nothing in that direction. See the module docstring for
        # the cross-execution adoption defect this action carries.
        if self.name not in _browser_pool:
            raise ValueError(f"Browser '{self.name}' not found in pool. Available: {list(_browser_pool.keys())}")

        driver = _browser_pool[self.name]
        self.context['browser'] = driver
        self.context['browser_pool_active'] = self.name

        logger.info("Switched to browser '%s'", self.name)

        return {
            "status": "success",
            "action": "switch",
            "name": self.name,
            "pool": list(_browser_pool.keys()),
            "count": len(_browser_pool),
        }

    async def _close(self) -> dict:
        found = None
        if self.name in _browser_pool:
            driver = _browser_pool[self.name]
            # Held across close(): the driver drops its own reference whether
            # the teardown worked or a step timed out and was swallowed.
            held = browser_object(driver)
            try:
                await driver.close()
            except Exception:
                pass
            found = observe_disconnected(held)
            del _browser_pool[self.name]

            # If we closed the active browser, clear context
            if self.context.get('browser_pool_active') == self.name:
                self.context.pop('browser', None)
                self.context.pop('browser_pool_active', None)

        logger.info("Closed browser '%s' (pool size: %d)", self.name, len(_browser_pool))

        result = {
            "status": "success",
            "action": "close",
            "name": self.name,
            "pool": list(_browser_pool.keys()),
            "count": len(_browser_pool),
        }
        if found is not None:
            disconnected, reason = found
            rung, claim_by, reading = closed_claim(
                disconnected=disconnected, reason=reason, extra={'name': self.name}
            )
            result["outcome"] = envelope(rung, claim_by=claim_by, effects=[reading])
        # No envelope when the name was not in the pool: nothing was attempted,
        # and no rung means "no instruction was issued".
        return result

    def _list(self) -> dict:
        # No envelope: every value below is read out of this module's own
        # dictionary. `count` would be unchanged if all five browsers in it had
        # been killed, which is the exact test this contract applies.
        return {
            "status": "success",
            "action": "list",
            "name": self.context.get('browser_pool_active', ''),
            "pool": list(_browser_pool.keys()),
            "count": len(_browser_pool),
        }

    async def _close_all(self) -> dict:
        closed = 0
        readings: List[Dict[str, Any]] = []
        for name, driver in list(_browser_pool.items()):
            held = browser_object(driver)
            try:
                await driver.close()
                closed += 1
            except Exception:
                pass
            disconnected, reason = observe_disconnected(held)
            readings.append({'name': name, 'disconnected': disconnected, 'reason': reason})
        _browser_pool.clear()
        self.context.pop('browser', None)
        self.context.pop('browser_pool_active', None)

        logger.info("Closed all %d browsers", closed)

        result = {
            "status": "success",
            "action": "close_all",
            "name": "",
            "pool": [],
            # A literal, and the honest reading of it: the dictionary is empty
            # because it was cleared two lines up, not because any process died.
            "count": 0,
        }
        found = _close_all_outcome(readings)
        if found is not None:
            result["outcome"] = found
        return result
