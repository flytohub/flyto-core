"""
Browser Frame Module

Switch to iframe or frame context.
"""
from typing import Any, Dict, Optional
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets, field


@register_module(
    module_id='browser.frame',
    version='1.0.0',
    category='browser',
    tags=['browser', 'frame', 'iframe', 'ssrf_protected'],
    label='Switch Frame',
    label_key='modules.browser.frame.label',
    description='Switch to iframe or frame context',
    description_key='modules.browser.frame.description',
    icon='LayoutGrid',
    color='#0D6EFD',

    # Connection types
    input_types=['page'],
    output_types=['page'],


    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'page.*', 'screenshot.*', 'flow.*'],
    params_schema=compose(
        presets.SELECTOR(required=False, placeholder='iframe#content'),
        field(
            'name',
            type='string',
            label='Frame Name',
            label_key='modules.browser.frame.params.name.label',
            description='Name attribute of the frame (alternative to selector)',
            placeholder='my-name',
            required=False,
        ),
        field(
            'url',
            type='string',
            label='Frame URL',
            label_key='modules.browser.frame.params.url.label',
            description='URL pattern to match frame (alternative to selector)',
            placeholder='https://example.com',
            required=False,
        ),
        field(
            'action',
            type='string',
            label='Action',
            label_key='modules.browser.frame.params.action.label',
            description='Frame action to perform',
            default='enter',
            options=[
                {'value': 'enter', 'label': 'Enter Frame (switch context)'},
                {'value': 'list', 'label': 'List All Frames'},
            ],
        ),
        presets.TIMEOUT_MS(default=30000),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.browser.frame.output.status.description'},
        'frame_url': {'type': 'string', 'description': 'Frame URL',
                'description_key': 'modules.browser.frame.output.frame_url.description'},
        'frame_name': {'type': 'string', 'description': 'The frame name',
                'description_key': 'modules.browser.frame.output.frame_name.description'},
        'frames': {'type': 'array', 'description': 'List of frames',
                'description_key': 'modules.browser.frame.output.frames.description'}
    },
    examples=[
        {
            'name': 'Switch to iframe by selector',
            'params': {'selector': 'iframe#content-frame'}
        },
        {
            'name': 'Switch to frame by name',
            'params': {'name': 'main-content'}
        },
        {
            'name': 'List all frames',
            'params': {'action': 'list'}
        }
    ],
    author='Flyto Team',
    license='MIT',
    timeout_ms=30000,
    required_permissions=["browser.automation"],
)
class BrowserFrameModule(BaseModule):
    """Switch Frame Module"""

    module_name = "Switch Frame"
    module_description = "Switch to iframe or frame context"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        self.selector = self.params.get('selector')
        self.name = self.params.get('name')
        self.url = self.params.get('url')
        self.action = self.params.get('action', 'enter')
        self.timeout = self.params.get('timeout', 30000)

        if self.action == 'enter' and not any([self.selector, self.name, self.url]):
            raise ValueError("enter action requires selector, name, or url")

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        page = browser.page

        if self.action == 'list':
            # List all frames
            frames = []
            for frame in page.frames:
                frames.append({
                    'name': frame.name,
                    'url': frame.url,
                    'is_main': frame == page.main_frame
                })
            return {
                "status": "success",
                "frames": frames,
                "count": len(frames)
            }

        # Find and switch to frame
        frame = None

        if self.selector:
            # Get frame by selector
            frame_element = await page.wait_for_selector(
                self.selector,
                timeout=self.timeout
            )
            frame = await frame_element.content_frame()

        elif self.name:
            # Get frame by name
            frame = page.frame(name=self.name)

        elif self.url:
            # Get frame by URL pattern
            import re
            pattern = re.compile(self.url)
            for f in page.frames:
                if pattern.search(f.url):
                    frame = f
                    break

        if not frame:
            raise RuntimeError(f"Frame not found")

        # Store the frame in context for subsequent operations
        self.context['current_frame'] = frame

        return {
            "status": "success",
            "frame_url": frame.url,
            "frame_name": frame.name or "(unnamed)"
        }
