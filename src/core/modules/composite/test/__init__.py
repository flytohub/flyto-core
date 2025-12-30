"""
Test Composite Modules
E2E testing, API testing, and AI-powered UI review automation

Enhanced with Data Lineage Tracking for swimlane visualization.
"""

from .e2e_flow import WebAppE2ETest
from .api_test import APITestSuite
from .ui_review import AIUIReview
from .verify_fix import VerifyFix
from .quality_gate import CIQualityGate

__all__ = ['WebAppE2ETest', 'APITestSuite', 'AIUIReview', 'VerifyFix', 'CIQualityGate']
