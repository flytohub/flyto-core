"""
Web Scrape to JSON Composite Module

Scrapes a webpage and outputs structured JSON data.
"""
from ..base import CompositeModule, register_composite, UIVisibility


@register_composite(
    module_id='composite.browser.scrape_to_json',
    version='1.1.0',
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
    ui_help='This module launches a headless browser, navigates to the specified URL, '
            'waits for the page to load, then extracts titles, links, and content '
            'using CSS selectors. The extracted data is returned as structured JSON. '
            'Supports JavaScript-rendered pages.',
    ui_help_key='composite.scrape_to_json.help',
    ui_group='Browser / Scraping',
    ui_icon='FileJson',
    ui_color='#10B981',

    # Connection types with labels and descriptions
    input_types=['string'],
    input_type_labels={
        'string': 'URL',
    },
    input_type_descriptions={
        'string': 'The full webpage URL to scrape (must include https://)',
    },

    output_types=['json', 'object'],
    output_type_labels={
        'json': 'Extracted Data',
        'object': 'Result Object',
    },
    output_type_descriptions={
        'json': 'JSON containing titles, links, and content arrays',
        'object': 'Full result with status, url, and data fields',
    },

    # Connection suggestions
    suggested_predecessors=[
        'core.file.read',
        'core.string.template',
        'core.data.transform',
    ],
    suggested_successors=[
        'core.file.write',
        'core.data.transform',
        'api.notion.create_page',
        'api.google_sheets.write',
    ],

    # Connection error messages
    connection_error_messages={
        'type_mismatch': 'This module expects a URL string, but received {received}',
        'missing_url': 'Please provide a URL to scrape',
    },

    # UI form generation with enhanced fields
    ui_params_schema={
        'url': {
            'type': 'string',
            'label': 'URL',
            'label_key': 'composite.scrape_to_json.url.label',
            'description': 'The webpage URL to scrape',
            'description_key': 'composite.scrape_to_json.url.desc',
            'help': 'Enter the full URL including https://. This module supports '
                    'JavaScript-rendered pages and will wait for content to load.',
            'help_key': 'composite.scrape_to_json.url.help',
            'hint': 'Tip: Test the URL in your browser first to ensure it loads correctly',
            'hint_key': 'composite.scrape_to_json.url.hint',
            'warning': 'Please ensure you have permission to scrape the target website',
            'warning_key': 'composite.scrape_to_json.url.warning',
            'placeholder': 'https://example.com',
            'examples': [
                'https://news.ycombinator.com',
                'https://github.com/trending',
                'https://www.producthunt.com',
            ],
            'required': True,
            'ui_component': 'input',
            'validation': {
                'pattern': r'^https?://.+',
                'pattern_error': 'URL must start with http:// or https://',
                'min_length': 10,
                'max_length': 2000,
            },
            'error_messages': {
                'required': 'Please enter a URL to scrape',
                'pattern': 'Invalid URL format. Must start with http:// or https://',
                'min_length': 'URL is too short',
                'max_length': 'URL exceeds maximum length of 2000 characters',
            },
        },
        'title_selector': {
            'type': 'string',
            'label': 'Title Selector',
            'label_key': 'composite.scrape_to_json.title_selector.label',
            'description': 'CSS selector for title elements',
            'description_key': 'composite.scrape_to_json.title_selector.desc',
            'help': 'Enter a CSS selector to find title elements. Multiple elements '
                    'will be extracted if the selector matches more than one element.',
            'help_key': 'composite.scrape_to_json.title_selector.help',
            'hint': 'Tip: Right-click an element in browser DevTools and select "Copy selector"',
            'hint_key': 'composite.scrape_to_json.title_selector.hint',
            'placeholder': 'h1, h2, .title',
            'examples': [
                'h1',
                '.article-title',
                '[data-testid="title"]',
                '.titleline > a',
            ],
            'required': True,
            'ui_component': 'input',
            'validation': {
                'min_length': 1,
                'max_length': 500,
            },
            'error_messages': {
                'required': 'Please enter a CSS selector for titles',
            },
        },
        'link_selector': {
            'type': 'string',
            'label': 'Link Selector',
            'label_key': 'composite.scrape_to_json.link_selector.label',
            'description': 'CSS selector for link elements',
            'description_key': 'composite.scrape_to_json.link_selector.desc',
            'help': 'Enter a CSS selector to find anchor (a) elements. '
                    'The href attribute will be extracted from each match.',
            'help_key': 'composite.scrape_to_json.link_selector.help',
            'placeholder': 'a.item-link',
            'examples': [
                'a.article-link',
                '.post a[href]',
                'nav a',
            ],
            'required': False,
            'ui_component': 'input',
        },
        'content_selector': {
            'type': 'string',
            'label': 'Content Selector',
            'label_key': 'composite.scrape_to_json.content_selector.label',
            'description': 'CSS selector for content elements',
            'description_key': 'composite.scrape_to_json.content_selector.desc',
            'help': 'Enter a CSS selector to find content/body elements. '
                    'The text content will be extracted from each match.',
            'help_key': 'composite.scrape_to_json.content_selector.help',
            'placeholder': '.content, p',
            'examples': [
                '.article-body p',
                '.description',
                '[class*="content"]',
            ],
            'required': False,
            'ui_component': 'input',
        },
        'wait_selector': {
            'type': 'string',
            'label': 'Wait Selector',
            'label_key': 'composite.scrape_to_json.wait_selector.label',
            'description': 'CSS selector to wait for before scraping',
            'description_key': 'composite.scrape_to_json.wait_selector.desc',
            'help': 'The module will wait for this element to appear before '
                    'starting extraction. Useful for JavaScript-rendered pages.',
            'help_key': 'composite.scrape_to_json.wait_selector.help',
            'hint': 'Leave as "body" for simple pages, or specify a key element for SPAs',
            'hint_key': 'composite.scrape_to_json.wait_selector.hint',
            'placeholder': 'body',
            'default': 'body',
            'examples': [
                'body',
                '.main-content',
                '[data-loaded="true"]',
            ],
            'required': False,
            'ui_component': 'input',
        }
    },

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

    # Enhanced output schema
    output_schema={
        'status': {
            'type': 'string',
            'description': 'Execution status',
            'help': 'Returns "success" on successful extraction',
            'enum': ['success', 'partial', 'failed'],
            'example': 'success',
        },
        'url': {
            'type': 'string',
            'description': 'The scraped URL',
            'example': 'https://news.ycombinator.com',
        },
        'data': {
            'type': 'object',
            'description': 'Extracted data',
            'help': 'Contains arrays of extracted titles, links, and content',
            'properties': {
                'titles': {
                    'type': 'array',
                    'description': 'Extracted title texts',
                    'example': ['First Title', 'Second Title'],
                },
                'links': {
                    'type': 'array',
                    'description': 'Extracted URLs from link elements',
                    'example': ['https://example.com/1', 'https://example.com/2'],
                },
                'content': {
                    'type': 'array',
                    'description': 'Extracted content texts',
                    'example': ['First paragraph...', 'Second paragraph...'],
                }
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
            'name': 'Scrape Hacker News',
            'description': 'Extract headlines and links from Hacker News front page',
            'params': {
                'url': 'https://news.ycombinator.com',
                'title_selector': '.titleline > a',
                'link_selector': '.titleline > a',
                'wait_selector': '.itemlist'
            }
        },
        {
            'name': 'Scrape GitHub Trending',
            'description': 'Extract trending repository names',
            'params': {
                'url': 'https://github.com/trending',
                'title_selector': 'h2.h3 a',
                'link_selector': 'h2.h3 a',
                'content_selector': 'p.col-9'
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
