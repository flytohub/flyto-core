"""Browser launch channel fallback contract."""

from unittest.mock import AsyncMock

import pytest

from core.browser.driver import BrowserDriver


def test_explicit_chromium_channel_is_authoritative():
    assert BrowserDriver._chromium_channel_candidates("chrome-beta") == ("chrome-beta",)


def test_default_chromium_channels_include_installed_browsers():
    assert BrowserDriver._chromium_channel_candidates(None) == (
        None,
        "chrome",
        "msedge",
    )


@pytest.mark.asyncio
async def test_chromium_launch_falls_back_to_system_chrome(monkeypatch):
    driver = BrowserDriver()
    persistent = AsyncMock(side_effect=[False, True])
    regular = AsyncMock(return_value=False)
    monkeypatch.setattr(driver, "_launch_persistent", persistent)
    monkeypatch.setattr(driver, "_launch_regular", regular)

    launched = await driver._launch_chromium(object(), [], {})

    assert launched == "chrome"
    assert [call.kwargs["channel"] for call in persistent.await_args_list] == [None, "chrome"]
    assert [call.kwargs["channel"] for call in regular.await_args_list] == [None]


@pytest.mark.asyncio
async def test_explicit_channel_does_not_fall_back_to_another_browser(monkeypatch):
    driver = BrowserDriver()
    persistent = AsyncMock(return_value=False)
    regular = AsyncMock(return_value=False)
    monkeypatch.setattr(driver, "_launch_persistent", persistent)
    monkeypatch.setattr(driver, "_launch_regular", regular)

    launched = await driver._launch_chromium(
        object(),
        [],
        {},
        channel="chrome-beta",
    )

    assert launched is False
    assert [call.kwargs["channel"] for call in persistent.await_args_list] == ["chrome-beta"]
    assert [call.kwargs["channel"] for call in regular.await_args_list] == ["chrome-beta"]


@pytest.mark.asyncio
async def test_worker_launch_skips_persistent_profiles(monkeypatch):
    driver = BrowserDriver()
    persistent = AsyncMock(return_value=True)
    regular = AsyncMock(side_effect=[False, True])
    monkeypatch.setattr(driver, "_launch_persistent", persistent)
    monkeypatch.setattr(driver, "_launch_regular", regular)

    launched = await driver._launch_chromium(
        object(),
        [],
        {},
        skip_persistent=True,
    )

    assert launched == "chrome"
    persistent.assert_not_awaited()
    assert [call.kwargs["channel"] for call in regular.await_args_list] == [None, "chrome"]
