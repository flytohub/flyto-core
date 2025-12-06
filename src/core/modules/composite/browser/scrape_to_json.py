"""
Web Scrape to JSON Composite Module

Scrapes a webpage and outputs structured JSON data.
"""
from ..base import CompositeModule, register_composite, UIVisibility


@register_composite(
    module_id='composite.browser.scrape_to_json',
    version='1.0.0',
    category='browser',
    subcategory='scrape',
    tags=['browser', 'scrape', 'json', 'data', 'extraction'],

    # Context requirements
    requires_context=None,
    provides_context=['data'],

    # UI metadata
    ui_visibility=UIVisibility.DEFAULT,
    ui_label='Scrape Web to JSON',
    ui_label_key='composite.scrape_to_json.label',
    ui_description='Scrape a webpage and extract data into structured JSON format',
    ui_description_key='composite.scrape_to_json.desc',
    ui_group='Browser / Scraping',
    ui_icon='FileJson',
    ui_color='#10B981',

    # UI form generation
    ui_params_schema={
        'url': {
            'type': 'string',
            'label': 'URL',
            'label_key': 'composite.scrape_to_json.url.label',
            'description': 'The webpage URL to scrape',
            'description_key': 'composite.scrape_to_json.url.desc',
            'placeholder': 'https://example.com',
            'required': True,
            'ui_component': 'input',
        },
        'title_selector': {
            'type': 'string',
            'label': 'Title Selector',
            'label_key': 'composite.scrape_to_json.title_selector.label',
            'description': 'CSS selector for title elements',
            'description_key': 'composite.scrape_to_json.title_selector.desc',
            'placeholder': 'h1, h2, .title',
            'required': True,
            'ui_component': 'input',
        },
        'link_selector': {
            'type': 'string',
            'label': 'Link Selector',
            'label_key': 'composite.scrape_to_json.link_selector.label',
            'description': 'CSS selector for link elements',
            'description_key': 'composite.scrape_to_json.link_selector.desc',
            'placeholder': 'a.item-link',
            'required': False,
            'ui_component': 'input',
        },
        'content_selector': {
            'type': 'string',
            'label': 'Content Selector',
            'label_key': 'composite.scrape_to_json.content_selector.label',
            'description': 'CSS selector for content elements',
            'description_key': 'composite.scrape_to_json.content_selector.desc',
            'placeholder': '.content, p',
            'required': False,
            'ui_component': 'input',
        },
        'wait_selector': {
            'type': 'string',
            'label': 'Wait Selector',
            'label_key': 'composite.scrape_to_json.wait_selector.label',
            'description': 'CSS selector to wait for before scraping',
            'description_key': 'composite.scrape_to_json.wait_selector.desc',
            'placeholder': 'body',
            'default': 'body',
            'required': False,
            'ui_component': 'input',
        }
    },

    # Connection types
    input_types=['url'],
    output_types=['json'],

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
            'id': 'extract_titles',
            'module': 'core.browser.extract',
            'params': {
                'selector': '${params.title_selector}',
                'attribute': 'textContent',
                'multiple': True
            }
        },
        {
            'id': 'extract_links',
            'module': 'core.browser.extract',
            'params': {
                'selector': '${params.link_selector}',
                'attribute': 'href',
                'multiple': True
            },
            'on_error': 'continue'
        },
        {
            'id': 'extract_content',
            'module': 'core.browser.extract',
            'params': {
                'selector': '${params.content_selector}',
                'attribute': 'textContent',
                'multiple': True
            },
            'on_error': 'continue'
        }
    ],

    # Output schema
    output_schema={
        'status': {'type': 'string'},
        'url': {'type': 'string'},
        'data': {
            'type': 'object',
            'properties': {
                'titles': {'type': 'array'},
                'links': {'type': 'array'},
                'content': {'type': 'array'}
            }
        }
    },

    # Execution settings
    timeout=60,
    retryable=True,
    max_retries=2,

    # Documentation
    examples=[
        {
            'name': 'Scrape news headlines',
            'description': 'Extract headlines from a news site',
            'params': {
                'url': 'https://news.ycombinator.com',
                'title_selector': '.titleline > a',
                'link_selector': '.titleline > a'
            }
        }
    ],
    author='Flyto Core Team',
    license='MIT'
)
class WebScrapeToJson(CompositeModule):
    """
    Web Scrape to JSON Composite Module

    This composite module:
    1. Launches a headless browser
    2. Navigates to the target URL
    3. Waits for content to load
    4. Extracts titles, links, and content
    5. Returns structured JSON data
    """

    def _build_output(self, metadata):
        """Build structured JSON output"""
        return {
            'status': 'success',
            'url': self.params.get('url', ''),
            'data': {
                'titles': self.step_results.get('extract_titles', {}).get('results', []),
                'links': self.step_results.get('extract_links', {}).get('results', []),
                'content': self.step_results.get('extract_content', {}).get('results', [])
            }
        }
