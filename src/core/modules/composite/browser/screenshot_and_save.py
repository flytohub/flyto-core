"""
Screenshot and Save Composite Module

Takes a screenshot of a webpage and saves it to a file.
"""
from ..base import CompositeModule, register_composite, UIVisibility


@register_composite(
    module_id='composite.browser.screenshot_and_save',
    version='1.0.0',
    category='browser',
    subcategory='screenshot',
    tags=['browser', 'screenshot', 'file', 'save'],

    # Context requirements
    requires_context=None,
    provides_context=['file'],

    # UI metadata
    ui_visibility=UIVisibility.DEFAULT,
    ui_label='Screenshot and Save',
    ui_label_key='composite.screenshot_and_save.label',
    ui_description='Take a screenshot of a webpage and save it to a file',
    ui_description_key='composite.screenshot_and_save.desc',
    ui_group='Browser / Screenshot',
    ui_icon='Camera',
    ui_color='#8B5CF6',

    # UI form generation
    ui_params_schema={
        'url': {
            'type': 'string',
            'label': 'URL',
            'label_key': 'composite.screenshot_and_save.url.label',
            'description': 'The webpage URL to screenshot',
            'description_key': 'composite.screenshot_and_save.url.desc',
            'placeholder': 'https://example.com',
            'required': True,
            'ui_component': 'input',
        },
        'output_path': {
            'type': 'string',
            'label': 'Output Path',
            'label_key': 'composite.screenshot_and_save.output_path.label',
            'description': 'File path to save the screenshot',
            'description_key': 'composite.screenshot_and_save.output_path.desc',
            'placeholder': './screenshots/page.png',
            'required': True,
            'ui_component': 'input',
        },
        'wait_selector': {
            'type': 'string',
            'label': 'Wait Selector',
            'label_key': 'composite.screenshot_and_save.wait_selector.label',
            'description': 'CSS selector to wait for before screenshot',
            'description_key': 'composite.screenshot_and_save.wait_selector.desc',
            'placeholder': 'body',
            'default': 'body',
            'required': False,
            'ui_component': 'input',
        },
        'full_page': {
            'type': 'boolean',
            'label': 'Full Page',
            'label_key': 'composite.screenshot_and_save.full_page.label',
            'description': 'Capture the full page (not just viewport)',
            'description_key': 'composite.screenshot_and_save.full_page.desc',
            'default': False,
            'required': False,
            'ui_component': 'checkbox',
        }
    },

    # Connection types
    input_types=['url'],
    output_types=['file_path', 'screenshot'],

    # Steps definition
    steps=[
        {
            'id': 'launch',
            'module': 'core.browser.launch',
            'params': {
                'headless': True
            }
        },
        {
            'id': 'goto',
            'module': 'core.browser.goto',
            'params': {
                'url': '${params.url}'
            }
        },
        {
            'id': 'wait',
            'module': 'core.browser.wait',
            'params': {
                'selector': '${params.wait_selector}',
                'timeout': 10000
            },
            'on_error': 'continue'
        },
        {
            'id': 'screenshot',
            'module': 'core.browser.screenshot',
            'params': {
                'path': '${params.output_path}',
                'full_page': '${params.full_page}'
            }
        }
    ],

    # Output schema
    output_schema={
        'status': {'type': 'string'},
        'url': {'type': 'string'},
        'file_path': {'type': 'string'},
        'full_page': {'type': 'boolean'}
    },

    # Execution settings
    timeout=60,
    retryable=True,
    max_retries=2,

    # Documentation
    examples=[
        {
            'name': 'Screenshot homepage',
            'description': 'Take a full-page screenshot',
            'params': {
                'url': 'https://example.com',
                'output_path': './screenshots/example.png',
                'full_page': True
            }
        }
    ],
    author='Flyto Core Team',
    license='MIT'
)
class ScreenshotAndSave(CompositeModule):
    """
    Screenshot and Save Composite Module

    This composite module:
    1. Launches a headless browser
    2. Navigates to the target URL
    3. Waits for content to load
    4. Takes a screenshot
    5. Saves to the specified file path
    """

    def _build_output(self, metadata):
        """Build output with file path information"""
        screenshot_result = self.step_results.get('screenshot', {})

        return {
            'status': 'success',
            'url': self.params.get('url', ''),
            'file_path': self.params.get('output_path', ''),
            'full_page': self.params.get('full_page', False)
        }
