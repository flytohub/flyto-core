"""
RPA Desktop Automation Implementation

Cross-platform desktop automation using pyautogui with optional
platform-specific API integration.

For usage:
    from src.core.enterprise.rpa.impl import get_automation
    automation = get_automation()
"""

import asyncio
import io
import logging
import os
import platform
import tempfile
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from . import (
    DesktopAction,
    DesktopActionResult,
    DesktopAutomation,
    DesktopAutomationCapabilities,
    DesktopElement,
    ImageMatchConfig,
    OCRConfig,
    SelectorStrategy,
)

logger = logging.getLogger(__name__)

# Optional dependencies
try:
    import pyautogui
    pyautogui.FAILSAFE = True
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False
    logger.warning("pyautogui not installed - desktop automation limited")

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import cv2
    import numpy as np
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False


# =============================================================================
# Platform Detection
# =============================================================================

def get_platform() -> str:
    """Get current platform."""
    system = platform.system().lower()
    if system == "darwin":
        return "macos"
    return system


# =============================================================================
# Image Matching
# =============================================================================

class ImageMatcher:
    """Image matching utilities."""

    @staticmethod
    def template_match(
        screen: Any,
        template: Any,
        confidence: float = 0.9,
    ) -> Optional[Tuple[int, int, int, int]]:
        """
        Find template in screen image using OpenCV.

        Returns (x, y, width, height) if found, None otherwise.
        """
        if not OPENCV_AVAILABLE:
            return None

        # Convert to numpy arrays if needed
        if isinstance(screen, Image.Image):
            screen = cv2.cvtColor(np.array(screen), cv2.COLOR_RGB2BGR)
        if isinstance(template, Image.Image):
            template = cv2.cvtColor(np.array(template), cv2.COLOR_RGB2BGR)

        # Convert to grayscale
        screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
        template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)

        # Template matching
        result = cv2.matchTemplate(screen_gray, template_gray, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

        if max_val >= confidence:
            h, w = template_gray.shape
            return (max_loc[0], max_loc[1], w, h)

        return None

    @staticmethod
    def multi_scale_match(
        screen: Any,
        template: Any,
        confidence: float = 0.9,
        scales: List[float] = None,
    ) -> Optional[Tuple[int, int, int, int, float]]:
        """
        Multi-scale template matching.

        Returns (x, y, width, height, matched_scale) if found.
        """
        if not OPENCV_AVAILABLE:
            return None

        scales = scales or [0.5, 0.75, 1.0, 1.25, 1.5]

        if isinstance(screen, Image.Image):
            screen = cv2.cvtColor(np.array(screen), cv2.COLOR_RGB2BGR)
        if isinstance(template, Image.Image):
            template = cv2.cvtColor(np.array(template), cv2.COLOR_BGR2GRAY)
        elif len(template.shape) == 3:
            template = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)

        screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)

        best_match = None
        best_confidence = 0

        for scale in scales:
            # Resize template
            h, w = template.shape
            new_w = int(w * scale)
            new_h = int(h * scale)
            if new_w < 10 or new_h < 10:
                continue

            scaled_template = cv2.resize(template, (new_w, new_h))

            # Match
            result = cv2.matchTemplate(screen_gray, scaled_template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)

            if max_val > best_confidence and max_val >= confidence:
                best_confidence = max_val
                best_match = (max_loc[0], max_loc[1], new_w, new_h, scale)

        return best_match


# =============================================================================
# Desktop Automation Implementation
# =============================================================================

class DesktopAutomationImpl(DesktopAutomation):
    """
    Cross-platform desktop automation implementation.

    Uses pyautogui for basic operations with optional platform-specific
    enhancements.
    """

    def __init__(self, capabilities: DesktopAutomationCapabilities = None):
        super().__init__(capabilities)
        self._platform = get_platform()
        self._screenshot_dir = tempfile.gettempdir()
        self._element_cache: Dict[str, DesktopElement] = {}

        # Check capabilities
        if not PYAUTOGUI_AVAILABLE:
            logger.warning("pyautogui not available - limited functionality")

    async def find_element(
        self,
        selector: str,
        selector_type: SelectorStrategy = SelectorStrategy.ACCESSIBILITY,
        timeout_ms: int = None,
        confidence: float = 0.9,
    ) -> Optional[DesktopElement]:
        """Find a UI element."""
        timeout_ms = timeout_ms or self.capabilities.default_timeout_ms
        start_time = time.time()

        while (time.time() - start_time) * 1000 < timeout_ms:
            element = await self._find_element_once(selector, selector_type, confidence)
            if element:
                self._element_cache[selector] = element
                return element
            await asyncio.sleep(self.capabilities.poll_interval_ms / 1000)

        return None

    async def _find_element_once(
        self,
        selector: str,
        selector_type: SelectorStrategy,
        confidence: float,
    ) -> Optional[DesktopElement]:
        """Single attempt to find element."""
        if selector_type == SelectorStrategy.IMAGE:
            return await self._find_by_image(selector, confidence)

        elif selector_type == SelectorStrategy.OCR:
            return await self._find_by_ocr(selector, confidence)

        elif selector_type == SelectorStrategy.COORDINATES:
            return self._parse_coordinates(selector)

        elif selector_type == SelectorStrategy.ACCESSIBILITY:
            # Platform-specific accessibility API
            return await self._find_by_accessibility(selector)

        elif selector_type == SelectorStrategy.NATIVE:
            return await self._find_by_native(selector)

        return None

    async def _find_by_image(
        self,
        image_path: str,
        confidence: float,
    ) -> Optional[DesktopElement]:
        """Find element by image template matching."""
        if not PYAUTOGUI_AVAILABLE or not PIL_AVAILABLE:
            return None

        # Take screenshot
        screen = pyautogui.screenshot()

        # Load template
        if os.path.exists(image_path):
            template = Image.open(image_path)
        else:
            # Assume base64 or URL
            logger.warning(f"Image not found: {image_path}")
            return None

        # Multi-scale matching
        if OPENCV_AVAILABLE and self.capabilities.image_match.multi_scale:
            result = ImageMatcher.multi_scale_match(screen, template, confidence)
            if result:
                x, y, w, h, scale = result
                return DesktopElement(
                    selector=image_path,
                    selector_type=SelectorStrategy.IMAGE,
                    bounds=(x, y, w, h),
                    confidence=confidence,
                )
        else:
            # Simple matching with pyautogui
            try:
                location = pyautogui.locate(image_path, screen, confidence=confidence)
                if location:
                    return DesktopElement(
                        selector=image_path,
                        selector_type=SelectorStrategy.IMAGE,
                        bounds=(location.left, location.top, location.width, location.height),
                        confidence=confidence,
                    )
            except Exception as e:
                logger.debug(f"Image match failed: {e}")

        return None

    async def _find_by_ocr(
        self,
        text: str,
        confidence: float,
    ) -> Optional[DesktopElement]:
        """Find element by OCR text matching."""
        if not PYAUTOGUI_AVAILABLE:
            return None

        # Take screenshot
        screen = pyautogui.screenshot()

        try:
            import pytesseract
            # Get bounding boxes with text
            data = pytesseract.image_to_data(
                screen,
                output_type=pytesseract.Output.DICT
            )

            text_lower = text.lower()
            for i, word in enumerate(data["text"]):
                if text_lower in str(word).lower():
                    x = data["left"][i]
                    y = data["top"][i]
                    w = data["width"][i]
                    h = data["height"][i]
                    conf = data["conf"][i] / 100

                    if conf >= confidence:
                        return DesktopElement(
                            selector=text,
                            selector_type=SelectorStrategy.OCR,
                            value=word,
                            bounds=(x, y, w, h),
                            confidence=conf,
                        )
        except ImportError:
            logger.warning("pytesseract not installed")
        except Exception as e:
            logger.debug(f"OCR match failed: {e}")

        return None

    async def _find_by_accessibility(
        self,
        selector: str,
    ) -> Optional[DesktopElement]:
        """Find element using accessibility API (platform-specific)."""
        # Placeholder - would need platform-specific implementation
        # Windows: pywinauto, comtypes for UI Automation
        # macOS: pyobjc for Accessibility API
        # Linux: python-atspi for AT-SPI2

        if self._platform == "windows":
            return await self._find_windows_element(selector)
        elif self._platform == "macos":
            return await self._find_macos_element(selector)
        elif self._platform == "linux":
            return await self._find_linux_element(selector)

        return None

    async def _find_windows_element(self, selector: str) -> Optional[DesktopElement]:
        """Find element on Windows using UI Automation."""
        try:
            import pywinauto
            # Parse selector (e.g., "Calculator > Display")
            parts = [p.strip() for p in selector.split(">")]
            app_name = parts[0] if parts else selector

            app = pywinauto.Application().connect(title_re=f".*{app_name}.*")
            window = app.top_window()

            if len(parts) > 1:
                element = window[parts[1]]
                rect = element.rectangle()
                return DesktopElement(
                    selector=selector,
                    selector_type=SelectorStrategy.ACCESSIBILITY,
                    name=parts[1],
                    bounds=(rect.left, rect.top, rect.width(), rect.height()),
                    enabled=element.is_enabled(),
                    visible=element.is_visible(),
                )
            else:
                rect = window.rectangle()
                return DesktopElement(
                    selector=selector,
                    selector_type=SelectorStrategy.ACCESSIBILITY,
                    name=app_name,
                    bounds=(rect.left, rect.top, rect.width(), rect.height()),
                )
        except ImportError:
            logger.debug("pywinauto not installed")
        except Exception as e:
            logger.debug(f"Windows element find failed: {e}")

        return None

    async def _find_macos_element(self, selector: str) -> Optional[DesktopElement]:
        """Find element on macOS using Accessibility API."""
        # Would require pyobjc and ApplicationServices framework
        logger.debug("macOS accessibility not implemented - use image/OCR")
        return None

    async def _find_linux_element(self, selector: str) -> Optional[DesktopElement]:
        """Find element on Linux using AT-SPI2."""
        # Would require python-atspi
        logger.debug("Linux accessibility not implemented - use image/OCR")
        return None

    async def _find_by_native(self, selector: str) -> Optional[DesktopElement]:
        """Find using native platform API."""
        return await self._find_by_accessibility(selector)

    def _parse_coordinates(self, selector: str) -> Optional[DesktopElement]:
        """Parse coordinate selector (x,y or x,y,w,h)."""
        try:
            parts = [int(p.strip()) for p in selector.split(",")]
            if len(parts) >= 2:
                x, y = parts[0], parts[1]
                w = parts[2] if len(parts) > 2 else 1
                h = parts[3] if len(parts) > 3 else 1
                return DesktopElement(
                    selector=selector,
                    selector_type=SelectorStrategy.COORDINATES,
                    bounds=(x, y, w, h),
                )
        except ValueError:
            pass
        return None

    async def click(
        self,
        element: DesktopElement,
        click_type: str = "single",
        offset: Tuple[int, int] = None,
    ) -> DesktopActionResult:
        """Click on an element."""
        start_time = time.time()

        if not PYAUTOGUI_AVAILABLE:
            return DesktopActionResult(
                success=False,
                action=DesktopAction.CLICK,
                error="pyautogui not available",
            )

        if not element.bounds:
            return DesktopActionResult(
                success=False,
                action=DesktopAction.CLICK,
                error="Element has no bounds",
            )

        # Calculate click position
        x, y, w, h = element.bounds
        click_x = x + w // 2 + (offset[0] if offset else 0)
        click_y = y + h // 2 + (offset[1] if offset else 0)

        try:
            if click_type == "double":
                pyautogui.doubleClick(click_x, click_y)
                action = DesktopAction.DOUBLE_CLICK
            elif click_type == "right":
                pyautogui.rightClick(click_x, click_y)
                action = DesktopAction.RIGHT_CLICK
            else:
                pyautogui.click(click_x, click_y)
                action = DesktopAction.CLICK

            duration = int((time.time() - start_time) * 1000)
            return DesktopActionResult(
                success=True,
                action=action,
                element=element,
                duration_ms=duration,
            )

        except Exception as e:
            return DesktopActionResult(
                success=False,
                action=DesktopAction.CLICK,
                error=str(e),
            )

    async def type_text(
        self,
        element: DesktopElement,
        text: str,
        clear_first: bool = False,
        typing_delay_ms: int = 0,
    ) -> DesktopActionResult:
        """Type text into an element."""
        start_time = time.time()

        if not PYAUTOGUI_AVAILABLE:
            return DesktopActionResult(
                success=False,
                action=DesktopAction.TYPE_TEXT,
                error="pyautogui not available",
            )

        try:
            # Click to focus
            if element.bounds:
                x, y, w, h = element.bounds
                pyautogui.click(x + w // 2, y + h // 2)
                await asyncio.sleep(0.1)

            # Clear if requested
            if clear_first:
                pyautogui.hotkey("ctrl", "a")
                await asyncio.sleep(0.05)
                pyautogui.press("delete")
                await asyncio.sleep(0.05)

            # Type text
            interval = typing_delay_ms / 1000 if typing_delay_ms > 0 else 0
            pyautogui.typewrite(text, interval=interval)

            duration = int((time.time() - start_time) * 1000)
            return DesktopActionResult(
                success=True,
                action=DesktopAction.TYPE_TEXT,
                element=element,
                duration_ms=duration,
            )

        except Exception as e:
            return DesktopActionResult(
                success=False,
                action=DesktopAction.TYPE_TEXT,
                error=str(e),
            )

    async def send_keys(
        self,
        keys: str,
        element: DesktopElement = None,
    ) -> DesktopActionResult:
        """Send keyboard input."""
        start_time = time.time()

        if not PYAUTOGUI_AVAILABLE:
            return DesktopActionResult(
                success=False,
                action=DesktopAction.SEND_KEYS,
                error="pyautogui not available",
            )

        try:
            # Focus element if provided
            if element and element.bounds:
                x, y, w, h = element.bounds
                pyautogui.click(x + w // 2, y + h // 2)
                await asyncio.sleep(0.1)

            # Parse and send keys
            # Format: "ctrl+c", "shift+enter", "tab", "f1", etc.
            if "+" in keys:
                parts = keys.lower().split("+")
                pyautogui.hotkey(*parts)
            else:
                pyautogui.press(keys.lower())

            duration = int((time.time() - start_time) * 1000)
            return DesktopActionResult(
                success=True,
                action=DesktopAction.SEND_KEYS,
                duration_ms=duration,
            )

        except Exception as e:
            return DesktopActionResult(
                success=False,
                action=DesktopAction.SEND_KEYS,
                error=str(e),
            )

    async def get_text(
        self,
        element: DesktopElement,
        method: str = "accessibility",
    ) -> DesktopActionResult:
        """Get text from an element."""
        start_time = time.time()

        if element.value:
            return DesktopActionResult(
                success=True,
                action=DesktopAction.GET_TEXT,
                element=element,
                text=element.value,
                duration_ms=int((time.time() - start_time) * 1000),
            )

        if method == "ocr" and element.bounds:
            try:
                import pytesseract
                x, y, w, h = element.bounds
                screen = pyautogui.screenshot(region=(x, y, w, h))
                text = pytesseract.image_to_string(screen)
                return DesktopActionResult(
                    success=True,
                    action=DesktopAction.GET_TEXT,
                    element=element,
                    text=text.strip(),
                    duration_ms=int((time.time() - start_time) * 1000),
                )
            except Exception as e:
                return DesktopActionResult(
                    success=False,
                    action=DesktopAction.GET_TEXT,
                    error=str(e),
                )

        return DesktopActionResult(
            success=False,
            action=DesktopAction.GET_TEXT,
            error="Cannot get text - use OCR method",
        )

    async def screenshot(
        self,
        region: Tuple[int, int, int, int] = None,
        element: DesktopElement = None,
    ) -> DesktopActionResult:
        """Take a screenshot."""
        start_time = time.time()

        if not PYAUTOGUI_AVAILABLE:
            return DesktopActionResult(
                success=False,
                action=DesktopAction.SCREENSHOT,
                error="pyautogui not available",
            )

        try:
            # Determine region
            if element and element.bounds:
                region = element.bounds
            elif region:
                pass
            else:
                region = None  # Full screen

            # Take screenshot
            screenshot = pyautogui.screenshot(region=region)

            # Save to temp file
            filename = f"screenshot_{uuid.uuid4().hex[:8]}.png"
            filepath = os.path.join(self._screenshot_dir, filename)
            screenshot.save(filepath)

            duration = int((time.time() - start_time) * 1000)
            return DesktopActionResult(
                success=True,
                action=DesktopAction.SCREENSHOT,
                screenshot_path=filepath,
                duration_ms=duration,
            )

        except Exception as e:
            return DesktopActionResult(
                success=False,
                action=DesktopAction.SCREENSHOT,
                error=str(e),
            )

    async def wait_element(
        self,
        selector: str,
        selector_type: SelectorStrategy = SelectorStrategy.ACCESSIBILITY,
        timeout_ms: int = 30000,
        poll_interval_ms: int = 100,
    ) -> Optional[DesktopElement]:
        """Wait for an element to appear."""
        return await self.find_element(
            selector,
            selector_type,
            timeout_ms=timeout_ms,
            confidence=0.9,
        )

    async def wait_vanish(
        self,
        selector: str,
        selector_type: SelectorStrategy = SelectorStrategy.ACCESSIBILITY,
        timeout_ms: int = 30000,
        poll_interval_ms: int = 100,
    ) -> bool:
        """Wait for an element to disappear."""
        start_time = time.time()

        while (time.time() - start_time) * 1000 < timeout_ms:
            element = await self._find_element_once(selector, selector_type, 0.9)
            if not element:
                return True
            await asyncio.sleep(poll_interval_ms / 1000)

        return False

    async def drag_drop(
        self,
        from_element: DesktopElement,
        to_element: DesktopElement,
        duration: float = 0.5,
    ) -> DesktopActionResult:
        """Drag from one element to another."""
        start_time = time.time()

        if not PYAUTOGUI_AVAILABLE:
            return DesktopActionResult(
                success=False,
                action=DesktopAction.DRAG_DROP,
                error="pyautogui not available",
            )

        if not from_element.bounds or not to_element.bounds:
            return DesktopActionResult(
                success=False,
                action=DesktopAction.DRAG_DROP,
                error="Elements must have bounds",
            )

        try:
            fx, fy, fw, fh = from_element.bounds
            tx, ty, tw, th = to_element.bounds

            from_x = fx + fw // 2
            from_y = fy + fh // 2
            to_x = tx + tw // 2
            to_y = ty + th // 2

            pyautogui.moveTo(from_x, from_y)
            pyautogui.drag(to_x - from_x, to_y - from_y, duration=duration)

            return DesktopActionResult(
                success=True,
                action=DesktopAction.DRAG_DROP,
                duration_ms=int((time.time() - start_time) * 1000),
            )

        except Exception as e:
            return DesktopActionResult(
                success=False,
                action=DesktopAction.DRAG_DROP,
                error=str(e),
            )

    async def scroll(
        self,
        clicks: int,
        element: DesktopElement = None,
    ) -> DesktopActionResult:
        """Scroll mouse wheel."""
        start_time = time.time()

        if not PYAUTOGUI_AVAILABLE:
            return DesktopActionResult(
                success=False,
                action=DesktopAction.SCROLL,
                error="pyautogui not available",
            )

        try:
            if element and element.bounds:
                x, y, w, h = element.bounds
                pyautogui.scroll(clicks, x + w // 2, y + h // 2)
            else:
                pyautogui.scroll(clicks)

            return DesktopActionResult(
                success=True,
                action=DesktopAction.SCROLL,
                duration_ms=int((time.time() - start_time) * 1000),
            )

        except Exception as e:
            return DesktopActionResult(
                success=False,
                action=DesktopAction.SCROLL,
                error=str(e),
            )


# =============================================================================
# Singleton Instance
# =============================================================================

_automation: DesktopAutomationImpl = None


def get_automation(capabilities: DesktopAutomationCapabilities = None) -> DesktopAutomationImpl:
    """Get desktop automation singleton."""
    global _automation
    if _automation is None:
        _automation = DesktopAutomationImpl(capabilities)
    return _automation


__all__ = [
    # Implementations
    "DesktopAutomationImpl",
    "ImageMatcher",
    # Factory functions
    "get_automation",
    "get_platform",
]
