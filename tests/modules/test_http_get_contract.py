"""Regression tests for the public ``http.get`` output contract."""

import importlib
from contextlib import asynccontextmanager

import pytest


class FakeResponse:
    """Minimal successful response for the HTTP module."""

    status = 200
    headers = {"Content-Type": "application/json", "X-Test": "present"}

    def __init__(self) -> None:
        self.released = False

    async def json(self) -> dict[str, str]:
        return {"message": "ok"}

    async def text(self) -> str:
        return "unused"

    def release(self) -> None:
        self.released = True


@pytest.mark.asyncio
async def test_http_get_success_matches_declared_output_schema(monkeypatch) -> None:
    """Successful responses expose each field declared by the module schema."""
    http_get_module = importlib.import_module("core.modules.atomic.http.get")
    response = FakeResponse()

    @asynccontextmanager
    async def fake_session(**_kwargs):
        yield object()

    async def fake_request(*_args, **_kwargs):
        return response

    monkeypatch.setattr(http_get_module, "guarded_client_session", fake_session)
    monkeypatch.setattr(
        http_get_module,
        "guarded_aiohttp_request",
        fake_request,
    )
    monkeypatch.setattr(
        http_get_module,
        "ssrf_protection_enabled",
        lambda: False,
    )

    result = await http_get_module.http_get(
        {"url": "https://example.com/data"},
        {},
    ).execute()

    assert result == {
        "ok": True,
        "status": 200,
        "body": {"message": "ok"},
        "headers": {
            "Content-Type": "application/json",
            "X-Test": "present",
        },
        "data": {
            "status": 200,
            "body": {"message": "ok"},
            "headers": {
                "Content-Type": "application/json",
                "X-Test": "present",
            },
        },
    }
    assert response.released is True
