"""
Web Scrape to JSON Composite Module

Scrapes a webpage and outputs structured JSON data.
Auto-derives connection types from steps.
"""
from ..base import CompositeModule, register_composite


@register_composite(
    module_id='composite.browser.scrape_to_json',
    label='Scrape Web to JSON',
    icon='FileJson',
    color='#10B981',

    steps=[
        {
            'id': 'launch',
            'module': 'browser.launch',
            'params': {'headless': True}
        },
        {
            'id': 'goto',
            'module': 'browser.goto',
            'params': {'url': '${params.url}'}
        },
        {
            'id': 'wait',
            'module': 'browser.wait',
            'params': {
                'selector': '${params.wait_selector}',
                'timeout': 10000
            },
            'on_error': 'continue'
        },
        {
            'id': 'extract_titles',
            'module': 'browser.extract',
            'params': {
                'selector': '${params.title_selector}',
                'attribute': 'textContent',
                'multiple': True
            }
        },
        {
            'id': 'extract_links',
            'module': 'browser.extract',
            'params': {
                'selector': '${params.link_selector}',
                'attribute': 'href',
                'multiple': True
            },
            'on_error': 'continue'
        },
        {
            'id': 'extract_content',
            'module': 'browser.extract',
            'params': {
                'selector': '${params.content_selector}',
                'attribute': 'textContent',
                'multiple': True
            },
            'on_error': 'continue'
        }
    ],

    params_schema={
        'url': {
            'type': 'string',
            'label': 'URL',
            'required': True,
            'placeholder': 'https://example.com'
        },
        'title_selector': {
            'type': 'string',
            'label': 'Title Selector',
            'required': True,
            'placeholder': 'h1, h2, .title'
        },
        'link_selector': {
            'type': 'string',
            'label': 'Link Selector',
            'placeholder': 'a.item-link'
        },
        'content_selector': {
            'type': 'string',
            'label': 'Content Selector',
            'placeholder': '.content, p'
        },
        'wait_selector': {
            'type': 'string',
            'label': 'Wait Selector',
            'default': 'body',
            'placeholder': 'body'
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

    timeout=60,
    retryable=True,
    max_retries=2,
)
class WebScrapeToJson(CompositeModule):
    """Web Scrape to JSON - extracts titles, links, and content from a webpage"""

    def _build_output(self, metadata):
        """Build structured JSON output from step results"""
        return {
            'status': 'success',
            'url': self.params.get('url', ''),
            'data': {
                'titles': self.step_results.get('extract_titles', {}).get('results', []),
                'links': self.step_results.get('extract_links', {}).get('results', []),
                'content': self.step_results.get('extract_content', {}).get('results', [])
            }
        }
