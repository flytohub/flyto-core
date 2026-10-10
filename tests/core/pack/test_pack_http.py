"""The http binding: endpoint from host configuration, locality-checked, no redirects."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from pack_helpers import write_pack

from core.modules.registry import ModuleRegistry
from core.pack.host import install_pack

HTTP_RUNTIME = {"binding": "http", "locality": "same_host", "request_timeout_ms": 5000}


class Handler(BaseHTTPRequestHandler):
    seen = []
    mode = "ok"

    def log_message(self, *args):
        return None

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length))
        Handler.seen.append({"path": self.path, "auth": self.headers.get("Authorization"), "body": body})
        if Handler.mode == "redirect":
            self.send_response(307)
            self.send_header("Location", "http://169.254.169.254/latest")
            self.end_headers()
            return
        if Handler.mode == "no-version":
            payload = {"ok": True, "data": 1}
        else:
            payload = {"contract_version": "flyto.pack.v1", "ok": True, "data": {"echo": body["params"]}}
        raw = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


@pytest.fixture
def server():
    Handler.seen = []
    Handler.mode = "ok"
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


@pytest.fixture
def http_pack(tmp_path):
    pack, _ = write_pack(tmp_path / "p", runtime=HTTP_RUNTIME)
    install_pack(pack, require_signature=False)
    return pack


async def run(params):
    return await ModuleRegistry.get("fake.echo")(params, {"secrets": {"x": "y"}}).run()


async def test_http_pack_round_trip(server, http_pack, monkeypatch):
    monkeypatch.setenv("FLYTO_PLUGIN_ENDPOINT__FAKE", server)
    monkeypatch.setenv("FLYTO_PLUGIN_TOKEN__FAKE", "tok-123")
    result = await run({"text": "hi"})
    assert result == {"ok": True, "data": {"echo": {"text": "hi"}}}
    request = Handler.seen[-1]
    assert request["path"] == "/v1/invoke"
    assert request["auth"] == "Bearer tok-123"
    assert request["body"]["contract_version"] == "flyto.pack.v1"
    assert request["body"]["context"] == {"pack_id": "com.example.fake", "module_id": "fake.echo"}


async def test_missing_endpoint_is_a_failure(http_pack, monkeypatch):
    monkeypatch.delenv("FLYTO_PLUGIN_ENDPOINT__FAKE", raising=False)
    result = await run({"text": "hi"})
    assert result["ok"] is False and result["error_code"] == "ENDPOINT_MISSING"


async def test_same_host_refuses_a_remote_endpoint(http_pack, monkeypatch):
    monkeypatch.setenv("FLYTO_PLUGIN_ENDPOINT__FAKE", "http://10.0.0.5:8080")
    result = await run({"text": "hi"})
    assert result["ok"] is False and result["error_code"] == "LOCALITY_DENIED"


async def test_redirects_are_not_followed(server, http_pack, monkeypatch):
    monkeypatch.setenv("FLYTO_PLUGIN_ENDPOINT__FAKE", server)
    Handler.mode = "redirect"
    result = await run({"text": "hi"})
    assert result["ok"] is False
    assert len(Handler.seen) == 1


async def test_reply_must_name_the_contract_version(server, http_pack, monkeypatch):
    monkeypatch.setenv("FLYTO_PLUGIN_ENDPOINT__FAKE", server)
    Handler.mode = "no-version"
    result = await run({"text": "hi"})
    assert result["ok"] is False and result["error_code"] == "PROTOCOL_ERROR"
