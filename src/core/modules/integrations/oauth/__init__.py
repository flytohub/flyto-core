"""
OAuth 2.0 Client Package

Provides OAuth 2.0 authentication flows for integrations:
- Authorization Code flow
- Client Credentials flow
- Refresh Token flow
- PKCE extension
"""

from .providers import OAuthProvider, PROVIDER_CONFIGS
from .models import OAuthConfig, OAuthToken
from .pkce import PKCEChallenge
from .client import OAuthClient, OAuthError
from .factories import (
    create_google_oauth,
    create_slack_oauth,
    create_salesforce_oauth,
    create_github_oauth,
    create_microsoft_oauth,
)

__all__ = [
    # Providers
    "OAuthProvider",
    "PROVIDER_CONFIGS",
    # Models
    "OAuthConfig",
    "OAuthToken",
    # PKCE
    "PKCEChallenge",
    # Client
    "OAuthClient",
    "OAuthError",
    # Factories
    "create_google_oauth",
    "create_slack_oauth",
    "create_salesforce_oauth",
    "create_github_oauth",
    "create_microsoft_oauth",
]
