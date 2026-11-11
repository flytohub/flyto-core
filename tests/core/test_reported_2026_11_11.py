# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Regression tests for the reports closed on 2026-11-11.

- GHSA-3j3m-rp8w-pxpv: image.download followed a redirect to an internal
  IP literal, and every guarded aiohttp session let IP literals skip the
  connect-time resolver.
- #152: agent.tool_use reported provider-truncated replies as accepted and
  ran their (partial) tool calls.
- #151: core.api.google_search could only reach the discontinued Google
  endpoint.
"""

import asyncio
import json

import pytest
from aiohttp import web

import core.utils as core_utils
from core.engine.outcome import Outcome, read_envelope
from core.modules import (
    atomic,  # noqa: F401
    third_party,  # noqa: F401
)
from core.modules.registry import ModuleRegistry
from core.utils import SSRFError, _check_literal_connect_target, guarded_client_session


def _run(module_id, params, context=None):
    module = ModuleRegistry.get(module_id)
    return asyncio.run(module(params, context or {}).execute())


def _envelope(result):
    body = result.get("data") if isinstance(result.get("data"), dict) else result
    return read_envelope(body)


@pytest.fixture
def strict_ssrf(monkeypatch):
    for name in ("FLYTO_ALLOW_PRIVATE_NETWORK", "FLYTO_VSCODE_LOCAL_MODE",
                 "FLYTO_HTTP_DISABLE_SSRF_GUARD"):
        monkeypatch.delenv(name, raising=False)


# ===========================================================================
# GHSA-3j3m-rp8w-pxpv
# ===========================================================================


@pytest.mark.parametrize("host", [
    "::ffff:127.0.0.1", "[::ffff:127.0.0.1]", "127.0.0.1", "169.254.169.254",
    "10.0.0.1", "::1",
])
def test_literal_private_targets_are_refused(strict_ssrf, monkeypatch, host):
    monkeypatch.delenv("FLYTO_ALLOWED_HOSTS", raising=False)
    with pytest.raises(SSRFError):
        _check_literal_connect_target(host)


def test_hostnames_and_public_literals_are_left_to_the_resolver(strict_ssrf):
    _check_literal_connect_target("example.com")
    _check_literal_connect_target("93.184.216.34")


def test_metadata_literal_is_refused_even_when_private_is_allowed(monkeypatch):
    monkeypatch.setenv("FLYTO_ALLOW_PRIVATE_NETWORK", "true")
    _check_literal_connect_target("127.0.0.1")
    with pytest.raises(SSRFError):
        _check_literal_connect_target("169.254.169.254")


def test_guarded_session_refuses_a_redirect_hop_to_an_ip_literal(strict_ssrf, monkeypatch):
    """The advisory's chain, end to end through real aiohttp: an allowed host
    redirects to ``[::ffff:127.0.0.1]``, which the resolver never sees."""
    monkeypatch.setenv("FLYTO_ALLOWED_HOSTS", "localhost")
    hits = {"internal": 0}

    async def scenario():
        async def internal(request):
            hits["internal"] += 1
            return web.Response(text="secret")

        internal_app = web.Application()
        internal_app.router.add_get("/", internal)
        internal_runner = web.AppRunner(internal_app)
        await internal_runner.setup()
        internal_site = web.TCPSite(internal_runner, "127.0.0.1", 0)
        await internal_site.start()
        internal_port = internal_site._server.sockets[0].getsockname()[1]

        async def redirect(request):
            raise web.HTTPFound(f"http://[::ffff:127.0.0.1]:{internal_port}/")

        redir_app = web.Application()
        redir_app.router.add_get("/redir", redirect)
        redir_runner = web.AppRunner(redir_app)
        await redir_runner.setup()
        redir_site = web.TCPSite(redir_runner, "127.0.0.1", 0)
        await redir_site.start()
        redir_port = redir_site._server.sockets[0].getsockname()[1]
        try:
            async with guarded_client_session() as session:
                with pytest.raises(SSRFError):
                    async with session.get(f"http://localhost:{redir_port}/redir"):
                        pass
        finally:
            await redir_runner.cleanup()
            await internal_runner.cleanup()

    asyncio.run(scenario())
    assert hits["internal"] == 0


def test_image_download_revalidates_each_redirect_hop(strict_ssrf, monkeypatch, tmp_path):
    """image.download must go through guarded_aiohttp_request, which re-runs
    the full URL policy on every Location."""
    monkeypatch.setenv("FLYTO_SANDBOX_DIR", str(tmp_path))
    import core.modules.atomic.image.download as download

    class _Resp:
        status = 302
        headers = {"Location": "http://[::ffff:127.0.0.1]:8080/"}

        def release(self):
            pass

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def request(self, method, url, **kwargs):
            assert kwargs.get("allow_redirects") is False
            return _Resp()

    monkeypatch.setattr(download, "guarded_client_session", lambda **kw: _Session())
    monkeypatch.setattr(download, "validate_url_with_env_config", lambda url: url)
    real_validate = core_utils.validate_url_with_env_config
    seen = []

    def spy(url):
        seen.append(url)
        if "127.0.0.1" in url:
            return real_validate(url)
        return url

    monkeypatch.setattr(core_utils, "validate_url_with_env_config", spy)

    result = _run("image.download", {
        "url": "http://public.example/redir.png",
        "output_path": str(tmp_path / "x.png"),
    })
    assert result["ok"] is False
    assert result["error_code"] == "SSRF_BLOCKED"
    assert any("127.0.0.1" in u for u in seen)
    assert not (tmp_path / "x.png").exists()


# ===========================================================================
# #152 agent.tool_use
# ===========================================================================


class _Resp:
    def __init__(self, payload):
        self._payload = payload
        self.status = 200

    async def json(self):
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _session(responses, sent):
    class _S:
        def __init__(self, *a, **k):
            self._queue = list(responses)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        def post(self, url, **kwargs):
            sent.append(kwargs.get("json"))
            return _Resp(self._queue.pop(0))

    return _S


def _agent(monkeypatch, provider, responses, **params):
    import core.modules.third_party.ai.agents.tool_use as tool_use

    ran = []
    sent = []

    async def fake_execute_tool(name, args, ctx):
        ran.append((name, args))
        return {"ok": True, "data": {}}

    monkeypatch.setattr(tool_use, "execute_tool", fake_execute_tool)
    monkeypatch.setattr(tool_use.aiohttp, "ClientSession", _session(responses, sent))
    result = _run("agent.tool_use", {
        "prompt": "write the report",
        "tools": [{"name": "file--write", "description": "write"}],
        "provider": provider,
        "model": "m",
        "api_key": "k",
        **params,
    })
    return result, ran, sent


def _anthropic(stop_reason, content):
    return {"stop_reason": stop_reason, "content": content, "model": "m"}


def test_anthropic_max_tokens_with_tool_use_runs_nothing(monkeypatch):
    result, ran, sent = _agent(monkeypatch, "anthropic", [
        _anthropic("max_tokens", [
            {"type": "text", "text": "Writing it now."},
            {"type": "tool_use", "id": "t1", "name": "file--write",
             "input": {"path": "report.md", "content": "first third"}},
        ]),
        _anthropic("end_turn", [{"type": "text", "text": "The report is written."}]),
    ])
    assert ran == []
    assert len(sent) == 1
    env = _envelope(result)
    assert env["rung"] == Outcome.INDETERMINATE.value
    cut = next(e for e in env["effects"] if e["kind"] == "agent_reply_cut_off")
    assert cut["stop_reason"] == "max_tokens"
    assert cut["skipped_tool_calls"] == 1
    assert result["data"]["result"] == "Writing it now."


@pytest.mark.parametrize("reason", ["max_tokens", "refusal", "model_context_window_exceeded"])
def test_anthropic_cut_off_text_is_not_accepted(monkeypatch, reason):
    result, _, _ = _agent(monkeypatch, "anthropic", [
        _anthropic(reason, [{"type": "text", "text": "Step two is to"}]),
    ])
    assert _envelope(result)["rung"] == Outcome.INDETERMINATE.value


def test_anthropic_max_tokens_is_configurable(monkeypatch):
    _, _, sent = _agent(monkeypatch, "anthropic", [
        _anthropic("end_turn", [{"type": "text", "text": "done"}]),
    ], max_tokens=16000)
    assert sent[0]["max_tokens"] == 16000


def test_anthropic_end_turn_is_still_accepted(monkeypatch):
    result, _, _ = _agent(monkeypatch, "anthropic", [
        _anthropic("end_turn", [{"type": "text", "text": "done"}]),
    ])
    assert _envelope(result)["rung"] == Outcome.ACCEPTED.value


def _openai(finish_reason, content=None, tool_calls=None):
    message = {"role": "assistant", "content": content}
    if tool_calls is not None:
        message["tool_calls"] = tool_calls
    return {"choices": [{"message": message, "finish_reason": finish_reason}], "model": "m"}


@pytest.mark.parametrize("reason", ["length", "content_filter"])
def test_openai_cut_off_text_is_not_accepted(monkeypatch, reason):
    result, _, _ = _agent(monkeypatch, "openai", [_openai(reason, "Step two is to")])
    assert _envelope(result)["rung"] == Outcome.INDETERMINATE.value


def test_openai_length_inside_a_tool_call_runs_nothing(monkeypatch):
    result, ran, _ = _agent(monkeypatch, "openai", [
        _openai("length", tool_calls=[{
            "id": "c1", "function": {"name": "file--write", "arguments": '{"path": "rep'},
        }]),
        _openai("stop", "Done."),
    ])
    assert ran == []
    assert _envelope(result)["rung"] == Outcome.INDETERMINATE.value


def test_openai_unparseable_arguments_never_run_the_tool_with_empty_args(monkeypatch):
    result, ran, sent = _agent(monkeypatch, "openai", [
        _openai("tool_calls", tool_calls=[{
            "id": "c1", "function": {"name": "file--write", "arguments": '{"path": "rep'},
        }]),
        _openai("stop", "Done."),
    ])
    assert ran == []
    tool_msg = next(m for m in sent[1]["messages"] if m.get("role") == "tool")
    assert "not valid JSON" in json.loads(tool_msg["content"])["error"]
    assert _envelope(result)["rung"] == Outcome.ACCEPTED.value


# ===========================================================================
# #151 core.api.google_search
# ===========================================================================


def test_google_search_endpoint_follows_operator_setting(monkeypatch):
    from core.modules.third_party.developer.http import search

    monkeypatch.delenv("GOOGLE_SEARCH_URL", raising=False)
    assert search._google_search_url() == "https://www.googleapis.com/customsearch/v1"
    monkeypatch.setenv("GOOGLE_SEARCH_URL", "https://cse-compatible.example/customsearch/v1")
    assert search._google_search_url() == "https://cse-compatible.example/customsearch/v1"


def test_google_search_setup_error_names_the_discontinuation(monkeypatch):
    from core.modules.third_party.developer.http import search

    guide = search._google_search_setup_error()["setup_guide"]
    assert "2027-01-01" in guide["notice"]
    assert "GOOGLE_SEARCH_URL" in guide["step2"]
