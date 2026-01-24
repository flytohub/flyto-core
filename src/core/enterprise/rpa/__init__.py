"""
RPA - Desktop Automation & Vision Capabilities

Cross-platform desktop automation supporting:
- Windows: UI Automation API + pywinauto
- macOS: Accessibility API + pyobjc
- Linux: AT-SPI2 + python-atspi

Reference: ITEM_PIPELINE_SPEC.md Section 13
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class SelectorStrategy(Enum):
    """Element selector strategies."""
    ACCESSIBILITY = "accessibility"  # Accessibility API (recommended)
    IMAGE = "image"                  # Image recognition
    OCR = "ocr"                      # Text recognition
    COORDINATES = "coordinates"      # Coordinates (last resort)
    NATIVE = "native"                # Native API (Windows UI Automation, macOS Accessibility)


class DesktopAction(Enum):
    """Supported desktop automation actions."""
    CLICK = "click"
    DOUBLE_CLICK = "double_click"
    RIGHT_CLICK = "right_click"
    TYPE_TEXT = "type_text"
    SEND_KEYS = "send_keys"
    DRAG_DROP = "drag_drop"
    SCROLL = "scroll"
    HOVER = "hover"
    FOCUS = "focus"
    GET_TEXT = "get_text"
    GET_ATTRIBUTE = "get_attribute"
    SCREENSHOT = "screenshot"
    WAIT_ELEMENT = "wait_element"
    WAIT_VANISH = "wait_vanish"


@dataclass
class DesktopElement:
    """Represents a UI element on the desktop."""
    selector: str
    selector_type: SelectorStrategy = SelectorStrategy.ACCESSIBILITY

    # Element properties (populated after find)
    name: Optional[str] = None
    role: Optional[str] = None
    value: Optional[str] = None
    bounds: Optional[Tuple[int, int, int, int]] = None  # x, y, width, height
    enabled: bool = True
    visible: bool = True

    # Match confidence (for image/OCR)
    confidence: float = 1.0

    # Parent/children for tree navigation
    parent_selector: Optional[str] = None
    children_count: int = 0


@dataclass
class ImageMatchConfig:
    """Image matching configuration."""
    algorithms: List[str] = field(default_factory=lambda: [
        "template_matching",    # OpenCV template matching
        "feature_matching",     # SIFT/ORB feature matching
        "deep_learning",        # CNN features (more robust)
    ])
    default_confidence: float = 0.9
    multi_scale: bool = True   # Support different scale ratios
    grayscale: bool = False    # Convert to grayscale before matching


@dataclass
class OCRConfig:
    """OCR configuration."""
    engine: str = "paddleocr"  # "paddleocr" | "tesseract" | "azure" | "google"
    languages: List[str] = field(default_factory=lambda: ["en", "zh-TW", "zh-CN"])
    output_format: str = "text"  # "text" | "structured" | "table"
    preprocess: bool = True      # Apply image preprocessing


@dataclass
class DesktopAutomationCapabilities:
    """Desktop automation capabilities declaration."""

    # Supported platforms
    platforms: List[str] = field(default_factory=lambda: ["windows", "macos", "linux"])

    # Selector strategies
    selectors: List[SelectorStrategy] = field(default_factory=lambda: list(SelectorStrategy))

    # Supported actions
    actions: List[DesktopAction] = field(default_factory=lambda: list(DesktopAction))

    # Image matching config
    image_match: ImageMatchConfig = field(default_factory=ImageMatchConfig)

    # OCR config
    ocr: OCRConfig = field(default_factory=OCRConfig)

    # Timeouts
    default_timeout_ms: int = 30000
    poll_interval_ms: int = 100

    # Safety settings
    require_element_visible: bool = True
    require_element_enabled: bool = True
    screenshot_on_error: bool = True


@dataclass
class DesktopActionResult:
    """Result of a desktop automation action."""
    success: bool
    action: DesktopAction
    element: Optional[DesktopElement] = None

    # Action-specific results
    text: Optional[str] = None           # For GET_TEXT, OCR
    attribute_value: Optional[str] = None  # For GET_ATTRIBUTE
    screenshot_path: Optional[str] = None  # For SCREENSHOT

    # Timing
    duration_ms: int = 0

    # Error info
    error: Optional[str] = None
    error_screenshot: Optional[str] = None


class DesktopAutomation:
    """
    Desktop automation interface.

    This is the abstract interface - platform-specific implementations
    should be provided by the runtime environment.
    """

    def __init__(self, capabilities: DesktopAutomationCapabilities = None):
        self.capabilities = capabilities or DesktopAutomationCapabilities()

    async def find_element(
        self,
        selector: str,
        selector_type: SelectorStrategy = SelectorStrategy.ACCESSIBILITY,
        timeout_ms: int = None,
        confidence: float = 0.9,
    ) -> Optional[DesktopElement]:
        """
        Find a UI element.

        Args:
            selector: Element selector (depends on selector_type)
            selector_type: Strategy to use for finding element
            timeout_ms: Maximum time to wait for element
            confidence: Minimum confidence for image/OCR matching

        Returns:
            DesktopElement if found, None otherwise
        """
        raise NotImplementedError("Platform-specific implementation required")

    async def click(
        self,
        element: DesktopElement,
        click_type: str = "single",
        offset: Tuple[int, int] = None,
    ) -> DesktopActionResult:
        """
        Click on an element.

        Args:
            element: Element to click
            click_type: "single", "double", or "right"
            offset: Optional offset from element center
        """
        raise NotImplementedError("Platform-specific implementation required")

    async def type_text(
        self,
        element: DesktopElement,
        text: str,
        clear_first: bool = False,
        typing_delay_ms: int = 0,
    ) -> DesktopActionResult:
        """
        Type text into an element.

        Args:
            element: Element to type into
            text: Text to type
            clear_first: Clear existing content first
            typing_delay_ms: Delay between keystrokes (for natural typing)
        """
        raise NotImplementedError("Platform-specific implementation required")

    async def send_keys(
        self,
        keys: str,
        element: DesktopElement = None,
    ) -> DesktopActionResult:
        """
        Send keyboard input.

        Args:
            keys: Key sequence (e.g., "ctrl+c", "enter", "tab")
            element: Optional element to focus first
        """
        raise NotImplementedError("Platform-specific implementation required")

    async def get_text(
        self,
        element: DesktopElement,
        method: str = "accessibility",
    ) -> DesktopActionResult:
        """
        Get text from an element.

        Args:
            element: Element to get text from
            method: "accessibility" or "ocr"
        """
        raise NotImplementedError("Platform-specific implementation required")

    async def screenshot(
        self,
        region: Tuple[int, int, int, int] = None,
        element: DesktopElement = None,
    ) -> DesktopActionResult:
        """
        Take a screenshot.

        Args:
            region: Optional region (x, y, width, height)
            element: Optional element to screenshot
        """
        raise NotImplementedError("Platform-specific implementation required")

    async def wait_element(
        self,
        selector: str,
        selector_type: SelectorStrategy = SelectorStrategy.ACCESSIBILITY,
        timeout_ms: int = 30000,
        poll_interval_ms: int = 100,
    ) -> Optional[DesktopElement]:
        """
        Wait for an element to appear.

        Args:
            selector: Element selector
            selector_type: Strategy to use
            timeout_ms: Maximum time to wait
            poll_interval_ms: Polling interval
        """
        raise NotImplementedError("Platform-specific implementation required")

    async def wait_vanish(
        self,
        selector: str,
        selector_type: SelectorStrategy = SelectorStrategy.ACCESSIBILITY,
        timeout_ms: int = 30000,
        poll_interval_ms: int = 100,
    ) -> bool:
        """
        Wait for an element to disappear.

        Args:
            selector: Element selector
            selector_type: Strategy to use
            timeout_ms: Maximum time to wait
            poll_interval_ms: Polling interval

        Returns:
            True if element vanished, False if timeout
        """
        raise NotImplementedError("Platform-specific implementation required")


__all__ = [
    'SelectorStrategy',
    'DesktopAction',
    'DesktopElement',
    'ImageMatchConfig',
    'OCRConfig',
    'DesktopAutomationCapabilities',
    'DesktopActionResult',
    'DesktopAutomation',
]
