"""Execution-hardening tests (defense-in-depth for the sandbox/file/database sinks):
  - sandbox subprocesses run with a scrubbed env (no host secret leakage)
  - file.delete is confined to the configured sandbox dir (no arbitrary deletion)
  - database.query rejects a client-supplied connection_string (SSRF-to-DB) by default
"""

import pytest

from core.modules import atomic  # noqa: F401 — registers modules
from core.modules.atomic.sandbox.safe_env import build_sandbox_env
from core.modules.atomic.file.delete import FileDeleteModule
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

    def test_inherit_flag_restores_full_env(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
        monkeypatch.setenv("FLYTO_SANDBOX_INHERIT_ENV", "1")
        env = build_sandbox_env()
        assert env.get("OPENAI_API_KEY") == "sk-secret"


class TestFileDeleteConfinement:
    @pytest.mark.asyncio
    async def test_refuses_outside_sandbox(self, monkeypatch, tmp_path):
        monkeypatch.setenv("FLYTO_SANDBOX_DIR", str(tmp_path))
        monkeypatch.delenv("FLYTO_ALLOW_ABSOLUTE_PATHS", raising=False)
        mod = FileDeleteModule({"file_path": "/etc/passwd"}, {})
        with pytest.raises(RuntimeError, match="Refusing to delete outside"):
            await mod.execute()

    @pytest.mark.asyncio
    async def test_deletes_inside_sandbox(self, monkeypatch, tmp_path):
        monkeypatch.setenv("FLYTO_SANDBOX_DIR", str(tmp_path))
        f = tmp_path / "x.txt"
        f.write_text("hi")
        mod = FileDeleteModule({"file_path": str(f)}, {})
        result = await mod.execute()
        assert result["deleted"] is True
        assert not f.exists()


@pytest.mark.asyncio
class TestDatabaseDSNGuard:
    async def test_client_dsn_rejected_by_default(self, monkeypatch):
        monkeypatch.delenv("FLYTO_ALLOW_CLIENT_DB_DSN", raising=False)
        res = await execute_module("database.query", {
            "query": "SELECT 1",
            "connection_string": "postgres://internal-rds:5432/x",
        })
        assert res.get("ok") is False
        assert "connection_string is disabled" in res.get("error", "")

    async def test_client_dsn_allowed_with_flag(self, monkeypatch):
        monkeypatch.setenv("FLYTO_ALLOW_CLIENT_DB_DSN", "1")
        # With the flag the guard must NOT fire; the call then fails later trying
        # to actually connect — assert only it is not the guard's rejection.
        res = await execute_module("database.query", {
            "query": "SELECT 1",
            "connection_string": "postgres://127.0.0.1:1/x",
            "database_type": "postgresql",
        })
        assert "connection_string is disabled" not in res.get("error", "")
