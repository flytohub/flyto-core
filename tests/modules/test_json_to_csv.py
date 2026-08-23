"""Regression coverage for the JSON-to-CSV workflow module."""

from unittest.mock import AsyncMock

import pytest

from core.modules.errors import InvalidTypeError, InvalidValueError, ValidationError
from core.modules.registry import ModuleRegistry


def _module(params):
    module_class = ModuleRegistry.get("data.json_to_csv")
    return module_class(params, {})


@pytest.mark.asyncio
async def test_default_output_is_created_inside_the_configured_sandbox(
    monkeypatch,
    tmp_path,
):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    monkeypatch.setenv("FLYTO_SANDBOX_DIR", str(sandbox))

    result = await _module(
        {"input_data": [{"name": "Ada", "active": True}]}
    ).run()

    output_path = sandbox / "output.csv"
    assert result["ok"] is True
    assert result["output_path"] == str(output_path)
    assert output_path.read_text(encoding="utf-8") == "active,name\nTrue,Ada\n"


@pytest.mark.asyncio
async def test_missing_input_reports_the_parameter_without_retry_noise():
    module = _module({})
    original_execute = module.execute
    module.execute = AsyncMock(side_effect=original_execute)

    with pytest.raises(ValidationError, match="Missing required parameter: input_data"):
        await module.run()

    module.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_non_object_rows_fail_with_a_typed_user_facing_error(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("FLYTO_SANDBOX_DIR", str(tmp_path))

    with pytest.raises(InvalidTypeError, match="only JSON objects"):
        await _module({"input_data": ["not-an-object"]}).run()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("input_data", "error_type", "message"),
    [
        ("not-json", InvalidValueError, "must contain valid JSON"),
        (42, InvalidTypeError, "must be a JSON array"),
        ([], InvalidValueError, "must not be empty"),
    ],
)
async def test_invalid_input_reports_a_typed_user_facing_error_without_retry(
    input_data,
    error_type,
    message,
):
    module = _module({"input_data": input_data})
    original_execute = module.execute
    module.execute = AsyncMock(side_effect=original_execute)

    with pytest.raises(error_type, match=message):
        await module.run()

    module.execute.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("output_path", [None, "", 42])
async def test_invalid_output_path_reports_a_typed_parameter_error(output_path):
    with pytest.raises(ValidationError, match="non-empty path"):
        await _module(
            {"input_data": [{"name": "Ada"}], "output_path": output_path}
        ).run()


def test_catalog_default_is_relative_to_the_runtime_sandbox():
    schema = ModuleRegistry.get_metadata("data.json_to_csv")["params_schema"]

    assert schema["output_path"]["default"] == "output.csv"
