"""
API Related Modules - Use official API instead of scraping
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
import aiohttp
import os


@register_module(
    module_id='core.api.google_search',
    version='1.0.0',
    category='api',
    subcategory='api',
    tags=['api', 'search', 'google', 'official'],
    label='Google Search (API)',
    label_key='modules.api.google_search.label',
    description='Use Google Custom Search API to search keywords',
    description_key='modules.api.google_search.description',
    icon='Search',
    color='#4285F4',

    # Connection types
    input_types=[],
    output_types=['json', 'array', 'api_response'],
    can_connect_to=['data.*', 'notification.*', 'file.*'],

    # Phase 2: Execution settings
    timeout=30,  # API calls should not take more than 30s
    retryable=True,  # Network errors can be retried
    max_retries=3,
    concurrent_safe=True,  # Multiple searches can run in parallel

    # Phase 2: Security settings
    requires_credentials=True,  # Needs GOOGLE_API_KEY
    handles_sensitive_data=False,  # Search results are public data
    required_permissions=['network.access'],

    params_schema={
        'keyword': {
            'type': 'string',
            'label': 'Keyword',
            'label_key': 'modules.api.google_search.params.keyword.label',
            'description': 'Search keyword',
            'description_key': 'modules.api.google_search.params.keyword.description',
            'placeholder': 'python tutorial',
            'required': True
        },
        'limit': {
            'type': 'number',
            'label': 'Limit',
            'label_key': 'modules.api.google_search.params.limit.label',
            'description': 'Maximum number of results (max 10 per API call)',
            'description_key': 'modules.api.google_search.params.limit.description',
            'default': 10,
            'min': 1,
            'max': 10,
            'required': False
        }
    },
    output_schema={
        'status': {'type': 'string'},
        'data': {'type': 'array'},
        'count': {'type': 'number'},
        'total_results': {'type': 'number', 'optional': True}
    },
    examples=[{
        'title': 'Search Python tutorials',
        'params': {
            'keyword': 'python tutorial',
            'limit': 10
        }
    }],
    author='Flyto2 Team',
    license='MIT'
)
class GoogleSearchAPIModule(BaseModule):
    """Google Search API Module - Use official Custom Search API"""

    module_name = "Google Search (API)"
    module_description = "Use Google Custom Search API to search keywords"
    required_permission = "api.search"

    def validate_params(self):
        if 'keyword' not in self.params:
            raise ValueError("Missing parameter: keyword")
        self.keyword = self.params['keyword']
        self.limit = self.params.get('limit', 10)

    async def execute(self) -> Any:
        # Google Custom Search API requires API Key and Search Engine ID
        api_key = os.getenv('GOOGLE_API_KEY')
        search_engine_id = os.getenv('GOOGLE_SEARCH_ENGINE_ID')

        if not api_key or not search_engine_id:
            # If API Key is not set, return instructions
            return {
                "status": "error",
                "message": "Please set GOOGLE_API_KEY and GOOGLE_SEARCH_ENGINE_ID environment variables",
                "setup_guide": {
                    "step1": "Go to https://console.cloud.google.com/apis/credentials",
                    "step2": "Create API Key",
                    "step3": "Enable Custom Search API",
                    "step4": "Go to https://programmablesearchengine.google.com/",
                    "step5": "Create search engine and get Search Engine ID",
                    "step6": "Set environment variable: GOOGLE_API_KEY and GOOGLE_SEARCH_ENGINE_ID"
                }
            }

        # Call Google Custom Search API
        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            'key': api_key,
            'cx': search_engine_id,
            'q': self.keyword,
            'num': min(self.limit, 10)  # Google API returns at most 10 items per call
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                if response.status != 200:
                    error_data = await response.json()
                    return {
                        "status": "error",
                        "message": f"API error: {error_data.get('error', {}).get('message', 'Unknown error')}"
                    }

                data = await response.json()

                # Parse search results
                results = []
                for item in data.get('items', []):
                    results.append({
                        'title': item.get('title'),
                        'url': item.get('link'),
                        'description': item.get('snippet')
                    })

                return {
                    "status": "success",
                    "data": results,
                    "count": len(results),
                    "total_results": data.get('searchInformation', {}).get('totalResults', 0)
                }


@register_module(
    module_id='core.api.serpapi_search',
    version='1.0.0',
    category='api',
    subcategory='api',
    tags=['api', 'search', 'google', 'serpapi', 'third-party'],
    label='Google Search (SerpAPI)',
    label_key='modules.api.serpapi_search.label',
    description='Use SerpAPI to search keywords (100 free searches/month)',
    description_key='modules.api.serpapi_search.description',
    icon='Search',
    color='#F39C12',

    # Connection types
    input_types=[],
    output_types=['json', 'array', 'api_response'],
    can_connect_to=['data.*', 'notification.*', 'file.*'],

    params_schema={
        'keyword': {
            'type': 'string',
            'label': 'Keyword',
            'label_key': 'modules.api.serpapi_search.params.keyword.label',
            'description': 'Search keyword',
            'description_key': 'modules.api.serpapi_search.params.keyword.description',
            'placeholder': 'python tutorial',
            'required': True
        },
        'limit': {
            'type': 'number',
            'label': 'Limit',
            'label_key': 'modules.api.serpapi_search.params.limit.label',
            'description': 'Maximum number of results',
            'description_key': 'modules.api.serpapi_search.params.limit.description',
            'default': 10,
            'min': 1,
            'max': 100,
            'required': False
        }
    },
    output_schema={
        'status': {'type': 'string'},
        'data': {'type': 'array'},
        'count': {'type': 'number'}
    },
    examples=[{
        'title': 'Search with SerpAPI',
        'params': {
            'keyword': 'machine learning',
            'limit': 10
        }
    }],
    author='Flyto2 Team',
    license='MIT'
)
class SerpAPISearchModule(BaseModule):
    """SerpAPI Search Module - Use third-party API (with free tier)"""

    module_name = "Google Search (SerpAPI)"
    module_description = "Use SerpAPI to search keywords (100 free searches/month)"
    required_permission = "api.search"

    def validate_params(self):
        if 'keyword' not in self.params:
            raise ValueError("Missing parameter: keyword")
        self.keyword = self.params['keyword']
        self.limit = self.params.get('limit', 10)

    async def execute(self) -> Any:
        # SerpAPI provides 100 free searches per month
        api_key = os.getenv('SERPAPI_KEY')

        if not api_key:
            return {
                "status": "error",
                "message": "Please set SERPAPI_KEY environment variable",
                "setup_guide": {
                    "step1": "Go to https://serpapi.com/",
                    "step2": "Register account (Free 100 searches per month)",
                    "step3": "Get API Key",
                    "step4": "Set environment variable: SERPAPI_KEY"
                }
            }

        # Call SerpAPI
        url = "https://serpapi.com/search"
        params = {
            'api_key': api_key,
            'q': self.keyword,
            'num': self.limit,
            'engine': 'google'
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                if response.status != 200:
                    return {
                        "status": "error",
                        "message": f"API error: HTTP {response.status}"
                    }

                data = await response.json()

                # Parse search results
                results = []
                for item in data.get('organic_results', []):
                    results.append({
                        'title': item.get('title'),
                        'url': item.get('link'),
                        'description': item.get('snippet')
                    })

                return {
                    "status": "success",
                    "data": results,
                    "count": len(results)
                }


@register_module(
    module_id='core.api.http_get',
    version='1.0.0',
    category='api',
    subcategory='api',
    tags=['api', 'http', 'request', 'get'],
    label='HTTP GET Request',
    label_key='modules.api.http_get.label',
    description='Send HTTP GET request to any URL',
    description_key='modules.api.http_get.description',
    icon='Globe',
    color='#3B82F6',

    # Connection types
    input_types=[],
    output_types=['json', 'text', 'api_response'],
    can_connect_to=['data.*', 'notification.*', 'file.*'],

    params_schema={
        'url': {
            'type': 'string',
            'label': 'URL',
            'label_key': 'modules.api.http_get.params.url.label',
            'description': 'Target URL',
            'description_key': 'modules.api.http_get.params.url.description',
            'placeholder': 'https://api.example.com/data',
            'required': True
        },
        'headers': {
            'type': 'object',
            'label': 'Headers',
            'label_key': 'modules.api.http_get.params.headers.label',
            'description': 'HTTP headers (optional)',
            'description_key': 'modules.api.http_get.params.headers.description',
            'required': False
        },
        'params': {
            'type': 'object',
            'label': 'Query Parameters',
            'label_key': 'modules.api.http_get.params.params.label',
            'description': 'Query parameters (optional)',
            'description_key': 'modules.api.http_get.params.params.description',
            'required': False
        },
        'timeout': {
            'type': 'number',
            'label': 'Timeout',
            'label_key': 'modules.api.http_get.params.timeout.label',
            'description': 'Request timeout in seconds',
            'description_key': 'modules.api.http_get.params.timeout.description',
            'default': 30,
            'required': False
        }
    },
    output_schema={
        'status_code': {'type': 'number'},
        'headers': {'type': 'object'},
        'body': {'type': 'string'},
        'json': {'type': 'object', 'optional': True}
    },
    examples=[{
        'title': 'Fetch API data',
        'params': {
            'url': 'https://api.github.com/users/octocat'
        }
    }],
    author='Flyto2 Team',
    license='MIT'
)
class HTTPGetModule(BaseModule):
    """
    Send HTTP GET request

    Params:
        url: Target URL
        headers: Optional HTTP headers (dict)
        params: Optional query parameters (dict)
        timeout: Request timeout in seconds

    Output:
        {
            'status_code': int,
            'headers': dict,
            'body': str,
            'json': dict (if response is JSON)
        }
    """

    module_name = "HTTP GET Request"
    module_description = "Send HTTP GET request to any URL"

    def validate_params(self):
        if 'url' not in self.params:
            raise ValueError("Missing required parameter: url")

    async def execute(self) -> Any:
        url = self.params.get('url')
        headers = self.params.get('headers', {})
        params = self.params.get('params', {})
        timeout = self.params.get('timeout', 30)

        if not url:
            raise ValueError("URL is required")

        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers=headers,
                params=params,
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as response:
                status_code = response.status
                response_headers = dict(response.headers)
                body = await response.text()

                result = {
                    'status_code': status_code,
                    'headers': response_headers,
                    'body': body
                }

                # Try to parse as JSON
                if 'application/json' in response_headers.get('Content-Type', ''):
                    try:
                        result['json'] = await response.json()
                    except Exception:
                        pass

                return result


@register_module(
    module_id='core.api.http_post',
    version='1.0.0',
    category='api',
    subcategory='api',
    tags=['api', 'http', 'request', 'post'],
    label='HTTP POST Request',
    label_key='modules.api.http_post.label',
    description='Send HTTP POST request to any URL',
    description_key='modules.api.http_post.description',
    icon='Send',
    color='#3B82F6',

    # Connection types
    input_types=['json', 'text', 'any'],
    output_types=['json', 'text', 'api_response'],
    can_receive_from=['data.*'],
    can_connect_to=['data.*', 'notification.*', 'file.*'],

    params_schema={
        'url': {
            'type': 'string',
            'label': 'URL',
            'label_key': 'modules.api.http_post.params.url.label',
            'description': 'Target URL',
            'description_key': 'modules.api.http_post.params.url.description',
            'placeholder': 'https://api.example.com/data',
            'required': True
        },
        'headers': {
            'type': 'object',
            'label': 'Headers',
            'label_key': 'modules.api.http_post.params.headers.label',
            'description': 'HTTP headers (optional)',
            'description_key': 'modules.api.http_post.params.headers.description',
            'required': False
        },
        'body': {
            'type': 'string',
            'label': 'Body',
            'label_key': 'modules.api.http_post.params.body.label',
            'description': 'Request body (string)',
            'description_key': 'modules.api.http_post.params.body.description',
            'required': False,
            'multiline': True
        },
        'json': {
            'type': 'object',
            'label': 'JSON Data',
            'label_key': 'modules.api.http_post.params.json.label',
            'description': 'JSON data to send',
            'description_key': 'modules.api.http_post.params.json.description',
            'required': False
        },
        'timeout': {
            'type': 'number',
            'label': 'Timeout',
            'label_key': 'modules.api.http_post.params.timeout.label',
            'description': 'Request timeout in seconds',
            'description_key': 'modules.api.http_post.params.timeout.description',
            'default': 30,
            'required': False
        }
    },
    output_schema={
        'status_code': {'type': 'number'},
        'headers': {'type': 'object'},
        'body': {'type': 'string'},
        'json': {'type': 'object', 'optional': True}
    },
    examples=[{
        'title': 'Post JSON data',
        'params': {
            'url': 'https://api.example.com/users',
            'json': {'name': 'John', 'email': 'john@example.com'}
        }
    }],
    author='Flyto2 Team',
    license='MIT'
)
class HTTPPostModule(BaseModule):
    """
    Send HTTP POST request

    Params:
        url: Target URL
        headers: Optional HTTP headers (dict)
        body: Request body (string or dict)
        json: JSON data to send (dict)
        timeout: Request timeout in seconds

    Output:
        {
            'status_code': int,
            'headers': dict,
            'body': str,
            'json': dict (if response is JSON)
        }
    """

    module_name = "HTTP POST Request"
    module_description = "Send HTTP POST request to any URL"

    def validate_params(self):
        if 'url' not in self.params:
            raise ValueError("Missing required parameter: url")

    async def execute(self) -> Any:
        url = self.params.get('url')
        headers = self.params.get('headers', {})
        body = self.params.get('body')
        json_data = self.params.get('json')
        timeout = self.params.get('timeout', 30)

        if not url:
            raise ValueError("URL is required")

        kwargs = {
            'headers': headers,
            'timeout': aiohttp.ClientTimeout(total=timeout)
        }

        # Determine request type
        if json_data:
            kwargs['json'] = json_data
        elif body:
            kwargs['data'] = body

        async with aiohttp.ClientSession() as session:
            async with session.post(url, **kwargs) as response:
                status_code = response.status
                response_headers = dict(response.headers)
                response_body = await response.text()

                result = {
                    'status_code': status_code,
                    'headers': response_headers,
                    'body': response_body
                }

                # Try to parse as JSON
                if 'application/json' in response_headers.get('Content-Type', ''):
                    try:
                        result['json'] = await response.json()
                    except Exception:
                        pass

                return result
