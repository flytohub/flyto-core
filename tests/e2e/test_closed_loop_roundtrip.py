"""E2E — closed-loop verify round trip.

Drives the SQL injection + auth bypass blueprints end-to-end without docker:

  1. Spin up a local HTTP mock that simulates a vulnerable endpoint.
  2. Build a SecurityFinding (same shape flyto-engine emits).
  3. Walk the blueprint's YAML steps directly against the mock, calling the
     real flyto-core modules (http.batch, test.assert_status, test.assert_timing,
     test.assert_contains).
  4. Feed the collected step outputs into flyto-cloud's verdict aggregator and
     assert we get the expected verdict.

This proves the exact chain that flyto-engine → flyto-cloud → worker would
follow in production, minus the network + firestore hops.
"""
from __future__ import annotations

import asyncio
import http.server
import importlib.util
import socketserver
import sys
import threading
import time
import urllib.parse
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
CORE_SRC = REPO_ROOT / "flyto-core" / "src"
AI_ROOT = REPO_ROOT / "flyto-ai"
CLOUD_BACKEND = REPO_ROOT / "flyto-cloud" / "src" / "ui" / "web" / "backend"

for p in (str(CORE_SRC), str(AI_ROOT), str(CLOUD_BACKEND)):
    if p not in sys.path:
        sys.path.insert(0, p)


# ---------------------------------------------------------------------------
# Mock HTTP target
# ---------------------------------------------------------------------------

class _VulnHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args, **kwargs):  # silence
        return

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(parsed.query)

        # SQL endpoint — vulnerable to injection: any single-quote + OR echoes
        # a realistic MySQL error message in the response body.
        if parsed.path == "/api/users":
            payload = q.get("user_id", [""])[0]
            if "'" in payload and "OR" in payload.upper():
                body = (
                    "You have an error in your SQL syntax; check the manual "
                    "that corresponds to your MySQL server version"
                )
                return self._send(500, body)
            if "WAITFOR" in payload.upper():
                time.sleep(3.2)  # simulate time-based blind
                return self._send(200, '{"rows": []}')
            return self._send(200, '{"rows": []}')

        if parsed.path == "/api/protected":
            # Only a specific well-formed token is accepted — every tampered
            # variant (missing, empty, alg:none forgery, swapped) gets 403.
            auth = self.headers.get("Authorization") or ""
            if auth == "Bearer real-valid-token":
                return self._send(200, "ok")
            return self._send(403, "forbidden")

        return self._send(404, "nope")

    def _send(self, status: int, body: str):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json" if body.startswith("{") else "text/plain")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture(scope="module")
def mock_server():
    server = socketserver.TCPServer(("127.0.0.1", 0), _VulnHandler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


# ---------------------------------------------------------------------------
# Real module execution — replays the blueprint's steps against flyto-core
# ---------------------------------------------------------------------------

def _load_modules():
    """Import the three new flyto-core modules so their decorators register."""
    import importlib
    from core.modules.registry import ModuleRegistry

    importlib.import_module("core.modules.atomic.http.batch")
    importlib.import_module("core.modules.atomic.testing.assert_status")
    importlib.import_module("core.modules.atomic.testing.assert_timing")
    importlib.import_module("core.modules.atomic.testing.assert_contains")
    return ModuleRegistry


async def _run_step(module_id: str, params: dict) -> dict:
    """Instantiate + execute a single flyto-core module."""
    from core.modules.registry import get_module

    module_cls = get_module(module_id)
    assert module_cls is not None, f"{module_id} not registered"
    instance = module_cls(params=params, context={})
    return await instance.execute()


def _load_verdict_aggregator():
    """Load flyto-cloud's _compute_verdict without importing its FastAPI app.

    verify.py hard-imports fastapi/pydantic/gateway.auth at module load, so we
    stub those before exec'ing the file. This keeps the e2e's dep surface
    minimal while still exercising the real aggregator code.
    """
    from unittest.mock import MagicMock

    for name in ("gateway", "gateway.auth", "fastapi", "pydantic"):
        if name not in sys.modules:
            sys.modules[name] = MagicMock()

    # Pydantic's BaseModel/Field must be subclassable and callable for the
    # module-level class definitions to work.
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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sqli_round_trip_reports_exploitable(mock_server):
    """SQL injection blueprint against a vulnerable mock → verdict=exploitable."""
    _load_modules()

    base = mock_server
    # Replay the sql_injection blueprint's key steps directly.
    probes = [
        {"method": "GET", "url": f"{base}/api/users?user_id=1", "label": "baseline"},
        {"method": "GET", "url": f"{base}/api/users?user_id=' OR '1'='1", "label": "classic"},
        {"method": "GET", "url": f"{base}/api/users?user_id=' ; WAITFOR DELAY '00:00:03", "label": "time_based"},
    ]
    batch_out = await _run_step("http.batch", {
        "requests": probes,
        "measure_time": True,
        "timeout": 15,
        "ssrf_protection": False,
        "detect_patterns": ["SQL syntax", "mysql_fetch", "ORA-"],
    })
    assert batch_out["ok"], batch_out
    # Pattern match on the classic probe body
    detected = batch_out.get("detected", [])
    assert any(d["matches"] for d in detected), detected

    # assert_contains with new verdict-mode params
    pattern_assert = await _run_step("test.assert_contains", {
        "source": batch_out,
        "patterns": ["SQL syntax", "mysql_fetch"],
        "match_mode": "any",
        "on_match": "exploitable",
        "on_no_match": "sanitized",
    })

    # assert_timing on the slow probe
    timing_assert = await _run_step("test.assert_timing", {
        "source": batch_out,
        "baseline_index": 0,
        "probe_index": 2,
        "threshold_ms": 2000,
        "on_slow": "exploitable",
        "on_normal": "inconclusive",
    })

    # Aggregate the per-step outputs — simulates what the worker writes into
    # ExecutionJob.streaming_context, then what GET /status reads.
    streaming_context = {
        "sql_probes": batch_out,
        "assert_sqli": pattern_assert,
        "assert_timing": timing_assert,
    }
    compute_verdict = _load_verdict_aggregator()
    verdict_result = compute_verdict(streaming_context)

    assert verdict_result["verdict"] == "exploitable", verdict_result
    # Either pattern or timing should have decided it
    assert verdict_result["decided_by"] in ("assert_sqli", "assert_timing"), verdict_result


@pytest.mark.asyncio
async def test_auth_bypass_round_trip_reports_sanitized(mock_server):
    """Auth bypass blueprint against a properly-guarded endpoint → sanitized."""
    _load_modules()

    base = mock_server
    # All tampered probes are rejected with 403 by the mock → sanitized
    probes = [
        {"method": "GET", "url": f"{base}/api/protected",
         "headers": {"Authorization": "Bearer real-valid-token"}, "label": "baseline"},
        {"method": "GET", "url": f"{base}/api/protected", "headers": {}, "label": "no_auth"},
        {"method": "GET", "url": f"{base}/api/protected",
         "headers": {"Authorization": ""}, "label": "empty_auth"},
        {"method": "GET", "url": f"{base}/api/protected",
         "headers": {"Authorization": "Bearer eyJhbGciOiJub25lIn0.ABC."}, "label": "alg_none"},
        {"method": "GET", "url": f"{base}/api/protected",
         "headers": {"Authorization": "Bearer aaaa-bbbb-cccc"}, "label": "swap"},
    ]
    batch_out = await _run_step("http.batch", {
        "requests": probes, "timeout": 10, "ssrf_protection": False,
    })

    status_assert = await _run_step("test.assert_status", {
        "source": batch_out,
        "baseline_index": 0,
        "probe_indices": [1, 2, 3, 4],
        "expected_blocked": [401, 403],
        "on_bypass": "exploitable",
        "on_blocked": "sanitized",
    })

    streaming_context = {
        "auth_probes": batch_out,
        "assert_bypass": status_assert,
    }
    verdict_result = _load_verdict_aggregator()(streaming_context)
    assert verdict_result["verdict"] == "sanitized", verdict_result


if __name__ == "__main__":
    # Allow running as: python test_closed_loop_roundtrip.py
    import subprocess
    sys.exit(subprocess.call([sys.executable, "-m", "pytest", "-xvs", __file__]))
