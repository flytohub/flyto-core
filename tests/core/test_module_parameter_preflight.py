"""Preflight checks only explicit, known values and never performs an action."""

import copy
import traceback

import pytest

from core.modules.atomic.browser.screenshot import BrowserScreenshotModule
from core.modules.preflight import ModulePreflightError, preflight_module_params
from core.modules.registry import ModuleRegistry
from core.utils import PathTraversalError, validate_path_with_env_config


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    directory = tmp_path / "sandbox"
    directory.mkdir()
    monkeypatch.chdir(directory)
    monkeypatch.setenv("FLYTO_SANDBOX_DIR", str(directory))
    monkeypatch.setenv("FLYTO_ALLOW_ABSOLUTE_PATHS", "true")
    return directory


@pytest.mark.parametrize("path", ["capture.png", "nested/capture.png", "absolute"])
def test_preflight_accepts_runtime_allowed_paths_without_writing(sandbox, path):
    raw_path = str(sandbox / "capture.png") if path == "absolute" else path
    params = {"path": raw_path, "full_page": True, "extra": {"unchanged": [1]}}
    original = copy.deepcopy(params)

    assert preflight_module_params("browser.screenshot", params) is None
    assert BrowserScreenshotModule(params, {}).path == validate_path_with_env_config(raw_path)
    assert params == original
    assert list(sandbox.iterdir()) == []


@pytest.mark.parametrize("path_kind", ["absolute", "relative", "symlink"])
def test_preflight_rejects_the_same_escape_as_runtime_without_disclosure(sandbox, path_kind):
    sentinel = "PRIVATE_PREFLIGHT_TEST_SENTINEL"
    outside = sandbox.parent / sentinel
    if path_kind == "relative":
        raw_path = "../" + sentinel
    elif path_kind == "symlink":
        (sandbox / "linked").symlink_to(sandbox.parent, target_is_directory=True)
        raw_path = "linked/" + sentinel
    else:
        raw_path = str(outside)
    params = {"path": raw_path}

    with pytest.raises(PathTraversalError):
        BrowserScreenshotModule(params, {})
    with pytest.raises(ModulePreflightError) as caught:
        preflight_module_params("browser.screenshot", params)

    error = caught.value
    assert error.field == "path"
    assert error.code == "path_not_allowed"
    assert str(error) == "A module parameter is not permitted by the execution host."
    assert error.__cause__ is None
    assert error.__context__ is None
    rendered = "".join(traceback.format_exception(error))
    assert sentinel not in rendered
    assert str(sandbox) not in rendered
    assert not outside.exists()
    assert params == {"path": raw_path}


def test_preflight_preserves_the_absolute_path_setting(sandbox, monkeypatch):
    monkeypatch.setenv("FLYTO_ALLOW_ABSOLUTE_PATHS", "false")
    params = {"path": str(sandbox / "capture.png")}
    with pytest.raises(PathTraversalError):
        BrowserScreenshotModule(params, {})
    with pytest.raises(ModulePreflightError):
        preflight_module_params("browser.screenshot", params)
    assert preflight_module_params("browser.screenshot", {"path": "capture.png"}) is None


@pytest.mark.parametrize("params", [{}, {"path": ""}, {"path": None}, {"path": False}])
def test_missing_or_empty_path_is_not_defaulted_or_validated(sandbox, monkeypatch, params):
    def unexpected(*args, **kwargs):
        pytest.fail("Unknown or base64-only path must not reach path validation")

    monkeypatch.setattr(
        "core.modules.atomic.browser.screenshot.validate_path_with_env_config", unexpected,
    )
    assert preflight_module_params("browser.screenshot", params) is None


@pytest.mark.parametrize("raw_path", [42, {"private": "sentinel"}, ["sentinel"]])
def test_invalid_known_path_has_a_safe_structured_error(sandbox, raw_path):
    with pytest.raises(ModulePreflightError) as caught:
        preflight_module_params("browser.screenshot", {"path": raw_path})
    assert caught.value.field == "path"
    assert caught.value.code == "path_not_allowed"
    assert "sentinel" not in str(caught.value)
    assert caught.value.__context__ is None


def test_preflight_never_constructs_or_executes_a_module(sandbox, monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("Preflight must not construct or execute a module")

    monkeypatch.setattr(BrowserScreenshotModule, "__init__", unexpected)
    monkeypatch.setattr(BrowserScreenshotModule, "execute", unexpected)
    assert preflight_module_params("browser.screenshot", {"path": "new/capture.png"}) is None
    assert list(sandbox.iterdir()) == []


@pytest.mark.parametrize("module_id", ["browser.download", "image.resize"])
def test_non_opted_in_modules_keep_runtime_validation_only(sandbox, monkeypatch, module_id):
    module_class = ModuleRegistry.get(module_id)

    def unexpected(*args, **kwargs):
        pytest.fail("Preflight must not infer module policy or instantiate it")

    monkeypatch.setattr(module_class, "__init__", unexpected)
    params = {"path": "../outside", "save_path": "../outside", "input_path": "../outside"}
    assert preflight_module_params(module_id, params) is None
    assert list(sandbox.iterdir()) == []


def test_unknown_module_does_not_gain_a_guessed_preflight(sandbox):
    assert preflight_module_params("unregistered.preflight_fixture", {"path": "../outside"}) is None


def test_runtime_revalidates_after_preflight_when_host_settings_change(sandbox, monkeypatch):
    params = {"path": str(sandbox / "capture.png")}
    preflight_module_params("browser.screenshot", params)
    monkeypatch.setenv("FLYTO_SANDBOX_DIR", str(sandbox.parent / "another-sandbox"))
    with pytest.raises(PathTraversalError):
        BrowserScreenshotModule(params, {})
    assert list(sandbox.iterdir()) == []
