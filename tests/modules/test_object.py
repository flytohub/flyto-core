"""
Tests for object.* modules

Tests all object manipulation modules:
- object.keys
- object.values
- object.merge
- object.pick
- object.omit
"""

import pytest
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))


class TestObjectKeys:
    """Tests for object.keys module."""

    MODULE_ID = "object.keys"

    @pytest.fixture
    def module_class(self):
        from core.modules.registry import ModuleRegistry
        from core.modules import atomic
        return ModuleRegistry.get(self.MODULE_ID)

    @pytest.mark.asyncio
    async def test_basic_keys(self, module_class):
        """Test getting keys from object."""
        instance = module_class({
            "object": {"name": "John", "age": 30, "city": "NYC"}
        }, {})
        result = await instance.execute()
        assert set(result["keys"]) == {"name", "age", "city"}
        assert result["count"] == 3

    @pytest.mark.asyncio
    async def test_empty_object(self, module_class):
        """Test with empty object."""
        instance = module_class({"object": {}}, {})
        result = await instance.execute()
        assert result["keys"] == []
        assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_invalid_type(self, module_class):
        """Test with invalid type."""
        instance = module_class({"object": "not an object"}, {})
        result = await instance.execute()
        assert result.get("ok") is False


class TestObjectValues:
    """Tests for object.values module."""

    MODULE_ID = "object.values"

    @pytest.fixture
    def module_class(self):
        from core.modules.registry import ModuleRegistry
        from core.modules import atomic
        return ModuleRegistry.get(self.MODULE_ID)

    @pytest.mark.asyncio
    async def test_basic_values(self, module_class):
        """Test getting values from object."""
        instance = module_class({
            "object": {"name": "John", "age": 30}
        }, {})
        result = await instance.execute()
        assert set(result["values"]) == {"John", 30}
        assert result["count"] == 2

    @pytest.mark.asyncio
    async def test_empty_object(self, module_class):
        """Test with empty object."""
        instance = module_class({"object": {}}, {})
        result = await instance.execute()
        assert result["values"] == []
        assert result["count"] == 0


class TestObjectMerge:
    """Tests for object.merge module."""

    MODULE_ID = "object.merge"

    @pytest.fixture
    def module_class(self):
        from core.modules.registry import ModuleRegistry
        from core.modules import atomic
        return ModuleRegistry.get(self.MODULE_ID)

    @pytest.mark.asyncio
    async def test_merge_two_objects(self, module_class):
        """Test merging two objects."""
        instance = module_class({
            "objects": [
                {"name": "John", "age": 30},
                {"city": "NYC", "country": "USA"}
            ]
        }, {})
        result = await instance.execute()
        assert result["result"] == {
            "name": "John",
            "age": 30,
            "city": "NYC",
            "country": "USA"
        }

    @pytest.mark.asyncio
    async def test_merge_overlapping_keys(self, module_class):
        """Test merging with overlapping keys."""
        instance = module_class({
            "objects": [
                {"name": "John"},
                {"name": "Jane"}
            ]
        }, {})
        result = await instance.execute()
        assert result["result"]["name"] == "Jane"

    @pytest.mark.asyncio
    async def test_merge_empty_array(self, module_class):
        """Test merging empty array."""
        instance = module_class({"objects": []}, {})
        result = await instance.execute()
        assert result["result"] == {}


class TestObjectPick:
    """Tests for object.pick module."""

    MODULE_ID = "object.pick"

    @pytest.fixture
    def module_class(self):
        from core.modules.registry import ModuleRegistry
        from core.modules import atomic
        return ModuleRegistry.get(self.MODULE_ID)

    @pytest.mark.asyncio
    async def test_pick_keys(self, module_class):
        """Test picking specific keys."""
        instance = module_class({
            "object": {"name": "John", "age": 30, "email": "john@example.com", "password": "secret"},
            "keys": ["name", "email"]
        }, {})
        result = await instance.execute()
        assert result["result"] == {"name": "John", "email": "john@example.com"}

    @pytest.mark.asyncio
    async def test_pick_nonexistent_key(self, module_class):
        """Test picking nonexistent key."""
        instance = module_class({
            "object": {"name": "John"},
            "keys": ["name", "nonexistent"]
        }, {})
        result = await instance.execute()
        assert result["result"] == {"name": "John"}

    @pytest.mark.asyncio
    async def test_pick_all_keys(self, module_class):
        """Test picking all keys."""
        instance = module_class({
            "object": {"a": 1, "b": 2},
            "keys": ["a", "b"]
        }, {})
        result = await instance.execute()
        assert result["result"] == {"a": 1, "b": 2}


class TestObjectOmit:
    """Tests for object.omit module."""

    MODULE_ID = "object.omit"

    @pytest.fixture
    def module_class(self):
        from core.modules.registry import ModuleRegistry
        from core.modules import atomic
        return ModuleRegistry.get(self.MODULE_ID)

    @pytest.mark.asyncio
    async def test_omit_keys(self, module_class):
        """Test omitting specific keys."""
        instance = module_class({
            "object": {"name": "John", "age": 30, "password": "secret", "ssn": "123"},
            "keys": ["password", "ssn"]
        }, {})
        result = await instance.execute()
        assert result["result"] == {"name": "John", "age": 30}

    @pytest.mark.asyncio
    async def test_omit_nonexistent_key(self, module_class):
        """Test omitting nonexistent key."""
        instance = module_class({
            "object": {"name": "John", "age": 30},
            "keys": ["nonexistent"]
        }, {})
        result = await instance.execute()
        assert result["result"] == {"name": "John", "age": 30}

    @pytest.mark.asyncio
    async def test_omit_all_keys(self, module_class):
        """Test omitting all keys."""
        instance = module_class({
            "object": {"a": 1, "b": 2},
            "keys": ["a", "b"]
        }, {})
        result = await instance.execute()
        assert result["result"] == {}
