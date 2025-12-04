"""
Web Scrape to JSON Composite Module

Scrapes a webpage and outputs structured JSON data.
"""
from ..base import CompositeModule, register_composite


@register_composite(
    module_id='composite.browser.scrape_to_json',
    version='1.0.0',
    category='composite',
    subcategory='browser',
    tags=['browser', 'scrape', 'json', 'data', 'extraction'],

    # Display
    label='Scrape Web to JSON',
    label_key='modules.composite.browser.scrape_to_json.label',
    description='Scrape a webpage and extract data into structured JSON format',
    description_key='modules.composite.browser.scrape_to_json.description',

    # Visual
    icon='FileJson',
    color='#10B981',

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

    # Schema
    params_schema={
        'url': {
            'type': 'string',
            'label': 'URL',
            'description': 'The webpage URL to scrape',
            'placeholder': 'https://example.com',
            'required': True
        },
        'title_selector': {
            'type': 'string',
            'label': 'Title Selector',
            'description': 'CSS selector for title elements',
            'placeholder': 'h1, h2, .title',
            'required': True
        },
        'link_selector': {
            'type': 'string',
            'label': 'Link Selector',
            'description': 'CSS selector for link elements',
            'placeholder': 'a.item-link',
            'required': False
        },
        'content_selector': {
            'type': 'string',
            'label': 'Content Selector',
            'description': 'CSS selector for content elements',
            'placeholder': '.content, p',
            'required': False
        },
        'wait_selector': {
            'type': 'string',
            'label': 'Wait Selector',
            'description': 'CSS selector to wait for before scraping',
            'placeholder': 'body',
            'default': 'body',
            'required': False
        }
    },
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
