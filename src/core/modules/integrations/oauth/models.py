"""
OAuth Data Models

Configuration and token storage dataclasses.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .providers import OAuthProvider, PROVIDER_CONFIGS


@dataclass
class OAuthConfig:
    """OAuth configuration for a provider."""
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
    """OAuth token storage with expiration tracking."""
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
