"""Tests for StepExecutor extracted mode methods (_execute_single_mode, _execute_items_mode, _execute_all_mode)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.engine.step_executor.executor import StepExecutor


class TestExecuteSingleMode:
    def setup_method(self):
        self.executor = StepExecutor()

    async def test_legacy_result_wrapped(self):
        module = AsyncMock()
        module.run = AsyncMock(return_value={"ok": True, "data": {"x": 1}})

        result = await self.executor._execute_single_mode("s1", module)
        assert isinstance(result, dict)
        module.run.assert_awaited_once()

    async def test_non_legacy_result_passthrough(self):
        module = AsyncMock()
        module.run = AsyncMock(return_value="raw_string")

        result = await self.executor._execute_single_mode("s1", module)
        assert result == "raw_string"

    async def test_dict_without_ok_passthrough(self):
        module = AsyncMock()
        module.run = AsyncMock(return_value={"status": "done"})

        result = await self.executor._execute_single_mode("s1", module)
        assert result == {"status": "done"}


class TestExecuteItemsMode:
    def setup_method(self):
        self.executor = StepExecutor()

    async def test_processes_items(self):
        from core.modules.items import Item

        module = AsyncMock()
        module.execute_item = AsyncMock(side_effect=[
            Item(json={"out": 1}),
            Item(json={"out": 2}),
        ])

        items = [Item(json={"in": 1}), Item(json={"in": 2})]
        result = await self.executor._execute_items_mode(
            "s1", module, {"$on_error": "stop"}, items, None,
        )
        assert module.execute_item.await_count == 2
        assert isinstance(result, dict)

    async def test_empty_items_creates_default(self):
        from core.modules.items import Item

        module = AsyncMock()
        module.execute_item = AsyncMock(return_value=Item(json={"done": True}))

        result = await self.executor._execute_items_mode(
            "s1", module, {}, None, None,
        )
        # Should have called with one default Item(json={})
        module.execute_item.assert_awaited_once()

    async def test_continue_on_error(self):
        from core.modules.items import Item

        module = AsyncMock()
        module.execute_item = AsyncMock(side_effect=[
            Item(json={"ok": True}),
            Exception("item failed"),
            Item(json={"ok": True}),
        ])

        items = [Item(json={}), Item(json={}), Item(json={})]
        result = await self.executor._execute_items_mode(
            "s1", module, {"$on_error": "continue"}, items, None,
        )
        assert isinstance(result, dict)
        # All 3 should be processed
        assert module.execute_item.await_count == 3

    async def test_stop_on_error_raises(self):
        from core.modules.items import Item

        module = AsyncMock()
        module.execute_item = AsyncMock(side_effect=Exception("boom"))

        items = [Item(json={})]
        with pytest.raises(Exception, match="boom"):
            await self.executor._execute_items_mode(
                "s1", module, {"$on_error": "stop"}, items, None,
            )

    async def test_list_result_extends(self):
        from core.modules.items import Item

        module = AsyncMock()
        module.execute_item = AsyncMock(return_value=[
            Item(json={"a": 1}),
            Item(json={"a": 2}),
        ])

        items = [Item(json={})]
        result = await self.executor._execute_items_mode(
            "s1", module, {}, items, None,
        )
        assert isinstance(result, dict)


class TestExecuteAllMode:
    def setup_method(self):
        self.executor = StepExecutor()

    async def test_passes_all_items(self):
        from core.modules.items import Item

        module = AsyncMock()
        module.execute_all = AsyncMock(return_value=[
            Item(json={"merged": True}),
        ])

        items = [Item(json={"a": 1}), Item(json={"b": 2})]
        result = await self.executor._execute_all_mode("s1", module, items)

        module.execute_all.assert_awaited_once()
        call_args = module.execute_all.call_args
        assert len(call_args[0][0]) == 2  # 2 items passed

    async def test_empty_items(self):
        from core.modules.items import Item

        module = AsyncMock()
        module.execute_all = AsyncMock(return_value=[])

        result = await self.executor._execute_all_mode("s1", module, None)
        call_args = module.execute_all.call_args
        assert call_args[0][0] == []  # empty list passed
