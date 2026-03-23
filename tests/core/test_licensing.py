"""
Tests for core.licensing
"""

import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from core.licensing import (
    LicenseTier, FeatureFlag, LicenseError,
    LicenseChecker, LicenseManager,
)


# =============================================================================
# LicenseTier enum
# =============================================================================

class TestLicenseTier:
    """Test LicenseTier enum."""

    def test_values(self):
        assert LicenseTier.FREE == "free"
        assert LicenseTier.PRO == "pro"
        assert LicenseTier.ENTERPRISE == "enterprise"

    def test_is_string_enum(self):
        assert isinstance(LicenseTier.FREE, str)
        assert isinstance(LicenseTier.PRO, str)
        assert isinstance(LicenseTier.ENTERPRISE, str)


# =============================================================================
# FeatureFlag enum
# =============================================================================

class TestFeatureFlag:
    """Test FeatureFlag enum."""

    def test_has_expected_flags(self):
        assert FeatureFlag.BASIC_WORKFLOW == "basic_workflow"
        assert FeatureFlag.CLOUD_EXECUTION == "cloud_execution"
        assert FeatureFlag.DESKTOP_AUTOMATION == "desktop_automation"

    def test_is_string_enum(self):
        assert isinstance(FeatureFlag.BASIC_WORKFLOW, str)
        assert isinstance(FeatureFlag.CLOUD_EXECUTION, str)
        assert isinstance(FeatureFlag.DESKTOP_AUTOMATION, str)


# =============================================================================
# LicenseError
# =============================================================================

class TestLicenseError:
    """Test LicenseError exception."""

    def test_message_only(self):
        err = LicenseError("Feature not available")
        assert str(err) == "Feature not available"
        assert err.feature is None
        assert err.tier_required is None

    def test_with_feature_and_tier(self):
        err = LicenseError(
            "Upgrade required",
            feature=FeatureFlag.CLOUD_EXECUTION,
            tier_required=LicenseTier.PRO,
        )
        assert str(err) == "Upgrade required"
        assert err.feature == FeatureFlag.CLOUD_EXECUTION
        assert err.tier_required == LicenseTier.PRO

    def test_is_exception(self):
        with pytest.raises(LicenseError):
            raise LicenseError("test")


# =============================================================================
# LicenseManager (without checker)
# =============================================================================

class TestLicenseManagerNoChecker:
    """Test LicenseManager without a registered checker."""

    @pytest.fixture(autouse=True)
    def cleanup(self):
        """Ensure no checker is registered before/after each test."""
        LicenseManager._checker = None
        yield
        LicenseManager._checker = None

    def test_get_instance(self):
        mgr = LicenseManager.get_instance()
        assert isinstance(mgr, LicenseManager)

    def test_get_tier_returns_free(self):
        mgr = LicenseManager.get_instance()
        assert mgr.get_tier() == LicenseTier.FREE

    def test_has_feature_basic_workflow(self):
        mgr = LicenseManager.get_instance()
        assert mgr.has_feature(FeatureFlag.BASIC_WORKFLOW) is True

    def test_has_feature_cloud_execution_denied(self):
        mgr = LicenseManager.get_instance()
        assert mgr.has_feature(FeatureFlag.CLOUD_EXECUTION) is False

    def test_can_access_module_fail_open(self):
        mgr = LicenseManager.get_instance()
        assert mgr.can_access_module("any.module") is True

    def test_get_module_access_info(self):
        mgr = LicenseManager.get_instance()
        info = mgr.get_module_access_info("any.module")
        assert isinstance(info, dict)
        assert info["accessible"] is True


# =============================================================================
# LicenseManager (with mock checker)
# =============================================================================

class TestLicenseManagerWithChecker:
    """Test LicenseManager with a mock checker registered."""

    @pytest.fixture(autouse=True)
    def cleanup(self):
        """Ensure checker is cleaned up after each test."""
        LicenseManager._checker = None
        yield
        LicenseManager._checker = None

    def _make_mock_checker(self):
        """Create a mock checker implementing the LicenseChecker protocol."""

        class MockChecker:
            def get_tier(self):
                return LicenseTier.ENTERPRISE

            def has_feature(self, feature):
                return True

            def can_access_module(self, module_id):
                return module_id.startswith("allowed.")

            def get_module_access_info(self, module_id):
                return {
                    "accessible": module_id.startswith("allowed."),
                    "required_tier": LicenseTier.ENTERPRISE.value,
                    "current_tier": LicenseTier.ENTERPRISE.value,
                }

        return MockChecker()

    def test_register_checker_delegates_get_tier(self):
        checker = self._make_mock_checker()
        LicenseManager.register_checker(checker)
        mgr = LicenseManager.get_instance()
        assert mgr.get_tier() == LicenseTier.ENTERPRISE

    def test_register_checker_delegates_has_feature(self):
        checker = self._make_mock_checker()
        LicenseManager.register_checker(checker)
        mgr = LicenseManager.get_instance()
        assert mgr.has_feature(FeatureFlag.CLOUD_EXECUTION) is True

    def test_register_checker_delegates_can_access_module(self):
        checker = self._make_mock_checker()
        LicenseManager.register_checker(checker)
        mgr = LicenseManager.get_instance()
        assert mgr.can_access_module("allowed.test") is True
        assert mgr.can_access_module("denied.test") is False

    def test_register_checker_delegates_get_module_access_info(self):
        checker = self._make_mock_checker()
        LicenseManager.register_checker(checker)
        mgr = LicenseManager.get_instance()
        info = mgr.get_module_access_info("allowed.test")
        assert info["accessible"] is True
        assert info["current_tier"] == "enterprise"
