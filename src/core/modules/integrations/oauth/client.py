"""
OAuth 2.0 Client

Handles OAuth authentication flows:
- Authorization Code flow
- Client Credentials flow
- Refresh Token flow
"""

import logging
import secrets
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlencode

import aiohttp

from .models import OAuthConfig, OAuthToken
from .pkce import PKCEChallenge

logger = logging.getLogger(__name__)


class OAuthError(Exception):
    """OAuth-related error."""
    pass


class OAuthClient:
    """
    OAuth 2.0 client for handling authentication flows.

    Usage:
        config = OAuthConfig(
            provider=OAuthProvider.SLACK,
            client_id="your_client_id",
            client_secret="your_client_secret",
            redirect_uri="https://your-app.com/oauth/callback",
            scopes=["chat:write", "channels:read"],
        )

        client = OAuthClient(config)

        # Step 1: Get authorization URL
        auth_url, state = client.get_authorization_url()

        # Step 2: Exchange code for token
        token = await client.exchange_code(code, state)

        # Step 3: Refresh when needed
        if token.needs_refresh:
            token = await client.refresh_token(token)
    """

    def __init__(self, config: OAuthConfig):
        """Initialize OAuth client."""
        self.config = config
        self._pkce: Optional[PKCEChallenge] = None
        self._state_storage: Dict[str, Dict[str, Any]] = {}
        self._token_callback: Optional[Callable[[OAuthToken], None]] = None

    def set_token_callback(self, callback: Callable[[OAuthToken], None]) -> None:
        """Set callback for token updates (for auto-refresh)."""
        self._token_callback = callback

    def get_authorization_url(
        self,
        state: Optional[str] = None,
        extra_params: Optional[Dict[str, str]] = None,
    ) -> tuple[str, str]:
        """
        Get OAuth authorization URL.

        Args:
            state: Custom state (generated if not provided)
            extra_params: Additional URL parameters

        Returns:
            Tuple of (authorization_url, state)
        """
        state = state or secrets.token_urlsafe(32)

        params = {
            "client_id": self.config.client_id,
            "redirect_uri": self.config.redirect_uri,
            "response_type": "code",
            "state": state,
        }

        if self.config.scopes:
            params["scope"] = self.config.scopes_separator.join(self.config.scopes)

        # Add PKCE if enabled
        if self.config.use_pkce:
            self._pkce = PKCEChallenge()
            params["code_challenge"] = self._pkce.code_challenge
            params["code_challenge_method"] = self._pkce.code_challenge_method
            self._state_storage[state] = {"pkce": self._pkce}

        # Add extra params
        if self.config.extra_params:
            params.update(self.config.extra_params)
        if extra_params:
            params.update(extra_params)

        url = f"{self.config.authorize_url}?{urlencode(params)}"
        return url, state

    async def exchange_code(
        self,
        code: str,
        state: Optional[str] = None,
    ) -> OAuthToken:
        """
        Exchange authorization code for access token.

        Args:
            code: Authorization code from callback
            state: State to verify (if PKCE)

        Returns:
            OAuthToken with access credentials
        """
        data = {
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": self.config.redirect_uri,
        }

        # Add PKCE verifier if used
        if state and state in self._state_storage:
            stored = self._state_storage.pop(state)
            if "pkce" in stored:
                data["code_verifier"] = stored["pkce"].code_verifier

        return await self._token_request(data)

    async def refresh_token(self, token: OAuthToken) -> OAuthToken:
        """
        Refresh an expired token.

        Args:
            token: Token with refresh_token

        Returns:
            New OAuthToken with refreshed access_token
        """
        if not token.refresh_token:
            raise ValueError("No refresh token available")

        data = {
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
            "refresh_token": token.refresh_token,
            "grant_type": "refresh_token",
        }

        new_token = await self._token_request(data)

        # Preserve refresh token if not returned
        if not new_token.refresh_token:
            new_token.refresh_token = token.refresh_token

        # Notify callback
        if self._token_callback:
            self._token_callback(new_token)

        return new_token

    async def get_client_credentials_token(
        self,
        scopes: Optional[List[str]] = None,
    ) -> OAuthToken:
        """
        Get token using client credentials flow.

        Args:
            scopes: Optional scope override

        Returns:
            OAuthToken for service-to-service auth
        """
        data = {
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
            "grant_type": "client_credentials",
        }

        if scopes:
            data["scope"] = self.config.scopes_separator.join(scopes)
        elif self.config.scopes:
            data["scope"] = self.config.scopes_separator.join(self.config.scopes)

        return await self._token_request(data)

    async def revoke_token(self, token: OAuthToken) -> bool:
        """
        Revoke an access token.

        Args:
            token: Token to revoke

        Returns:
            True if revoked successfully
        """
        if not self.config.revoke_url:
            logger.warning(f"Revoke URL not configured for {self.config.provider}")
            return False

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.config.revoke_url,
                data={"token": token.access_token},
            ) as response:
                return response.status < 400

    async def _token_request(self, data: Dict[str, str]) -> OAuthToken:
        """Make token request."""
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.config.token_url,
                data=data,
                headers=headers,
            ) as response:
                if response.status >= 400:
                    error_text = await response.text()
                    raise OAuthError(f"Token request failed: {response.status} - {error_text}")

                result = await response.json()

                if "error" in result:
                    raise OAuthError(f"OAuth error: {result.get('error_description', result['error'])}")

                return OAuthToken.from_response(result)

    async def ensure_valid_token(self, token: OAuthToken) -> OAuthToken:
        """
        Ensure token is valid, refreshing if needed.

        Args:
            token: Current token

        Returns:
            Valid token (may be refreshed)
        """
        if token.needs_refresh and token.refresh_token:
            logger.debug("Token needs refresh, refreshing...")
            return await self.refresh_token(token)
        return token
