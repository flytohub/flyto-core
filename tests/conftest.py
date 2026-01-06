"""
Pytest Configuration for flyto-core tests

Provides global fixtures and configuration for all tests.
"""

import sys
import os
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
import asyncio


@pytest.fixture(scope="session")
def event_loop():
    """Provide event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
def setup_test_env():
    """Set up test environment variables."""
    os.environ["FLYTO_ENV"] = "test"
    os.environ["LOG_LEVEL"] = "ERROR"  # Reduce log noise during tests


@pytest.fixture
def base_context():
    """Basic execution context for modules."""
    return {
        "params": {},
        "vars": {},
        "cache": {},
        "workflow_id": "test-workflow",
    }


@pytest.fixture
def mock_browser_context(base_context):
    """Mock browser context for browser modules."""
    return {
        **base_context,
        "browser": None,
        "page": None,
        "elements": {},
    }


# Register fixtures module
pytest_plugins = ["tests.fixtures.module_base"]
