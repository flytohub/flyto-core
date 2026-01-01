"""
Search API Modules

Google Search and SerpAPI integration modules.
"""

import os
from typing import Any

import aiohttp

from ....base import BaseModule
from ....registry import register_module
from ....schema import compose, presets


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
    input_types=[],
    output_types=['json', 'array', 'api_response'],
    can_connect_to=['data.*', 'notification.*', 'file.*'],
    can_receive_from=['*'],
    timeout=30,
    retryable=True,
    max_retries=3,
    concurrent_safe=True,
    requires_credentials=True,
    handles_sensitive_data=False,
    required_permissions=['network.access'],
    params_schema=compose(
        presets.SEARCH_KEYWORD(placeholder='python tutorial'),
        presets.SEARCH_LIMIT(max_val=10),
    ),
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
        api_key = os.getenv('GOOGLE_API_KEY')
        search_engine_id = os.getenv('GOOGLE_SEARCH_ENGINE_ID')

        if not api_key or not search_engine_id:
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

        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            'key': api_key,
            'cx': search_engine_id,
            'q': self.keyword,
            'num': min(self.limit, 10)
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
    input_types=[],
    output_types=['json', 'array', 'api_response'],
    can_connect_to=['data.*', 'notification.*', 'file.*'],
    can_receive_from=['*'],
    params_schema=compose(
        presets.SEARCH_KEYWORD(placeholder='python tutorial'),
        presets.SEARCH_LIMIT(),
    ),
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
