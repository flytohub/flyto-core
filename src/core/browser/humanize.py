# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Human-like Browser Behavior — Simulate realistic user interactions

Profiles:
    fast: No delays, direct actions (maximum speed)
    normal: Small delays, basic randomization
    careful: Moderate delays, mouse movement, random scrolls
    human_like: Full simulation — mouse curves, reading time, scroll patterns
"""
import asyncio
import logging
import random

logger = logging.getLogger(__name__)

# Timing ranges in milliseconds: (min, max)
PROFILES = {
    'fast': {
        'click_delay': (0, 0),
        'type_delay': (0, 0),        # per character
        'scroll_delay': (0, 0),
        'page_think_time': (0, 0),
        'mouse_move': False,
        'random_scroll': False,
        'typo_rate': 0.0,
    },
    'normal': {
        'click_delay': (50, 200),
        'type_delay': (30, 80),
        'scroll_delay': (100, 300),
        'page_think_time': (500, 1500),
        'mouse_move': False,
        'random_scroll': False,
        'typo_rate': 0.0,
    },
    'careful': {
        'click_delay': (100, 400),
        'type_delay': (50, 120),
        'scroll_delay': (200, 600),
        'page_think_time': (1000, 3000),
        'mouse_move': True,
        'random_scroll': True,
        'typo_rate': 0.0,
    },
    'human_like': {
        'click_delay': (200, 800),
        'type_delay': (80, 200),
        'scroll_delay': (300, 1000),
        'page_think_time': (2000, 6000),
        'mouse_move': True,
        'random_scroll': True,
        'typo_rate': 0.02,  # 2% chance per character
    },
}


class HumanBehavior:
    """Simulates human-like browser behavior based on profile."""

    PROFILES = list(PROFILES.keys())

    def __init__(self, profile: str = 'fast'):
        if profile not in PROFILES:
            raise ValueError(f"Unknown profile: {profile}. Use: {list(PROFILES.keys())}")
        self.profile = profile
        self._config = PROFILES[profile]

    @property
    def is_fast(self) -> bool:
        return self.profile == 'fast'

    def _rand_ms(self, key: str) -> float:
        lo, hi = self._config[key]
        if lo == 0 and hi == 0:
            return 0
        return random.uniform(lo, hi)

    async def before_click(self, page, selector=None):
        """Simulate human behavior before clicking an element."""
        if self.is_fast:
            return

        # Move mouse to element with natural curve
        if self._config['mouse_move'] and selector:
            try:
                el = await page.query_selector(selector)
                if el:
                    box = await el.bounding_box()
                    if box:
                        # Humans don't click dead center
                        x = box['x'] + box['width'] * random.uniform(0.25, 0.75)
                        y = box['y'] + box['height'] * random.uniform(0.25, 0.75)
                        steps = random.randint(5, 15)
                        await page.mouse.move(x, y, steps=steps)
            except Exception:
                pass

        delay = self._rand_ms('click_delay')
        if delay > 0:
            await asyncio.sleep(delay / 1000)

    async def before_type(self, page):
        """Simulate pause before typing (focus delay)."""
        # Use half the type_delay range as focus time (shorter than click)
        lo, hi = self._config['type_delay']
        if lo == 0 and hi == 0:
            return
        delay = random.uniform(lo * 0.3, hi * 0.6)
        if delay > 0:
            await asyncio.sleep(delay / 1000)

    def get_type_delay(self) -> int:
        """Get per-character typing delay in ms."""
        return int(self._rand_ms('type_delay'))

    @property
    def typo_rate(self) -> float:
        return self._config['typo_rate']

    async def after_navigation(self, page):
        """Simulate reading/thinking time after page load."""
        if self.is_fast:
            return

        think_time = self._rand_ms('page_think_time')
        if think_time > 0:
            await asyncio.sleep(think_time / 1000)

        # Random scroll to simulate reading
        if self._config['random_scroll']:
            try:
                scroll_amount = random.randint(100, 500)
                await page.evaluate(f'window.scrollBy(0, {scroll_amount})')
                await asyncio.sleep(random.uniform(0.3, 1.0))
                # Scroll back partially (humans don't scroll perfectly)
                await page.evaluate(f'window.scrollBy(0, {-scroll_amount // 2})')
            except Exception:
                pass

    async def before_scroll(self, page):
        """Simulate delay before scrolling."""
        delay = self._rand_ms('scroll_delay')
        if delay > 0:
            await asyncio.sleep(delay / 1000)
