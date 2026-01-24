"""
Flyto Licensing - Type Definitions and Abstract Interface

This module provides ONLY:
1. Type definitions (enums) - safe to expose in open source
2. Abstract interface protocol - for flyto-pro to implement

IMPORTANT: No actual validation logic here!
All license validation is implemented in flyto-pro.

Product Versions:
- 離線版 (Offline Free): FREE tier, local execution only
- 線上版 (Online/Cloud): PRO tier, cloud features
- 企業版 (Enterprise): ENTERPRISE tier, full features
- 離線授權版 (Offline Licensed): ENTERPRISE tier, local execution
"""

from enum import Enum
from typing import Any, Callable, Dict, Optional, Protocol, Set


# =============================================================================
# Type Definitions (safe for open source)
# =============================================================================

class LicenseTier(str, Enum):
    """License tiers."""
    FREE = "free"              # 離線版 - Basic features
    PRO = "pro"                # 線上版 - Cloud features
    ENTERPRISE = "enterprise"  # 企業版/離線授權版 - Full features


class FeatureFlag(str, Enum):
    """Feature flags for fine-grained control."""
    # Core features (FREE)
    BASIC_WORKFLOW = "basic_workflow"
    BASIC_MODULES = "basic_modules"
    LOCAL_EXECUTION = "local_execution"

    # PRO features
    CLOUD_EXECUTION = "cloud_execution"
    CLOUD_STORAGE = "cloud_storage"
    TEAM_COLLABORATION = "team_collaboration"
    API_ACCESS = "api_access"
    WEBHOOK_TRIGGERS = "webhook_triggers"
    SCHEDULED_JOBS = "scheduled_jobs"

    # ENTERPRISE features
    DESKTOP_AUTOMATION = "desktop_automation"
    DOCUMENT_PROCESSING = "document_processing"
    PROCESS_MINING = "process_mining"
    ORCHESTRATOR = "orchestrator"
    ROBOT_MANAGEMENT = "robot_management"
    WORK_QUEUE = "work_queue"
    TRANSACTION_SUPPORT = "transaction_support"
    STATE_MACHINE = "state_machine"
    AI_AGENT = "ai_agent"
    WORKFLOW_EVOLUTION = "workflow_evolution"
    NL_TO_WORKFLOW = "nl_to_workflow"
    SSO = "sso"
    AUDIT_LOG = "audit_log"
    CUSTOM_BRANDING = "custom_branding"
    PRIORITY_SUPPORT = "priority_support"
    ON_PREMISE = "on_premise"


class LicenseError(Exception):
    """License-related error."""
    def __init__(
        self,
        message: str,
        feature: Optional[FeatureFlag] = None,
        tier_required: Optional[LicenseTier] = None
    ):
        super().__init__(message)
        self.feature = feature
        self.tier_required = tier_required


# =============================================================================
# Abstract Interface (Protocol)
# =============================================================================

class LicenseChecker(Protocol):
    """
    Abstract interface for license checking.

    flyto-pro provides the actual implementation.
    flyto-core only defines this interface.
    """

    def get_tier(self) -> LicenseTier:
        """Get current license tier."""
        ...

    def has_feature(self, feature: FeatureFlag) -> bool:
        """Check if a feature is enabled."""
        ...

    def can_access_module(self, module_id: str) -> bool:
        """Check if module is accessible with current license."""
        ...

    def get_module_access_info(self, module_id: str) -> Dict[str, Any]:
        """Get access info for a module (for UI display)."""
        ...


# =============================================================================
# Pluggable License Manager
# =============================================================================

class LicenseManager:
    """
    Pluggable license manager.

    By default, allows all access (FREE tier behavior).
    flyto-pro can register a custom checker implementation.

    Usage:
        # In flyto-pro initialization:
        from flyto_core.licensing import LicenseManager
        LicenseManager.register_checker(ProLicenseChecker())
    """
    _checker: Optional[LicenseChecker] = None

    @classmethod
    def register_checker(cls, checker: LicenseChecker) -> None:
        """Register a license checker implementation (called by flyto-pro)."""
        cls._checker = checker

    @classmethod
    def get_instance(cls) -> "LicenseManager":
        """Get the license manager instance."""
        return cls()

    def get_tier(self) -> LicenseTier:
        """Get current license tier."""
        if self._checker is None:
            return LicenseTier.FREE
        return self._checker.get_tier()

    def has_feature(self, feature: FeatureFlag) -> bool:
        """Check if a feature is enabled."""
        if self._checker is None:
            # No checker = FREE tier = allow basic features only
            return feature in {
                FeatureFlag.BASIC_WORKFLOW,
                FeatureFlag.BASIC_MODULES,
                FeatureFlag.LOCAL_EXECUTION,
            }
        return self._checker.has_feature(feature)

    def can_access_module(self, module_id: str) -> bool:
        """Check if module is accessible with current license."""
        if self._checker is None:
            # No checker = allow all (fail open for core-only usage)
            return True
        return self._checker.can_access_module(module_id)

    def get_module_access_info(self, module_id: str) -> Dict[str, Any]:
        """Get access info for a module (for UI display)."""
        if self._checker is None:
            return {
                "accessible": True,
                "required_tier": None,
                "current_tier": LicenseTier.FREE.value,
            }
        return self._checker.get_module_access_info(module_id)


__all__ = [
    # Enums
    'LicenseTier',
    'FeatureFlag',
    # Errors
    'LicenseError',
    # Protocol
    'LicenseChecker',
    # Manager
    'LicenseManager',
]
