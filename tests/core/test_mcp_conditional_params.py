"""MCP parameter validation follows the real conditional module contract."""

from copy import deepcopy

import pytest

from core.mcp_handler import get_module_info, validate_params
from core.modules.registry import ModuleRegistry


@pytest.mark.parametrize("input_type", [None, "text", "email"])
def test_browser_text_does_not_require_inactive_password_field(input_type):
    params = {"type_method": "selector", "selector": "#field", "text": "ordinary text"}
    if input_type is not None:
        params["input_type"] = input_type
    original = deepcopy(params)

    assert validate_params("browser.type", params)["valid"] is True
    assert params == original


def test_browser_password_does_not_require_inactive_plaintext_field():
    result = validate_params("browser.type", {
        "type_method": "selector", "selector": "#field", "input_type": "password",
        "sensitive_text": "${env.TEST_BROWSER_PASSWORD}",
    })
    assert result["valid"] is True


@pytest.mark.parametrize("input_type,missing", [
    (None, "text"),
    ("password", "sensitive_text"),
])
def test_active_browser_field_remains_required(input_type, missing):
    params = {"type_method": "selector", "selector": "#field"}
    if input_type is not None:
        params["input_type"] = input_type
    result = validate_params("browser.type", params)
    assert result["valid"] is False
    assert result["errors"] == [f"Missing required parameter: {missing}"]
    assert result["suggestions"]["hints"] == [f"Missing required: {missing} (string)"]


def test_browser_schema_keeps_password_conditional_and_secret():
    schema = get_module_info("browser.type")["params_schema"]
    assert schema["sensitive_text"]["required"] is True
    assert schema["sensitive_text"]["showIf"] == {"input_type": {"$in": ["password"]}}
    assert schema["sensitive_text"]["secret"] is True


@pytest.mark.parametrize("visibility", [
    {"showIf": {"mode": {"$in": ["active"]}}},
    {"hideIf": {"mode": {"$ne": "active"}}},
    {"displayOptions": {"show": {"mode": ["active"]}}},
    {"displayOptions": {"hide": {"mode": ["inactive"]}}},
])
def test_effective_defaults_activate_required_fields_without_mutating_params(monkeypatch, visibility):
    schema = {
        "mode": {"type": "string", "default": "active"},
        "value": {"type": "string", "required": True, **visibility},
    }
    monkeypatch.setattr(ModuleRegistry, "get_metadata", lambda _: {"params_schema": schema})
    monkeypatch.setattr(ModuleRegistry, "get", lambda _: None)
    params = {}
    assert validate_params("test.conditional", params)["errors"] == ["Missing required parameter: value"]
    assert params == {}
    assert validate_params("test.conditional", {"mode": "inactive"})["valid"] is True


@pytest.mark.parametrize("default", [False, 0, "default value"])
def test_required_schema_defaults_are_available_to_module_validation(monkeypatch, default):
    class Module:
        def __init__(self, params, context):
            assert params == {"value": default}

        def validate_params(self):
            pass

    monkeypatch.setattr(ModuleRegistry, "get_metadata", lambda _: {
        "params_schema": {"value": {"required": True, "default": default}},
    })
    monkeypatch.setattr(ModuleRegistry, "get", lambda _: Module)
    assert validate_params("test.default", {})["valid"] is True


def test_module_specific_validation_still_rejects_an_invalid_selector():
    result = validate_params("browser.type", {"type_method": "selector", "text": "ordinary text"})
    assert result["valid"] is False
    assert any("selector" in message.lower() for message in result["errors"])
