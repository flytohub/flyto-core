# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Pool — Multiple concurrent browser instances

Each browser instance can have its own proxy, enabling
parallel scraping with IP rotation.
"""
import asyncio
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class PoolTaskError:
    """Structured error from a pool task, distinguishable from real results."""

    def __init__(self, error: str, retryable: bool = True):
        self.error = error
        self.retryable = retryable

    def to_dict(self) -> dict:
        return {'error': self.error, 'retryable': self.retryable}

    def __repr__(self):
        return f"PoolTaskError({self.error!r}, retryable={self.retryable})"


class BrowserPool:
    """Manages a pool of BrowserDriver instances for concurrent operations.

    Usage:
        pool = BrowserPool(size=3)
        await pool.launch_all(headless=True, proxy_pool=proxy_pool, ...)

        # Acquire/release pattern
        driver = await pool.acquire()
        try:
            await driver.goto(url)
            data = await driver.evaluate('...')
        finally:
            await pool.release(driver)

        # Or use parallel execution
        results = await pool.map(urls, scrape_fn)

        await pool.close_all()
    """

    def __init__(self, size: int = 1):
        if size < 1:
            raise ValueError("Pool size must be >= 1")
        self.size = size
        self._browsers: list = []
        self._available: Optional[asyncio.Queue] = None
        self._launched = False
        self._launch_kwargs: Dict[str, Any] = {}

    async def launch_all(
        self,
        headless: bool = True,
        viewport: Optional[Dict[str, int]] = None,
        browser_type: str = 'chromium',
        proxy_pool=None,
        user_agent: Optional[str] = None,
        locale: Optional[str] = None,
        slow_mo: int = 0,
        channel: Optional[str] = None,
        stealth: bool = True,
        behavior: Optional[str] = None,
    ):
        """Launch all browser instances in the pool.

        Each instance gets its own proxy from proxy_pool (if provided).
        """
        from .driver import BrowserDriver

        # Store launch params for relaunch on health check failure
        self._launch_kwargs = {
            'headless': headless, 'viewport': viewport,
            'browser_type': browser_type, 'user_agent': user_agent,
            'locale': locale, 'slow_mo': slow_mo, 'channel': channel,
            'stealth': stealth, 'behavior': behavior,
        }
        self._proxy_pool = proxy_pool
        self._available = asyncio.Queue()

        for i in range(self.size):
            proxy = proxy_pool.next() if proxy_pool else None

            driver = BrowserDriver(
                headless=headless,
                viewport=viewport,
                browser_type=browser_type,
            )
            await driver.launch(
                proxy=proxy,
                user_agent=user_agent,
                locale=locale,
                slow_mo=slow_mo,
                channel=channel,
                stealth=stealth,
            )

            # Set behavior profile if provided
            if behavior:
                from .humanize import HumanBehavior
                driver._human = HumanBehavior(behavior)

            # Store proxy reference for rotation
            driver._current_proxy = proxy

            self._browsers.append(driver)
            await self._available.put(driver)
            logger.info(f"Pool browser {i + 1}/{self.size} launched (proxy={proxy})")

        self._launched = True

    async def _check_health(self, driver) -> bool:
        """Check if a browser driver is still alive."""
        try:
            if not driver._page:
                return False
            await asyncio.wait_for(
                driver._page.evaluate('1'),
                timeout=3.0,
            )
            return True
        except Exception:
            return False

    async def _relaunch_driver(self, driver) -> Any:
        """Relaunch a dead browser driver with original params."""
        from .driver import BrowserDriver

        # Close the dead one silently
        try:
            await asyncio.wait_for(driver.close(), timeout=5.0)
        except Exception:
            pass

        kw = self._launch_kwargs
        proxy = self._proxy_pool.next() if self._proxy_pool else None

        new_driver = BrowserDriver(
            headless=kw.get('headless', True),
            viewport=kw.get('viewport'),
            browser_type=kw.get('browser_type', 'chromium'),
        )
        await new_driver.launch(
            proxy=proxy,
            user_agent=kw.get('user_agent'),
            locale=kw.get('locale'),
            slow_mo=kw.get('slow_mo', 0),
            channel=kw.get('channel'),
            stealth=kw.get('stealth', True),
        )

        behavior = kw.get('behavior')
        if behavior:
            from .humanize import HumanBehavior
            new_driver._human = HumanBehavior(behavior)
        new_driver._current_proxy = proxy

        # Replace in the browsers list
        try:
            idx = self._browsers.index(driver)
            self._browsers[idx] = new_driver
        except ValueError:
            self._browsers.append(new_driver)

        logger.info(f"Pool browser relaunched (proxy={proxy})")
        return new_driver

    async def acquire(self, timeout: float = 30.0):
        """Acquire a healthy browser from the pool.

        Runs a health check on the acquired driver. If dead,
        relaunches it before returning.
        """
        if not self._launched:
            raise RuntimeError("Pool not launched. Call launch_all() first.")
        try:
            driver = await asyncio.wait_for(self._available.get(), timeout=timeout)
        except asyncio.TimeoutError:
            raise RuntimeError(f"No browser available in pool after {timeout}s")

        # Health check — relaunch if dead
        if not await self._check_health(driver):
            logger.warning("Acquired browser is dead, relaunching")
            driver = await self._relaunch_driver(driver)

        return driver

    async def release(self, driver):
        """Return a browser to the pool."""
        if self._available is not None:
            await self._available.put(driver)

    async def map(self, items: list, fn, max_concurrency: int = 0) -> List[Any]:
        """Execute fn(driver, item) for each item using pool browsers.

        Args:
            items: List of items to process
            fn: Async function(driver, item) -> result
            max_concurrency: Max concurrent tasks (0 = pool size)

        Returns:
            List of results in same order as items.
            Failed items return PoolTaskError (check with isinstance).
        """
        if not self._launched:
            raise RuntimeError("Pool not launched. Call launch_all() first.")

        concurrency = max_concurrency or self.size
        semaphore = asyncio.Semaphore(concurrency)
        results: List[Any] = [None] * len(items)

        async def _worker(idx, item):
            async with semaphore:
                driver = await self.acquire()
                try:
                    results[idx] = await fn(driver, item)
                except Exception as e:
                    is_browser_crash = 'Target closed' in str(e) or 'closed' in str(e).lower()
                    results[idx] = PoolTaskError(
                        error=str(e),
                        retryable=is_browser_crash,
                    )
                    logger.warning(f"Pool task {idx} failed: {e}")
                finally:
                    await self.release(driver)

        await asyncio.gather(*[_worker(i, item) for i, item in enumerate(items)])
        return results

    async def close_all(self):
        """Close all browser instances in the pool."""
        for i, driver in enumerate(self._browsers):
            try:
                await driver.close()
                logger.info(f"Pool browser {i + 1}/{self.size} closed")
            except Exception as e:
                logger.warning(f"Failed to close pool browser {i + 1}: {e}")
        self._browsers.clear()
        self._available = None
        self._launched = False

    @property
    def launched(self) -> bool:
        return self._launched

    @property
    def browsers(self) -> list:
        return list(self._browsers)
