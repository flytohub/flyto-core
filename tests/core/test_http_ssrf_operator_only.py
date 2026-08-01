"""SSRF protection must be operator-controlled, not disableable by a client/recipe
`ssrf_protection` param (pass-2 G4)."""

import asyncio

import pytest

from core.mcp_handler import execute_module
from core.modules import atomic  # noqa: F401 — registers modules
from core.utils import (
    SSRFError,
    get_ssrf_config,
    ssrf_protection_enabled,
    trusted_outbound_network_scope,
    validate_url_with_env_config,
)

METADATA = "http://169.254.169.254/latest/meta-data/"


class TestHelper:
    def test_default_on(self, monkeypatch):
        monkeypatch.delenv("FLYTO_HTTP_DISABLE_SSRF_GUARD", raising=False)
        assert ssrf_protection_enabled() is True

    def test_operator_can_disable(self, monkeypatch):
        monkeypatch.setenv("FLYTO_HTTP_DISABLE_SSRF_GUARD", "1")
        assert ssrf_protection_enabled() is False

    def test_allowed_host_still_needs_operator_allowed_port(self, monkeypatch):
        monkeypatch.delenv("FLYTO_VSCODE_LOCAL_MODE", raising=False)
        monkeypatch.delenv("FLYTO_ALLOW_PRIVATE_NETWORK", raising=False)
        monkeypatch.setenv("FLYTO_ALLOWED_HOSTS", "127.0.0.1")
        monkeypatch.delenv("FLYTO_HTTP_ALLOWED_PORTS", raising=False)

        with pytest.raises(SSRFError, match="Port 5180 not allowed"):
            validate_url_with_env_config("http://127.0.0.1:5180")

    def test_operator_can_allow_dev_port_without_disabling_ssrf(self, monkeypatch):
        monkeypatch.delenv("FLYTO_VSCODE_LOCAL_MODE", raising=False)
        monkeypatch.delenv("FLYTO_ALLOW_PRIVATE_NETWORK", raising=False)
        monkeypatch.setenv("FLYTO_ALLOWED_HOSTS", "127.0.0.1")
        monkeypatch.setenv("FLYTO_HTTP_ALLOWED_PORTS", "5180")

        assert validate_url_with_env_config("http://127.0.0.1:5180") == "http://127.0.0.1:5180"

    def test_operator_private_mode_preserves_dynamic_dev_ports(self, monkeypatch):
        monkeypatch.setenv("FLYTO_ALLOW_PRIVATE_NETWORK", "true")
        monkeypatch.delenv("FLYTO_HTTP_ALLOWED_PORTS", raising=False)

        assert (
            validate_url_with_env_config("http://127.0.0.1:49152")
            == "http://127.0.0.1:49152"
        )

    def test_allowed_port_without_host_still_blocks_loopback(self, monkeypatch):
        monkeypatch.delenv("FLYTO_VSCODE_LOCAL_MODE", raising=False)
        monkeypatch.delenv("FLYTO_ALLOW_PRIVATE_NETWORK", raising=False)
        monkeypatch.delenv("FLYTO_ALLOWED_HOSTS", raising=False)
        monkeypatch.setenv("FLYTO_HTTP_ALLOWED_PORTS", "5180")

        with pytest.raises(SSRFError, match="Hostname blocked"):
            validate_url_with_env_config("http://127.0.0.1:5180")

    @pytest.mark.parametrize(
        "environment_name,environment_value",
        [
            ("FLYTO_ALLOW_PRIVATE_NETWORK", "true"),
            ("FLYTO_ALLOWED_HOSTS", "169.254.169.254"),
        ],
    )
    def test_metadata_is_permanently_blocked(
        self,
        monkeypatch,
        environment_name,
        environment_value,
    ):
        monkeypatch.setenv(environment_name, environment_value)
        with pytest.raises(SSRFError, match="metadata"):
            validate_url_with_env_config(METADATA)

    def test_trusted_scope_is_exact_and_restores_default(self, monkeypatch):
        monkeypatch.delenv("FLYTO_ALLOW_PRIVATE_NETWORK", raising=False)
        monkeypatch.delenv("FLYTO_ALLOWED_HOSTS", raising=False)
        monkeypatch.delenv("FLYTO_HTTP_ALLOWED_PORTS", raising=False)

        with trusted_outbound_network_scope(
            allowed_hosts=["127.0.0.1"],
            allowed_ports=[5180],
            allow_private_targets=True,
        ):
            assert (
                validate_url_with_env_config("http://127.0.0.1:5180/health")
                == "http://127.0.0.1:5180/health"
            )
            with pytest.raises(SSRFError, match="trusted outbound scope"):
                validate_url_with_env_config("http://127.0.0.1:5181/health")
            with pytest.raises(SSRFError, match="trusted outbound scope"):
                validate_url_with_env_config("https://example.com/health")

        with pytest.raises(SSRFError):
            validate_url_with_env_config("http://127.0.0.1:5180/health")

    @pytest.mark.asyncio
    async def test_trusted_scope_is_task_local(self, monkeypatch):
        monkeypatch.delenv("FLYTO_ALLOW_PRIVATE_NETWORK", raising=False)
        monkeypatch.delenv("FLYTO_ALLOWED_HOSTS", raising=False)
        monkeypatch.delenv("FLYTO_HTTP_ALLOWED_PORTS", raising=False)

        async def scoped_config():
            with trusted_outbound_network_scope(
                allowed_hosts=["127.0.0.1"],
                allowed_ports=[5180],
                allow_private_targets=True,
            ):
                await asyncio.sleep(0)
                return get_ssrf_config()

        async def ordinary_config():
            await asyncio.sleep(0)
            return get_ssrf_config()

        scoped, ordinary = await asyncio.gather(
            scoped_config(),
            ordinary_config(),
        )
        assert scoped["restricted_hosts"] == ["127.0.0.1"]
        assert scoped["restricted_ports"] == {5180}
        assert ordinary["restricted_hosts"] is None
        assert ordinary["restricted_ports"] is None


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
