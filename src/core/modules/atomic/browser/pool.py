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
"""
import logging
from typing import Any, Dict, Optional
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field

logger = logging.getLogger(__name__)

# Module-level pool storage (shared across all executions in same process)
_browser_pool: Dict[str, Any] = {}


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
        'count':    {'type': 'number',  'description': 'Number of active browsers'},
    },
    examples=[
        {'name': 'Create named browser', 'params': {'action': 'create', 'name': 'scraper1'}},
        {'name': 'Switch to browser', 'params': {'action': 'switch', 'name': 'scraper1'}},
        {'name': 'List all browsers', 'params': {'action': 'list'}},
    ],
    author='Flyto Team', license='MIT', timeout_ms=30000,
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

        return {
            "status": "success",
            "action": "create",
            "name": self.name,
            "pool": list(_browser_pool.keys()),
            "count": len(_browser_pool),
        }

    def _switch(self) -> dict:
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
        if self.name in _browser_pool:
            try:
                await _browser_pool[self.name].close()
            except Exception:
                pass
            del _browser_pool[self.name]

            # If we closed the active browser, clear context
            if self.context.get('browser_pool_active') == self.name:
                self.context.pop('browser', None)
                self.context.pop('browser_pool_active', None)

        logger.info("Closed browser '%s' (pool size: %d)", self.name, len(_browser_pool))

        return {
            "status": "success",
            "action": "close",
            "name": self.name,
            "pool": list(_browser_pool.keys()),
            "count": len(_browser_pool),
        }

    def _list(self) -> dict:
        return {
            "status": "success",
            "action": "list",
            "name": self.context.get('browser_pool_active', ''),
            "pool": list(_browser_pool.keys()),
            "count": len(_browser_pool),
        }

    async def _close_all(self) -> dict:
        closed = 0
        for name, driver in list(_browser_pool.items()):
            try:
                await driver.close()
                closed += 1
            except Exception:
                pass
        _browser_pool.clear()
        self.context.pop('browser', None)
        self.context.pop('browser_pool_active', None)

        logger.info("Closed all %d browsers", closed)

        return {
            "status": "success",
            "action": "close_all",
            "name": "",
            "pool": [],
            "count": 0,
        }
