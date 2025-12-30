"""
API Related Modules

DEPRECATED: This file is maintained for backwards compatibility.
Please import from core.modules.third_party.developer.http instead:

    from core.modules.third_party.developer.http import (
        HTTPGetModule,
        HTTPPostModule,
    )

All functionality has been split into:
- core/modules/third_party/developer/http/search.py - Search API modules
- core/modules/third_party/developer/http/requests.py - HTTP request modules
"""

# Re-export for backwards compatibility
from .http import (
    GoogleSearchAPIModule,
    SerpAPISearchModule,
    HTTPGetModule,
    HTTPPostModule,
)

__all__ = [
    "GoogleSearchAPIModule",
    "SerpAPISearchModule",
    "HTTPGetModule",
    "HTTPPostModule",
]
