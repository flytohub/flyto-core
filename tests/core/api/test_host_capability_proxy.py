from __future__ import annotations

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from starlette.testclient import TestClient

from core.api.host_capability import HostCapabilityProxy, validate_host_capability_endpoint
from core.api.server import create_app


class _Handler(BaseHTTPRequestHandler):
    token = ""
    requests: list[dict] = []

    def do_POST(self):  # noqa: N802
        if self.headers.get("Authorization") != f"Bearer {self.token}":
            self.send_response(401)
            self.end_headers()
            return
        size = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(size))
        type(self).requests.append(body)
        payload = json.dumps(
            {
                "outcome": "completed",
                "detail": "",
                "adapter_id": "test.loopback",
                "commanded_resource_id": body["request"]["resource_id"],
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_args):
        return


@pytest.fixture
def host_dispatch():
    token = "t" * 48
    _Handler.token = token
    _Handler.requests = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/internal/capability", token
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_host_proxy_accepts_only_literal_loopback():
    assert (
        validate_host_capability_endpoint("http://127.0.0.1:9999/internal/capability")
        == "http://127.0.0.1:9999/internal/capability"
    )
    for value in (
        "http://localhost:9999/internal/capability",
        "http://192.168.1.5:9999/internal/capability",
        "https://127.0.0.1:9999/internal/capability",
        "http://127.0.0.1/internal/capability",
    ):
        with pytest.raises(ValueError):
            validate_host_capability_endpoint(value)


def test_host_proxy_forwards_only_capability_request(host_dispatch):
    endpoint, token = host_dispatch
    proxy = HostCapabilityProxy(endpoint=endpoint, token=token)

    result = asyncio.run(
        proxy.invoke(
            {
                "resource_id": "robot-1",
                "capability_id": "motion.halt",
                "arguments": {},
            }
        )
    )

    assert result["outcome"] == "completed"
    assert _Handler.requests == [
        {
            "request": {
                "resource_id": "robot-1",
                "capability_id": "motion.halt",
                "arguments": {},
            }
        }
    ]


def test_workflow_api_injects_host_authority_without_putting_it_in_workflow(host_dispatch):
    endpoint, token = host_dispatch
    app = create_app()
    from core.api import security as sec

    workflow = {
        "id": "host-capability-proxy-test",
        "name": "Host capability proxy test",
        "steps": [
            {
                "id": "invoke",
                "module": "capability.invoke",
                "params": {
                    "resource_id": "robot-1",
                    "capability_id": "motion.halt",
                    "arguments": {},
                },
            }
        ],
    }
    with TestClient(app) as client:
        response = client.post(
            "/v1/workflow/run",
            headers={
                "Authorization": f"Bearer {sec._active_token}",
                "X-Flyto-Host-Capability-Endpoint": endpoint,
                "X-Flyto-Host-Capability-Token": token,
                "X-Flyto-Host-Capability-Timeout": "5",
            },
            json={
                "workflow": workflow,
                "enable_evidence": False,
                "enable_trace": False,
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["status"] == "completed"
    assert token not in json.dumps(body)
    assert token not in json.dumps(workflow)
    assert _Handler.requests[-1]["request"]["capability_id"] == "motion.halt"
