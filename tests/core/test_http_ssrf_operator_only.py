"""SSRF protection must be operator-controlled, not disableable by a client/recipe
`ssrf_protection` param (pass-2 G4)."""

import pytest

from core.modules import atomic  # noqa: F401 — registers modules
from core.utils import SSRFError, ssrf_protection_enabled, validate_url_with_env_config
from core.mcp_handler import execute_module

METADATA = "http://169.254.169.254/latest/meta-data/"


class TestHelper:
    def test_default_on(self, monkeypatch):
        monkeypatch.delenv("FLYTO_HTTP_DISABLE_SSRF_GUARD", raising=False)
        assert ssrf_protection_enabled() is True

    def test_operator_can_disable(self, monkeypatch):
        monkeypatch.setenv("FLYTO_HTTP_DISABLE_SSRF_GUARD", "1")
        assert ssrf_protection_enabled() is False

    def test_allowed_host_still_needs_operator_allowed_port(self, monkeypatch):
        monkeypatch.delenv("FLYTO_ALLOW_PRIVATE_NETWORK", raising=False)
        monkeypatch.setenv("FLYTO_ALLOWED_HOSTS", "127.0.0.1")
        monkeypatch.delenv("FLYTO_HTTP_ALLOWED_PORTS", raising=False)

        with pytest.raises(SSRFError, match="Port 5180 not allowed"):
            validate_url_with_env_config("http://127.0.0.1:5180")

    def test_operator_can_allow_dev_port_without_disabling_ssrf(self, monkeypatch):
        monkeypatch.delenv("FLYTO_ALLOW_PRIVATE_NETWORK", raising=False)
        monkeypatch.setenv("FLYTO_ALLOWED_HOSTS", "127.0.0.1")
        monkeypatch.setenv("FLYTO_HTTP_ALLOWED_PORTS", "5180")

        assert validate_url_with_env_config("http://127.0.0.1:5180") == "http://127.0.0.1:5180"

    def test_allowed_port_without_host_still_blocks_loopback(self, monkeypatch):
        monkeypatch.delenv("FLYTO_ALLOW_PRIVATE_NETWORK", raising=False)
        monkeypatch.delenv("FLYTO_ALLOWED_HOSTS", raising=False)
        monkeypatch.setenv("FLYTO_HTTP_ALLOWED_PORTS", "5180")

        with pytest.raises(SSRFError, match="Hostname blocked"):
            validate_url_with_env_config("http://127.0.0.1:5180")


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
