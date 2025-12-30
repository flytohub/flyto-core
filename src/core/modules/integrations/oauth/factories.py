"""
OAuth Client Factories

Convenience functions for creating pre-configured OAuth clients.
"""

from typing import List, Optional

from .client import OAuthClient
from .models import OAuthConfig
from .providers import OAuthProvider


def create_google_oauth(
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    scopes: List[str],
) -> OAuthClient:
    """
    Create Google OAuth client.

    Args:
        client_id: Google OAuth client ID
        client_secret: Google OAuth client secret
        redirect_uri: Callback URL after authorization
        scopes: List of OAuth scopes to request

    Returns:
        Configured OAuthClient for Google
    """
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
    """
    Create Slack OAuth client.

    Args:
        client_id: Slack app client ID
        client_secret: Slack app client secret
        redirect_uri: Callback URL after authorization
        scopes: List of Slack scopes to request

    Returns:
        Configured OAuthClient for Slack
    """
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
    """
    Create Salesforce OAuth client.

    Args:
        client_id: Salesforce connected app client ID
        client_secret: Salesforce connected app client secret
        redirect_uri: Callback URL after authorization
        scopes: List of scopes (defaults to api, refresh_token)
        sandbox: Use sandbox instance instead of production

    Returns:
        Configured OAuthClient for Salesforce
    """
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


def create_github_oauth(
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    scopes: List[str],
) -> OAuthClient:
    """
    Create GitHub OAuth client.

    Args:
        client_id: GitHub OAuth app client ID
        client_secret: GitHub OAuth app client secret
        redirect_uri: Callback URL after authorization
        scopes: List of GitHub scopes to request

    Returns:
        Configured OAuthClient for GitHub
    """
    config = OAuthConfig(
        provider=OAuthProvider.GITHUB,
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scopes=scopes,
    )
    return OAuthClient(config)


def create_microsoft_oauth(
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    scopes: List[str],
    tenant: str = "common",
) -> OAuthClient:
    """
    Create Microsoft OAuth client.

    Args:
        client_id: Azure AD app client ID
        client_secret: Azure AD app client secret
        redirect_uri: Callback URL after authorization
        scopes: List of Microsoft Graph scopes to request
        tenant: Azure AD tenant (common, organizations, consumers, or tenant ID)

    Returns:
        Configured OAuthClient for Microsoft
    """
    config = OAuthConfig(
        provider=OAuthProvider.MICROSOFT,
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scopes=scopes,
        authorize_url=f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize",
        token_url=f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
    )
    return OAuthClient(config)
