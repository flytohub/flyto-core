"""
Test Composite Modules
E2E testing, API testing, and AI-powered UI review automation

Enhanced with Data Lineage Tracking for swimlane visualization.
"""

from .e2e_flow import E2EFlowTest
from .api_test import ApiTestSuite
from .ui_review import UIReview
from .verify_fix import VerifyFix
from .quality_gate import QualityGate

__all__ = ['E2EFlowTest', 'ApiTestSuite', 'UIReview', 'VerifyFix', 'QualityGate']
