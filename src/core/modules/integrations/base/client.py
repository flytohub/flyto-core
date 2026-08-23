# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Base Integration Client

Abstract base class for building API integrations.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import aiohttp

from ....utils import enforce_outbound_url, guarded_client_session
from .egress import assert_env_credential_target_allowed
from .models import APIResponse, IntegrationConfig
from .rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


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
            # Guarded connector: the IP the SSRF check validated is the IP the
            # request connects to, so a name that re-resolves into private space
            # between the two cannot slip through.
            self._session = guarded_client_session(
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

        # SECURITY: this one method is the outbound sink for the whole
        # integration.* family, and the base URL under it is caller-derived —
        # Jira's `domain`, Salesforce's `instance_url`. Unguarded it was both an
        # SSRF primitive and, because _get_auth_header attaches the operator's
        # credential to whatever host was named, a credential-exfiltration
        # primitive (GHSA-4346-4gqg-59f9). Two controls, because the SSRF guard
        # permits ordinary public hosts by design and an attacker's collector is
        # an ordinary public host.
        #
        # The credential check runs first: it is a policy question about a host
        # name, so it needs no DNS and stays decisive for a target that does not
        # resolve — where the SSRF guard's own fail-closed answer would be right
        # but would describe the wrong problem.
        assert_env_credential_target_allowed(
            url,
            service_name=self.config.service_name,
            operator_hosts=self.config.env_credential_hosts,
            credentials_from_env=self.config.credentials_from_env,
        )
        enforce_outbound_url(url)

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
                        ok=self._response_is_ok(response.status, data),
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

    def _response_is_ok(self, status: int, data: Any) -> bool:
        """Whether a response represents success.

        Defaults to the HTTP status. Override for an API that answers HTTP 200
        with the real outcome in the body — Slack does, so a rejected token
        produced ``ok=True`` with every field null, which is a failure reported
        as a success.
        """
        return status < 400

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
