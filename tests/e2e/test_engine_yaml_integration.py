"""Integration test — real YAML → WorkflowEngine → verdict end-to-end.

Unlike test_closed_loop_roundtrip (which calls modules directly), this test
exercises the full engine path:

  flyto-ai.generate_test_from_finding(SecurityFinding)   → YAML string
  yaml.safe_load                                         → workflow dict
  WorkflowEngine(workflow_dict).execute()                → step outputs
  _compute_verdict(step outputs)                         → final verdict

If the engine fails to resolve a module, fails to bind variables
(`${sql_probes.data}`), or mis-routes edges, this test catches it.
"""
from __future__ import annotations

import asyncio
import http.server
import importlib.util
import os
import socketserver
import sys
import threading
import time
import urllib.parse
from pathlib import Path

import pytest
import yaml as pyyaml

# Loosen SSRF guard BEFORE importing modules, since the config is read once.
os.environ["FLYTO_ALLOW_PRIVATE_NETWORK"] = "true"
os.environ["FLYTO_AI_ALLOW_PROD_TARGETS"] = "1"  # relax generator's hostname check

REPO_ROOT = Path(__file__).resolve().parents[3]
CORE_SRC = REPO_ROOT / "flyto-core" / "src"
AI_ROOT = REPO_ROOT / "flyto-ai"
CLOUD_BACKEND = REPO_ROOT / "flyto-cloud" / "src" / "ui" / "web" / "backend"

for p in (str(CORE_SRC), str(AI_ROOT), str(CLOUD_BACKEND)):
    if p not in sys.path:
        sys.path.insert(0, p)


# ---------------------------------------------------------------------------
# Vulnerable mock target
# ---------------------------------------------------------------------------

class _MockHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args, **kwargs):
        return

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(parsed.query)
        if parsed.path == "/api/users":
            payload = q.get("user_id", [""])[0]
            if "'" in payload and "OR" in payload.upper():
                return self._send(500,
                    "You have an error in your SQL syntax; mysql_fetch_array")
            if "WAITFOR" in payload.upper():
                time.sleep(3.2)
                return self._send(200, '{"rows": []}')
            return self._send(200, '{"rows": []}')
        if parsed.path == "/api/protected":
            # Accept only a single well-formed bearer token.
            auth = self.headers.get("Authorization") or ""
            if auth == "Bearer real-valid-token":
                return self._send(200, "ok")
            return self._send(403, "forbidden")

        if parsed.path == "/fetch":
            # Simulates a vulnerable SSRF endpoint that fetches any user URL
            # and echoes its body back.
            target = q.get("url", [""])[0]
            if "169.254.169.254" in target:
                return self._send(200, 'ami-id: ami-12345\ninstance-identity: docs')
            if "metadata.google.internal" in target:
                return self._send(200, 'computeMetadata/v1/ root access_token found')
            if target.startswith("http://127.0.0.1") or target.startswith("http://10."):
                return self._send(200, "internal service banner")
            return self._send(200, "external content fetched")

        if parsed.path == "/redirect":
            # Vulnerable open-redirect — echoes the destination into the body
            # (plus sets Location header). Tests assert on body for simplicity.
            next_url = q.get("next", [""])[0]
            body = (
                f'<html><body>Redirecting to <a href="{next_url}">'
                f'{next_url}</a></body></html>'
            )
            data = body.encode("utf-8")
            self.send_response(302)
            self.send_header("Location", next_url)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if parsed.path == "/exec":
            # Vulnerable command-injection endpoint: echoes shell output.
            cmd = q.get("cmd", [""])[0]
            if "id" in cmd and any(c in cmd for c in (";", "|", "`", "\n")):
                return self._send(200, "uid=1000(app) gid=1000(app) groups=1000(app)")
            if "uname" in cmd:
                return self._send(200, "Linux vulnhost 6.5 x86_64")
            if "sleep" in cmd:
                # extract sleep duration
                import re as _re
                m = _re.search(r"sleep\s+(\d+)", cmd)
                dur = int(m.group(1)) if m else 1
                time.sleep(min(dur, 5))
                return self._send(200, "slept")
            return self._send(200, f"echo: {cmd}")

        if parsed.path == "/download":
            # Vulnerable path-traversal endpoint — echoes file content if the
            # `file` param traverses outside the intended dir.
            file_param = q.get("file", [""])[0]
            # Decode URL-encoded traversal then check for /etc/passwd pattern.
            import urllib.parse as _up
            decoded = _up.unquote(_up.unquote(file_param))
            if "etc/passwd" in decoded or "etc\\passwd" in decoded:
                return self._send(200, "root:x:0:0:root:/root:/bin/bash\ndaemon:x:1:1:daemon:/usr/sbin:/usr/sbin/nologin")
            if "win.ini" in decoded.lower():
                return self._send(200, "[fonts]\n[extensions]\nhlp=winhlp32.exe")
            return self._send(200, "file content placeholder")

        if parsed.path == "/hello":
            # Vulnerable SSTI endpoint — reflects input through a template engine.
            name = q.get("name", [""])[0]
            import re as _re
            m = _re.match(r"\{\{\s*(\d+)\s*\*\s*(\d+)\s*\}\}", name)
            if m:
                val = int(m.group(1)) * int(m.group(2))
                return self._send(200, f"<html><body>Hello <b>{val}</b></body></html>")
            m = _re.match(r"\$\{\s*(\d+)\s*\*\s*(\d+)\s*\}", name)
            if m:
                val = int(m.group(1)) * int(m.group(2))
                return self._send(200, f'{{"greeting": "Hello {val}"}}')
            m = _re.match(r"<%=\s*(\d+)\s*\*\s*(\d+)\s*%>", name)
            if m:
                val = int(m.group(1)) * int(m.group(2))
                return self._send(200, f"<html><body>Hello {val}</body></html>")
            return self._send(200, f"<html><body>Hello {name}</body></html>")

        if parsed.path == "/go":
            # Vulnerable CRLF endpoint — inserts raw user value into a header.
            redirect = q.get("redirect", [""])[0]
            import urllib.parse as _up
            decoded = _up.unquote(redirect)
            # If the decoded value contains CRLF + a header name, echo it
            # back in the body (simulates a log line that got corrupted).
            if "\r\n" in decoded or "\n" in decoded:
                return self._send(200, f"Redirect requested:\n{decoded}")
            return self._send(200, f"Redirecting to {redirect}")

        return self._send(404, "nope")

    def do_POST(self):
        import json as _json
        parsed = urllib.parse.urlparse(self.path)
        content_length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_length) if content_length > 0 else b""

        if parsed.path == "/xml":
            # Vulnerable XXE endpoint — parses XML with external entities.
            body = raw_body.decode("utf-8", errors="replace")
            if "file:///etc/passwd" in body and "<!ENTITY" in body:
                return self._send(200,
                    "<result>root:x:0:0:root:/root:/bin/bash</result>")
            return self._send(200, "<result>ok</result>")

        if parsed.path == "/login":
            # Vulnerable NoSQLi — Mongo-style operator injection flips auth.
            try:
                body_dict = _json.loads(raw_body.decode("utf-8")) if raw_body else {}
            except Exception:
                return self._send(400, '{"error": "bad json"}')
            pw = body_dict.get("password")
            if isinstance(pw, dict) and any(k.startswith("$") for k in pw):
                # Any operator-style password "succeeds"
                return self._send(200, '{"ok": true, "token": "forged"}')
            # Wrong-password baseline
            return self._send(401, '{"ok": false, "error": "invalid credentials"}')

        if parsed.path == "/api/import":
            # Vulnerable deserialization — echoes back parser error.
            body = raw_body.decode("utf-8", errors="replace")
            if "O:8:\"Attacker\"" in body:
                return self._send(500,
                    '{"error": "Exception: __wakeup magic method invoked during unserialize()"}')
            if "gAS" in body or "gASVDA" in body or "\\x80" in body:
                # Python pickle signature
                return self._send(500,
                    '{"error": "TypeError in pickle.Unpickler: __reduce__ gadget"}')
            if "ruby/object" in body:
                return self._send(500,
                    '{"error": "Psych::Exception YAMLError: unsafe deserialization"}')
            return self._send(200, '{"ok": true}')

        return self._send(404, "nope")

    def do_PATCH(self):
        import json as _json
        parsed = urllib.parse.urlparse(self.path)
        content_length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_length) if content_length > 0 else b""

        if parsed.path == "/api/users/me":
            # Vulnerable mass-assignment — echoes back the full user object.
            try:
                body_dict = _json.loads(raw_body.decode("utf-8")) if raw_body else {}
            except Exception:
                return self._send(400, '{"error": "bad json"}')
            import json as _j
            merged = {"id": "u1", "name": "Alice"}
            merged.update(body_dict)  # vulnerable: accepts all client-supplied fields
            return self._send(200, _j.dumps(merged))

        return self._send(404, "nope")

    def _send(self, status, body):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type",
                         "application/json" if body.startswith("{") else "text/plain")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture(scope="module")
def mock_server():
    server = socketserver.TCPServer(("127.0.0.1", 0), _MockHandler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_closed_loop_modules():
    """Ensure the three new modules are registered before the engine needs them."""
    import importlib

    from core.modules.registry import ModuleRegistry

    importlib.import_module("core.modules.atomic.http.batch")
    importlib.import_module("core.modules.atomic.testing.assert_status")
    importlib.import_module("core.modules.atomic.testing.assert_timing")
    importlib.import_module("core.modules.atomic.testing.assert_contains")
    # Engine also needs flow.start and output.display for the blueprint.
    importlib.import_module("core.modules.atomic.flow")
    importlib.import_module("core.modules.atomic.output")
    return ModuleRegistry


def _load_verdict_aggregator():
    from unittest.mock import MagicMock
    for name in ("gateway", "gateway.auth", "fastapi", "pydantic"):
        if name not in sys.modules:
            sys.modules[name] = MagicMock()

    class _FakeBase:
        def __init_subclass__(cls, **kw):
            return None
    sys.modules["pydantic"].BaseModel = _FakeBase
    sys.modules["pydantic"].Field = lambda *a, **kw: None
    sys.modules["pydantic"].ConfigDict = dict
    sys.modules["fastapi"].APIRouter = lambda *a, **kw: MagicMock()
    sys.modules["fastapi"].Depends = lambda *a, **kw: None
    sys.modules["fastapi"].HTTPException = type("HTTPException", (Exception,), {})

    spec = importlib.util.spec_from_file_location(
        "verify_mod", CLOUD_BACKEND / "api" / "workflows" / "verify.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._compute_verdict


def _extract_step_outputs(engine) -> dict:
    """Pull each step's result out of the engine's context after execution."""
    ctx = getattr(engine, "context", {}) or {}
    outputs = {}
    for key, val in ctx.items():
        if isinstance(val, dict):
            outputs[key] = val
    return outputs


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_full_yaml_pipeline_produces_exploitable_verdict(mock_server):
    """flyto-ai → YAML → WorkflowEngine → verdict aggregator → exploitable."""
    _load_closed_loop_modules()

    from flyto_ai.security import generate_test_from_finding, SecurityFinding
    from core.engine.workflow import WorkflowEngine

    finding = SecurityFinding(
        category="sql_injection",
        source="request.args.get('user_id')",
        source_file="handler.py",
        source_line=42,
        sink="cursor.execute(q)",
        sink_file="handler.py",
        sink_line=55,
        severity="critical",
        param_name="user_id",
        endpoint_path="/api/users",
        http_method="GET",
    )

    yaml_str = generate_test_from_finding(
        finding=finding,
        target_url=mock_server,
        auth_token=None,
    )
    assert "http.batch" in yaml_str
    assert "test.assert_timing" in yaml_str

    workflow = pyyaml.safe_load(yaml_str)
    engine = WorkflowEngine(workflow=workflow, params={})
    result = await engine.execute()

    # The engine must have completed. Status should be "success" or "completed".
    assert result is not None
    status = result.get("status") or getattr(engine, "status", None)
    assert str(status).lower() in ("success", "completed", "ok", "workflowstatus.success"), (status, result)

    # Inspect per-step outputs for verdicts.
    step_outputs = _extract_step_outputs(engine)
    # Some engines store outputs keyed by step id, others under a sub-dict.
    # Flatten both possibilities.
    candidates = {**step_outputs}
    for v in list(step_outputs.values()):
        if isinstance(v, dict):
            for k2, v2 in v.items():
                if isinstance(v2, dict) and "verdict" in v2:
                    candidates[k2] = v2

    compute_verdict = _load_verdict_aggregator()
    verdict_out = compute_verdict(candidates, result.get("variables") if isinstance(result, dict) else None)

    # If the engine actually wired the modules right, one of the assert_* steps
    # produced a verdict.
    assert verdict_out["verdict"] is not None, (
        "engine ran but no verdict was surfaced — step outputs: "
        f"{list(candidates.keys())}"
    )
    assert verdict_out["verdict"] == "exploitable", verdict_out


@pytest.mark.asyncio
async def test_auth_bypass_yaml_pipeline_produces_sanitized(mock_server):
    """auth_bypass blueprint → guarded endpoint → WorkflowEngine → sanitized."""
    _load_closed_loop_modules()

    from flyto_ai.security import generate_test_from_finding, SecurityFinding
    from core.engine.workflow import WorkflowEngine

    finding = SecurityFinding(
        category="auth_bypass",
        source="missing auth middleware",
        source_file="routes.py",
        source_line=12,
        sink="app.get('/api/protected')",
        sink_file="routes.py",
        sink_line=15,
        severity="high",
        endpoint_path="/api/protected",
        http_method="GET",
    )

    yaml_str = generate_test_from_finding(
        finding=finding,
        target_url=mock_server,
        auth_token="real-valid-token",
    )

    workflow = pyyaml.safe_load(yaml_str)
    engine = WorkflowEngine(workflow=workflow, params={})
    result = await engine.execute()

    step_outputs = _extract_step_outputs(engine)
    candidates = {**step_outputs}
    for v in list(step_outputs.values()):
        if isinstance(v, dict):
            for k2, v2 in v.items():
                if isinstance(v2, dict) and "verdict" in v2:
                    candidates[k2] = v2

    compute_verdict = _load_verdict_aggregator()
    verdict_out = compute_verdict(candidates, result.get("variables") if isinstance(result, dict) else None)
    assert verdict_out["verdict"] == "sanitized", verdict_out


@pytest.mark.asyncio
async def test_ssrf_yaml_pipeline_reports_exploitable(mock_server):
    """SSRF blueprint → mock echo-fetch → WorkflowEngine → exploitable."""
    _load_closed_loop_modules()

    from flyto_ai.security import generate_test_from_finding, SecurityFinding
    from core.engine.workflow import WorkflowEngine

    finding = SecurityFinding(
        category="ssrf",
        source="request.query['url']",
        source_file="fetcher.py", source_line=20,
        sink="requests.get(url)",
        sink_file="fetcher.py", sink_line=25,
        severity="high",
        param_name="url",
        endpoint_path="/fetch",
        http_method="GET",
    )

    yaml_str = generate_test_from_finding(finding, mock_server, None)
    workflow = pyyaml.safe_load(yaml_str)
    engine = WorkflowEngine(workflow=workflow, params={})
    result = await engine.execute()

    step_outputs = _extract_step_outputs(engine)
    candidates = {**step_outputs}
    for v in list(step_outputs.values()):
        if isinstance(v, dict):
            for k2, v2 in v.items():
                if isinstance(v2, dict) and "verdict" in v2:
                    candidates[k2] = v2

    verdict_out = _load_verdict_aggregator()(candidates,
        result.get("variables") if isinstance(result, dict) else None)
    assert verdict_out["verdict"] == "exploitable", verdict_out


@pytest.mark.asyncio
async def test_open_redirect_yaml_pipeline_reports_exploitable(mock_server):
    """Open redirect blueprint → vulnerable /redirect → exploitable."""
    _load_closed_loop_modules()

    from flyto_ai.security import generate_test_from_finding, SecurityFinding
    from core.engine.workflow import WorkflowEngine

    finding = SecurityFinding(
        category="open_redirect",
        source="request.query['next']",
        source_file="auth.py", source_line=40,
        sink="redirect(next_url)",
        sink_file="auth.py", sink_line=44,
        severity="medium",
        param_name="next",
        endpoint_path="/redirect",
        http_method="GET",
    )

    yaml_str = generate_test_from_finding(finding, mock_server, None)
    workflow = pyyaml.safe_load(yaml_str)
    engine = WorkflowEngine(workflow=workflow, params={})
    result = await engine.execute()

    step_outputs = _extract_step_outputs(engine)
    candidates = {**step_outputs}
    for v in list(step_outputs.values()):
        if isinstance(v, dict):
            for k2, v2 in v.items():
                if isinstance(v2, dict) and "verdict" in v2:
                    candidates[k2] = v2

    verdict_out = _load_verdict_aggregator()(candidates,
        result.get("variables") if isinstance(result, dict) else None)
    assert verdict_out["verdict"] == "exploitable", verdict_out


@pytest.mark.asyncio
async def test_command_injection_yaml_pipeline_reports_exploitable(mock_server):
    """Command injection blueprint → /exec → exploitable via pattern + timing."""
    _load_closed_loop_modules()

    from flyto_ai.security import generate_test_from_finding, SecurityFinding
    from core.engine.workflow import WorkflowEngine

    finding = SecurityFinding(
        category="command_injection",
        source="request.query['cmd']",
        source_file="ops.py", source_line=10,
        sink="os.system(cmd)",
        sink_file="ops.py", sink_line=12,
        severity="critical",
        param_name="cmd",
        endpoint_path="/exec",
        http_method="GET",
    )

    yaml_str = generate_test_from_finding(finding, mock_server, None)
    workflow = pyyaml.safe_load(yaml_str)
    engine = WorkflowEngine(workflow=workflow, params={})
    result = await engine.execute()

    step_outputs = _extract_step_outputs(engine)
    candidates = {**step_outputs}
    for v in list(step_outputs.values()):
        if isinstance(v, dict):
            for k2, v2 in v.items():
                if isinstance(v2, dict) and "verdict" in v2:
                    candidates[k2] = v2

    verdict_out = _load_verdict_aggregator()(candidates,
        result.get("variables") if isinstance(result, dict) else None)
    assert verdict_out["verdict"] == "exploitable", verdict_out


async def _run_blueprint(mock_server, category, param, endpoint, method="GET"):
    """Shared runner: generate YAML → engine → verdict."""
    _load_closed_loop_modules()
    from flyto_ai.security import generate_test_from_finding, SecurityFinding
    from core.engine.workflow import WorkflowEngine

    finding = SecurityFinding(
        category=category,
        source="user_input",
        source_file="handler.py", source_line=10,
        sink="dangerous_call()",
        sink_file="handler.py", sink_line=20,
        severity="high",
        param_name=param,
        endpoint_path=endpoint,
        http_method=method,
    )
    yaml_str = generate_test_from_finding(finding, mock_server, None)
    workflow = pyyaml.safe_load(yaml_str)
    engine = WorkflowEngine(workflow=workflow, params={})
    result = await engine.execute()

    step_outputs = _extract_step_outputs(engine)
    candidates = {**step_outputs}
    for v in list(step_outputs.values()):
        if isinstance(v, dict):
            for k2, v2 in v.items():
                if isinstance(v2, dict) and "verdict" in v2:
                    candidates[k2] = v2

    return _load_verdict_aggregator()(
        candidates, result.get("variables") if isinstance(result, dict) else None
    )


@pytest.mark.asyncio
async def test_path_traversal_reports_exploitable(mock_server):
    verdict = await _run_blueprint(mock_server, "path_traversal", "file", "/download")
    assert verdict["verdict"] == "exploitable", verdict


@pytest.mark.asyncio
async def test_xxe_reports_exploitable(mock_server):
    verdict = await _run_blueprint(mock_server, "xxe", None, "/xml", method="POST")
    assert verdict["verdict"] == "exploitable", verdict


@pytest.mark.asyncio
async def test_ssti_reports_exploitable(mock_server):
    verdict = await _run_blueprint(mock_server, "ssti", "name", "/hello")
    assert verdict["verdict"] == "exploitable", verdict


@pytest.mark.asyncio
async def test_nosql_injection_reports_exploitable(mock_server):
    verdict = await _run_blueprint(
        mock_server, "nosql_injection", "password", "/login", method="POST",
    )
    assert verdict["verdict"] == "exploitable", verdict


@pytest.mark.asyncio
async def test_insecure_deserialization_reports_exploitable(mock_server):
    verdict = await _run_blueprint(
        mock_server, "insecure_deserialization", "data", "/api/import", method="POST",
    )
    assert verdict["verdict"] == "exploitable", verdict


@pytest.mark.asyncio
async def test_mass_assignment_reports_exploitable(mock_server):
    verdict = await _run_blueprint(
        mock_server, "mass_assignment", None, "/api/users/me", method="PATCH",
    )
    assert verdict["verdict"] == "exploitable", verdict


@pytest.mark.asyncio
async def test_crlf_injection_reports_exploitable(mock_server):
    verdict = await _run_blueprint(mock_server, "crlf_injection", "redirect", "/go")
    assert verdict["verdict"] == "exploitable", verdict


if __name__ == "__main__":
    import subprocess
    sys.exit(subprocess.call([sys.executable, "-m", "pytest", "-xvs", __file__]))
