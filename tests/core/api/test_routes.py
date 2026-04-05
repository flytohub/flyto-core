"""
Tests for API routes.

Tests health, info, modules, execute, workflow endpoints,
plus ModuleFilter, Pydantic models, ServerState, and security helpers.
"""

import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from starlette.testclient import TestClient

from core.api.server import create_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_header(app):
    """Return Authorization header dict with the active token."""
    from core.api import security as sec
    token = sec._active_token
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# TestHealthEndpoint
# ---------------------------------------------------------------------------

class TestHealthEndpoint:

    def test_health_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "version" in body


# ---------------------------------------------------------------------------
# TestServerInfo
# ---------------------------------------------------------------------------

class TestServerInfo:

    def test_info_returns_server_info(self, client):
        resp = client.get("/v1/info")
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "flyto-core"
        assert "version" in body
        assert "module_count" in body
        assert "category_count" in body


# ---------------------------------------------------------------------------
# TestModulesEndpoint
# ---------------------------------------------------------------------------

class TestModulesEndpoint:

    def test_list_all_modules(self, client):
        resp = client.get("/v1/modules")
        assert resp.status_code == 200
        body = resp.json()
        assert "total_categories" in body
        assert isinstance(body["categories"], list)
        assert body["total_categories"] > 0

    def test_list_modules_by_category(self, client):
        resp = client.get("/v1/modules", params={"category": "math"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["category"] == "math"
        assert isinstance(body["modules"], list)

    def test_get_module_info(self, client):
        resp = client.get("/v1/modules/math.abs")
        assert resp.status_code == 200
        body = resp.json()
        assert body["module_id"] == "math.abs"

    def test_get_nonexistent_module(self, client):
        resp = client.get("/v1/modules/nonexistent.module")
        assert resp.status_code == 404
        body = resp.json()
        assert "error" in body


# ---------------------------------------------------------------------------
# TestExecuteEndpoint
# ---------------------------------------------------------------------------

class TestExecuteEndpoint:

    def test_execute_without_auth(self, client):
        resp = client.post("/v1/execute", json={
            "module_id": "math.abs",
            "params": {"value": -5},
        })
        assert resp.status_code in (401, 403)

    def test_execute_with_invalid_auth(self, client):
        resp = client.post(
            "/v1/execute",
            json={"module_id": "math.abs", "params": {"value": -5}},
            headers={"Authorization": "Bearer wrong-token-value"},
        )
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# TestWorkflowEndpoint
# ---------------------------------------------------------------------------

class TestWorkflowEndpoint:

    def test_run_workflow_without_auth(self, client):
        resp = client.post("/v1/workflow/run", json={
            "workflow": {"steps": []},
        })
        assert resp.status_code in (401, 403)

    def test_get_nonexistent_execution(self, client):
        resp = client.get("/v1/workflow/nonexistent")
        assert resp.status_code == 404
        body = resp.json()
        assert "error" in body


# ---------------------------------------------------------------------------
# TestModuleFilter
# ---------------------------------------------------------------------------

class TestModuleFilter:

    def test_default_denylist(self):
        from core.api.security import ModuleFilter
        mf = ModuleFilter()
        assert not mf.is_allowed("shell.exec")
        assert not mf.is_allowed("process.kill")

    def test_allowed_module(self):
        from core.api.security import ModuleFilter
        mf = ModuleFilter()
        assert mf.is_allowed("math.abs")

    def test_denied_module(self):
        from core.api.security import ModuleFilter
        mf = ModuleFilter()
        assert not mf.is_allowed("shell.exec")

    def test_custom_denylist(self, monkeypatch):
        from core.api.security import ModuleFilter
        monkeypatch.setenv("FLYTO_MODULE_DENYLIST", "custom.*,danger.*")
        # Clear allowlist so denylist takes effect
        monkeypatch.delenv("FLYTO_MODULE_ALLOWLIST", raising=False)
        mf = ModuleFilter()
        assert not mf.is_allowed("custom.run")
        assert not mf.is_allowed("danger.delete")
        assert mf.is_allowed("shell.exec")  # no longer denied
        assert mf.is_allowed("math.abs")


# ---------------------------------------------------------------------------
# TestModels
# ---------------------------------------------------------------------------

class TestModels:

    def test_execute_module_request_valid(self):
        from core.api.models import ExecuteModuleRequest
        req = ExecuteModuleRequest(module_id="math.abs", params={"value": -1})
        assert req.module_id == "math.abs"
        assert req.params == {"value": -1}
        assert req.context is None

    def test_execute_module_request_missing_module_id(self):
        from core.api.models import ExecuteModuleRequest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ExecuteModuleRequest(params={"value": 1})

    def test_run_workflow_request_defaults(self):
        from core.api.models import RunWorkflowRequest
        req = RunWorkflowRequest(workflow={"steps": []})
        assert req.workflow == {"steps": []}
        assert req.params is None
        assert req.enable_evidence is True
        assert req.enable_trace is True

    def test_workflow_run_response(self):
        from core.api.models import WorkflowRunResponse
        resp = WorkflowRunResponse(
            ok=True,
            execution_id="exec_abc123",
            status="completed",
            duration_ms=42,
        )
        assert resp.ok is True
        assert resp.execution_id == "exec_abc123"
        assert resp.status == "completed"
        assert resp.duration_ms == 42
        assert resp.error is None
        assert resp.result is None


# ---------------------------------------------------------------------------
# TestServerState
# ---------------------------------------------------------------------------

class TestServerState:

    def test_initial_state(self, tmp_path):
        from core.api.state import ServerState
        state = ServerState(evidence_path=tmp_path / "evidence")
        assert state.browser_sessions == {}
        assert state.running_workflows == {}


# ---------------------------------------------------------------------------
# TestSecurity
# ---------------------------------------------------------------------------

class TestSecurity:

    def test_generate_token_length(self):
        from core.api.security import generate_token
        token = generate_token()
        assert isinstance(token, str)
        assert len(token) > 0

    def test_generate_token_unique(self):
        from core.api.security import generate_token
        t1 = generate_token()
        t2 = generate_token()
        assert t1 != t2

    def test_cors_origins_defaults(self):
        from core.api.security import get_cors_origins
        origins = get_cors_origins()
        assert isinstance(origins, list)
        assert any("localhost" in o for o in origins)


# ---------------------------------------------------------------------------
# TestExecuteWithAuth
# ---------------------------------------------------------------------------

class TestExecuteWithAuth:
    """Tests for POST /v1/execute with valid auth."""

    def test_execute_math_module(self, client, auth_header):
        resp = client.post("/v1/execute", json={
            "module_id": "math.abs",
            "params": {"number": -42},
        }, headers=auth_header)
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["data"]["data"]["result"] == 42
        assert body["duration_ms"] >= 0

    def test_execute_nonexistent_module(self, client, auth_header):
        resp = client.post("/v1/execute", json={
            "module_id": "nonexistent.module",
            "params": {},
        }, headers=auth_header)
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert "not found" in body["error"].lower() or "Module" in body["error"]

    def test_execute_denied_module(self, client, auth_header):
        resp = client.post("/v1/execute", json={
            "module_id": "shell.exec",
            "params": {"command": "ls"},
        }, headers=auth_header)
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert "blocked" in body["error"].lower() or "security" in body["error"].lower()

    def test_execute_string_module(self, client, auth_header):
        resp = client.post("/v1/execute", json={
            "module_id": "string.uppercase",
            "params": {"text": "hello"},
        }, headers=auth_header)
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["data"]["data"]["result"] == "HELLO"

    def test_execute_with_missing_params(self, client, auth_header):
        resp = client.post("/v1/execute", json={
            "module_id": "math.abs",
            "params": {},
        }, headers=auth_header)
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False  # Should fail with missing param error

    def test_execute_hash_module(self, client, auth_header):
        resp = client.post("/v1/execute", json={
            "module_id": "hash.sha256",
            "params": {"text": "test"},
        }, headers=auth_header)
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert "hash" in body["data"].get("data", body["data"])


# ---------------------------------------------------------------------------
# TestWorkflowWithAuth
# ---------------------------------------------------------------------------

class TestWorkflowWithAuth:
    """Tests for workflow routes with valid auth."""

    def test_run_simple_workflow(self, client, auth_header):
        resp = client.post("/v1/workflow/run", json={
            "workflow": {
                "steps": [
                    {"id": "s1", "module": "math.abs", "params": {"number": -10}},
                ]
            },
            "enable_evidence": False,
            "enable_trace": False,
        }, headers=auth_header)
        assert resp.status_code == 200
        body = resp.json()
        assert "execution_id" in body

    def test_run_workflow_blocked_module(self, client, auth_header):
        resp = client.post("/v1/workflow/run", json={
            "workflow": {
                "steps": [
                    {"id": "s1", "module": "shell.exec", "params": {"command": "ls"}},
                ]
            },
        }, headers=auth_header)
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert "blocked" in body.get("error", "").lower() or body["status"] == "blocked"

    def test_get_nonexistent_evidence(self, client):
        resp = client.get("/v1/workflow/nonexistent/evidence")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# TestModulesEndpointExtended
# ---------------------------------------------------------------------------

class TestModulesEndpointExtended:
    """Extended module listing tests."""

    def test_nonexistent_category(self, client):
        resp = client.get("/v1/modules", params={"category": "nonexistent_category"})
        assert resp.status_code == 404

    def test_category_has_modules(self, client):
        resp = client.get("/v1/modules", params={"category": "string"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] > 0
        assert len(body["modules"]) > 0


# ---------------------------------------------------------------------------
# TestReplayEndpoint
# ---------------------------------------------------------------------------

class TestReplayEndpoint:
    """Tests for replay routes."""

    def test_replay_without_auth(self, client):
        resp = client.post("/v1/workflow/exec_test/replay/step1", json={})
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# TestSecurityExtended
# ---------------------------------------------------------------------------

class TestSecurityExtended:
    """Extended security tests."""

    def test_cors_wildcard(self, monkeypatch):
        monkeypatch.setenv("FLYTO_CORS_ORIGINS", "*")
        from core.api.security import get_cors_origins
        origins = get_cors_origins()
        assert origins == ["*"]

    def test_cors_custom(self, monkeypatch):
        monkeypatch.setenv("FLYTO_CORS_ORIGINS", "https://a.com, https://b.com")
        from core.api.security import get_cors_origins
        origins = get_cors_origins()
        assert origins == ["https://a.com", "https://b.com"]

    def test_init_auth_with_env_token(self, monkeypatch):
        monkeypatch.setenv("FLYTO_API_TOKEN", "test-fixed-token")
        from core.api.security import init_auth
        token = init_auth(9999)
        assert token == "test-fixed-token"
        # Clean up
        import core.api.security as sec
        sec._active_token = None

    def test_init_auth_auto_generate(self, monkeypatch):
        monkeypatch.delenv("FLYTO_API_TOKEN", raising=False)
        from core.api.security import init_auth
        token = init_auth(9998)
        assert token is not None
        assert len(token) > 10
        # Clean up
        import core.api.security as sec
        sec._active_token = None

    def test_write_and_read_token_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr("core.api.security._TOKEN_DIR", tmp_path)
        from core.api.security import write_token_file, read_token_file
        write_token_file("my-secret", 7777)
        assert read_token_file(7777) == "my-secret"

    def test_read_missing_token_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr("core.api.security._TOKEN_DIR", tmp_path)
        from core.api.security import read_token_file
        assert read_token_file(1111) is None

    def test_module_filter_allowlist(self, monkeypatch):
        monkeypatch.setenv("FLYTO_MODULE_ALLOWLIST", "math.*,string.*")
        monkeypatch.delenv("FLYTO_MODULE_DENYLIST", raising=False)
        from core.api.security import ModuleFilter
        mf = ModuleFilter()
        assert mf.is_allowed("math.abs")
        assert mf.is_allowed("string.uppercase")
        assert not mf.is_allowed("shell.exec")
        assert not mf.is_allowed("browser.click")

    def test_module_filter_empty_denylist(self, monkeypatch):
        monkeypatch.setenv("FLYTO_MODULE_DENYLIST", "")
        monkeypatch.delenv("FLYTO_MODULE_ALLOWLIST", raising=False)
        from core.api.security import ModuleFilter
        mf = ModuleFilter()
        assert mf.is_allowed("shell.exec")  # Nothing denied
        assert mf.is_allowed("process.kill")


# ---------------------------------------------------------------------------
# TestEvidenceHooks
# ---------------------------------------------------------------------------

class TestEvidenceHooks:
    """Tests for APIEvidenceHooks and helper functions."""

    def test_safe_copy_primitives(self):
        from core.api.evidence_hooks import _safe_copy
        result = _safe_copy({"a": "str", "b": 42, "c": 3.14, "d": True, "e": None})
        assert result == {"a": "str", "b": 42, "c": 3.14, "d": True, "e": None}

    def test_safe_copy_serializable_collections(self):
        from core.api.evidence_hooks import _safe_copy
        result = _safe_copy({"list": [1, 2, 3], "dict": {"nested": "val"}})
        assert result == {"list": [1, 2, 3], "dict": {"nested": "val"}}

    def test_safe_copy_non_serializable(self):
        from core.api.evidence_hooks import _safe_copy
        class Custom:
            pass
        result = _safe_copy({"obj": Custom()})
        assert "<Custom>" in result["obj"]

    def test_result_to_dict_none(self):
        from core.api.evidence_hooks import _result_to_dict
        assert _result_to_dict(None) == {}

    def test_result_to_dict_dict(self):
        from core.api.evidence_hooks import _result_to_dict
        d = {"ok": True}
        assert _result_to_dict(d) == {"ok": True}

    def test_result_to_dict_string(self):
        from core.api.evidence_hooks import _result_to_dict
        assert _result_to_dict("hello") == {"value": "hello"}

    def test_result_to_dict_number(self):
        from core.api.evidence_hooks import _result_to_dict
        assert _result_to_dict(42) == {"value": "42"}

    def test_hooks_init(self, tmp_path):
        from core.api.evidence_hooks import APIEvidenceHooks
        from core.engine.evidence import EvidenceStore
        store = EvidenceStore(base_path=tmp_path)
        hooks = APIEvidenceHooks(store, "exec_test")
        assert hooks.execution_id == "exec_test"
        assert hooks._step_starts == {}

    def test_hooks_lifecycle(self, tmp_path):
        from core.api.evidence_hooks import APIEvidenceHooks
        from core.engine.hooks import HookContext, HookResult, HookAction
        from core.engine.evidence import EvidenceStore
        store = EvidenceStore(base_path=tmp_path)
        hooks = APIEvidenceHooks(store, "exec_test")
        ctx = HookContext(workflow_id="wf1", step_id="s1", module_id="math.abs", variables={})
        # on_workflow_start
        result = hooks.on_workflow_start(ctx)
        assert result.action == HookAction.CONTINUE
        # on_retry
        result = hooks.on_retry(ctx)
        assert result.action == HookAction.CONTINUE
        # on_module_missing
        result = hooks.on_module_missing(ctx)
        assert result.action == HookAction.ABORT

    def test_hooks_pre_post_execute(self, tmp_path):
        from core.api.evidence_hooks import APIEvidenceHooks
        from core.engine.hooks import HookContext
        from core.engine.evidence import EvidenceStore
        store = EvidenceStore(base_path=tmp_path)
        hooks = APIEvidenceHooks(store, "exec_test")
        # Pre-execute
        ctx_pre = HookContext(workflow_id="wf1", step_id="s1", module_id="math.abs", variables={"x": 1})
        hooks.on_pre_execute(ctx_pre)
        assert "s1" in hooks._step_starts
        # Post-execute
        ctx_post = HookContext(workflow_id="wf1", step_id="s1", module_id="math.abs", variables={"x": 1, "result": 42}, result={"ok": True})
        hooks.on_post_execute(ctx_post)
        assert "s1" not in hooks._step_starts

    def test_hooks_error(self, tmp_path):
        from core.api.evidence_hooks import APIEvidenceHooks
        from core.engine.hooks import HookContext
        from core.engine.evidence import EvidenceStore
        store = EvidenceStore(base_path=tmp_path)
        hooks = APIEvidenceHooks(store, "exec_test")
        # Pre-execute then error
        ctx = HookContext(workflow_id="wf1", step_id="s1", module_id="math.abs", variables={})
        hooks.on_pre_execute(ctx)
        err_ctx = HookContext(workflow_id="wf1", step_id="s1", module_id="math.abs", variables={}, error=Exception("test"), error_message="test error")
        hooks.on_error(err_ctx)
        assert "s1" not in hooks._step_starts

    def test_hooks_error_without_pre(self, tmp_path):
        """Error without pre_execute should still work."""
        from core.api.evidence_hooks import APIEvidenceHooks
        from core.engine.hooks import HookContext, HookAction
        from core.engine.evidence import EvidenceStore
        store = EvidenceStore(base_path=tmp_path)
        hooks = APIEvidenceHooks(store, "exec_test")
        err_ctx = HookContext(workflow_id="wf1", step_id="s1", module_id="math.abs", variables={}, error=Exception("test"), error_message="test error")
        result = hooks.on_error(err_ctx)
        assert result.action == HookAction.CONTINUE


# ---------------------------------------------------------------------------
# TestServerStateExtended
# ---------------------------------------------------------------------------

class TestServerStateExtended:

    def test_evidence_path(self, tmp_path):
        from core.api.state import ServerState
        state = ServerState(evidence_path=tmp_path / "ev")
        assert state.evidence_path == tmp_path / "ev"


# ---------------------------------------------------------------------------
# TestPluginService
# ---------------------------------------------------------------------------

class TestPluginService:
    """Tests for PluginService."""

    def test_get_plugin_service_singleton(self):
        from core.api.plugins.service import get_plugin_service
        svc1 = get_plugin_service()
        svc2 = get_plugin_service()
        assert svc1 is svc2

    def test_plugin_service_default_config(self):
        from core.api.plugins.service import PluginService, PluginServiceConfig
        svc = PluginService()
        assert svc.config.enable_marketplace is True
        assert svc.config.catalog_cache_ttl == 300

    def test_get_catalog_empty(self):
        from core.api.plugins.service import PluginService
        svc = PluginService()
        catalog = svc.get_catalog()
        assert isinstance(catalog, list)

    def test_get_installed_plugins_empty(self):
        from core.api.plugins.service import PluginService
        svc = PluginService()
        installed = svc.get_installed_plugins()
        assert isinstance(installed, list)
        assert len(installed) == 0

    def test_get_installed_modules_empty(self):
        from core.api.plugins.service import PluginService
        svc = PluginService()
        modules = svc.get_installed_modules()
        assert isinstance(modules, list)

    def test_install_nonexistent_plugin(self, tmp_path):
        from core.api.plugins.service import PluginService, PluginServiceConfig
        svc = PluginService(config=PluginServiceConfig(plugins_dir=str(tmp_path)))
        result = svc.install_plugin("nonexistent-plugin")
        assert result["ok"] is False

    def test_uninstall_nonexistent_plugin(self, tmp_path):
        from core.api.plugins.service import PluginService, PluginServiceConfig
        svc = PluginService(config=PluginServiceConfig(plugins_dir=str(tmp_path)))
        result = svc.uninstall_plugin("nonexistent-plugin")
        assert result["ok"] is False

    def test_catalog_etag(self):
        from core.api.plugins.service import PluginService
        svc = PluginService()
        etag = svc.get_catalog_etag()
        assert isinstance(etag, str)
        assert len(etag) > 0
