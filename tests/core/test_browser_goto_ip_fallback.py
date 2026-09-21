"""An unavailable IP destination must never become a different DNS hostname."""

import importlib
import socket
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import urlsplit

import pytest

from core.utils import validate_url_with_env_config

IP_URLS = (
    "http://127.0.0.1:8080/calendar",
    "https://8.8.8.8/calendar?day=today#events",
    "http://[::1]:8080/calendar",
    "https://[2001:4860:4860::8888]/calendar",
    "http://[::ffff:127.0.0.1]:8080/calendar",
    "http://[fe80::1%25en0]:8080/calendar",
)


def navigation_policy(monkeypatch, url):
    """Exercise the real guard with deterministic DNS and no external network."""
    host = urlsplit(url).hostname
    monkeypatch.setenv("FLYTO_ALLOWED_HOSTS", host)
    monkeypatch.setenv("FLYTO_HTTP_ALLOWED_PORTS", "8080")
    monkeypatch.delenv("FLYTO_ALLOW_PRIVATE_NETWORK", raising=False)
    monkeypatch.delenv("DEPLOYMENT_MODE", raising=False)
    resolved = []

    def resolve(name, *_args, **_kwargs):
        resolved.append(name)
        # A derived hostname must not become safe merely because it resolves
        # publicly. All answers are inert: no real socket is opened.
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    module = importlib.import_module("core.modules.atomic.browser.goto")
    checked = []

    def validate(target):
        checked.append(target)
        return validate_url_with_env_config(target)

    monkeypatch.setattr(module, "validate_url_with_env_config", validate)
    return module, checked, resolved


@pytest.mark.parametrize("url", IP_URLS)
@pytest.mark.parametrize("failure", ("connection_refused", "http_warning"))
async def test_failed_ip_navigation_does_not_derive_or_resolve_another_host(
    monkeypatch, url, failure,
):
    module, checked, resolved = navigation_policy(monkeypatch, url)
    navigated = []
    original_error = RuntimeError("net::ERR_CONNECTION_REFUSED")
    browser = SimpleNamespace(
        _page=SimpleNamespace(close=AsyncMock()),
        _context=SimpleNamespace(new_page=AsyncMock()),
        get_hints=AsyncMock(return_value={}),
    )

    async def navigate(target, **kwargs):
        assert kwargs["validate_ssrf"] is True
        navigated.append(target)
        validate_url_with_env_config(target)
        if len(navigated) == 1:
            if failure == "connection_refused":
                raise original_error
            return {"url": target, "status_code": None,
                    "warning": "HTTP error response, but page loaded"}
        return {"url": target, "status_code": 200}

    browser.goto = navigate
    instance = module.BrowserGotoModule({"url": url}, {"browser": browser})
    if failure == "connection_refused":
        with pytest.raises(RuntimeError) as caught:
            await instance.execute()
        assert caught.value is original_error
    else:
        result = await instance.execute()
        assert result["url"] == url
        assert result["status_code"] is None
        assert result["outcome"]["rung"] == "accepted"
    assert navigated == [url]
    assert checked == [url]
    assert resolved and set(resolved) == {urlsplit(url).hostname}
    browser._context.new_page.assert_not_awaited()
    browser._page.close.assert_not_awaited()


@pytest.mark.parametrize("original,alternative", (
    ("https://flyto2.com/path?day=today#events", "https://www.flyto2.com/path?day=today#events"),
    ("https://www.flyto2.com/path?day=today#events", "https://flyto2.com/path?day=today#events"),
))
async def test_domain_fallback_still_revalidates_and_navigates(monkeypatch, original, alternative):
    module, checked, resolved = navigation_policy(monkeypatch, original)
    browser = SimpleNamespace(
        _page=SimpleNamespace(close=AsyncMock()),
        _context=SimpleNamespace(new_page=AsyncMock()),
        goto=AsyncMock(side_effect=[RuntimeError("net::ERR_CONNECTION_REFUSED"),
                                   {"url": alternative, "status_code": 200}]),
        get_hints=AsyncMock(return_value={}),
    )
    instance = module.BrowserGotoModule({"url": original}, {"browser": browser})
    result = await instance.execute()
    assert result["url"] == alternative
    assert result["status_code"] == 200
    assert checked == [original, alternative]
    assert resolved == [urlsplit(original).hostname, urlsplit(alternative).hostname]
    assert [call.args[0] for call in browser.goto.await_args_list] == [original, alternative]
    assert all(call.kwargs["validate_ssrf"] is True for call in browser.goto.await_args_list)


@pytest.mark.browser
@pytest.mark.parametrize("url", ("http://127.0.0.1:8080/calendar", "http://[::1]:8080/calendar"))
async def test_chromium_ip_connection_failure_keeps_original_destination(monkeypatch, url):
    from playwright.async_api import async_playwright

    from core.browser.driver import BrowserDriver

    module, checked, resolved = navigation_policy(monkeypatch, url)
    requested = []

    async def refuse(route):
        requested.append(route.request.url)
        await route.abort("connectionrefused")

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(channel="chrome", headless=True)
        try:
            context = await browser.new_context()
            await context.route("**/*", refuse)
            driver = BrowserDriver(headless=True)
            driver._context = context
            driver._page = await context.new_page()
            instance = module.BrowserGotoModule({"url": url}, {"browser": driver})
            with pytest.raises(RuntimeError, match="ERR_CONNECTION_REFUSED"):
                await instance.execute()
            assert requested == [url]
            assert checked == [url]
            assert resolved and set(resolved) == {urlsplit(url).hostname}
            assert len(context.pages) == 1
        finally:
            await browser.close()
