"""
OAuth Provider Definitions

Pre-configured OAuth provider endpoints and settings.
"""

from enum import Enum
from typing import Dict, Any


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


# Provider configurations with OAuth endpoints
PROVIDER_CONFIGS: Dict[OAuthProvider, Dict[str, Any]] = {
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
