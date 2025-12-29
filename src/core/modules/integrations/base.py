"""
Base Integration Classes

Provides foundational classes for building integrations quickly.
"""

import asyncio
import hashlib
import hmac
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Union

import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class IntegrationConfig:
    """Configuration for an integration."""
    service_name: str
    base_url: str
    api_version: str = "v1"
    timeout: int = 30
    max_retries: int = 3
    retry_delay: float = 1.0
    rate_limit_calls: int = 100
    rate_limit_period: int = 60  # seconds
    verify_ssl: bool = True
    user_agent: str = "Flyto2-Integration/1.0"

    def get_api_url(self, endpoint: str) -> str:
        """Build full API URL."""
        base = self.base_url.rstrip("/")
        endpoint = endpoint.lstrip("/")
        if self.api_version:
            return f"{base}/{self.api_version}/{endpoint}"
        return f"{base}/{endpoint}"


class RateLimiter:
    """
    Token bucket rate limiter.

    Usage:
        limiter = RateLimiter(calls=100, period=60)
        await limiter.acquire()  # Blocks if rate limited
    """

    def __init__(self, calls: int = 100, period: int = 60):
        """
        Initialize rate limiter.

        Args:
            calls: Maximum calls allowed in period
            period: Period in seconds
        """
        self.calls = calls
        self.period = period
        self.tokens = calls
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Acquire a token, blocking if rate limited."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_update

            # Refill tokens
            refill = (elapsed / self.period) * self.calls
            self.tokens = min(self.calls, self.tokens + refill)
            self.last_update = now

            if self.tokens < 1:
                # Calculate wait time
                wait = (1 - self.tokens) * (self.period / self.calls)
                logger.debug(f"Rate limited, waiting {wait:.2f}s")
                await asyncio.sleep(wait)
                self.tokens = 0
            else:
                self.tokens -= 1

    def reset(self) -> None:
        """Reset rate limiter."""
        self.tokens = self.calls
        self.last_update = time.monotonic()


class WebhookHandler:
    """
    Webhook signature verification and handling.

    Usage:
        handler = WebhookHandler(secret="webhook_secret")
        if handler.verify_signature(payload, signature):
            data = handler.parse(payload)
    """

    def __init__(
        self,
        secret: str,
        signature_header: str = "X-Signature",
        algorithm: str = "sha256",
    ):
        """
        Initialize webhook handler.

        Args:
            secret: Webhook secret for HMAC verification
            signature_header: Header containing signature
            algorithm: HMAC algorithm (sha256, sha1)
        """
        self.secret = secret.encode() if isinstance(secret, str) else secret
        self.signature_header = signature_header
        self.algorithm = algorithm

    def compute_signature(self, payload: Union[str, bytes]) -> str:
        """Compute HMAC signature for payload."""
        if isinstance(payload, str):
            payload = payload.encode()

        if self.algorithm == "sha256":
            mac = hmac.new(self.secret, payload, hashlib.sha256)
        elif self.algorithm == "sha1":
            mac = hmac.new(self.secret, payload, hashlib.sha1)
        else:
            raise ValueError(f"Unsupported algorithm: {self.algorithm}")

        return mac.hexdigest()

    def verify_signature(
        self,
        payload: Union[str, bytes],
        signature: str,
    ) -> bool:
        """
        Verify webhook signature.

        Args:
            payload: Raw request body
            signature: Signature from header

        Returns:
            True if signature is valid
        """
        # Handle prefixed signatures like "sha256=..."
        if "=" in signature:
            sig_algo, sig_value = signature.split("=", 1)
        else:
            sig_value = signature

        expected = self.compute_signature(payload)
        return hmac.compare_digest(expected, sig_value)

    def parse(
        self,
        payload: Union[str, bytes],
        content_type: str = "application/json",
    ) -> Dict[str, Any]:
        """Parse webhook payload."""
        import json

        if isinstance(payload, bytes):
            payload = payload.decode()

        if "json" in content_type:
            return json.loads(payload)
        elif "form" in content_type:
            from urllib.parse import parse_qs
            return {k: v[0] if len(v) == 1 else v for k, v in parse_qs(payload).items()}
        else:
            return {"raw": payload}


@dataclass
class APIResponse:
    """Standardized API response."""
    ok: bool
    status: int
    data: Any = None
    error: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)
    rate_limit_remaining: Optional[int] = None
    rate_limit_reset: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "data": self.data,
            "error": self.error,
        }


class BaseIntegration(ABC):
    """
    Base class for building integrations.

    Provides:
    - HTTP client with retry logic
    - Rate limiting
    - Authentication handling
    - Response normalization

    Usage:
        class SlackIntegration(BaseIntegration):
            service_name = "slack"
            base_url = "https://slack.com/api"

            async def send_message(self, channel: str, text: str):
                return await self.post("chat.postMessage", json={
                    "channel": channel,
                    "text": text,
                })
    """

    # Override in subclasses
    service_name: str = "base"
    base_url: str = ""
    api_version: str = ""

    def __init__(
        self,
        api_key: Optional[str] = None,
        access_token: Optional[str] = None,
        config: Optional[IntegrationConfig] = None,
    ):
        """
        Initialize integration.

        Args:
            api_key: API key for authentication
            access_token: OAuth access token
            config: Custom configuration
        """
        self.api_key = api_key
        self.access_token = access_token

        self.config = config or IntegrationConfig(
            service_name=self.service_name,
            base_url=self.base_url,
            api_version=self.api_version,
        )

        self._rate_limiter = RateLimiter(
            calls=self.config.rate_limit_calls,
            period=self.config.rate_limit_period,
        )

        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        """Context manager entry."""
        await self._ensure_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        await self.close()

    async def _ensure_session(self) -> aiohttp.ClientSession:
        """Ensure HTTP session exists."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                headers=self._default_headers(),
            )
        return self._session

    async def close(self) -> None:
        """Close HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    def _default_headers(self) -> Dict[str, str]:
        """Get default headers."""
        headers = {
            "User-Agent": self.config.user_agent,
            "Accept": "application/json",
        }

        # Add authentication
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        elif self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        return headers

    @abstractmethod
    def _get_auth_header(self) -> Dict[str, str]:
        """
        Get authentication header.

        Override in subclasses for custom auth.
        """
        pass

    def _build_url(self, endpoint: str) -> str:
        """Build full URL for endpoint."""
        return self.config.get_api_url(endpoint)

    async def _request(
        self,
        method: str,
        endpoint: str,
        **kwargs,
    ) -> APIResponse:
        """
        Make HTTP request with retry logic.

        Args:
            method: HTTP method
            endpoint: API endpoint
            **kwargs: Additional arguments for aiohttp

        Returns:
            APIResponse with result
        """
        session = await self._ensure_session()
        url = self._build_url(endpoint)

        # Apply rate limiting
        await self._rate_limiter.acquire()

        # Merge auth headers
        headers = kwargs.pop("headers", {})
        headers.update(self._get_auth_header())

        last_error = None
        for attempt in range(self.config.max_retries):
            try:
                async with session.request(
                    method,
                    url,
                    headers=headers,
                    ssl=self.config.verify_ssl,
                    **kwargs,
                ) as response:
                    # Parse response
                    try:
                        data = await response.json()
                    except Exception:
                        data = await response.text()

                    # Extract rate limit info
                    rate_remaining = response.headers.get("X-RateLimit-Remaining")
                    rate_reset = response.headers.get("X-RateLimit-Reset")

                    api_response = APIResponse(
                        ok=response.status < 400,
                        status=response.status,
                        data=data,
                        headers=dict(response.headers),
                        rate_limit_remaining=int(rate_remaining) if rate_remaining else None,
                        rate_limit_reset=datetime.fromtimestamp(int(rate_reset), tz=timezone.utc) if rate_reset else None,
                    )

                    if not api_response.ok:
                        api_response.error = self._extract_error(data, response.status)

                    # Handle rate limiting
                    if response.status == 429:
                        retry_after = response.headers.get("Retry-After", "60")
                        wait = min(int(retry_after), 300)
                        logger.warning(f"{self.service_name}: Rate limited, waiting {wait}s")
                        await asyncio.sleep(wait)
                        continue

                    return api_response

            except aiohttp.ClientError as e:
                last_error = str(e)
                logger.warning(
                    f"{self.service_name}: Request failed (attempt {attempt + 1}): {e}"
                )
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(self.config.retry_delay * (2 ** attempt))

        return APIResponse(
            ok=False,
            status=0,
            error=f"Request failed after {self.config.max_retries} attempts: {last_error}",
        )

    def _extract_error(self, data: Any, status: int) -> str:
        """Extract error message from response."""
        if isinstance(data, dict):
            # Common error field names
            for key in ["error", "message", "error_message", "detail", "errors"]:
                if key in data:
                    value = data[key]
                    if isinstance(value, dict) and "message" in value:
                        return value["message"]
                    return str(value)
        return f"HTTP {status}"

    # Convenience methods
    async def get(self, endpoint: str, **kwargs) -> APIResponse:
        """Make GET request."""
        return await self._request("GET", endpoint, **kwargs)

    async def post(self, endpoint: str, **kwargs) -> APIResponse:
        """Make POST request."""
        return await self._request("POST", endpoint, **kwargs)

    async def put(self, endpoint: str, **kwargs) -> APIResponse:
        """Make PUT request."""
        return await self._request("PUT", endpoint, **kwargs)

    async def patch(self, endpoint: str, **kwargs) -> APIResponse:
        """Make PATCH request."""
        return await self._request("PATCH", endpoint, **kwargs)

    async def delete(self, endpoint: str, **kwargs) -> APIResponse:
        """Make DELETE request."""
        return await self._request("DELETE", endpoint, **kwargs)

    # Health check
    async def health_check(self) -> bool:
        """Check if service is reachable."""
        try:
            response = await self.get("")
            return response.ok or response.status < 500
        except Exception:
            return False


class PaginatedIntegration(BaseIntegration):
    """
    Base class for integrations with pagination support.

    Handles cursor-based and offset-based pagination.
    """

    async def paginate(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        page_key: str = "page",
        limit_key: str = "per_page",
        limit: int = 100,
        max_pages: Optional[int] = None,
        data_key: Optional[str] = None,
    ) -> List[Any]:
        """
        Fetch all pages of a paginated endpoint.

        Args:
            endpoint: API endpoint
            params: Query parameters
            page_key: Parameter name for page number
            limit_key: Parameter name for page size
            limit: Items per page
            max_pages: Maximum pages to fetch
            data_key: Key in response containing data list

        Returns:
            Combined list of all items
        """
        params = params or {}
        params[limit_key] = limit

        all_items = []
        page = 1

        while True:
            params[page_key] = page
            response = await self.get(endpoint, params=params)

            if not response.ok:
                logger.error(f"Pagination failed at page {page}: {response.error}")
                break

            # Extract items from response
            data = response.data
            if data_key and isinstance(data, dict):
                items = data.get(data_key, [])
            elif isinstance(data, list):
                items = data
            else:
                items = [data] if data else []

            if not items:
                break

            all_items.extend(items)

            # Check if more pages
            if len(items) < limit:
                break

            if max_pages and page >= max_pages:
                break

            page += 1

        return all_items

    async def cursor_paginate(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        cursor_key: str = "cursor",
        response_cursor_key: str = "next_cursor",
        data_key: str = "data",
        max_pages: Optional[int] = None,
    ) -> List[Any]:
        """
        Fetch all pages using cursor-based pagination.

        Args:
            endpoint: API endpoint
            params: Query parameters
            cursor_key: Parameter name for cursor
            response_cursor_key: Key in response containing next cursor
            data_key: Key in response containing data list
            max_pages: Maximum pages to fetch

        Returns:
            Combined list of all items
        """
        params = params or {}
        all_items = []
        cursor = None
        page = 0

        while True:
            if cursor:
                params[cursor_key] = cursor

            response = await self.get(endpoint, params=params)

            if not response.ok:
                logger.error(f"Cursor pagination failed: {response.error}")
                break

            data = response.data
            if isinstance(data, dict):
                items = data.get(data_key, [])
                cursor = data.get(response_cursor_key)
            else:
                items = data if isinstance(data, list) else []
                cursor = None

            all_items.extend(items)

            if not cursor:
                break

            page += 1
            if max_pages and page >= max_pages:
                break

        return all_items
