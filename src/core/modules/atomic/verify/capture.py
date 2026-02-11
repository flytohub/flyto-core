"""
Verify Capture Module - Capture computed styles from browser

Uses Playwright to extract computedStyle from real browser rendering.
"""
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets, field as schema_field


@dataclass
class CapturedElement:
    """Captured element with computed styles."""
    selector: str
    tag_name: str
    text_content: Optional[str] = None

    # Computed styles
    font_family: Optional[str] = None
    font_size: Optional[float] = None
    font_weight: Optional[int] = None
    line_height: Optional[float] = None
    letter_spacing: Optional[float] = None
    text_align: Optional[str] = None
    color: Optional[str] = None

    # Layout
    width: Optional[float] = None
    height: Optional[float] = None
    padding_top: Optional[float] = None
    padding_right: Optional[float] = None
    padding_bottom: Optional[float] = None
    padding_left: Optional[float] = None
    margin_top: Optional[float] = None
    margin_right: Optional[float] = None
    margin_bottom: Optional[float] = None
    margin_left: Optional[float] = None
    gap: Optional[float] = None

    # Background / Border
    background_color: Optional[str] = None
    border_radius: Optional[float] = None
    border_width: Optional[float] = None
    border_color: Optional[str] = None

    # Box model
    box_sizing: Optional[str] = None
    display: Optional[str] = None
    position: Optional[str] = None

    # Visibility
    opacity: Optional[float] = None
    visibility: Optional[str] = None

    # Bounding rect
    bounding_box: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}


# JavaScript to extract computed styles
CAPTURE_SCRIPT = """(selector) => {
    const el = document.querySelector(selector);
    if (!el) return null;

    const computed = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();

    const parsePx = (v) => {
        if (!v || v === 'auto' || v === 'none') return null;
        const num = parseFloat(v);
        return isNaN(num) ? null : num;
    };

    const rgbToHex = (rgb) => {
        if (!rgb || rgb === 'transparent') return null;
        const match = rgb.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
        if (!match) return rgb;
        const r = parseInt(match[1]).toString(16).padStart(2, '0');
        const g = parseInt(match[2]).toString(16).padStart(2, '0');
        const b = parseInt(match[3]).toString(16).padStart(2, '0');
        return `#${r}${g}${b}`;
    };

    return {
        tagName: el.tagName.toLowerCase(),
        textContent: el.textContent?.trim().slice(0, 100) || null,
        fontFamily: computed.fontFamily,
        fontSize: parsePx(computed.fontSize),
        fontWeight: parseInt(computed.fontWeight) || null,
        lineHeight: parsePx(computed.lineHeight),
        letterSpacing: parsePx(computed.letterSpacing),
        textAlign: computed.textAlign,
        color: rgbToHex(computed.color),
        width: rect.width,
        height: rect.height,
        paddingTop: parsePx(computed.paddingTop),
        paddingRight: parsePx(computed.paddingRight),
        paddingBottom: parsePx(computed.paddingBottom),
        paddingLeft: parsePx(computed.paddingLeft),
        marginTop: parsePx(computed.marginTop),
        marginRight: parsePx(computed.marginRight),
        marginBottom: parsePx(computed.marginBottom),
        marginLeft: parsePx(computed.marginLeft),
        gap: parsePx(computed.gap),
        backgroundColor: rgbToHex(computed.backgroundColor),
        borderRadius: parsePx(computed.borderRadius),
        borderWidth: parsePx(computed.borderWidth),
        borderColor: rgbToHex(computed.borderColor),
        boxSizing: computed.boxSizing,
        display: computed.display,
        position: computed.position,
        opacity: parseFloat(computed.opacity),
        visibility: computed.visibility,
        boundingBox: { x: rect.x, y: rect.y, width: rect.width, height: rect.height }
    };
}"""


@register_module(
    module_id='verify.capture',
    version='1.0.0',
    category='verify',
    tags=['verify', 'browser', 'capture', 'style', 'design'],
    label='Capture Element Styles',
    label_key='modules.verify.capture.label',
    description='Capture computed styles from browser element',
    description_key='modules.verify.capture.description',
    icon='Scan',
    color='#8B5CF6',

    input_types=['browser', 'page'],
    output_types=['object'],

    can_receive_from=['browser.*', 'verify.*'],
    can_connect_to=['verify.*', 'data.*', 'flow.*'],

    timeout_ms=30000,
    retryable=True,
    max_retries=2,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['browser.read'],

    params_schema=compose(
        schema_field('url', type='string', required=True, description='URL to capture from',
                     placeholder='https://example.com'),
        schema_field('selector', type='string', required=True, description='CSS selector',
                     placeholder='#element or .class'),
        schema_field('wait_for', type='string', required=False, description='Wait for selector before capture',
                     placeholder='Enter Wait For...'),
        schema_field('viewport_width', type='integer', required=False, default=1280, description='Viewport width'),
        schema_field('viewport_height', type='integer', required=False, default=800, description='Viewport height'),
    ),
    output_schema={
        'element': {'type': 'object', 'description': 'Captured element with styles'},
        'found': {'type': 'boolean', 'description': 'Whether element was found'},
    },
)
class VerifyCaptureModule(BaseModule):
    """Capture computed styles from browser element."""

    module_name = "Capture Element Styles"
    module_description = "Extract computedStyle from browser"

    def validate_params(self) -> None:
        self.url = self.params.get('url')
        self.selector = self.params.get('selector')
        self.wait_for = self.params.get('wait_for')
        self.viewport_width = self.params.get('viewport_width', 1280)
        self.viewport_height = self.params.get('viewport_height', 800)

        if not self.url:
            raise ValueError("url is required")
        if not self.selector:
            raise ValueError("selector is required")

    async def execute(self) -> Dict[str, Any]:
        from core.browser.driver import BrowserDriver

        # Use existing browser from context or create new
        driver = self.context.get('browser')
        created_browser = False

        if not driver:
            driver = BrowserDriver(headless=True)
            await driver.launch()
            created_browser = True

        try:
            page = await driver.new_page()
            await page.set_viewport_size({
                'width': self.viewport_width,
                'height': self.viewport_height
            })

            await page.goto(self.url, wait_until='networkidle')

            if self.wait_for:
                await page.wait_for_selector(self.wait_for, timeout=10000)

            # Capture styles via JavaScript
            styles = await page.evaluate(CAPTURE_SCRIPT, self.selector)

            if not styles:
                return {
                    'ok': True,
                    'data': {
                        'found': False,
                        'element': None,
                        'selector': self.selector,
                    }
                }

            element = CapturedElement(
                selector=self.selector,
                tag_name=styles.get('tagName', ''),
                text_content=styles.get('textContent'),
                font_family=styles.get('fontFamily'),
                font_size=styles.get('fontSize'),
                font_weight=styles.get('fontWeight'),
                line_height=styles.get('lineHeight'),
                letter_spacing=styles.get('letterSpacing'),
                text_align=styles.get('textAlign'),
                color=styles.get('color'),
                width=styles.get('width'),
                height=styles.get('height'),
                padding_top=styles.get('paddingTop'),
                padding_right=styles.get('paddingRight'),
                padding_bottom=styles.get('paddingBottom'),
                padding_left=styles.get('paddingLeft'),
                margin_top=styles.get('marginTop'),
                margin_right=styles.get('marginRight'),
                margin_bottom=styles.get('marginBottom'),
                margin_left=styles.get('marginLeft'),
                gap=styles.get('gap'),
                background_color=styles.get('backgroundColor'),
                border_radius=styles.get('borderRadius'),
                border_width=styles.get('borderWidth'),
                border_color=styles.get('borderColor'),
                box_sizing=styles.get('boxSizing'),
                display=styles.get('display'),
                position=styles.get('position'),
                opacity=styles.get('opacity'),
                visibility=styles.get('visibility'),
                bounding_box=styles.get('boundingBox', {}),
            )

            # Store in context for chaining
            self.context['captured_element'] = element

            return {
                'ok': True,
                'data': {
                    'found': True,
                    'element': element.to_dict(),
                    'selector': self.selector,
                }
            }

        finally:
            if created_browser:
                await driver.close()
