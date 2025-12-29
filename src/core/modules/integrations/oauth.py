"""
OAuth 2.0 Client

Provides OAuth 2.0 authentication flows for integrations.
Supports:
- Authorization Code flow
- Client Credentials flow
- Refresh Token flow
- PKCE extension
"""

import base64
import hashlib
import logging
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlencode

import aiohttp

logger = logging.getLogger(__name__)


class OAuthProvider(str, Enum):
    """Pre-configured OAuth providers."""
    GOOGLE = "google"
    MICROSOFT = "microsoft"
    GITHUB = "github"
    SLACK = "slack"
    SALESFORCE = "salesforce"
    HUBSPOT = "hubspot"
    JIRA = "jira"
    NOTION = "notion"
    CUSTOM = "custom"


# Provider configurations
PROVIDER_CONFIGS = {
    OAuthProvider.GOOGLE: {
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "revoke_url": "https://oauth2.googleapis.com/revoke",
        "scopes_separator": " ",
    },
    OAuthProvider.MICROSOFT: {
        "authorize_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "scopes_separator": " ",
    },
    OAuthProvider.GITHUB: {
        "authorize_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "scopes_separator": " ",
    },
    OAuthProvider.SLACK: {
        "authorize_url": "https://slack.com/oauth/v2/authorize",
        "token_url": "https://slack.com/api/oauth.v2.access",
        "scopes_separator": ",",
    },
    OAuthProvider.SALESFORCE: {
        "authorize_url": "https://login.salesforce.com/services/oauth2/authorize",
        "token_url": "https://login.salesforce.com/services/oauth2/token",
        "revoke_url": "https://login.salesforce.com/services/oauth2/revoke",
        "scopes_separator": " ",
    },
    OAuthProvider.HUBSPOT: {
        "authorize_url": "https://app.hubspot.com/oauth/authorize",
        "token_url": "https://api.hubapi.com/oauth/v1/token",
        "scopes_separator": " ",
    },
    OAuthProvider.JIRA: {
        "authorize_url": "https://auth.atlassian.com/authorize",
        "token_url": "https://auth.atlassian.com/oauth/token",
        "scopes_separator": " ",
    },
    OAuthProvider.NOTION: {
        "authorize_url": "https://api.notion.com/v1/oauth/authorize",
        "token_url": "https://api.notion.com/v1/oauth/token",
        "scopes_separator": " ",
    },
}


@dataclass
class OAuthConfig:
    """OAuth configuration."""
    provider: OAuthProvider
    client_id: str
    client_secret: str
    redirect_uri: str
    scopes: List[str] = field(default_factory=list)
    authorize_url: Optional[str] = None
    token_url: Optional[str] = None
    revoke_url: Optional[str] = None
    scopes_separator: str = " "
    use_pkce: bool = False
    extra_params: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        """Apply provider defaults."""
        if self.provider != OAuthProvider.CUSTOM:
            defaults = PROVIDER_CONFIGS.get(self.provider, {})
            if not self.authorize_url:
                self.authorize_url = defaults.get("authorize_url")
            if not self.token_url:
                self.token_url = defaults.get("token_url")
            if not self.revoke_url:
                self.revoke_url = defaults.get("revoke_url")
            if self.scopes_separator == " ":
                self.scopes_separator = defaults.get("scopes_separator", " ")


@dataclass
class OAuthToken:
    """OAuth token storage."""
    access_token: str
    token_type: str = "Bearer"
    expires_at: Optional[datetime] = None
    refresh_token: Optional[str] = None
    scope: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        """Check if token is expired."""
        if not self.expires_at:
            return False
        return datetime.now(timezone.utc) >= self.expires_at

    @property
    def needs_refresh(self) -> bool:
        """Check if token should be refreshed (5 min buffer)."""
        if not self.expires_at:
            return False
        from datetime import timedelta
        buffer = timedelta(minutes=5)
        return datetime.now(timezone.utc) >= (self.expires_at - buffer)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "access_token": self.access_token,
            "token_type": self.token_type,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "refresh_token": self.refresh_token,
            "scope": self.scope,
            "extra": self.extra,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OAuthToken":
        """Create from dictionary."""
        expires_at = data.get("expires_at")
        if expires_at and isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)

        return cls(
            access_token=data["access_token"],
            token_type=data.get("token_type", "Bearer"),
            expires_at=expires_at,
            refresh_token=data.get("refresh_token"),
            scope=data.get("scope"),
            extra=data.get("extra", {}),
        )

    @classmethod
    def from_response(cls, data: Dict[str, Any]) -> "OAuthToken":
        """Create from OAuth token response."""
        expires_at = None
        if "expires_in" in data:
            from datetime import timedelta
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(data["expires_in"]))

        # Common fields
        known_fields = {
            "access_token", "token_type", "expires_in", "refresh_token", "scope"
        }
        extra = {k: v for k, v in data.items() if k not in known_fields}

        return cls(
            access_token=data["access_token"],
            token_type=data.get("token_type", "Bearer"),
            expires_at=expires_at,
            refresh_token=data.get("refresh_token"),
            scope=data.get("scope"),
            extra=extra,
        )


class PKCEChallenge:
    """PKCE challenge generator."""

    def __init__(self):
        """Generate code verifier and challenge."""
        # Generate 43-128 character code verifier
        self.code_verifier = secrets.token_urlsafe(32)

        # Generate challenge (SHA256 hash of verifier, base64url encoded)
        digest = hashlib.sha256(self.code_verifier.encode()).digest()
        self.code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
        self.code_challenge_method = "S256"


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


class OAuthError(Exception):
    """OAuth-related error."""
    pass


# Convenience functions for common providers

def create_google_oauth(
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    scopes: List[str],
) -> OAuthClient:
    """Create Google OAuth client."""
    config = OAuthConfig(
        provider=OAuthProvider.GOOGLE,
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scopes=scopes,
        use_pkce=True,
        extra_params={"access_type": "offline", "prompt": "consent"},
    )
    return OAuthClient(config)


def create_slack_oauth(
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    scopes: List[str],
) -> OAuthClient:
    """Create Slack OAuth client."""
    config = OAuthConfig(
        provider=OAuthProvider.SLACK,
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scopes=scopes,
    )
    return OAuthClient(config)


def create_salesforce_oauth(
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    scopes: Optional[List[str]] = None,
    sandbox: bool = False,
) -> OAuthClient:
    """Create Salesforce OAuth client."""
    base = "https://test.salesforce.com" if sandbox else "https://login.salesforce.com"

    config = OAuthConfig(
        provider=OAuthProvider.SALESFORCE,
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scopes=scopes or ["api", "refresh_token"],
        authorize_url=f"{base}/services/oauth2/authorize",
        token_url=f"{base}/services/oauth2/token",
        revoke_url=f"{base}/services/oauth2/revoke",
    )
    return OAuthClient(config)
