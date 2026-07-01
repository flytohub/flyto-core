"""
Pytest Configuration for flyto-core tests

Provides global fixtures and configuration for all tests.
"""

import os
import sys
from contextlib import contextmanager
from pathlib import Path

# Add src and tests to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

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


@contextmanager
def allow_local_http_port_for_test(port: int, host: str = "127.0.0.1"):
    """Temporarily allow a dynamic localhost port through the SSRF guard."""
    old_hosts = os.environ.get("FLYTO_ALLOWED_HOSTS")
    old_ports = os.environ.get("FLYTO_HTTP_ALLOWED_PORTS")

    hosts = [h.strip() for h in (old_hosts or "").split(",") if h.strip()]
    ports = [p.strip() for p in (old_ports or "").split(",") if p.strip()]
    if host not in hosts:
        hosts.append(host)
    port_str = str(port)
    if port_str not in ports:
        ports.append(port_str)

    os.environ["FLYTO_ALLOWED_HOSTS"] = ",".join(hosts)
    os.environ["FLYTO_HTTP_ALLOWED_PORTS"] = ",".join(ports)
    try:
        yield
    finally:
        if old_hosts is None:
            os.environ.pop("FLYTO_ALLOWED_HOSTS", None)
        else:
            os.environ["FLYTO_ALLOWED_HOSTS"] = old_hosts
        if old_ports is None:
            os.environ.pop("FLYTO_HTTP_ALLOWED_PORTS", None)
        else:
            os.environ["FLYTO_HTTP_ALLOWED_PORTS"] = old_ports
