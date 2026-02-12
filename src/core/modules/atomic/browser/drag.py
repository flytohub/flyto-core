"""
Browser Drag Module

Drag and drop elements.
"""
from typing import Any, Dict, Optional
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets, field


@register_module(
    module_id='browser.drag',
    version='1.0.0',
    category='browser',
    tags=['browser', 'drag', 'drop', 'interaction', 'ssrf_protected'],
    label='Drag and Drop',
    label_key='modules.browser.drag.label',
    description='Drag and drop elements',
    description_key='modules.browser.drag.description',
    icon='Move',
    color='#6F42C1',

    # Connection types
    input_types=['page'],
    output_types=['page'],


    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'page.*', 'screenshot.*', 'flow.*'],    params_schema=compose(
        presets.SELECTOR(key='source', required=True, placeholder='#draggable', label='Source Selector'),
        presets.SELECTOR(key='target', required=True, placeholder='#dropzone', label='Target Selector'),
        field(
            'source_position',
            type='object',
            label='Source Position',
            label_key='modules.browser.drag.params.source_position.label',
            description='Position within source element {x, y} as percentages',
            required=False,
        ),
        field(
            'target_position',
            type='object',
            label='Target Position',
            label_key='modules.browser.drag.params.target_position.label',
            description='Position within target element {x, y} as percentages',
            required=False,
        ),
        presets.TIMEOUT_MS(default=30000),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.browser.drag.output.status.description'},
        'source': {'type': 'string', 'description': 'The source',
                'description_key': 'modules.browser.drag.output.source.description'},
        'target': {'type': 'string', 'description': 'The target',
                'description_key': 'modules.browser.drag.output.target.description'}
    },
    examples=[
        {
            'name': 'Simple drag and drop',
            'params': {'source': '#item1', 'target': '#dropzone'}
        },
        {
            'name': 'Drag to specific position',
            'params': {
                'source': '.draggable',
                'target': '.container',
                'target_position': {'x': 0.5, 'y': 0.5}
            }
        }
    ],
    author='Flyto Team',
    license='MIT',
    timeout_ms=30000,
    required_permissions=["browser.automation"],
)
class BrowserDragModule(BaseModule):
    """Drag and Drop Module"""

    module_name = "Drag and Drop"
    module_description = "Drag and drop elements"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        if 'source' not in self.params:
            raise ValueError("Missing required parameter: source")
        if 'target' not in self.params:
            raise ValueError("Missing required parameter: target")

        self.source = self.params['source']
        self.target = self.params['target']
        self.source_position = self.params.get('source_position')
        self.target_position = self.params.get('target_position')
        self.timeout = self.params.get('timeout', 30000)

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        page = browser.page

        # Wait for both elements
        source_locator = page.locator(self.source)
        target_locator = page.locator(self.target)

        await source_locator.wait_for(timeout=self.timeout)
        await target_locator.wait_for(timeout=self.timeout)

        # Get element bounding boxes
        source_box = await source_locator.bounding_box()
        target_box = await target_locator.bounding_box()

        if not source_box:
            raise RuntimeError(f"Could not get bounding box for source: {self.source}")
        if not target_box:
            raise RuntimeError(f"Could not get bounding box for target: {self.target}")

        # Calculate positions
        if self.source_position:
            source_x = source_box['x'] + source_box['width'] * self.source_position.get('x', 0.5)
            source_y = source_box['y'] + source_box['height'] * self.source_position.get('y', 0.5)
        else:
            source_x = source_box['x'] + source_box['width'] / 2
            source_y = source_box['y'] + source_box['height'] / 2

        if self.target_position:
            target_x = target_box['x'] + target_box['width'] * self.target_position.get('x', 0.5)
            target_y = target_box['y'] + target_box['height'] * self.target_position.get('y', 0.5)
        else:
            target_x = target_box['x'] + target_box['width'] / 2
            target_y = target_box['y'] + target_box['height'] / 2

        # Perform drag and drop
        await page.mouse.move(source_x, source_y)
        await page.mouse.down()
        await page.mouse.move(target_x, target_y, steps=10)
        await page.mouse.up()

        return {
            "status": "success",
            "source": self.source,
            "target": self.target,
            "from": {"x": source_x, "y": source_y},
            "to": {"x": target_x, "y": target_y}
        }
