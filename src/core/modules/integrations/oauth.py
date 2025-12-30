"""
OAuth 2.0 Client

DEPRECATED: This file is maintained for backwards compatibility.
Please import from core.modules.integrations.oauth instead:

    from core.modules.integrations.oauth import (
        OAuthClient,
        OAuthConfig,
        OAuthToken,
        OAuthProvider,
    )

All functionality has been split into:
- core/modules/integrations/oauth/providers.py - Provider definitions
- core/modules/integrations/oauth/models.py - Config and Token models
- core/modules/integrations/oauth/pkce.py - PKCE support
- core/modules/integrations/oauth/client.py - OAuth client
- core/modules/integrations/oauth/factories.py - Convenience functions
"""

# Re-export for backwards compatibility
from .oauth import (
    # Providers
    OAuthProvider,
    PROVIDER_CONFIGS,
    # Models
    OAuthConfig,
    OAuthToken,
    # PKCE
    PKCEChallenge,
    # Client
    OAuthClient,
    OAuthError,
    # Factories
    create_google_oauth,
    create_slack_oauth,
    create_salesforce_oauth,
    create_github_oauth,
    create_microsoft_oauth,
)

__all__ = [
    "OAuthProvider",
    "PROVIDER_CONFIGS",
    "OAuthConfig",
    "OAuthToken",
    "PKCEChallenge",
    "OAuthClient",
    "OAuthError",
    "create_google_oauth",
    "create_slack_oauth",
    "create_salesforce_oauth",
    "create_github_oauth",
    "create_microsoft_oauth",
]
