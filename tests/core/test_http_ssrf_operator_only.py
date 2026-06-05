"""SSRF protection must be operator-controlled, not disableable by a client/recipe
`ssrf_protection` param (pass-2 G4)."""

import pytest

from core.modules import atomic  # noqa: F401 — registers modules
from core.utils import ssrf_protection_enabled
from core.mcp_handler import execute_module

METADATA = "http://169.254.169.254/latest/meta-data/"


class TestHelper:
    def test_default_on(self, monkeypatch):
        monkeypatch.delenv("FLYTO_HTTP_DISABLE_SSRF_GUARD", raising=False)
        assert ssrf_protection_enabled() is True

    def test_operator_can_disable(self, monkeypatch):
        monkeypatch.setenv("FLYTO_HTTP_DISABLE_SSRF_GUARD", "1")
        assert ssrf_protection_enabled() is False


@pytest.mark.asyncio
class TestParamCannotDisable:
    async def test_http_request_param_false_still_blocks_metadata(self, monkeypatch):
        monkeypatch.delenv("FLYTO_HTTP_DISABLE_SSRF_GUARD", raising=False)
        # Attacker tries to turn off the guard via the request param.
        res = await execute_module("http.request", {
            "url": METADATA, "method": "GET", "ssrf_protection": False,
        })
        text = repr(res).lower()
        assert "ssrf" in text or "blocked" in text or res.get("ok") is False

    async def test_http_get_param_false_still_blocks_metadata(self, monkeypatch):
        monkeypatch.delenv("FLYTO_HTTP_DISABLE_SSRF_GUARD", raising=False)
        res = await execute_module("http.get", {
            "url": METADATA, "ssrf_protection": False,
        })
        assert res.get("ok") is not True
        assert "169.254" not in str(res.get("data", "")) or res.get("ok") is False
