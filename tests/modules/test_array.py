"""
Tests for array.* modules

Tests all array manipulation modules:
- array.map
- array.reduce
- array.flatten
- array.join
- array.chunk
- array.intersection
- array.difference
"""

import pytest
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from core.modules.errors import ValidationError, InvalidTypeError, InvalidValueError


class TestArrayMap:
    """Tests for array.map module."""

    MODULE_ID = "array.map"

    @pytest.fixture
    def module_class(self):
        from core.modules.registry import ModuleRegistry
        from core.modules import atomic
        return ModuleRegistry.get(self.MODULE_ID)

    @pytest.mark.asyncio
    async def test_multiply_operation(self, module_class):
        """Test multiply operation."""
        instance = module_class({
            "array": [1, 2, 3, 4, 5],
            "operation": "multiply",
            "value": 2
        }, {})
        result = await instance.execute()
        assert result["data"]["result"] == [2, 4, 6, 8, 10]
        assert result["data"]["length"] == 5

    @pytest.mark.asyncio
    async def test_add_operation(self, module_class):
        """Test add operation."""
        instance = module_class({
            "array": [1, 2, 3],
            "operation": "add",
            "value": 10
        }, {})
        result = await instance.execute()
        assert result["data"]["result"] == [11, 12, 13]

    @pytest.mark.asyncio
    async def test_extract_operation(self, module_class):
        """Test extract operation on objects."""
        instance = module_class({
            "array": [{"name": "Alice"}, {"name": "Bob"}],
            "operation": "extract",
            "value": "name"
        }, {})
        result = await instance.execute()
        assert result["data"]["result"] == ["Alice", "Bob"]

    @pytest.mark.asyncio
    async def test_uppercase_operation(self, module_class):
        """Test uppercase operation."""
        instance = module_class({
            "array": ["hello", "world"],
            "operation": "uppercase"
        }, {})
        result = await instance.execute()
        assert result["data"]["result"] == ["HELLO", "WORLD"]

    @pytest.mark.asyncio
    async def test_invalid_array(self, module_class):
        """Test with invalid array type raises InvalidTypeError."""
        instance = module_class({
            "array": "not an array",
            "operation": "multiply"
        }, {})
        with pytest.raises(InvalidTypeError):
            await instance.execute()


class TestArrayReduce:
    """Tests for array.reduce module."""

    MODULE_ID = "array.reduce"

    @pytest.fixture
    def module_class(self):
        from core.modules.registry import ModuleRegistry
        from core.modules import atomic
        return ModuleRegistry.get(self.MODULE_ID)

    @pytest.mark.asyncio
    async def test_sum_operation(self, module_class):
        """Test sum operation."""
        instance = module_class({
            "array": [1, 2, 3, 4, 5],
            "operation": "sum"
        }, {})
        result = await instance.execute()
        assert result["data"]["result"] == 15
        assert result["data"]["operation"] == "sum"

    @pytest.mark.asyncio
    async def test_product_operation(self, module_class):
        """Test product operation."""
        instance = module_class({
            "array": [1, 2, 3, 4],
            "operation": "product"
        }, {})
        result = await instance.execute()
        assert result["data"]["result"] == 24

    @pytest.mark.asyncio
    async def test_average_operation(self, module_class):
        """Test average operation."""
        instance = module_class({
            "array": [10, 20, 30],
            "operation": "average"
        }, {})
        result = await instance.execute()
        assert result["data"]["result"] == 20

    @pytest.mark.asyncio
    async def test_min_max_operations(self, module_class):
        """Test min and max operations."""
        instance = module_class({
            "array": [5, 2, 8, 1, 9],
            "operation": "min"
        }, {})
        result = await instance.execute()
        assert result["data"]["result"] == 1

        instance = module_class({
            "array": [5, 2, 8, 1, 9],
            "operation": "max"
        }, {})
        result = await instance.execute()
        assert result["data"]["result"] == 9

    @pytest.mark.asyncio
    async def test_join_operation(self, module_class):
        """Test join operation."""
        instance = module_class({
            "array": ["Hello", "World"],
            "operation": "join",
            "separator": " "
        }, {})
        result = await instance.execute()
        assert result["data"]["result"] == "Hello World"

    @pytest.mark.asyncio
    async def test_empty_array(self, module_class):
        """Test with empty array."""
        instance = module_class({
            "array": [],
            "operation": "sum"
        }, {})
        result = await instance.execute()
        assert result["data"]["result"] is None


class TestArrayFlatten:
    """Tests for array.flatten module."""

    MODULE_ID = "array.flatten"

    @pytest.fixture
    def module_class(self):
        from core.modules.registry import ModuleRegistry
        from core.modules import atomic
        return ModuleRegistry.get(self.MODULE_ID)

    @pytest.mark.asyncio
    async def test_flatten_one_level(self, module_class):
        """Test flattening one level."""
        instance = module_class({
            "array": [[1, 2], [3, 4], [5, 6]],
            "depth": 1
        }, {})
        result = await instance.execute()
        assert result["data"]["result"] == [1, 2, 3, 4, 5, 6]
        assert result["data"]["length"] == 6

    @pytest.mark.asyncio
    async def test_flatten_deep(self, module_class):
        """Test deep flattening."""
        instance = module_class({
            "array": [[1, [2, [3, [4]]]]],
            "depth": -1
        }, {})
        result = await instance.execute()
        assert result["data"]["result"] == [1, 2, 3, 4]

    @pytest.mark.asyncio
    async def test_flatten_mixed(self, module_class):
        """Test flattening mixed array."""
        instance = module_class({
            "array": [1, [2, 3], 4, [5]],
            "depth": 1
        }, {})
        result = await instance.execute()
        assert result["data"]["result"] == [1, 2, 3, 4, 5]


class TestArrayJoin:
    """Tests for array.join module."""

    MODULE_ID = "array.join"

    @pytest.fixture
    def module_class(self):
        from core.modules.registry import ModuleRegistry
        from core.modules import atomic
        return ModuleRegistry.get(self.MODULE_ID)

    @pytest.mark.asyncio
    async def test_join_with_comma(self, module_class):
        """Test joining with comma."""
        instance = module_class({
            "array": ["apple", "banana", "cherry"],
            "separator": ", "
        }, {})
        result = await instance.execute()
        assert result["data"]["result"] == "apple, banana, cherry"

    @pytest.mark.asyncio
    async def test_join_default_separator(self, module_class):
        """Test joining with default separator."""
        instance = module_class({
            "array": ["a", "b", "c"]
        }, {})
        result = await instance.execute()
        assert result["data"]["result"] == "a,b,c"

    @pytest.mark.asyncio
    async def test_join_numbers(self, module_class):
        """Test joining numbers."""
        instance = module_class({
            "array": [1, 2, 3],
            "separator": "-"
        }, {})
        result = await instance.execute()
        assert result["data"]["result"] == "1-2-3"


class TestArrayChunk:
    """Tests for array.chunk module."""

    MODULE_ID = "array.chunk"

    @pytest.fixture
    def module_class(self):
        from core.modules.registry import ModuleRegistry
        from core.modules import atomic
        return ModuleRegistry.get(self.MODULE_ID)

    @pytest.mark.asyncio
    async def test_chunk_even_split(self, module_class):
        """Test chunking with even split."""
        instance = module_class({
            "array": [1, 2, 3, 4, 5, 6],
            "size": 2
        }, {})
        result = await instance.execute()
        assert result["data"]["result"] == [[1, 2], [3, 4], [5, 6]]
        assert result["data"]["chunks"] == 3

    @pytest.mark.asyncio
    async def test_chunk_uneven_split(self, module_class):
        """Test chunking with uneven split."""
        instance = module_class({
            "array": [1, 2, 3, 4, 5],
            "size": 2
        }, {})
        result = await instance.execute()
        assert result["data"]["result"] == [[1, 2], [3, 4], [5]]
        assert result["data"]["chunks"] == 3

    @pytest.mark.asyncio
    async def test_chunk_invalid_size(self, module_class):
        """Test chunking with invalid size raises InvalidValueError."""
        instance = module_class({
            "array": [1, 2, 3],
            "size": 0
        }, {})
        with pytest.raises(InvalidValueError):
            await instance.execute()


class TestArrayIntersection:
    """Tests for array.intersection module."""

    MODULE_ID = "array.intersection"

    @pytest.fixture
    def module_class(self):
        from core.modules.registry import ModuleRegistry
        from core.modules import atomic
        return ModuleRegistry.get(self.MODULE_ID)

    @pytest.mark.asyncio
    async def test_two_arrays(self, module_class):
        """Test intersection of two arrays."""
        instance = module_class({
            "arrays": [[1, 2, 3, 4], [2, 3, 5]]
        }, {})
        result = await instance.execute()
        assert set(result["data"]["result"]) == {2, 3}
        assert result["data"]["length"] == 2

    @pytest.mark.asyncio
    async def test_three_arrays(self, module_class):
        """Test intersection of three arrays."""
        instance = module_class({
            "arrays": [[1, 2, 3, 4], [2, 3, 5], [2, 3, 6]]
        }, {})
        result = await instance.execute()
        assert set(result["data"]["result"]) == {2, 3}

    @pytest.mark.asyncio
    async def test_no_common_elements(self, module_class):
        """Test with no common elements."""
        instance = module_class({
            "arrays": [[1, 2], [3, 4]]
        }, {})
        result = await instance.execute()
        assert result["data"]["result"] == []
        assert result["data"]["length"] == 0

    @pytest.mark.asyncio
    async def test_insufficient_arrays(self, module_class):
        """Test with less than 2 arrays raises InvalidValueError."""
        instance = module_class({
            "arrays": [[1, 2, 3]]
        }, {})
        with pytest.raises(InvalidValueError):
            await instance.execute()


class TestArrayDifference:
    """Tests for array.difference module."""

    MODULE_ID = "array.difference"

    @pytest.fixture
    def module_class(self):
        from core.modules.registry import ModuleRegistry
        from core.modules import atomic
        return ModuleRegistry.get(self.MODULE_ID)

    @pytest.mark.asyncio
    async def test_basic_difference(self, module_class):
        """Test basic difference."""
        instance = module_class({
            "array": [1, 2, 3, 4, 5],
            "subtract": [[2, 4]]
        }, {})
        result = await instance.execute()
        assert set(result["data"]["result"]) == {1, 3, 5}

    @pytest.mark.asyncio
    async def test_multiple_subtract(self, module_class):
        """Test subtracting multiple arrays."""
        instance = module_class({
            "array": [1, 2, 3, 4, 5],
            "subtract": [[2, 4], [5]]
        }, {})
        result = await instance.execute()
        assert set(result["data"]["result"]) == {1, 3}

    @pytest.mark.asyncio
    async def test_no_difference(self, module_class):
        """Test when all elements are subtracted."""
        instance = module_class({
            "array": [1, 2, 3],
            "subtract": [[1, 2, 3]]
        }, {})
        result = await instance.execute()
        assert result["data"]["result"] == []
        assert result["data"]["length"] == 0
