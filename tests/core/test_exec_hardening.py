"""Execution-hardening tests (defense-in-depth for the sandbox/database sinks):
  - subprocess spawns run with a scrubbed env (no host-secret leakage)
  - database.* rejects a client-supplied connection target (SSRF-to-DB) by
    default, and refuses SSRF-sensitive hosts even when client DSNs are allowed.

Note: database.* is denied by default at the capability layer; these tests
allowlist it so the *DSN guard itself* (the defense-in-depth layer for an
opted-in operator) is the thing under test.
"""

import pytest

import core.module_policy as module_policy
from core.module_policy import ModuleFilter
from core.modules import atomic  # noqa: F401 — registers modules
from core.modules.atomic.sandbox.safe_env import build_sandbox_env
from core.modules.atomic.database._dsn_guard import (
    guard_client_dsn,
    guard_resolved_host,
    DatabaseTargetError,
)
from core.mcp_handler import execute_module


class TestBuildSandboxEnv:
    def test_scrubs_secrets_keeps_path(self, monkeypatch):
        monkeypatch.setenv("PATH", "/usr/bin")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
        monkeypatch.setenv("DATABASE_URL", "postgres://host/db")
        monkeypatch.delenv("FLYTO_SANDBOX_INHERIT_ENV", raising=False)
        env = build_sandbox_env()
        assert env.get("PATH") == "/usr/bin"
        assert "OPENAI_API_KEY" not in env
        assert "DATABASE_URL" not in env

    def test_merges_caller_extra(self, monkeypatch):
        monkeypatch.delenv("FLYTO_SANDBOX_INHERIT_ENV", raising=False)
        env = build_sandbox_env({"FOO": "bar"})
        assert env["FOO"] == "bar"

    def test_caller_extra_is_literal_no_expansion(self, monkeypatch):
        # {"X":"$AWS_SECRET"} must be injected literally, not substituted.
        monkeypatch.setenv("AWS_SECRET", "topsecret")
        monkeypatch.delenv("FLYTO_SANDBOX_INHERIT_ENV", raising=False)
        env = build_sandbox_env({"X": "$AWS_SECRET"})
        assert env["X"] == "$AWS_SECRET"

    def test_inherit_flag_restores_full_env(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
        monkeypatch.setenv("FLYTO_SANDBOX_INHERIT_ENV", "1")
        env = build_sandbox_env()
        assert env.get("OPENAI_API_KEY") == "sk-secret"


@pytest.mark.asyncio
async def test_shell_exec_cannot_leak_host_secret(monkeypatch):
    """shell.exec returns child stdout; with a scrubbed env, `env` must not
    surface a host secret. shell.* is denied by default, so allowlist it first."""
    monkeypatch.setenv("SUPER_SECRET_TOKEN", "leak-me-AKIA1234567890ABCDEF")
    monkeypatch.delenv("FLYTO_SANDBOX_INHERIT_ENV", raising=False)
    monkeypatch.delenv("FLYTO_MODULE_DENYLIST", raising=False)
    monkeypatch.setenv("FLYTO_MODULE_ALLOWLIST", "shell.exec")
    monkeypatch.setenv("FLYTO_GRANTED_PERMISSIONS", "shell.execute")
    monkeypatch.setattr(module_policy, "module_filter", ModuleFilter())

    res = await execute_module("shell.exec", {"command": "env"})
    blob = repr(res)
    assert "SUPER_SECRET_TOKEN" not in blob, blob
    assert "leak-me" not in blob, blob


class TestDatabaseDSNGuardUnit:
    def test_client_connection_string_rejected_by_default(self, monkeypatch):
        monkeypatch.delenv("FLYTO_ALLOW_CLIENT_DB_DSN", raising=False)
        with pytest.raises(DatabaseTargetError, match="client-supplied"):
            guard_client_dsn({"connection_string": "postgres://internal-rds:5432/x"})

    def test_client_host_port_rejected_by_default(self, monkeypatch):
        # The host/port bypass (no connection_string) is also closed.
        monkeypatch.delenv("FLYTO_ALLOW_CLIENT_DB_DSN", raising=False)
        with pytest.raises(DatabaseTargetError, match="client-supplied"):
            guard_client_dsn({"host": "internal-rds", "port": 5432})

    def test_server_configured_passes(self, monkeypatch):
        monkeypatch.delenv("FLYTO_ALLOW_CLIENT_DB_DSN", raising=False)
        guard_client_dsn({"query": "SELECT 1"})  # no client target → no raise

    def test_metadata_host_blocked_even_when_allowed(self, monkeypatch):
        monkeypatch.setenv("FLYTO_ALLOW_CLIENT_DB_DSN", "1")
        with pytest.raises(DatabaseTargetError, match="SSRF"):
            guard_client_dsn({"host": "169.254.169.254", "port": 80})

    def test_loopback_blocked_even_when_allowed(self, monkeypatch):
        monkeypatch.setenv("FLYTO_ALLOW_CLIENT_DB_DSN", "1")
        with pytest.raises(DatabaseTargetError):
            guard_resolved_host("127.0.0.1")

    def test_public_host_passes_resolution(self):
        guard_resolved_host("93.184.216.34")  # example.com IP — not internal


@pytest.mark.asyncio
class TestDatabaseDSNGuardThroughModule:
    @pytest.fixture(autouse=True)
    def _allow_database(self, monkeypatch):
        # Allowlist database so the DSN guard (not the denylist) is exercised.
        monkeypatch.delenv("FLYTO_MODULE_DENYLIST", raising=False)
        monkeypatch.setenv("FLYTO_MODULE_ALLOWLIST", "database.*")
        monkeypatch.setattr(module_policy, "module_filter", ModuleFilter())

    async def test_client_dsn_rejected_by_default(self, monkeypatch):
        monkeypatch.delenv("FLYTO_ALLOW_CLIENT_DB_DSN", raising=False)
        res = await execute_module("database.query", {
            "query": "SELECT 1",
            "connection_string": "postgres://internal-rds:5432/x",
        })
        assert res.get("ok") is False
        assert "client-supplied" in res.get("error", ""), res

    async def test_client_dsn_allowed_with_flag_reaches_connect(self, monkeypatch):
        # With the flag + a public-ish host the guard must NOT fire; the call then
        # fails later trying to connect. Assert it is not the guard's rejection.
        monkeypatch.setenv("FLYTO_ALLOW_CLIENT_DB_DSN", "1")
        res = await execute_module("database.query", {
            "query": "SELECT 1",
            "connection_string": "postgres://93.184.216.34:1/x",
            "database_type": "postgresql",
        })
        assert "client-supplied" not in res.get("error", "")
