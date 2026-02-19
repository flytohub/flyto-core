"""
Integration Models

Data classes for integration configuration and responses.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


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
