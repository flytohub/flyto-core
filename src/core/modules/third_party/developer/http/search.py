# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Search API Modules

Google Search, SerpAPI, and Tavily integration modules.

HOW FAR THESE THREE FOLLOW REALITY

The same three answers in all three modules, because all three do the same
thing: send one request to a search API and read the reply to that same
request.

  the API answered 200                       ACCEPTED
      A server received the query, ran it, and chose a reply. The results in
      that reply are the peer describing its own work, which is what
      `http.request` settled for every 2xx in this product and what all
      thirteen `api.*` modules claim (`tests/modules/test_api_outcome.py`).
      Nothing here reads anything back, so there is no rung above it.

      The number of results is recorded in the effect and is deliberately NOT
      allowed to raise the rung to OBSERVED, which is where `database.query`
      draws the same line from the other side: `len(rows)` earns OBSERVED there
      because the rows ARE the state a SELECT went to look at, while a search
      API's `organic_results` array is a document the vendor composed about a
      query it ran for us. A count of items in a reply is not a measurement of
      the world; it is a measurement of the reply.

  the API answered non-2xx                   FAILED
      A read that was refused returned no data and changed nothing on either
      side, which is `integrations/outcomes.py::read_refused`'s reasoning and
      applies unchanged: nothing about the world is in doubt, only data we do
      not have.

  no API key configured                      FAILED, and nothing was sent
      Worth its own envelope precisely because of what happens without one:
      `default_for` stamps a module that reports nothing as `dispatched` -- "the
      instruction left us" -- and for a module that returned a setup guide
      without opening a socket, that default is false in the direction that
      matters. These three returns also carry no `ok` key, so the engine records
      the step as a SUCCESS and a setup guide flows downstream in the shape of
      a search result. The rung is what tells a consumer otherwise.

WHAT IS MISSING, and is not papered over: none of the three wraps its request
in a try/except, so a timeout or a transport error escapes as an exception and
no payload -- and therefore no INDETERMINATE envelope -- ever reaches a
consumer. For a read that is a smaller loss than it would be for a write:
nothing is left half-done at the far end. Adding a handler here would change
the retry semantics of three modules for a rung that only says "we do not
know", so it is written down rather than done.
"""

import os
from typing import Any, Dict, Optional

import aiohttp

from .....constants import APIEndpoints, EnvVars
from .....engine.outcome import ClaimBy, Outcome, envelope
from ....base import BaseModule
from ....registry import register_module
from ....schema import compose, presets


def _search_answered(*, service: str, status: int, result_count: int) -> Dict[str, Any]:
    """ACCEPTED -- the search API ran the query and sent back what it found.

    `result_count` rides in the effect, labelled as a count of the items the
    vendor put in this reply, so that a consumer reading `count: 0` can see
    which question that zero answers. It answers "how many results did this
    reply carry", never "how many exist" and never "was the query correct" --
    a renamed response key would produce the same 0 as a query that genuinely
    matched nothing, which is exactly why it does not decide the rung.
    """
    return envelope(
        Outcome.ACCEPTED,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'search_reply_read',
            'service': service,
            'status': status,
            'results_in_reply': result_count,
            'measured_by': 'HTTP status of the reply, and len() over the results array in it',
            'detail': (
                'A search API answered this query. The results are the vendor '
                'reporting on work it did for us; nothing was read back and '
                'nothing was verified, so this is the whole distance travelled.'
            ),
        }],
    )


def _search_refused(*, service: str, status: int, message: Optional[str] = None) -> Dict[str, Any]:
    """FAILED -- the API answered, and its answer was a refusal.

    FAILED rather than INDETERMINATE: a search alters nothing at either end, so
    a refusal leaves no effect in doubt. There is only data we do not have.
    """
    return envelope(
        Outcome.FAILED,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'search_refused',
            'service': service,
            'status': status,
            'message': message,
            'measured_by': 'HTTP status of the reply',
            'detail': 'The API refused this query and returned no results.',
        }],
    )


def _search_not_sent(*, service: str, missing: str) -> Dict[str, Any]:
    """FAILED -- no credentials, so no request was built and none was sent."""
    return envelope(
        Outcome.FAILED,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'request_not_sent',
            'service': service,
            'missing': missing,
            'measured_by': 'os.getenv returned nothing before any session was opened',
            'detail': (
                'No request was issued: the credentials this module needs are not '
                'configured. The API was never contacted.'
            ),
        }],
    )


def _google_search_setup_error():
    return {
        "status": "error",
        "message": (
            f"Please set {EnvVars.GOOGLE_API_KEY} and "
            f"{EnvVars.GOOGLE_SEARCH_ENGINE_ID} environment variables"
        ),
        "setup_guide": {
            "step1": "Go to https://console.cloud.google.com/apis/credentials",
            "step2": "Create API Key",
            "step3": "Enable Custom Search API",
            "step4": "Go to https://programmablesearchengine.google.com/",
            "step5": "Create search engine and get Search Engine ID",
            "step6": (
                f"Set environment variables: {EnvVars.GOOGLE_API_KEY} and "
                f"{EnvVars.GOOGLE_SEARCH_ENGINE_ID}"
            ),
        },
        "outcome": _search_not_sent(
            service='google',
            missing=f'{EnvVars.GOOGLE_API_KEY} and/or {EnvVars.GOOGLE_SEARCH_ENGINE_ID}',
        ),
    }


def _parse_search_results(items):
    return [{'title': i.get('title'), 'url': i.get('link'), 'description': i.get('snippet')} for i in items]


@register_module(
    module_id='core.api.google_search',
    version='1.0.0',
    category='api',
    subcategory='api',
    tags=['api', 'search', 'google', 'official', 'ssrf_protected'],
    label='Google Search (API)',
    label_key='modules.api.google_search.label',
    description='Use Google Custom Search API to search keywords',
    description_key='modules.api.google_search.description',
    icon='Search',
    color='#4285F4',
    input_types=['string'],
    output_types=['json', 'array', 'api_response'],
    can_connect_to=['data.*', 'notify.*', 'file.*'],
    can_receive_from=['start', 'flow.*'],
    timeout_ms=30000,
    retryable=True,
    max_retries=3,
    concurrent_safe=True,
    requires_credentials=True,
    credential_keys=['GOOGLE_API_KEY', 'GOOGLE_SEARCH_ENGINE_ID'],
    handles_sensitive_data=False,
    required_permissions=['network.access'],
    params_schema=compose(
        presets.SEARCH_KEYWORD(placeholder='python tutorial'),
        presets.SEARCH_LIMIT(max_val=10),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.core.api.google_search.output.status.description'},
        'data': {'type': 'array', 'description': 'Output data from the operation',
                'description_key': 'modules.core.api.google_search.output.data.description'},
        'count': {'type': 'number', 'description': 'Number of items',
                'description_key': 'modules.core.api.google_search.output.count.description'},
        'total_results': {'type': 'number', 'optional': True, 'description': 'Total number of search results available',
                'description_key': 'modules.core.api.google_search.output.total_results.description'},
        'outcome': {'type': 'object', 'description': (
                    'How far the search was followed: "accepted" when the API answered, '
                    '"failed" when it refused or when no API key was configured and no '
                    'request was sent. Never higher: the results are the vendor reporting '
                    'on its own work'),
                'description_key': 'modules.core.api.google_search.output.outcome.description'}
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

    def validate_params(self) -> None:
        if 'keyword' not in self.params:
            raise ValueError("Missing parameter: keyword")
        self.keyword = self.params['keyword']
        self.limit = self.params.get('limit', 10)

    async def execute(self) -> Any:
        api_key = os.getenv(EnvVars.GOOGLE_API_KEY)
        search_engine_id = os.getenv(EnvVars.GOOGLE_SEARCH_ENGINE_ID)

        if not api_key or not search_engine_id:
            return _google_search_setup_error()

        params = {'key': api_key, 'cx': search_engine_id, 'q': self.keyword, 'num': min(self.limit, 10)}
        timeout = aiohttp.ClientTimeout(total=30)
        async with (
            aiohttp.ClientSession(timeout=timeout) as session,
            session.get(APIEndpoints.GOOGLE_SEARCH_URL, params=params) as response,
        ):
            if response.status != 200:
                error_data = await response.json()
                message = f"API error: {error_data.get('error', {}).get('message', 'Unknown error')}"
                return {
                    "status": "error",
                    "message": message,
                    "outcome": _search_refused(
                        service='google', status=response.status, message=message,
                    ),
                }
            data = await response.json()
            results = _parse_search_results(data.get('items', []))
            return {"status": "success", "data": results, "count": len(results),
                    "total_results": data.get('searchInformation', {}).get('totalResults', 0),
                    "outcome": _search_answered(
                        service='google', status=response.status, result_count=len(results),
                    )}


@register_module(
    module_id='core.api.serpapi_search',
    version='1.0.0',
    category='api',
    subcategory='api',
    tags=['api', 'search', 'google', 'serpapi', 'third-party', 'ssrf_protected'],
    label='Google Search (SerpAPI)',
    label_key='modules.api.serpapi_search.label',
    description='Use SerpAPI to search keywords (100 free searches/month)',
    description_key='modules.api.serpapi_search.description',
    icon='Search',
    color='#F39C12',
    input_types=['string'],
    output_types=['json', 'array', 'api_response'],
    can_connect_to=['data.*', 'notify.*', 'file.*'],
    can_receive_from=['start', 'flow.*'],
    timeout_ms=30000,
    retryable=True,
    max_retries=3,
    concurrent_safe=True,
    requires_credentials=True,
    credential_keys=['SERPAPI_KEY'],
    handles_sensitive_data=False,
    required_permissions=['network.access'],
    params_schema=compose(
        presets.SEARCH_KEYWORD(placeholder='python tutorial'),
        presets.SEARCH_LIMIT(),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)'},
        'data': {'type': 'array', 'description': 'Output data from the operation'},
        'count': {'type': 'number', 'description': 'Number of items'},
        'outcome': {'type': 'object', 'description': (
            'How far the search was followed: "accepted" when the API answered, '
            '"failed" when it refused or when no API key was configured and no '
            'request was sent. Never higher: the results are the vendor reporting '
            'on its own work')}
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

    def validate_params(self) -> None:
        if 'keyword' not in self.params:
            raise ValueError("Missing parameter: keyword")
        self.keyword = self.params['keyword']
        self.limit = self.params.get('limit', 10)

    async def execute(self) -> Any:
        api_key = os.getenv(EnvVars.SERPAPI_KEY)

        if not api_key:
            return {
                "status": "error",
                "message": f"Please set {EnvVars.SERPAPI_KEY} environment variable",
                "setup_guide": {
                    "step1": "Go to https://serpapi.com/",
                    "step2": "Register account (Free 100 searches per month)",
                    "step3": "Get API Key",
                    "step4": f"Set environment variable: {EnvVars.SERPAPI_KEY}"
                },
                "outcome": _search_not_sent(service='serpapi', missing=EnvVars.SERPAPI_KEY),
            }

        params = {
            'api_key': api_key,
            'q': self.keyword,
            'num': self.limit,
            'engine': 'google'
        }

        timeout = aiohttp.ClientTimeout(total=30)
        async with (
            aiohttp.ClientSession(timeout=timeout) as session,
            session.get(APIEndpoints.SERPAPI_BASE_URL, params=params) as response,
        ):
            if response.status != 200:
                return {
                    "status": "error",
                    "message": f"API error: HTTP {response.status}",
                    "outcome": _search_refused(service='serpapi', status=response.status),
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
                "count": len(results),
                "outcome": _search_answered(
                    service='serpapi', status=response.status, result_count=len(results),
                ),
            }


@register_module(
    module_id='core.api.tavily_search',
    version='1.0.0',
    category='api',
    subcategory='api',
    tags=['api', 'search', 'tavily', 'third-party', 'ssrf_protected'],
    label='Web Search (Tavily)',
    label_key='modules.api.tavily_search.label',
    description='Use Tavily API for AI-optimized web search',
    description_key='modules.api.tavily_search.description',
    icon='Search',
    color='#5B4FDB',
    input_types=['string'],
    output_types=['json', 'array', 'api_response'],
    can_connect_to=['data.*', 'notify.*', 'file.*'],
    can_receive_from=['start', 'flow.*'],
    timeout_ms=30000,
    retryable=True,
    max_retries=3,
    concurrent_safe=True,
    requires_credentials=True,
    credential_keys=['TAVILY_API_KEY'],
    handles_sensitive_data=False,
    required_permissions=['network.access'],
    params_schema=compose(
        presets.SEARCH_KEYWORD(placeholder='python tutorial'),
        presets.SEARCH_LIMIT(),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)'},
        'data': {'type': 'array', 'description': 'Output data from the operation'},
        'count': {'type': 'number', 'description': 'Number of items'},
        'outcome': {'type': 'object', 'description': (
            'How far the search was followed: "accepted" when the API answered, '
            '"failed" when it refused or when no API key was configured and no '
            'request was sent. Never higher: the results are the vendor reporting '
            'on its own work')}
    },
    examples=[{
        'title': 'Search with Tavily',
        'params': {
            'keyword': 'machine learning',
            'limit': 10
        }
    }],
    author='Flyto2 Team',
    license='MIT'
)
class TavilySearchModule(BaseModule):
    """Tavily Search Module - Use Tavily API for web search"""

    module_name = "Web Search (Tavily)"
    module_description = "Use Tavily API for AI-optimized web search"
    required_permission = "api.search"

    def validate_params(self) -> None:
        if 'keyword' not in self.params:
            raise ValueError("Missing parameter: keyword")
        self.keyword = self.params['keyword']
        self.limit = self.params.get('limit', 10)

    async def execute(self) -> Any:
        api_key = os.getenv(EnvVars.TAVILY_API_KEY)

        if not api_key:
            return {
                "status": "error",
                "message": f"Please set {EnvVars.TAVILY_API_KEY} environment variable",
                "setup_guide": {
                    "step1": "Go to https://app.tavily.com/",
                    "step2": "Create an account",
                    "step3": "Get API Key",
                    "step4": f"Set environment variable: {EnvVars.TAVILY_API_KEY}"
                },
                "outcome": _search_not_sent(service='tavily', missing=EnvVars.TAVILY_API_KEY),
            }

        payload = {
            'query': self.keyword,
            'max_results': min(max(self.limit, 1), APIEndpoints.TAVILY_MAX_RESULTS),
            'search_depth': 'basic',
        }
        headers = {'Authorization': f'Bearer {api_key}'}
        timeout = aiohttp.ClientTimeout(total=30)

        async with (
            aiohttp.ClientSession(timeout=timeout) as session,
            session.post(
                APIEndpoints.TAVILY_BASE_URL,
                headers=headers,
                json=payload,
            ) as response,
        ):
            if response.status != 200:
                return {
                    "status": "error",
                    "message": f"API error: HTTP {response.status}",
                    "outcome": _search_refused(service='tavily', status=response.status),
                }

            data = await response.json()

            results = []
            for item in data.get('results', []):
                results.append({
                    'title': item.get('title'),
                    'url': item.get('url'),
                    'description': item.get('content')
                })

            return {
                "status": "success",
                "data": results,
                "count": len(results),
                "outcome": _search_answered(
                    service='tavily', status=response.status, result_count=len(results),
                ),
            }
