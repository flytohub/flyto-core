# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Xquik API modules for X data and account workflows."""

import os
from typing import Any, Dict, Optional
from urllib.parse import quote, urlsplit

import aiohttp

from ....constants import APIEndpoints, EnvVars, Timeouts
from ...base import BaseModule
from ...registry import register_module


def _missing_api_key() -> Dict[str, Any]:
    return {
        "status": "error",
        "message": f"Set {EnvVars.XQUIK_API_KEY} or provide api_key.",
    }


def _normalize_path(path: str) -> str:
    parsed = urlsplit(path)
    if (
        not path.startswith("/")
        or parsed.scheme
        or parsed.netloc
        or parsed.query
        or parsed.fragment
        or ".." in parsed.path.split("/")
    ):
        raise ValueError("path must be an absolute Xquik API path without a host or query")
    return parsed.path


def _validate_idempotency_key(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 255
        or any(not 33 <= ord(character) <= 126 for character in value)
    ):
        raise ValueError("idempotency_key must contain 1 to 255 visible ASCII characters")
    return value


def _error_message(payload: Any, status: int) -> str:
    if isinstance(payload, dict):
        message = payload.get("message") or payload.get("error")
        if isinstance(message, str) and message:
            return message
    return f"Xquik API request failed with HTTP {status}"


async def _response_payload(response: aiohttp.ClientResponse) -> Any:
    try:
        return await response.json()
    except (aiohttp.ContentTypeError, ValueError):
        text = await response.text()
        return {"message": text} if text else {}


async def _xquik_request(
    method: str,
    path: str,
    api_key: str,
    *,
    query: Optional[Dict[str, Any]] = None,
    body: Optional[Dict[str, Any]] = None,
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    headers = {
        "Accept": "application/json",
        "x-api-key": api_key,
        "xquik-api-contract": APIEndpoints.XQUIK_API_CONTRACT,
    }
    if body is not None:
        headers["Content-Type"] = "application/json"
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key

    request_options: Dict[str, Any] = {"headers": headers}
    if query:
        request_options["params"] = query
    if body is not None:
        request_options["json"] = body

    timeout = aiohttp.ClientTimeout(total=Timeouts.API_DEFAULT)
    url = f"{APIEndpoints.XQUIK_BASE_URL}{_normalize_path(path)}"
    async with (
        aiohttp.ClientSession(timeout=timeout) as session,
        session.request(method, url, **request_options) as response,
    ):
        payload = await _response_payload(response)
        result = {
            "http_status": response.status,
            "data": payload,
        }
        if 200 <= response.status < 300:
            return {"status": "success", **result}
        return {
            "status": "error",
            "message": _error_message(payload, response.status),
            **result,
        }


def _api_key(params: Dict[str, Any]) -> Optional[str]:
    value = params.get("api_key") or os.getenv(EnvVars.XQUIK_API_KEY)
    return value if isinstance(value, str) and value else None


@register_module(
    module_id="api.xquik.request",
    version="1.0.0",
    category="api",
    subcategory="social",
    tags=["api", "xquik", "x", "social", "integration"],
    label="Xquik API Request",
    description="Call any documented Xquik API path",
    icon="Radio",
    color="#111827",
    input_types=["string", "object"],
    output_types=["json", "object", "api_response"],
    can_receive_from=["*"],
    can_connect_to=["*"],
    timeout_ms=30000,
    retryable=True,
    max_retries=3,
    concurrent_safe=True,
    requires_credentials=True,
    credential_keys=["XQUIK_API_KEY"],
    handles_sensitive_data=True,
    required_permissions=["network.access"],
    params_schema={
        "method": {
            "type": "select",
            "label": "Method",
            "description": "HTTP method for the Xquik API request",
            "options": ["GET", "POST", "PUT", "PATCH", "DELETE"],
            "default": "GET",
            "required": True,
        },
        "path": {
            "type": "string",
            "label": "API Path",
            "description": "Documented API path beginning with /",
            "placeholder": "/x/tweets/search",
            "required": True,
        },
        "query": {
            "type": "object",
            "label": "Query",
            "description": "Query parameters",
            "required": False,
        },
        "body": {
            "type": "object",
            "label": "Body",
            "description": "JSON request body",
            "required": False,
        },
        "idempotency_key": {
            "type": "string",
            "label": "Idempotency Key",
            "description": "Unique key required for write requests",
            "required": False,
            "sensitive": True,
        },
        "api_key": {
            "type": "string",
            "label": "API Key",
            "description": "Xquik API key; defaults to XQUIK_API_KEY",
            "placeholder": "${env.XQUIK_API_KEY}",
            "required": False,
            "sensitive": True,
        },
    },
    output_schema={
        "status": {"type": "string", "description": "Operation status"},
        "http_status": {"type": "number", "description": "HTTP response status"},
        "data": {"type": "any", "description": "Xquik response body"},
        "message": {
            "type": "string",
            "description": "Error message when the request fails",
            "optional": True,
        },
    },
    examples=[
        {
            "name": "Search recent posts",
            "params": {
                "method": "GET",
                "path": "/x/tweets/search",
                "query": {"q": "Flyto2", "queryType": "Latest"},
            },
        }
    ],
    docs_url="https://docs.xquik.com/api",
    author="Flyto2 Community",
    license="Apache-2.0",
)
class XquikRequestModule(BaseModule):
    """Call any documented Xquik REST API path."""

    module_id = "api.xquik.request"
    module_name = "Xquik API Request"
    module_description = "Call any documented Xquik API path"

    def validate_params(self) -> None:
        method = str(self.params.get("method", "GET")).upper()
        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            raise ValueError("method must be GET, POST, PUT, PATCH, or DELETE")
        path = self.params.get("path")
        if not isinstance(path, str) or not path:
            raise ValueError("Missing parameter: path")
        self.method = method
        self.path = _normalize_path(path)
        self.query = self.params.get("query") or {}
        self.body = self.params.get("body")
        self.idempotency_key = self.params.get("idempotency_key")
        if not isinstance(self.query, dict):
            raise ValueError("query must be an object")
        if self.body is not None and not isinstance(self.body, dict):
            raise ValueError("body must be an object")
        if method != "GET":
            self.idempotency_key = _validate_idempotency_key(self.idempotency_key)

    async def execute(self) -> Any:
        api_key = _api_key(self.params)
        if api_key is None:
            return _missing_api_key()
        return await _xquik_request(
            self.method,
            self.path,
            api_key,
            query=self.query,
            body=self.body,
            idempotency_key=self.idempotency_key,
        )


@register_module(
    module_id="api.xquik.search_tweets",
    version="1.0.0",
    category="api",
    subcategory="social",
    tags=["api", "xquik", "x", "search", "social"],
    label="Search X Posts",
    description="Search X posts with Xquik",
    icon="Search",
    color="#111827",
    input_types=["string", "object"],
    output_types=["array", "json", "api_response"],
    can_receive_from=["*"],
    can_connect_to=["*"],
    timeout_ms=30000,
    retryable=True,
    max_retries=3,
    concurrent_safe=True,
    requires_credentials=True,
    credential_keys=["XQUIK_API_KEY"],
    handles_sensitive_data=False,
    required_permissions=["network.access"],
    params_schema={
        "query": {
            "type": "string",
            "label": "Search Query",
            "description": "Keywords, operators, post ID, or X status URL",
            "required": True,
        },
        "query_type": {
            "type": "select",
            "label": "Sort Order",
            "description": "Latest or engagement-ranked results",
            "options": ["Latest", "Top"],
            "default": "Latest",
            "required": False,
        },
        "cursor": {
            "type": "string",
            "label": "Cursor",
            "description": "Pagination cursor",
            "required": False,
        },
        "limit": {
            "type": "number",
            "label": "Limit",
            "description": "Maximum posts to return",
            "default": 20,
            "min": 1,
            "max": 200,
            "required": False,
        },
        "filters": {
            "type": "object",
            "label": "Filters",
            "description": "Additional documented search filters",
            "required": False,
        },
        "api_key": {
            "type": "string",
            "label": "API Key",
            "description": "Xquik API key; defaults to XQUIK_API_KEY",
            "placeholder": "${env.XQUIK_API_KEY}",
            "required": False,
            "sensitive": True,
        },
    },
    output_schema={
        "status": {"type": "string", "description": "Operation status"},
        "tweets": {"type": "array", "description": "Matching X posts"},
        "count": {"type": "number", "description": "Number of returned posts"},
        "has_next_page": {
            "type": "boolean",
            "description": "Whether another page is available",
        },
        "next_cursor": {
            "type": "string",
            "description": "Cursor for the next page",
            "optional": True,
        },
        "data": {"type": "object", "description": "Full Xquik response"},
        "http_status": {"type": "number", "description": "HTTP response status"},
        "message": {
            "type": "string",
            "description": "Error message when the request fails",
            "optional": True,
        },
    },
    examples=[
        {
            "name": "Track a brand mention",
            "params": {"query": '"Flyto2"', "query_type": "Latest", "limit": 50},
        }
    ],
    docs_url="https://docs.xquik.com/api",
    author="Flyto2 Community",
    license="Apache-2.0",
)
class XquikSearchTweetsModule(BaseModule):
    """Search X posts through Xquik."""

    module_id = "api.xquik.search_tweets"
    module_name = "Search X Posts"
    module_description = "Search X posts with Xquik"

    def validate_params(self) -> None:
        query = self.params.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ValueError("Missing parameter: query")
        self.query = query
        self.query_type = self.params.get("query_type", "Latest")
        if self.query_type not in {"Latest", "Top"}:
            raise ValueError("query_type must be Latest or Top")
        self.cursor = self.params.get("cursor")
        self.limit = self.params.get("limit", 20)
        if not isinstance(self.limit, int) or not 1 <= self.limit <= 200:
            raise ValueError("limit must be an integer from 1 to 200")
        self.filters = self.params.get("filters") or {}
        if not isinstance(self.filters, dict):
            raise ValueError("filters must be an object")

    async def execute(self) -> Any:
        api_key = _api_key(self.params)
        if api_key is None:
            return _missing_api_key()
        query: Dict[str, Any] = {
            **self.filters,
            "q": self.query,
            "queryType": self.query_type,
            "limit": self.limit,
        }
        if self.cursor:
            query["cursor"] = self.cursor
        result = await _xquik_request(
            "GET",
            "/x/tweets/search",
            api_key,
            query=query,
        )
        if result["status"] != "success":
            return result
        data = result["data"] if isinstance(result["data"], dict) else {}
        tweets = data.get("tweets", [])
        return {
            **result,
            "tweets": tweets,
            "count": len(tweets) if isinstance(tweets, list) else 0,
            "has_next_page": bool(data.get("has_next_page", False)),
            "next_cursor": data.get("next_cursor"),
        }


@register_module(
    module_id="api.xquik.get_tweet",
    version="1.0.0",
    category="api",
    subcategory="social",
    tags=["api", "xquik", "x", "tweet", "lookup"],
    label="Get X Post",
    description="Get one X post with Xquik",
    icon="MessageSquare",
    color="#111827",
    input_types=["string"],
    output_types=["json", "object", "api_response"],
    can_receive_from=["*"],
    can_connect_to=["*"],
    timeout_ms=30000,
    retryable=True,
    max_retries=3,
    concurrent_safe=True,
    requires_credentials=True,
    credential_keys=["XQUIK_API_KEY"],
    handles_sensitive_data=False,
    required_permissions=["network.access"],
    params_schema={
        "tweet_id": {
            "type": "string",
            "label": "Post ID",
            "description": "Numeric X post ID",
            "required": True,
        },
        "api_key": {
            "type": "string",
            "label": "API Key",
            "description": "Xquik API key; defaults to XQUIK_API_KEY",
            "placeholder": "${env.XQUIK_API_KEY}",
            "required": False,
            "sensitive": True,
        },
    },
    output_schema={
        "status": {"type": "string", "description": "Operation status"},
        "tweet": {"type": "object", "description": "X post details"},
        "author": {"type": "object", "description": "Post author"},
        "data": {"type": "object", "description": "Full Xquik response"},
        "http_status": {"type": "number", "description": "HTTP response status"},
        "message": {
            "type": "string",
            "description": "Error message when the request fails",
            "optional": True,
        },
    },
    docs_url="https://docs.xquik.com/api",
    author="Flyto2 Community",
    license="Apache-2.0",
)
class XquikGetTweetModule(BaseModule):
    """Get one X post through Xquik."""

    module_id = "api.xquik.get_tweet"
    module_name = "Get X Post"
    module_description = "Get one X post with Xquik"

    def validate_params(self) -> None:
        tweet_id = self.params.get("tweet_id")
        if not isinstance(tweet_id, str) or not tweet_id.isdigit() or not 15 <= len(tweet_id) <= 20:
            raise ValueError("tweet_id must contain 15 to 20 digits")
        self.tweet_id = tweet_id

    async def execute(self) -> Any:
        api_key = _api_key(self.params)
        if api_key is None:
            return _missing_api_key()
        result = await _xquik_request(
            "GET",
            f"/x/tweets/{quote(self.tweet_id, safe='')}",
            api_key,
        )
        if result["status"] != "success":
            return result
        data = result["data"] if isinstance(result["data"], dict) else {}
        return {
            **result,
            "tweet": data.get("tweet", {}),
            "author": data.get("author", {}),
        }


@register_module(
    module_id="api.xquik.get_user",
    version="1.0.0",
    category="api",
    subcategory="social",
    tags=["api", "xquik", "x", "user", "profile"],
    label="Get X User",
    description="Get an X user profile with Xquik",
    icon="User",
    color="#111827",
    input_types=["string"],
    output_types=["json", "object", "api_response"],
    can_receive_from=["*"],
    can_connect_to=["*"],
    timeout_ms=30000,
    retryable=True,
    max_retries=3,
    concurrent_safe=True,
    requires_credentials=True,
    credential_keys=["XQUIK_API_KEY"],
    handles_sensitive_data=False,
    required_permissions=["network.access"],
    params_schema={
        "user": {
            "type": "string",
            "label": "Username Or ID",
            "description": "X username or user ID",
            "required": True,
        },
        "api_key": {
            "type": "string",
            "label": "API Key",
            "description": "Xquik API key; defaults to XQUIK_API_KEY",
            "placeholder": "${env.XQUIK_API_KEY}",
            "required": False,
            "sensitive": True,
        },
    },
    output_schema={
        "status": {"type": "string", "description": "Operation status"},
        "user": {"type": "object", "description": "X user profile"},
        "data": {"type": "object", "description": "Full Xquik response"},
        "http_status": {"type": "number", "description": "HTTP response status"},
        "message": {
            "type": "string",
            "description": "Error message when the request fails",
            "optional": True,
        },
    },
    docs_url="https://docs.xquik.com/api",
    author="Flyto2 Community",
    license="Apache-2.0",
)
class XquikGetUserModule(BaseModule):
    """Get an X user profile through Xquik."""

    module_id = "api.xquik.get_user"
    module_name = "Get X User"
    module_description = "Get an X user profile with Xquik"

    def validate_params(self) -> None:
        user = self.params.get("user")
        if not isinstance(user, str):
            raise ValueError("Missing parameter: user")
        normalized = user.strip().lstrip("@")
        if not normalized:
            raise ValueError("Missing parameter: user")
        self.user = normalized

    async def execute(self) -> Any:
        api_key = _api_key(self.params)
        if api_key is None:
            return _missing_api_key()
        result = await _xquik_request(
            "GET",
            f"/x/users/{quote(self.user, safe='')}",
            api_key,
        )
        if result["status"] != "success":
            return result
        data = result["data"] if isinstance(result["data"], dict) else {}
        return {**result, "user": data.get("user", data)}


@register_module(
    module_id="api.xquik.create_tweet",
    version="1.0.0",
    category="api",
    subcategory="social",
    tags=["api", "xquik", "x", "tweet", "write"],
    label="Create X Post",
    description="Create an X post with Xquik",
    icon="Send",
    color="#111827",
    input_types=["string", "object"],
    output_types=["json", "object", "api_response"],
    can_receive_from=["*"],
    can_connect_to=["*"],
    timeout_ms=30000,
    retryable=True,
    max_retries=3,
    concurrent_safe=False,
    requires_credentials=True,
    credential_keys=["XQUIK_API_KEY"],
    handles_sensitive_data=True,
    required_permissions=["network.access"],
    params_schema={
        "account": {
            "type": "string",
            "label": "Account",
            "description": "X account username or account ID",
            "required": True,
        },
        "text": {
            "type": "string",
            "label": "Text",
            "description": "Post text",
            "required": False,
        },
        "media": {
            "type": "array",
            "label": "Media URLs",
            "description": "Public media URLs to attach",
            "required": False,
        },
        "reply_to_tweet_id": {
            "type": "string",
            "label": "Reply To Post ID",
            "description": "Post ID to reply to",
            "required": False,
        },
        "community_id": {
            "type": "string",
            "label": "Community ID",
            "description": "Community destination",
            "required": False,
        },
        "is_note_tweet": {
            "type": "boolean",
            "label": "Long Post",
            "description": "Create a long-form X post",
            "default": False,
            "required": False,
        },
        "idempotency_key": {
            "type": "string",
            "label": "Idempotency Key",
            "description": "Unique key for this intended write",
            "required": True,
            "sensitive": True,
        },
        "api_key": {
            "type": "string",
            "label": "API Key",
            "description": "Xquik API key; defaults to XQUIK_API_KEY",
            "placeholder": "${env.XQUIK_API_KEY}",
            "required": False,
            "sensitive": True,
        },
    },
    output_schema={
        "status": {"type": "string", "description": "Operation status"},
        "action": {"type": "object", "description": "Write action result"},
        "data": {"type": "object", "description": "Full Xquik response"},
        "http_status": {"type": "number", "description": "HTTP response status"},
        "message": {
            "type": "string",
            "description": "Error message when the request fails",
            "optional": True,
        },
    },
    docs_url="https://docs.xquik.com/api",
    author="Flyto2 Community",
    license="Apache-2.0",
)
class XquikCreateTweetModule(BaseModule):
    """Create an X post through Xquik."""

    module_id = "api.xquik.create_tweet"
    module_name = "Create X Post"
    module_description = "Create an X post with Xquik"

    def validate_params(self) -> None:
        account = self.params.get("account")
        if not isinstance(account, str) or not account.strip():
            raise ValueError("Missing parameter: account")
        media = self.params.get("media") or []
        if (
            not isinstance(media, list)
            or len(media) > 4
            or any(not isinstance(url, str) or not url for url in media)
        ):
            raise ValueError("media must contain at most 4 URLs")
        text = self.params.get("text")
        if not (isinstance(text, str) and text.strip()) and not media:
            raise ValueError("Provide text, media, or both")
        self.account = account
        self.text = text
        self.media = media
        self.idempotency_key = _validate_idempotency_key(self.params.get("idempotency_key"))

    async def execute(self) -> Any:
        api_key = _api_key(self.params)
        if api_key is None:
            return _missing_api_key()
        body = {
            key: value
            for key, value in {
                "account": self.account,
                "text": self.text,
                "media": self.media or None,
                "reply_to_tweet_id": self.params.get("reply_to_tweet_id"),
                "community_id": self.params.get("community_id"),
                "is_note_tweet": self.params.get("is_note_tweet", False),
            }.items()
            if value is not None
        }
        result = await _xquik_request(
            "POST",
            "/x/tweets",
            api_key,
            body=body,
            idempotency_key=self.idempotency_key,
        )
        if result["status"] != "success":
            return result
        data = result["data"] if isinstance(result["data"], dict) else {}
        return {**result, "action": data.get("action", data)}


@register_module(
    module_id="api.xquik.get_write_action",
    version="1.0.0",
    category="api",
    subcategory="social",
    tags=["api", "xquik", "x", "write", "status"],
    label="Get X Write Status",
    description="Get an Xquik write action status",
    icon="Activity",
    color="#111827",
    input_types=["string"],
    output_types=["json", "object", "api_response"],
    can_receive_from=["*"],
    can_connect_to=["*"],
    timeout_ms=30000,
    retryable=True,
    max_retries=3,
    concurrent_safe=True,
    requires_credentials=True,
    credential_keys=["XQUIK_API_KEY"],
    handles_sensitive_data=True,
    required_permissions=["network.access"],
    params_schema={
        "action_id": {
            "type": "string",
            "label": "Action ID",
            "description": "Pending Xquik write action ID",
            "required": True,
        },
        "api_key": {
            "type": "string",
            "label": "API Key",
            "description": "Xquik API key; defaults to XQUIK_API_KEY",
            "placeholder": "${env.XQUIK_API_KEY}",
            "required": False,
            "sensitive": True,
        },
    },
    output_schema={
        "status": {"type": "string", "description": "Operation status"},
        "action": {"type": "object", "description": "Write action status"},
        "data": {"type": "object", "description": "Full Xquik response"},
        "http_status": {"type": "number", "description": "HTTP response status"},
        "message": {
            "type": "string",
            "description": "Error message when the request fails",
            "optional": True,
        },
    },
    docs_url="https://docs.xquik.com/api",
    author="Flyto2 Community",
    license="Apache-2.0",
)
class XquikGetWriteActionModule(BaseModule):
    """Get an Xquik write action status."""

    module_id = "api.xquik.get_write_action"
    module_name = "Get X Write Status"
    module_description = "Get an Xquik write action status"

    def validate_params(self) -> None:
        action_id = self.params.get("action_id")
        if not isinstance(action_id, str) or not action_id:
            raise ValueError("Missing parameter: action_id")
        self.action_id = action_id

    async def execute(self) -> Any:
        api_key = _api_key(self.params)
        if api_key is None:
            return _missing_api_key()
        result = await _xquik_request(
            "GET",
            f"/x/write-actions/{quote(self.action_id, safe='')}",
            api_key,
        )
        if result["status"] != "success":
            return result
        data = result["data"] if isinstance(result["data"], dict) else {}
        return {**result, "action": data.get("action", data)}


__all__ = [
    "XquikRequestModule",
    "XquikSearchTweetsModule",
    "XquikGetTweetModule",
    "XquikGetUserModule",
    "XquikCreateTweetModule",
    "XquikGetWriteActionModule",
]
