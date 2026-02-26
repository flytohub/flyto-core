# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Driver - Playwright wrapper for browser automation
"""
import asyncio
import logging
import os
import shutil
import sys
from typing import Any, Dict, List, Optional
from pathlib import Path
from playwright.async_api import async_playwright, Browser, Page, ElementHandle

from ..constants import (
    DEFAULT_VIEWPORT_WIDTH,
    DEFAULT_VIEWPORT_HEIGHT,
    DEFAULT_BROWSER_TIMEOUT_MS,
    DEFAULT_USER_AGENT,
)


logger = logging.getLogger(__name__)

# Node.js version to auto-download when system node is unavailable
_NODE_VERSION = '20.18.3'


def _find_external_node() -> Optional[str]:
    """Find a usable Node.js binary outside the PyInstaller temp dir.

    Only uses the auto-downloaded copy at ~/.flyto/node/ to avoid
    version/PATH issues with nvm, fnm, or system-installed node.
    """
    import platform as _platform

    flyto_node = Path.home() / '.flyto' / 'node' / 'bin' / 'node'
    if _platform.system() == 'Windows':
        flyto_node = Path.home() / '.flyto' / 'node' / 'node.exe'
    if flyto_node.exists():
        return str(flyto_node)

    return None


class BrowserDriver:
    """
    Playwright-based browser automation driver

    Provides high-level methods for browser control:
    - Launch and close browsers
    - Navigate to URLs
    - Click, type, wait for elements
    - Extract data from pages
    - Take screenshots
    """

    def __init__(self,
                 headless: bool = True,
                 viewport: Optional[Dict[str, int]] = None,
                 browser_type: str = 'chromium'):
        """
        Initialize browser driver

        Args:
            headless: Run browser in headless mode
            viewport: Browser viewport size (e.g., {'width': 1920, 'height': 1080})
            browser_type: Browser type ('chromium', 'firefox', 'webkit')
        """
        self.headless = headless
        self.viewport = viewport or {'width': DEFAULT_VIEWPORT_WIDTH, 'height': DEFAULT_VIEWPORT_HEIGHT}
        self.browser_type = browser_type

        # Playwright objects
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._page: Optional[Page] = None
        self._context = None
        # Track whether a snapshot was taken since last navigation.
        # Used by modules to auto-snapshot before interaction.
        self._snapshot_since_nav = False

    async def launch(
        self,
        proxy: Optional[str] = None,
        user_agent: Optional[str] = None,
        locale: Optional[str] = None,
        slow_mo: int = 0,
        record_video_dir: Optional[str] = None,
        record_video_size: Optional[Dict[str, int]] = None,
    ) -> Dict[str, Any]:
        """
        Launch browser instance

        Args:
            proxy: HTTP/SOCKS proxy server URL (e.g., 'http://proxy:8080')
            user_agent: Custom user agent string (overrides default)
            slow_mo: Delay between actions in milliseconds
            record_video_dir: Directory to save recorded videos (enables Playwright video recording)
            record_video_size: Video resolution (e.g., {'width': 1280, 'height': 720}). Defaults to viewport size.

        Returns:
            Status dictionary
        """
        try:
            logger.info(f"Launching {self.browser_type} browser (headless={self.headless})")

            # PyInstaller --onefile: the bundled Node.js binary crashes with
            # "Failed to reserve virtual memory for CodeRange" because the
            # 2 GB temp extraction exhausts virtual address space.
            # Use an external node binary instead.
            if getattr(sys, 'frozen', False) and not os.environ.get('PLAYWRIGHT_NODEJS_PATH'):
                node_path = _find_external_node()
                if node_path:
                    os.environ['PLAYWRIGHT_NODEJS_PATH'] = node_path
                    logger.info(f"Using external node for Playwright: {node_path}")

            self._playwright = await async_playwright().start()

            # Select browser type
            if self.browser_type == 'firefox':
                browser_launcher = self._playwright.firefox
            elif self.browser_type == 'webkit':
                browser_launcher = self._playwright.webkit
            else:
                browser_launcher = self._playwright.chromium

            # Build launch options with anti-detection args
            import platform
            launch_args = [
                '--disable-blink-features=AutomationControlled',
            ]
            # Docker/CI args — only on Linux where sandbox/shm are issues;
            # on macOS/Windows these block CDN resources (jQuery etc.).
            if platform.system() == 'Linux':
                launch_args += [
                    '--disable-dev-shm-usage',
                    '--no-sandbox',
                    '--disable-background-timer-throttling',
                    '--disable-renderer-backgrounding',
                ]

            # Use explicit locale or default to en-US
            if not locale:
                locale = 'en-US'

            # Build languages array: [locale, lang, "en"] (deduplicated)
            lang = locale.split('-')[0]  # "zh-TW" → "zh"
            languages = list(dict.fromkeys([locale, lang, 'en']))

            # Only override UA when explicitly provided; let the real browser
            # send its native UA + Sec-CH-UA so versions match the TLS
            # fingerprint (Cloudflare detects mismatches as bot signals).
            context_kwargs: Dict[str, Any] = {
                'viewport': self.viewport,
                'locale': locale,
                'extra_http_headers': {
                    'Accept-Language': ','.join(languages) + ',en-US;q=0.9,en;q=0.8',
                },
            }
            if user_agent:
                context_kwargs['user_agent'] = user_agent
            if record_video_dir:
                Path(record_video_dir).mkdir(parents=True, exist_ok=True)
                context_kwargs['record_video_dir'] = record_video_dir
                context_kwargs['record_video_size'] = record_video_size or self.viewport
                logger.info(f"Video recording enabled: {record_video_dir}")

            # --- Try persistent context (preserves cookies across sessions) ---
            if self.browser_type == 'chromium':
                launched = await self._launch_persistent(
                    browser_launcher, launch_args, context_kwargs,
                    slow_mo=slow_mo, proxy=proxy,
                )
                if not launched:
                    # Persistent context failed; fall back to regular launch
                    launched = await self._launch_regular(
                        browser_launcher, launch_args, context_kwargs,
                        slow_mo=slow_mo, proxy=proxy,
                    )
                if not launched:
                    raise RuntimeError(
                        "No browser engine available. Install Google Chrome for immediate use."
                    )
            else:
                launch_kwargs: Dict[str, Any] = {
                    'headless': self.headless,
                    'args': launch_args,
                }
                if slow_mo > 0:
                    launch_kwargs['slow_mo'] = slow_mo
                if proxy:
                    launch_kwargs['proxy'] = {'server': proxy}
                self._browser = await browser_launcher.launch(**launch_kwargs)
                self._context = await self._browser.new_context(**context_kwargs)
                self._page = await self._context.new_page()

            # Stealth: hide automation signals
            languages_js = str(languages)
            await self._context.add_init_script(f"""
                // Hide navigator.webdriver
                Object.defineProperty(navigator, 'webdriver', {{ get: () => undefined }});

                // Fix chrome runtime
                window.chrome = {{ runtime: {{}}, loadTimes: () => {{}}, csi: () => {{}} }};

                // Fix permissions query
                const origQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (params) =>
                    params.name === 'notifications'
                        ? Promise.resolve({{ state: Notification.permission }})
                        : origQuery(params);

                // Realistic plugins (headless returns empty array)
                Object.defineProperty(navigator, 'plugins', {{
                    get: () => {{
                        const arr = [
                            {{ name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' }},
                            {{ name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' }},
                            {{ name: 'Native Client', filename: 'internal-nacl-plugin', description: '' }},
                        ];
                        arr.refresh = () => {{}};
                        return arr;
                    }},
                }});

                // Match system languages
                Object.defineProperty(navigator, 'languages', {{
                    get: () => {languages_js},
                }});

                // Realistic hardware concurrency
                Object.defineProperty(navigator, 'hardwareConcurrency', {{
                    get: () => 8,
                }});

                // Realistic device memory
                Object.defineProperty(navigator, 'deviceMemory', {{
                    get: () => 8,
                }});

                // Hide automation-related properties
                Object.defineProperty(navigator, 'maxTouchPoints', {{
                    get: () => 0,
                }});

                // Fix iframe contentWindow access (headless detection vector)
                const originalAttachShadow = Element.prototype.attachShadow;
                Element.prototype.attachShadow = function(init) {{
                    return originalAttachShadow.call(this, {{ ...init, mode: 'open' }});
                }};
            """)

            # Create a fresh page so init_script applies (persistent context's
            # initial page was created before add_init_script).
            new_page = await self._context.new_page()
            old_page = self._page
            self._page = new_page
            if old_page and old_page != new_page and hasattr(old_page, 'close'):
                try:
                    await old_page.close()
                except Exception:
                    pass

            logger.info("Browser launched successfully")

            return {
                'status': 'success',
                'browser_type': self.browser_type,
                'headless': self.headless
            }

        except Exception as e:
            logger.error(f"Failed to launch browser: {str(e)}")
            raise RuntimeError(f"Browser launch failed: {str(e)}") from e

    async def _launch_persistent(self, launcher, args, context_kwargs, slow_mo=0, proxy=None):
        """Try launching with persistent context for cookie persistence (Cloudflare etc.)."""
        user_data_dir = Path.home() / '.flyto' / 'chrome-profile'
        user_data_dir.mkdir(parents=True, exist_ok=True)

        # Clean stale lock files from previous crashed sessions
        for lock_name in ('SingletonLock', 'SingletonSocket', 'SingletonCookie'):
            lock_file = user_data_dir / lock_name
            if lock_file.exists():
                try:
                    lock_file.unlink()
                except OSError:
                    pass

        persistent_kwargs = {
            **context_kwargs,
            'headless': self.headless,
            'args': args,
            'ignore_default_args': ['--enable-automation'],
        }
        if slow_mo > 0:
            persistent_kwargs['slow_mo'] = slow_mo
        if proxy:
            persistent_kwargs['proxy'] = {'server': proxy}

        for channel in (None, 'chrome', 'msedge'):
            try:
                ch_label = channel or 'playwright-chromium'
                logger.info(f"Launching persistent context ({ch_label})...")
                kw = {**persistent_kwargs}
                if channel:
                    kw['channel'] = channel
                self._context = await launcher.launch_persistent_context(
                    str(user_data_dir), **kw
                )
                self._browser = None  # persistent context manages browser internally
                self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()
                logger.info(f"Persistent context launched ({ch_label})")
                return True
            except Exception as e:
                logger.warning(f"Persistent context ({channel or 'chromium'}) failed: {e}")
        return False

    async def _launch_regular(self, launcher, args, context_kwargs, slow_mo=0, proxy=None):
        """Fallback: regular launch + new_context (no cookie persistence)."""
        launch_kwargs: Dict[str, Any] = {
            'headless': self.headless,
            'args': args,
            'ignore_default_args': ['--enable-automation'],
        }
        if slow_mo > 0:
            launch_kwargs['slow_mo'] = slow_mo
        if proxy:
            launch_kwargs['proxy'] = {'server': proxy}

        for channel in (None, 'chrome', 'msedge'):
            try:
                ch_label = channel or 'playwright-chromium'
                logger.info(f"Launching regular ({ch_label})...")
                kw = {**launch_kwargs}
                if channel:
                    kw['channel'] = channel
                self._browser = await launcher.launch(**kw)
                self._context = await self._browser.new_context(**context_kwargs)
                self._page = await self._context.new_page()
                logger.info(f"Regular launch succeeded ({ch_label})")
                return True
            except Exception as e:
                logger.warning(f"Regular launch ({channel or 'chromium'}) failed: {e}")
        return False

    async def goto(self,
                   url: str,
                   wait_until: str = 'domcontentloaded',
                   timeout_ms: int = DEFAULT_BROWSER_TIMEOUT_MS) -> Dict[str, Any]:
        """
        Navigate to URL

        Args:
            url: Target URL
            wait_until: When to consider navigation succeeded
                       ('load', 'domcontentloaded', 'networkidle')
            timeout_ms: Navigation timeout in milliseconds

        Returns:
            Navigation result with status and final URL
        """
        self._ensure_page()

        try:
            logger.info(f"Navigating to: {url}")

            response = await self._page.goto(
                url,
                wait_until=wait_until,
                timeout=timeout_ms
            )

            final_url = self._page.url
            status_code = response.status if response else None

            # Best-effort wait for dynamic content (JS challenges, SPAs).
            if wait_until != 'networkidle':
                try:
                    await asyncio.wait_for(
                        self._page.wait_for_load_state('networkidle'),
                        timeout=10,
                    )
                except (asyncio.TimeoutError, Exception):
                    pass

            # Wait for page to have meaningful content (handles Cloudflare
            # challenges that redirect after JS verification).
            try:
                await self._page.wait_for_function(
                    'document.body && document.body.innerText.trim().length > 50',
                    timeout=15000,
                )
            except Exception:
                pass  # best-effort; don't fail if page is legitimately sparse

            final_url = self._page.url  # may have changed after JS redirect
            logger.info(f"Navigation completed: {final_url} (status: {status_code})")
            self._snapshot_since_nav = False

            return {
                'status': 'success',
                'url': final_url,
                'status_code': status_code
            }

        except Exception as e:
            err_str = str(e)

            # Some sites return non-2xx but still serve a usable page.
            if "ERR_HTTP_RESPONSE_CODE_FAILURE" in err_str:
                final_url = self._page.url
                if final_url and final_url not in ('about:blank', 'chrome-error://chromewebdata/'):
                    logger.warning(f"Navigation got HTTP error but page loaded: {final_url}")
                    try:
                        await asyncio.wait_for(
                            self._page.wait_for_load_state('networkidle'),
                            timeout=10,
                        )
                    except (asyncio.TimeoutError, Exception):
                        pass
                    try:
                        await self._page.wait_for_function(
                            'document.body && document.body.innerText.trim().length > 50',
                            timeout=15000,
                        )
                    except Exception:
                        pass
                    final_url = self._page.url
                    return {
                        'status': 'success',
                        'url': final_url,
                        'status_code': None,
                        'warning': 'HTTP error response, but page loaded',
                    }

            logger.error(f"Navigation failed: {err_str}")
            raise RuntimeError(f"Failed to navigate to {url}: {err_str}") from e

    async def click(self,
                    selector: str,
                    timeout_ms: int = DEFAULT_BROWSER_TIMEOUT_MS,
                    force: bool = False) -> Dict[str, Any]:
        """
        Click element by selector

        Args:
            selector: CSS selector
            timeout_ms: Timeout in milliseconds
            force: Force click even if element is not actionable

        Returns:
            Click result
        """
        self._ensure_page()

        try:
            logger.info(f"Clicking element: {selector}")

            await self._page.click(
                selector,
                timeout=timeout_ms,
                force=force
            )

            logger.info(f"Clicked: {selector}")

            return {
                'status': 'success',
                'selector': selector
            }

        except Exception as e:
            logger.error(f"Click failed: {str(e)}")
            raise RuntimeError(f"Failed to click {selector}: {str(e)}") from e

    async def type(self,
                   selector: str,
                   text: str,
                   delay_ms: int = 0,
                   timeout_ms: int = DEFAULT_BROWSER_TIMEOUT_MS) -> Dict[str, Any]:
        """
        Type text into element

        Args:
            selector: CSS selector
            text: Text to type
            delay_ms: Delay between keystrokes in milliseconds
            timeout_ms: Timeout in milliseconds

        Returns:
            Type result
        """
        self._ensure_page()

        try:
            logger.info(f"Typing into element: {selector}")

            await self._page.type(
                selector,
                text,
                delay=delay_ms,
                timeout=timeout_ms
            )

            logger.info(f"Typed text into: {selector}")

            return {
                'status': 'success',
                'selector': selector,
                'text_length': len(text)
            }

        except Exception as e:
            logger.error(f"Type failed: {str(e)}")
            raise RuntimeError(f"Failed to type into {selector}: {str(e)}") from e

    async def wait(self,
                   selector: str,
                   state: str = 'visible',
                   timeout_ms: int = DEFAULT_BROWSER_TIMEOUT_MS) -> Dict[str, Any]:
        """
        Wait for element to reach specified state

        Args:
            selector: CSS selector
            state: Element state ('attached', 'detached', 'visible', 'hidden')
            timeout_ms: Timeout in milliseconds

        Returns:
            Wait result
        """
        self._ensure_page()

        try:
            logger.info(f"Waiting for element: {selector} (state: {state})")

            await self._page.wait_for_selector(
                selector,
                state=state,
                timeout=timeout_ms
            )

            logger.info(f"Element ready: {selector}")

            return {
                'status': 'success',
                'selector': selector,
                'state': state
            }

        except Exception as e:
            logger.error(f"Wait failed: {str(e)}")
            raise RuntimeError(f"Failed to wait for {selector}: {str(e)}") from e

    async def extract(self,
                      selector: str,
                      fields: Dict[str, str],
                      multiple: bool = False) -> Dict[str, Any]:
        """
        Extract data from elements

        Args:
            selector: CSS selector for target elements
            fields: Field extraction map (field_name -> sub_selector or attribute)
                   Examples:
                   - {'title': 'h2', 'price': '.price', 'url': 'a@href'}
                   - Use '@attr' to extract attribute value
                   - Use selector alone to extract text content
            multiple: Extract from multiple elements (returns list)

        Returns:
            Extracted data
        """
        self._ensure_page()

        try:
            logger.info(f"Extracting data: {selector} (multiple={multiple})")

            if multiple:
                # Extract from multiple elements (supports CSS and XPath)
                elements = await self._query_selector_all(selector)

                results = []
                for element in elements:
                    item_data = await self._extract_from_element(element, fields)
                    results.append(item_data)

                logger.info(f"Extracted {len(results)} items")

                return {
                    'status': 'success',
                    'count': len(results),
                    'data': results
                }
            else:
                # Extract from single element (supports CSS and XPath)
                element = await self._query_selector(selector)

                if not element:
                    raise ValueError(f"Element not found: {selector}")

                data = await self._extract_from_element(element, fields)

                logger.info(f"Extracted data from: {selector}")

                return {
                    'status': 'success',
                    'data': data
                }

        except Exception as e:
            logger.error(f"Extraction failed: {str(e)}")
            raise RuntimeError(f"Failed to extract from {selector}: {str(e)}") from e

    async def _extract_from_element(self,
                                    element: ElementHandle,
                                    fields: Dict[str, str]) -> Dict[str, Any]:
        """
        Extract fields from a single element

        Args:
            element: Element handle
            fields: Field extraction map

        Returns:
            Extracted field data
        """
        result = {}

        for field_name, field_selector in fields.items():
            try:
                # Check if extracting attribute
                if '@' in field_selector:
                    parts = field_selector.split('@')
                    sub_selector = parts[0].strip() if parts[0].strip() else None
                    attr_name = parts[1].strip()

                    if sub_selector:
                        # Find sub-element first, then get attribute
                        sub_element = await element.query_selector(sub_selector)
                        if sub_element:
                            value = await sub_element.get_attribute(attr_name)
                        else:
                            value = None
                    else:
                        # Get attribute from current element
                        value = await element.get_attribute(attr_name)
                else:
                    # Extract text content
                    if field_selector:
                        # Find sub-element and get text
                        sub_element = await element.query_selector(field_selector)
                        if sub_element:
                            value = await sub_element.inner_text()
                        else:
                            value = None
                    else:
                        # Get text from current element
                        value = await element.inner_text()

                result[field_name] = value

            except Exception as e:
                logger.warning(f"Failed to extract field '{field_name}': {str(e)}")
                result[field_name] = None

        return result

    async def screenshot(self,
                        path: Optional[str] = None,
                        full_page: bool = False,
                        type: Optional[str] = None,
                        quality: Optional[int] = None) -> Dict[str, Any]:
        """
        Take screenshot

        Args:
            path: File path to save screenshot
                 If None, returns base64-encoded image
            full_page: Capture full scrollable page
            type: Image format ('png', 'jpeg', or 'webp'). Defaults to 'png'.
            quality: Image quality 0-100 (only for 'jpeg' and 'webp' formats)

        Returns:
            Screenshot result with path or base64 data
        """
        self._ensure_page()

        try:
            logger.info(f"Taking screenshot (full_page={full_page}, type={type})")

            kwargs: Dict[str, Any] = {
                'path': path,
                'full_page': full_page,
            }
            if type:
                kwargs['type'] = type
            if quality is not None and type in ('jpeg', 'webp'):
                kwargs['quality'] = quality

            screenshot_data = await self.real_page.screenshot(**kwargs)

            import base64
            result = {
                'status': 'success',
                'full_page': full_page,
                'base64': base64.b64encode(screenshot_data).decode('utf-8'),
                'media_type': 'image/{}'.format(type or 'png'),
            }

            if path:
                result['path'] = path
                logger.info(f"Screenshot saved: {path}")
            else:
                logger.info("Screenshot captured (base64)")

            return result

        except Exception as e:
            logger.error(f"Screenshot failed: {str(e)}")
            raise RuntimeError(f"Failed to take screenshot: {str(e)}") from e

    async def evaluate(self, script: str) -> Any:
        """
        Execute JavaScript in page context

        Args:
            script: JavaScript code to execute

        Returns:
            Script return value
        """
        self._ensure_page()

        try:
            logger.info("Executing JavaScript")
            result = await self._page.evaluate(script)
            return result

        except Exception as e:
            logger.error(f"Script execution failed: {str(e)}")
            raise RuntimeError(f"Failed to execute script: {str(e)}") from e

    async def close(self) -> Dict[str, Any]:
        """
        Close browser instance

        Returns:
            Close result
        """
        _CLOSE_TIMEOUT = 2  # seconds per sub-step (keep total < module timeout)

        try:
            logger.info("Closing browser")

            if self._page:
                # _page may be a Frame (set by browser.frame); only Page has close()
                if hasattr(self._page, 'close'):
                    try:
                        await asyncio.wait_for(self._page.close(), timeout=_CLOSE_TIMEOUT)
                    except (asyncio.TimeoutError, Exception):
                        logger.debug("Page close timed out or failed, continuing")
                self._page = None

            if self._context:
                try:
                    await asyncio.wait_for(self._context.close(), timeout=_CLOSE_TIMEOUT)
                except (asyncio.TimeoutError, Exception):
                    logger.debug("Context close timed out or failed, continuing")
                self._context = None

            if self._browser:
                try:
                    await asyncio.wait_for(self._browser.close(), timeout=_CLOSE_TIMEOUT)
                except (asyncio.TimeoutError, Exception):
                    logger.debug("Browser close timed out or failed, continuing")
                self._browser = None

            if self._playwright:
                try:
                    await asyncio.wait_for(self._playwright.stop(), timeout=_CLOSE_TIMEOUT)
                except (asyncio.TimeoutError, Exception):
                    logger.debug("Playwright stop timed out or failed, continuing")
                self._playwright = None

            logger.info("Browser closed successfully")

            return {'status': 'success'}

        except Exception as e:
            logger.error(f"Close failed: {str(e)}")
            raise RuntimeError(f"Failed to close browser: {str(e)}") from e

    # _launch_persistent and _launch_regular handle all fallback logic above

    def _ensure_page(self):
        """Ensure page is available"""
        if not self._page:
            raise RuntimeError("Browser not launched. Call launch() first.")

    def _needs_locator_api(self, selector: str) -> bool:
        """
        Check if selector needs Playwright's locator API.

        Locator API is needed for:
        - XPath: starts with //, .., or xpath=
        - Text: starts with text=
        - Role: starts with role=
        - Label: starts with label=

        CSS selectors can use faster query_selector.
        """
        return (
            selector.startswith('//') or
            selector.startswith('..') or
            selector.startswith('xpath=') or
            selector.startswith('text=') or
            selector.startswith('role=') or
            selector.startswith('label=')
        )

    def _parse_modifiers(self, selector: str) -> tuple:
        """
        Parse selector modifiers like :nth=N and :near=selector.

        Supports:
        - selector:nth=0
        - selector:near=other
        - selector:nth=0:near=other

        Returns:
            (base_selector, nth_index, near_selector)
        """
        nth_index = None
        near_selector = None
        base_selector = selector

        # Parse :near= first (it comes last in the string)
        if ':near=' in base_selector:
            parts = base_selector.rsplit(':near=', 1)
            base_selector = parts[0]
            near_selector = parts[1]

        # Parse :nth=N from the remaining base
        if ':nth=' in base_selector:
            parts = base_selector.rsplit(':nth=', 1)
            base_selector = parts[0]
            try:
                nth_index = int(parts[1])
            except ValueError:
                nth_index = 0

        return base_selector, nth_index, near_selector

    def _normalize_selector(self, selector: str) -> str:
        """
        Normalize user-friendly selectors to CSS or locator format.

        Conversions:
        - placeholder=xxx → [placeholder="xxx"] (exact match)
        - name=xxx → [name="xxx"] (exact match)
        - id*=xxx → [id*="xxx"] (contains)
        - class*=xxx → [class*="xxx"] (contains)
        - id^=xxx → [id^="xxx"] (starts with)
        - id$=xxx → [id$="xxx"] (ends with)
        """
        # Fuzzy matching: attr*=, attr^=, attr$= (contains, starts, ends)
        import re
        fuzzy_match = re.match(r'^(id|class|name|placeholder|value|type|data-\w+)([*^$]?)=(.+)$', selector)
        if fuzzy_match:
            attr = fuzzy_match.group(1)
            operator = fuzzy_match.group(2) or ''  # *, ^, $, or empty for exact
            attr_value = fuzzy_match.group(3)

            # Handle quoted and unquoted values
            if not (attr_value.startswith('"') or attr_value.startswith("'")):
                attr_value = f'"{attr_value}"'

            return f'[{attr}{operator}={attr_value}]'

        return selector

    def _get_locator_selector(self, selector: str) -> str:
        """
        Convert selector to Playwright locator format.

        - //div → xpath=//div
        - ../parent → xpath=../parent
        - text=Hello → text=Hello (unchanged)
        - xpath=//div → xpath=//div (unchanged)
        - css=div → div (strip prefix for CSS)
        """
        if selector.startswith('//') or selector.startswith('..'):
            return f'xpath={selector}'
        if selector.startswith('css='):
            return selector[4:]
        return selector

    async def _query_selector(self, selector: str) -> Optional[ElementHandle]:
        """
        Query single element with CSS, XPath, text, or shortcut selectors.

        Supported formats:
        - CSS: .class, #id, div[attr=value]
        - XPath: //div[@class="x"], xpath=//div
        - Text: text=按鈕文字, text=Submit
        - Role: role=button[name="Submit"]
        - Label: label=Email (for associated input)
        - Shortcuts: placeholder=請輸入, name=email, value=送出
        - Fuzzy: id*=login, class*=btn (contains match)
        - Modifiers: selector:nth=0, selector:near=other

        Returns:
            ElementHandle or None
        """
        self._ensure_page()

        # Parse modifiers first
        base_selector, nth_index, near_selector = self._parse_modifiers(selector)

        # Normalize shortcuts like placeholder=xxx → [placeholder="xxx"]
        base_selector = self._normalize_selector(base_selector)

        # Get locator for the base selector
        if self._needs_locator_api(base_selector):
            locator_selector = self._get_locator_selector(base_selector)
            locator = self._page.locator(locator_selector)
        else:
            css_selector = base_selector[4:] if base_selector.startswith('css=') else base_selector
            locator = self._page.locator(css_selector)

        # Apply :near= modifier if present
        if near_selector:
            near_base = self._normalize_selector(near_selector)
            if self._needs_locator_api(near_base):
                near_locator = self._page.locator(self._get_locator_selector(near_base))
            else:
                near_locator = self._page.locator(near_base)
            locator = locator.near(near_locator)

        # Apply :nth= modifier or get first
        count = await locator.count()
        if count == 0:
            return None

        if nth_index is not None:
            if nth_index < count:
                return await locator.nth(nth_index).element_handle()
            return None
        else:
            return await locator.first.element_handle()

    async def _query_selector_all(self, selector: str) -> List[ElementHandle]:
        """
        Query all matching elements with CSS, XPath, text, or shortcut selectors.

        Supported formats:
        - CSS: .class, #id, div[attr=value]
        - XPath: //div[@class="x"], xpath=//div
        - Text: text=按鈕文字, text=Submit
        - Role: role=button[name="Submit"]
        - Label: label=Email (for associated input)
        - Shortcuts: placeholder=請輸入, name=email, value=送出
        - Fuzzy: id*=login, class*=btn (contains match)
        - Modifiers: selector:near=other

        Returns:
            List of ElementHandle
        """
        self._ensure_page()

        # Parse modifiers (note: :nth= doesn't make sense for _all, ignore it)
        base_selector, _, near_selector = self._parse_modifiers(selector)

        # Normalize shortcuts like placeholder=xxx → [placeholder="xxx"]
        base_selector = self._normalize_selector(base_selector)

        # Get locator for the base selector
        if self._needs_locator_api(base_selector):
            locator_selector = self._get_locator_selector(base_selector)
            locator = self._page.locator(locator_selector)
        else:
            css_selector = base_selector[4:] if base_selector.startswith('css=') else base_selector
            locator = self._page.locator(css_selector)

        # Apply :near= modifier if present
        if near_selector:
            near_base = self._normalize_selector(near_selector)
            if self._needs_locator_api(near_base):
                near_locator = self._page.locator(self._get_locator_selector(near_base))
            else:
                near_locator = self._page.locator(near_base)
            locator = locator.near(near_locator)

        # Get all matching elements
        count = await locator.count()
        elements = []
        for i in range(count):
            el = await locator.nth(i).element_handle()
            if el:
                elements.append(el)
        return elements

    async def new_page(self) -> Page:
        """
        Create a new page (or return existing if only one needed).

        Returns:
            Page instance
        """
        if not self._browser:
            raise RuntimeError("Browser not launched. Call launch() first.")

        # If no page exists, create one
        if not self._page:
            self._page = await self._context.new_page()

        return self._page

    @property
    def page(self) -> Page:
        """Get current page instance"""
        self._ensure_page()
        return self._page

    @property
    def real_page(self):
        """Get the actual Page object, even when inside a frame context.
        Use this for Page-only APIs: screenshot, pdf, keyboard, mouse,
        route, on/off events, expect_download, context."""
        if self._page is not None and hasattr(self._page, 'page'):
            return self._page.page  # Frame.page returns the owning Page
        return self._page

    @property
    def browser(self) -> Browser:
        """Get browser instance"""
        if not self._browser:
            raise RuntimeError("Browser not launched. Call launch() first.")
        return self._browser
