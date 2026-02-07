"""
Browser Emulate Module - Device Emulation

Emulate mobile devices, tablets, and custom viewports.
Uses Playwright's device descriptors and viewport settings.

Works across all browsers (Chromium, Firefox, WebKit).
"""
from typing import Any, Dict, List, Optional
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field, presets


# Device presets based on Playwright's device descriptors
DEVICE_PRESETS = {
    # iPhones
    'iphone_12': {
        'viewport': {'width': 390, 'height': 844},
        'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1',
        'device_scale_factor': 3,
        'is_mobile': True,
        'has_touch': True,
    },
    'iphone_14': {
        'viewport': {'width': 390, 'height': 844},
        'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
        'device_scale_factor': 3,
        'is_mobile': True,
        'has_touch': True,
    },
    'iphone_14_pro_max': {
        'viewport': {'width': 430, 'height': 932},
        'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
        'device_scale_factor': 3,
        'is_mobile': True,
        'has_touch': True,
    },
    'iphone_se': {
        'viewport': {'width': 375, 'height': 667},
        'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1',
        'device_scale_factor': 2,
        'is_mobile': True,
        'has_touch': True,
    },

    # Android phones
    'pixel_7': {
        'viewport': {'width': 412, 'height': 915},
        'user_agent': 'Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36',
        'device_scale_factor': 2.625,
        'is_mobile': True,
        'has_touch': True,
    },
    'pixel_5': {
        'viewport': {'width': 393, 'height': 851},
        'user_agent': 'Mozilla/5.0 (Linux; Android 11; Pixel 5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.91 Mobile Safari/537.36',
        'device_scale_factor': 2.75,
        'is_mobile': True,
        'has_touch': True,
    },
    'galaxy_s21': {
        'viewport': {'width': 360, 'height': 800},
        'user_agent': 'Mozilla/5.0 (Linux; Android 11; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.91 Mobile Safari/537.36',
        'device_scale_factor': 3,
        'is_mobile': True,
        'has_touch': True,
    },
    'galaxy_s23': {
        'viewport': {'width': 360, 'height': 780},
        'user_agent': 'Mozilla/5.0 (Linux; Android 13; SM-S911B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36',
        'device_scale_factor': 3,
        'is_mobile': True,
        'has_touch': True,
    },

    # Tablets
    'ipad_pro': {
        'viewport': {'width': 1024, 'height': 1366},
        'user_agent': 'Mozilla/5.0 (iPad; CPU OS 14_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1',
        'device_scale_factor': 2,
        'is_mobile': True,
        'has_touch': True,
    },
    'ipad_mini': {
        'viewport': {'width': 768, 'height': 1024},
        'user_agent': 'Mozilla/5.0 (iPad; CPU OS 14_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1',
        'device_scale_factor': 2,
        'is_mobile': True,
        'has_touch': True,
    },
    'galaxy_tab_s8': {
        'viewport': {'width': 800, 'height': 1280},
        'user_agent': 'Mozilla/5.0 (Linux; Android 12; SM-X800) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.45 Safari/537.36',
        'device_scale_factor': 2,
        'is_mobile': True,
        'has_touch': True,
    },

    # Desktop
    'desktop_chrome': {
        'viewport': {'width': 1920, 'height': 1080},
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'device_scale_factor': 1,
        'is_mobile': False,
        'has_touch': False,
    },
    'desktop_firefox': {
        'viewport': {'width': 1920, 'height': 1080},
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/120.0',
        'device_scale_factor': 1,
        'is_mobile': False,
        'has_touch': False,
    },
    'desktop_safari': {
        'viewport': {'width': 1920, 'height': 1080},
        'user_agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
        'device_scale_factor': 2,
        'is_mobile': False,
        'has_touch': False,
    },
    'desktop_edge': {
        'viewport': {'width': 1920, 'height': 1080},
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0',
        'device_scale_factor': 1,
        'is_mobile': False,
        'has_touch': False,
    },

    # Special viewports
    'laptop': {
        'viewport': {'width': 1366, 'height': 768},
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'device_scale_factor': 1,
        'is_mobile': False,
        'has_touch': False,
    },
    'macbook_pro': {
        'viewport': {'width': 1440, 'height': 900},
        'user_agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
        'device_scale_factor': 2,
        'is_mobile': False,
        'has_touch': False,
    },
}


@register_module(
    module_id='browser.emulate',
    version='1.0.0',
    category='browser',
    tags=['browser', 'emulation', 'device', 'mobile', 'viewport', 'responsive'],
    label='Device Emulation',
    label_key='modules.browser.emulate.label',
    description='Emulate mobile devices, tablets, and custom viewports',
    description_key='modules.browser.emulate.description',
    icon='Smartphone',
    color='#8B5CF6',

    # Connection types
    input_types=['browser'],
    output_types=['page'],

    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'flow.*'],

    params_schema=compose(
        field(
            'device',
            type='string',
            label='Device',
            label_key='modules.browser.emulate.params.device.label',
            description='Device preset or "custom" for manual settings',
            required=True,
            options=[
                {'value': 'iphone_12', 'label': 'iPhone 12'},
                {'value': 'iphone_14', 'label': 'iPhone 14'},
                {'value': 'iphone_14_pro_max', 'label': 'iPhone 14 Pro Max'},
                {'value': 'iphone_se', 'label': 'iPhone SE'},
                {'value': 'pixel_7', 'label': 'Pixel 7'},
                {'value': 'pixel_5', 'label': 'Pixel 5'},
                {'value': 'galaxy_s21', 'label': 'Galaxy S21'},
                {'value': 'galaxy_s23', 'label': 'Galaxy S23'},
                {'value': 'ipad_pro', 'label': 'iPad Pro'},
                {'value': 'ipad_mini', 'label': 'iPad Mini'},
                {'value': 'galaxy_tab_s8', 'label': 'Galaxy Tab S8'},
                {'value': 'desktop_chrome', 'label': 'Desktop Chrome'},
                {'value': 'desktop_firefox', 'label': 'Desktop Firefox'},
                {'value': 'desktop_safari', 'label': 'Desktop Safari'},
                {'value': 'desktop_edge', 'label': 'Desktop Edge'},
                {'value': 'laptop', 'label': 'Laptop (1366x768)'},
                {'value': 'macbook_pro', 'label': 'MacBook Pro'},
                {'value': 'custom', 'label': 'Custom'},
            ],
        ),
        field(
            'width',
            type='number',
            label='Width',
            label_key='modules.browser.emulate.params.width.label',
            description='Custom viewport width (for custom device)',
            required=False,
            min=320,
            max=3840,
        ),
        field(
            'height',
            type='number',
            label='Height',
            label_key='modules.browser.emulate.params.height.label',
            description='Custom viewport height (for custom device)',
            required=False,
            min=240,
            max=2160,
        ),
        field(
            'user_agent',
            type='string',
            label='User Agent',
            label_key='modules.browser.emulate.params.user_agent.label',
            description='Custom user agent string',
            required=False,
        ),
        field(
            'is_mobile',
            type='boolean',
            label='Mobile Mode',
            label_key='modules.browser.emulate.params.is_mobile.label',
            description='Enable mobile browser behavior',
            required=False,
            default=None,
        ),
        field(
            'has_touch',
            type='boolean',
            label='Touch Support',
            label_key='modules.browser.emulate.params.has_touch.label',
            description='Enable touch event support',
            required=False,
            default=None,
        ),
        field(
            'device_scale_factor',
            type='number',
            label='Device Scale Factor',
            label_key='modules.browser.emulate.params.device_scale_factor.label',
            description='Device pixel ratio (1-3)',
            required=False,
            min=1,
            max=3,
        ),
    ),
    output_schema={
        'status': {
            'type': 'string',
            'description': 'Operation status',
            'description_key': 'modules.browser.emulate.output.status.description'
        },
        'device': {
            'type': 'string',
            'description': 'Emulated device name',
            'description_key': 'modules.browser.emulate.output.device.description'
        },
        'viewport': {
            'type': 'object',
            'description': 'Applied viewport dimensions',
            'description_key': 'modules.browser.emulate.output.viewport.description'
        },
        'is_mobile': {
            'type': 'boolean',
            'description': 'Whether mobile mode is enabled',
            'description_key': 'modules.browser.emulate.output.is_mobile.description'
        },
    },
    examples=[
        {
            'name': 'Emulate iPhone 14',
            'params': {'device': 'iphone_14'}
        },
        {
            'name': 'Emulate iPad Pro',
            'params': {'device': 'ipad_pro'}
        },
        {
            'name': 'Custom mobile viewport',
            'params': {
                'device': 'custom',
                'width': 400,
                'height': 800,
                'is_mobile': True,
                'has_touch': True,
                'device_scale_factor': 2
            }
        },
        {
            'name': 'Desktop with custom user agent',
            'params': {
                'device': 'desktop_chrome',
                'user_agent': 'CustomBot/1.0'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=30000,
    required_permissions=['browser.automation'],
)
class BrowserEmulateModule(BaseModule):
    """Device Emulation Module"""

    module_name = "Device Emulation"
    module_description = "Emulate mobile devices and viewports"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        self.device = self.params.get('device')
        if not self.device:
            raise ValueError("Missing required parameter: device")

        # Get device preset or use custom
        if self.device == 'custom':
            # Custom device requires width and height
            self.width = self.params.get('width')
            self.height = self.params.get('height')
            if not self.width or not self.height:
                raise ValueError("Custom device requires width and height")
            self.preset = None
        elif self.device in DEVICE_PRESETS:
            self.preset = DEVICE_PRESETS[self.device]
            self.width = self.params.get('width', self.preset['viewport']['width'])
            self.height = self.params.get('height', self.preset['viewport']['height'])
        else:
            raise ValueError(
                f"Unknown device: {self.device}. "
                f"Available: {', '.join(sorted(DEVICE_PRESETS.keys()))}, custom"
            )

        # Custom overrides
        self.user_agent = self.params.get('user_agent')
        self.is_mobile = self.params.get('is_mobile')
        self.has_touch = self.params.get('has_touch')
        self.device_scale_factor = self.params.get('device_scale_factor')

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        # Build emulation settings
        if self.preset:
            settings = {
                'viewport': {'width': self.width, 'height': self.height},
                'user_agent': self.user_agent or self.preset['user_agent'],
                'device_scale_factor': self.device_scale_factor or self.preset['device_scale_factor'],
                'is_mobile': self.is_mobile if self.is_mobile is not None else self.preset['is_mobile'],
                'has_touch': self.has_touch if self.has_touch is not None else self.preset['has_touch'],
            }
        else:
            # Custom device
            settings = {
                'viewport': {'width': self.width, 'height': self.height},
                'user_agent': self.user_agent or 'Mozilla/5.0 (compatible)',
                'device_scale_factor': self.device_scale_factor or 1,
                'is_mobile': self.is_mobile if self.is_mobile is not None else False,
                'has_touch': self.has_touch if self.has_touch is not None else False,
            }

        # Close current page and context
        old_page = browser._page
        old_context = browser._context
        current_url = old_page.url if old_page else None

        try:
            # Create new context with device emulation
            new_context = await browser._browser.new_context(
                viewport=settings['viewport'],
                user_agent=settings['user_agent'],
                device_scale_factor=settings['device_scale_factor'],
                is_mobile=settings['is_mobile'],
                has_touch=settings['has_touch'],
            )

            # Create new page
            new_page = await new_context.new_page()

            # Navigate to same URL if we had one
            if current_url and current_url != 'about:blank':
                await new_page.goto(current_url)

            # Close old context (this also closes old page)
            await old_context.close()

            # Update browser references
            browser._context = new_context
            browser._page = new_page

            return {
                "status": "success",
                "device": self.device,
                "viewport": settings['viewport'],
                "user_agent": settings['user_agent'],
                "is_mobile": settings['is_mobile'],
                "has_touch": settings['has_touch'],
                "device_scale_factor": settings['device_scale_factor'],
                "url": new_page.url,
            }

        except Exception as e:
            # Try to restore old context on error
            browser._context = old_context
            browser._page = old_page
            raise RuntimeError(f"Failed to apply device emulation: {str(e)}") from e
