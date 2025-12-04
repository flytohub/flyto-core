"""
Browser Driver - Playwright wrapper for browser automation
"""
import asyncio
import logging
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

    async def launch(self) -> Dict[str, Any]:
        """
        Launch browser instance

        Returns:
            Status dictionary
        """
        try:
            logger.info(f"Launching {self.browser_type} browser (headless={self.headless})")

            self._playwright = await async_playwright().start()

            # Select browser type
            if self.browser_type == 'firefox':
                browser_launcher = self._playwright.firefox
            elif self.browser_type == 'webkit':
                browser_launcher = self._playwright.webkit
            else:
                browser_launcher = self._playwright.chromium

            # Launch browser
            self._browser = await browser_launcher.launch(headless=self.headless)

            # Create context with viewport
            self._context = await self._browser.new_context(
                viewport=self.viewport,
                user_agent=DEFAULT_USER_AGENT
            )

            # Create page
            self._page = await self._context.new_page()

            logger.info("Browser launched successfully")

            return {
                'status': 'success',
                'browser_type': self.browser_type,
                'headless': self.headless
            }

        except Exception as e:
            logger.error(f"Failed to launch browser: {str(e)}")
            raise RuntimeError(f"Browser launch failed: {str(e)}") from e

    async def goto(self,
                   url: str,
                   wait_until: str = 'networkidle',
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

            logger.info(f"Navigation completed: {final_url} (status: {status_code})")

            return {
                'status': 'success',
                'url': final_url,
                'status_code': status_code
            }

        except Exception as e:
            logger.error(f"Navigation failed: {str(e)}")
            raise RuntimeError(f"Failed to navigate to {url}: {str(e)}") from e

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
                # Extract from multiple elements
                elements = await self._page.query_selector_all(selector)

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
                # Extract from single element
                element = await self._page.query_selector(selector)

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
                        full_page: bool = False) -> Dict[str, Any]:
        """
        Take screenshot

        Args:
            path: File path to save screenshot (PNG format)
                 If None, returns base64-encoded image
            full_page: Capture full scrollable page

        Returns:
            Screenshot result with path or base64 data
        """
        self._ensure_page()

        try:
            logger.info(f"Taking screenshot (full_page={full_page})")

            screenshot_data = await self._page.screenshot(
                path=path,
                full_page=full_page
            )

            result = {
                'status': 'success',
                'full_page': full_page
            }

            if path:
                result['path'] = path
                logger.info(f"Screenshot saved: {path}")
            else:
                import base64
                result['base64'] = base64.b64encode(screenshot_data).decode('utf-8')
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
        try:
            logger.info("Closing browser")

            if self._page:
                await self._page.close()
                self._page = None

            if self._context:
                await self._context.close()
                self._context = None

            if self._browser:
                await self._browser.close()
                self._browser = None

            if self._playwright:
                await self._playwright.stop()
                self._playwright = None

            logger.info("Browser closed successfully")

            return {'status': 'success'}

        except Exception as e:
            logger.error(f"Close failed: {str(e)}")
            raise RuntimeError(f"Failed to close browser: {str(e)}") from e

    def _ensure_page(self):
        """Ensure page is available"""
        if not self._page:
            raise RuntimeError("Browser not launched. Call launch() first.")

    @property
    def page(self) -> Page:
        """Get current page instance"""
        self._ensure_page()
        return self._page

    @property
    def browser(self) -> Browser:
        """Get browser instance"""
        if not self._browser:
            raise RuntimeError("Browser not launched. Call launch() first.")
        return self._browser
