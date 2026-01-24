"""
Tests for item-based execution pipeline behavior in StepExecutor.
"""

import pytest

from core.engine.step_executor.executor import StepExecutor
from core.engine.variable_resolver import VariableResolver
from core.modules.base import BaseModule
from core.modules.items import Item
from core.modules.registry.core import ModuleRegistry


class _PassThroughItemsModule(BaseModule):
    module_id = "test.items.pass"
    execution_mode = "items"

    def validate_params(self) -> None:
        return None

    async def execute(self):
        return self.success({})

    async def execute_item(self, item: Item, index: int, context):
        return Item(json=item.json)


class _FlakyItemsModule(BaseModule):
    module_id = "test.items.flaky"
    execution_mode = "items"

    def validate_params(self) -> None:
        return None

    async def execute(self):
        return self.success({})

    async def execute_item(self, item: Item, index: int, context):
        value = item.json.get("value")
        if value == 2:
            raise RuntimeError("boom")
        return Item(json={"value": value})


@pytest.mark.asyncio
async def test_items_continue_uses_step_on_error():
    ModuleRegistry.register(_FlakyItemsModule.module_id, _FlakyItemsModule)
    try:
        executor = StepExecutor()
        context = {
            "up1": {"ok": True, "items": [1, 2]},
        }
        resolver = VariableResolver(params={}, context=context)
        step_config = {
            "id": "step1",
            "module": _FlakyItemsModule.module_id,
            "params": {},
            "on_error": "continue",
            "inputs": ["up1"],
        }

        result = await executor.execute_step(
            step_config=step_config,
            step_index=0,
            context=context,
            resolver=resolver,
            should_execute=True,
        )

        assert result["ok"] is True
        assert result["items"] == [{"value": 1}, {}]
        assert result["items_full"][1]["error"]["message"] == "boom"
    finally:
        ModuleRegistry.unregister(_FlakyItemsModule.module_id)


@pytest.mark.asyncio
async def test_items_from_context_support_non_dict_values():
    ModuleRegistry.register(_PassThroughItemsModule.module_id, _PassThroughItemsModule)
    try:
        executor = StepExecutor()
        context = {
            "up1": {"ok": True, "items": [1, "a", {"x": 1}]},
        }
        resolver = VariableResolver(params={}, context=context)
        step_config = {
            "id": "step2",
            "module": _PassThroughItemsModule.module_id,
            "params": {},
            "inputs": ["up1"],
        }

        result = await executor.execute_step(
            step_config=step_config,
            step_index=0,
            context=context,
            resolver=resolver,
            should_execute=True,
        )

        assert result["items"] == [{"value": 1}, {"value": "a"}, {"x": 1}]
        assert len(result.get("items_full", [])) == 3
    finally:
        ModuleRegistry.unregister(_PassThroughItemsModule.module_id)
