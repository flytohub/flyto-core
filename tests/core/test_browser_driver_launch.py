"""Browser launch channel fallback contract."""

from pathlib import Path
from types import SimpleNamespace
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


@pytest.mark.asyncio
async def test_regular_launch_failure_is_recorded(monkeypatch):
    """The reason a channel refused to start must survive the fallback loop."""
    driver = BrowserDriver()
    launcher = SimpleNamespace(
        launch=AsyncMock(side_effect=RuntimeError("Executable doesn't exist at /nope"))
    )

    launched = await driver._launch_regular(launcher, [], {}, channel="chrome")

    assert launched is False
    assert driver._launch_failures == [
        "chrome (regular): Executable doesn't exist at /nope"
    ]


@pytest.mark.asyncio
async def test_persistent_launch_failure_is_recorded(monkeypatch, tmp_path):
    driver = BrowserDriver()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    launcher = SimpleNamespace(
        launch_persistent_context=AsyncMock(side_effect=RuntimeError("profile is locked"))
    )

    launched = await driver._launch_persistent(launcher, [], {})

    assert launched is False
    assert driver._launch_failures == ["playwright-chromium (persistent): profile is locked"]


@pytest.mark.asyncio
async def test_no_engine_message_names_every_failed_attempt(monkeypatch):
    """A generic 'no engine' sentence is not actionable; the causes are."""
    driver = BrowserDriver()

    async def failing(*args, **kwargs):
        driver._record_launch_failure(kwargs.get("channel"), "regular", RuntimeError("boom"))
        return False

    monkeypatch.setattr(driver, "_launch_persistent", AsyncMock(return_value=False))
    monkeypatch.setattr(driver, "_launch_regular", failing)

    assert await driver._launch_chromium(object(), [], {}) is False

    message = driver._no_engine_message()
    assert "playwright install chromium" in message
    assert "playwright-chromium (regular): boom" in message
    assert "chrome (regular): boom" in message
    assert "msedge (regular): boom" in message


def test_no_engine_message_without_attempts_is_the_base_advice():
    driver = BrowserDriver()
    message = driver._no_engine_message()
    assert message.endswith("channel.")
    assert "Attempts:" not in message


@pytest.mark.asyncio
async def test_launch_failures_do_not_accumulate_across_attempts(monkeypatch):
    """A later successful launch must not report a previous run's failures."""
    driver = BrowserDriver()
    driver._launch_failures = ["stale (regular): from a previous launch"]
    monkeypatch.setattr(driver, "_launch_persistent", AsyncMock(return_value=True))
    monkeypatch.setattr(driver, "_launch_regular", AsyncMock(return_value=False))

    assert await driver._launch_chromium(object(), [], {}) == "chromium"
    assert driver._launch_failures == []


@pytest.mark.asyncio
async def test_multiline_failure_is_reduced_to_its_first_line(monkeypatch):
    """Playwright errors carry long install banners; keep the message readable."""
    driver = BrowserDriver()
    launcher = SimpleNamespace(
        launch=AsyncMock(side_effect=RuntimeError("missing executable\n╔══ install ══╗\nrun playwright"))
    )

    await driver._launch_regular(launcher, [], {})

    assert driver._launch_failures == ["playwright-chromium (regular): missing executable"]
