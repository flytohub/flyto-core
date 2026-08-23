# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""The outbound guard must not depend on which HTTP client happens to be installed.

Every `httpx.AsyncClient` call site in this package sat behind
`try: import httpx / except ImportError:` with a guarded aiohttp fallback. So the
SSRF posture of a deployment was decided by whether some *other* package had
pulled httpx in: an environment with `openai` installed ran twelve unguarded
call sites, one without ran the guarded twin, and nothing anywhere said so. The
guard-coverage test could not see it either - it matches source references to
guard symbols, and `llm.chat` does call `validate_url_with_env_config(base_url)`;
what it never checked was whether the connection then went through a guarded
transport.

Two invariants are pinned here.
"""
import re
import socket
from pathlib import Path

import pytest

from core.utils import DEFAULT_ALLOWED_PORTS, SSRFError, guarded_httpx_client

SRC = Path(__file__).resolve().parents[2] / "src"
UTILS = SRC / "core" / "utils.py"
ASYNC_CLIENT = re.compile(r"\bhttpx\.AsyncClient\(")


def test_no_module_constructs_an_unguarded_httpx_client():
    """`httpx.AsyncClient(` belongs to `guarded_httpx_client` and nowhere else.

    Narrow on purpose. It does not claim every outbound call in the package is
    guarded - forty `aiohttp.ClientSession(` constructions remain, most of them
    to fixed vendor endpoints that take no caller-supplied host. It claims the
    one thing that was actually false: that the httpx path and the aiohttp path
    enforce the same policy.
    """
    offenders = []
    for path in sorted(SRC.rglob("*.py")):
        if path == UTILS:
            continue
        for number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if ASYNC_CLIENT.search(line) and not line.lstrip().startswith("#"):
                offenders.append(f"{path.relative_to(SRC)}:{number}")
    assert not offenders, (
        "construct httpx clients through core.utils.guarded_httpx_client so the "
        "httpx path enforces the same SSRF policy as the aiohttp path: "
        + ", ".join(offenders)
    )


def test_guarded_httpx_client_refuses_a_metadata_target():
    client = guarded_httpx_client()
    transport = client._transport
    with pytest.raises(SSRFError):
        _resolve_through(transport, "169.254.169.254", 80)


def test_guarded_httpx_client_refuses_a_private_target():
    client = guarded_httpx_client()
    transport = client._transport
    with pytest.raises(SSRFError):
        _resolve_through(transport, "10.0.0.5", 80)


def test_guarded_httpx_client_allows_a_public_target():
    client = guarded_httpx_client()
    transport = client._transport
    assert _resolve_through(transport, "93.184.216.34", 443) == "93.184.216.34"


def _resolve_through(transport, host, port):
    """Drive the transport's own resolution step without opening a socket."""
    import asyncio

    from core.utils import _guarded_resolve

    assert transport.__class__.__name__ == "_GuardedTransport", (
        "guarded_httpx_client must install the guarding transport"
    )
    return asyncio.run(_guarded_resolve(host, port))


def test_ollama_port_is_added_to_the_policy_and_only_that_port():
    """The remote-Ollama fix must not silently widen the port policy.

    `ai.local_ollama.chat` adds Ollama's own port so a real remote host stays
    reachable; a security fix that removes the feature it is protecting is not a
    fix. Nothing else moves - 11434 is added, 22 is not.
    """
    from core.constants import OLLAMA_DEFAULT_PORT

    assert OLLAMA_DEFAULT_PORT not in DEFAULT_ALLOWED_PORTS
    widened = set(DEFAULT_ALLOWED_PORTS) | {OLLAMA_DEFAULT_PORT}
    assert 22 not in widened
    assert widened - DEFAULT_ALLOWED_PORTS == {OLLAMA_DEFAULT_PORT}


class TestLocalOllamaRemoteFlag:
    """`FLYTO_ALLOW_REMOTE_OLLAMA=true` must widen the host, not remove the guard.

    The module carried an outbound-guard exemption reading "restricts to loopback
    inline, which is stricter than the shared guard". That was true only while the
    flag was unset; with the documented flag on, `validate_params` returned with no
    check at all and `execute` opened a bare `aiohttp.ClientSession`, so a
    caller-supplied `ollama_url` reached cloud metadata and any RFC1918 address
    with the response body handed back. The agent path already refused the same
    input - see `test_agent_ollama_blocks_metadata_even_when_remote_is_enabled`.
    """

    @staticmethod
    def _module(url):
        import core.modules  # noqa: F401  (registers the catalogue)
        from core.modules.registry import ModuleRegistry

        return ModuleRegistry.get("ai.local_ollama.chat")(
            {"prompt": "x", "ollama_url": url}, {}
        )

    def test_metadata_endpoint_is_refused_with_the_flag_on(self, monkeypatch):
        monkeypatch.setenv("FLYTO_ALLOW_REMOTE_OLLAMA", "true")
        with pytest.raises(SSRFError):
            self._module("http://169.254.169.254:11434")

    def test_private_address_is_refused_with_the_flag_on(self, monkeypatch):
        monkeypatch.setenv("FLYTO_ALLOW_REMOTE_OLLAMA", "true")
        with pytest.raises(SSRFError):
            self._module("http://10.0.0.5:11434")

    def test_loopback_still_works_with_the_flag_off(self, monkeypatch):
        monkeypatch.delenv("FLYTO_ALLOW_REMOTE_OLLAMA", raising=False)
        assert self._module("http://127.0.0.1:11434") is not None

    def test_remote_host_is_refused_with_the_flag_off(self, monkeypatch):
        monkeypatch.delenv("FLYTO_ALLOW_REMOTE_OLLAMA", raising=False)
        with pytest.raises(ValueError):
            self._module("http://10.0.0.5:11434")

    def test_a_reachable_public_host_on_ollamas_port_is_not_refused_for_its_port(
        self, monkeypatch
    ):
        """The feature survives the fix: 11434 itself must not be the refusal."""
        monkeypatch.setenv("FLYTO_ALLOW_REMOTE_OLLAMA", "true")
        try:
            socket.gethostbyname("example.com")
        except OSError:  # pragma: no cover - offline runner
            pytest.skip("no DNS available to exercise a public host")
        try:
            self._module("http://example.com:11434")
        except SSRFError as error:  # pragma: no cover - defensive
            assert "Port" not in str(error), (
                "Ollama's own port must be allowed once remote Ollama is enabled"
            )
