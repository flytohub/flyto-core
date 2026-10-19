"""Pointing a standalone pack at a provider for local testing: ``--provider-base-url``.

A provider developing its pack runs the built zip against its recorded fake
(``flyto pack serve-fixtures``) before any real account exists. The override
replaces only where the signed manifest's ``base_url`` (and token URL) send
requests, for this run. It is loopback-only unless the SSRF allow-list
(``FLYTO_ALLOWED_HOSTS``) already names the host, and a loopback origin is
admitted for this one host and port only while the pack is open. Every
refusal comes before the pack is installed.
"""

import os

import pytest
from devkit_helpers import LOCK, decided_scaffold

from core.pack import host
from core.pack.manifest import PackManifestError
from core.pack.portable import build_portable_pack
from core.pack.recorded import serve_fixtures
from core.pack.standalone import health, load_standalone

TOKEN = "fixture-token-not-real"  # the scaffold fixture's test credential
GUARD_ENV = ("FLYTO_ALLOWED_HOSTS", "FLYTO_HTTP_ALLOWED_PORTS")


@pytest.fixture
def built(tmp_path, monkeypatch):
    monkeypatch.setenv("FLYTO_PACK_NO_KEYCHAIN", "1")
    monkeypatch.setenv("FLYTO_CREDENTIAL_ITEMS_API_TOKEN", TOKEN)
    for name in GUARD_ENV:
        monkeypatch.delenv(name, raising=False)
    source = decided_scaffold(tmp_path)
    out = tmp_path / "items.zip"
    build_portable_pack(source, out, lockfile=LOCK)
    return source, out


def guard_env():
    return {name: os.environ.get(name) for name in GUARD_ENV}


def test_health_against_the_recorded_fake_is_healthy(built):
    source, out = built
    with serve_fixtures(source) as url:
        report = health(out, require_signature=False, provider_base_url=url)
    assert report["healthy"] is True, report["problems"]
    assert report["entitled_tools"] == 2
    assert report["provider_base_url"] == url
    assert report["entitlements"]["source"] == "provider"


async def test_calls_go_to_the_override_and_the_guard_opening_is_closed_after(built):
    source, out = built
    before = guard_env()
    with serve_fixtures(source) as url:
        pack = load_standalone(out, transport="stdio", require_signature=False, provider_base_url=url)
        port = url.rsplit(":", 1)[1]
        try:
            assert port in os.environ["FLYTO_HTTP_ALLOWED_PORTS"].split(",")
            answer = await pack.dispatch({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                          "params": {"name": "items.item.get", "arguments": {"item": "item-1"}}})
        finally:
            await pack.close()
    assert answer["result"]["isError"] is False, answer
    assert answer["result"]["structuredContent"]["data"]["id"] == "item-1"
    assert guard_env() == before


def test_without_the_override_health_reports_the_manifest_base_url(built):
    _, out = built
    pack_report = load_standalone(out, transport="stdio", require_signature=False)
    try:
        assert pack_report.provider_base_url is None
    finally:
        import asyncio

        asyncio.run(pack_report.close())


@pytest.mark.parametrize("url, code", [
    ("http://10.0.0.5:8080", "PROVIDER_BASE_URL_REFUSED"),          # private, not loopback, not allow-listed
    ("https://api.elsewhere.example", "PROVIDER_BASE_URL_REFUSED"),  # public, not allow-listed
    ("http://api.elsewhere.example", "PROVIDER_BASE_URL_REFUSED"),   # where comes before how
    ("http://user:secret@127.0.0.1:9", "INLINE_SECRET"),
    ("http://127.0.0.1:9/v1?x=1", "INVALID_BASE_URL"),
    ("not a url", "INVALID_BASE_URL"),
])
def test_an_override_outside_loopback_or_the_allow_list_is_refused_before_install(built, url, code):
    _, out = built
    with pytest.raises(PackManifestError) as caught:
        load_standalone(out, transport="stdio", require_signature=False, provider_base_url=url)
    assert caught.value.code == code
    assert host._INSTALLED == {}
    assert guard_env() == dict.fromkeys(GUARD_ENV)


async def test_an_allow_listed_https_host_is_accepted_and_the_list_is_not_widened(built, monkeypatch):
    _, out = built
    monkeypatch.setenv("FLYTO_ALLOWED_HOSTS", "api.staging.example")
    pack = load_standalone(out, transport="stdio", require_signature=False,
                           provider_base_url="https://api.staging.example")
    try:
        assert pack.provider_base_url == "https://api.staging.example"
        assert os.environ["FLYTO_ALLOWED_HOSTS"] == "api.staging.example"
    finally:
        await pack.close()
    # Allow-listed is where; the scheme rule still holds: plain http only to loopback.
    with pytest.raises(PackManifestError) as caught:
        load_standalone(out, transport="stdio", require_signature=False, provider_base_url="http://api.staging.example")
    assert caught.value.code == "INVALID_BASE_URL"


def test_the_cli_flag_reaches_health(built, capsys):
    from devkit_helpers import cli

    source, out = built
    with serve_fixtures(source) as url:
        capsys.readouterr()
        code = cli("health", out, "--allow-unsigned", "--provider-base-url", url)
    assert code == 0, capsys.readouterr()


def test_serve_fixtures_answers_only_what_was_recorded(built):
    import json
    import urllib.error
    import urllib.request

    source, _ = built
    with serve_fixtures(source) as url:
        request = urllib.request.Request(url + "/v1/account/entitlements",
                                         headers={"Authorization": f"Bearer {TOKEN}"})
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310 - loopback fake
            assert json.loads(response.read()) == {"features": ["items"]}
        with pytest.raises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(urllib.request.Request(url + "/v1/account/entitlements"), timeout=10)  # noqa: S310
        assert caught.value.code == 401
