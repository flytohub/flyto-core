import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))


def get_module(module_id: str):
    from core.modules import atomic  # noqa: F401
    from core.modules.registry import ModuleRegistry

    return ModuleRegistry.get(module_id)


def test_mcp_recipe_module_is_registered():
    module = get_module("mcp.recipe")
    assert module is not None
    assert module.module_name == "MCP Recipe"


@pytest.mark.asyncio
async def test_mcp_recipe_emits_redacted_runtime_evidence():
    module = get_module("mcp.recipe")

    result = await module(
        {
            "recipe_id": "warroom-smoke",
            "scenario_id": "authenticated",
            "default_args": {
                "target": "https://example.test",
                "password": "stored-default-password",
            },
            "runtime_required_args": ["target", "username", "password"],
        },
        {
            "username": "tester",
            "password": "runtime-password",
            "trigger_payload": {"arguments": {"token": "runtime-token"}},
        },
    ).execute()

    serialized = json.dumps(result, sort_keys=True)
    assert result["ok"] is True
    assert result["recipe_ok"] is True
    assert result["status"] == "completed"
    assert result["secret_values_stored"] is False
    assert result["runtime_args_missing"] == []
    assert result["runtime_args_present"] == ["password", "target", "username"]
    assert "runtime-password" not in serialized
    assert "runtime-token" not in serialized
    assert "stored-default-password" not in serialized
    assert result["evidence"]["default_args"]["password"] == "[REDACTED]"


@pytest.mark.asyncio
async def test_mcp_recipe_reports_missing_args_without_failing_workflow():
    module = get_module("mcp.recipe")

    result = await module(
        {
            "recipe_id": "warroom-smoke",
            "scenario_id": "authenticated",
            "default_args": {"target": "https://example.test"},
            "runtime_required_args": ["target", "username", "password"],
        },
        {},
    ).execute()

    assert result["ok"] is True
    assert result["recipe_ok"] is False
    assert result["status"] == "needs_runtime_args"
    assert result["runtime_args_missing"] == ["username", "password"]
