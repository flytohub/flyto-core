from __future__ import annotations

from pathlib import Path

import pytest
from aiohttp import web

from core.runtime.capability_bridge import (
    BRIDGE_TOKEN_HEADER,
    EXECUTION_SCHEMA,
    FlytoRuntimeBridgeError,
    FlytoRuntimeCapabilityClient,
)

TOKEN = "test-token-abcdefghijklmnopqrstuvwxyz-0123456789"


async def _start_bridge(handler):
    app = web.Application()
    app.router.add_get("/flyto2/capabilities/v1/manifest", handler.manifest)
    app.router.add_post("/flyto2/capabilities/v1/invoke", handler.invoke)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    sockets = site._server.sockets  # aiohttp exposes the bound ephemeral port here.
    port = sockets[0].getsockname()[1]
    return runner, f"http://127.0.0.1:{port}"


class _BridgeHandler:
    def __init__(self) -> None:
        self.calls = []
        self.delegate_calls = 0
        self.wait_calls = 0

    def _authorized(self, request: web.Request) -> bool:
        return request.headers.get(BRIDGE_TOKEN_HEADER) == TOKEN

    async def manifest(self, request: web.Request) -> web.Response:
        if not self._authorized(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        return web.json_response(
            {
                "schema": EXECUTION_SCHEMA,
                "product": "Flyto2",
                "runtime": "flyto-runtime",
                "runtime_version": "1.1.4",
                "runtime_id": "rt_test",
                "display_name": "test runtime",
                "platform": "test",
                "roles": ["executes_jobs"],
                "capabilities": [
                    {
                        "id": "agent.delegate",
                        "revision": 1,
                        "risk_level": "high",
                        "approval": "explicit",
                        "evidence": ["agent"],
                    },
                    {
                        "id": "agent.wait",
                        "revision": 1,
                        "risk_level": "low",
                        "approval": "none",
                        "evidence": ["agent"],
                    },
                ],
            }
        )

    async def invoke(self, request: web.Request) -> web.Response:
        if not self._authorized(request):
            return web.json_response({"secret": "must-not-leak"}, status=401)
        body = await request.json()
        self.calls.append(body)
        if body["capability"] == "agent.wait":
            self.wait_calls += 1
            if self.wait_calls == 1:
                return web.json_response(_accepted(body))
            return web.json_response(_success(body, {"status": "completed"}))
        self.delegate_calls += 1
        if self.delegate_calls == 1:
            return web.json_response(_accepted(body))
        return web.json_response(_success(body, {"status": "idle", "response": "done"}))


def _accepted(invocation):
    return {
        "schema": EXECUTION_SCHEMA,
        "invocation_id": invocation["invocation_id"],
        "capability": invocation["capability"],
        "revision": invocation["revision"],
        "status": "accepted",
        "started_at": "2026-09-30T00:00:00Z",
        "output": {"agent_id": "agt_test", "status": "running"},
        "evidence": [],
        "operation": {
            "kind": "agent",
            "ref": "agt_test",
            "state": "running",
            "wait": {
                "capability": "agent.wait",
                "input": {"workspace_id": "ws_test", "agent_id": "agt_test"},
            },
        },
    }


def _success(invocation, output):
    return {
        "schema": EXECUTION_SCHEMA,
        "invocation_id": invocation["invocation_id"],
        "capability": invocation["capability"],
        "revision": invocation["revision"],
        "status": "success",
        "started_at": "2026-09-30T00:00:00Z",
        "completed_at": "2026-09-30T00:00:01Z",
        "output": output,
        "evidence": [],
    }


@pytest.mark.asyncio
async def test_manifest_and_nested_accepted_followups_close_over_wire_contract():
    handler = _BridgeHandler()
    runner, origin = await _start_bridge(handler)
    try:
        async with FlytoRuntimeCapabilityClient(TOKEN, base_url=origin) as client:
            manifest = await client.manifest()
            assert manifest.supports("agent.delegate")
            result = await client.invoke_until_terminal(
                "agent.delegate",
                {
                    "workspace_id": "ws_test",
                    "target": "codex",
                    "prompt": "Inspect the repository.",
                },
                operation_id="core-operation-agent-1",
                invocation_id="core-invocation-agent-1",
                workspace_id="ws_test",
            )
        assert result.status == "success"
        assert result.output["response"] == "done"
        assert [call["capability"] for call in handler.calls] == [
            "agent.delegate",
            "agent.wait",
            "agent.wait",
            "agent.delegate",
        ]
        assert handler.calls[0]["operation_id"] == handler.calls[3]["operation_id"]
        assert all(call["workspace_id"] == "ws_test" for call in handler.calls)
    finally:
        await runner.cleanup()


def test_client_rejects_non_loopback_runtime_bridge():
    with pytest.raises(ValueError, match="loopback"):
        FlytoRuntimeCapabilityClient(
            TOKEN,
            base_url="http://api.flyto2.com/flyto2/capabilities/v1",
        )


def test_token_file_is_explicit_runtime_input(tmp_path: Path):
    token_file = tmp_path / "runtime.token"
    token_file.write_text(f"{TOKEN}\n", encoding="utf-8")
    client = FlytoRuntimeCapabilityClient.from_token_file(token_file)
    assert "test-token" not in repr(client)


@pytest.mark.asyncio
async def test_transport_error_does_not_echo_response_body_secret():
    async def manifest(_request: web.Request) -> web.Response:
        return web.json_response({"password": "super-secret"}, status=401)

    app = web.Application()
    app.router.add_get("/flyto2/capabilities/v1/manifest", manifest)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    try:
        async with FlytoRuntimeCapabilityClient(
            TOKEN,
            base_url=f"http://127.0.0.1:{port}",
        ) as client:
            with pytest.raises(FlytoRuntimeBridgeError) as exc:
                await client.manifest()
        assert "super-secret" not in str(exc.value)
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_bridge_never_follows_redirect_with_same_user_token():
    leaked_headers = []

    async def redirected_manifest(request: web.Request) -> web.Response:
        leaked_headers.append(request.headers.get(BRIDGE_TOKEN_HEADER))
        return web.json_response({"error": "token forwarded"}, status=401)

    receiver = web.Application()
    receiver.router.add_get("/capture", redirected_manifest)
    receiver_runner = web.AppRunner(receiver)
    await receiver_runner.setup()
    receiver_site = web.TCPSite(receiver_runner, "127.0.0.1", 0)
    await receiver_site.start()
    receiver_port = receiver_site._server.sockets[0].getsockname()[1]

    async def redirect(_request: web.Request) -> web.Response:
        raise web.HTTPFound(location=f"http://127.0.0.1:{receiver_port}/capture")

    origin = web.Application()
    origin.router.add_get("/flyto2/capabilities/v1/manifest", redirect)
    origin_runner = web.AppRunner(origin)
    await origin_runner.setup()
    origin_site = web.TCPSite(origin_runner, "127.0.0.1", 0)
    await origin_site.start()
    origin_port = origin_site._server.sockets[0].getsockname()[1]

    try:
        async with FlytoRuntimeCapabilityClient(
            TOKEN, base_url=f"http://127.0.0.1:{origin_port}"
        ) as client:
            with pytest.raises(FlytoRuntimeBridgeError, match="HTTP 302"):
                await client.manifest()
        assert leaked_headers == []
    finally:
        await origin_runner.cleanup()
        await receiver_runner.cleanup()
