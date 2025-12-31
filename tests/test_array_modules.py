"""
Tests for Array Operation Modules

Tests for array manipulation modules including:
- chunk
- flatten
- unique
- sort
- join
- difference
- intersection
"""
import pytest
import pytest_asyncio


class TestArrayChunkModule:
    """Tests for ArrayChunkModule"""

    @pytest.mark.asyncio
    async def test_chunk_basic(self):
        """Test basic array chunking"""
        from core.modules.atomic.array.chunk import ArrayChunkModule

        module = ArrayChunkModule(
            params={'array': [1, 2, 3, 4, 5, 6, 7, 8, 9], 'size': 3},
            context={}
        )
        result = await module.execute()

        assert result['result'] == [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
        assert result['chunks'] == 3

    @pytest.mark.asyncio
    async def test_chunk_uneven(self):
        """Test chunking with remainder elements"""
        from core.modules.atomic.array.chunk import ArrayChunkModule

        module = ArrayChunkModule(
            params={'array': [1, 2, 3, 4, 5], 'size': 2},
            context={}
        )
        result = await module.execute()

        assert result['result'] == [[1, 2], [3, 4], [5]]
        assert result['chunks'] == 3

    @pytest.mark.asyncio
    async def test_chunk_empty_array(self):
        """Test chunking empty array"""
        from core.modules.atomic.array.chunk import ArrayChunkModule

        module = ArrayChunkModule(
            params={'array': [], 'size': 3},
            context={}
        )
        result = await module.execute()

        assert result['result'] == []
        assert result['chunks'] == 0

    @pytest.mark.asyncio
    async def test_chunk_size_larger_than_array(self):
        """Test chunk size larger than array length"""
        from core.modules.atomic.array.chunk import ArrayChunkModule

        module = ArrayChunkModule(
            params={'array': [1, 2, 3], 'size': 10},
            context={}
        )
        result = await module.execute()

        assert result['result'] == [[1, 2, 3]]
        assert result['chunks'] == 1

    def test_chunk_invalid_size(self):
        """Test validation with invalid size"""
        from core.modules.atomic.array.chunk import ArrayChunkModule

        with pytest.raises(ValueError, match="size must be a positive number"):
            ArrayChunkModule(
                params={'array': [1, 2, 3], 'size': 0},
                context={}
            )

    def test_chunk_invalid_array(self):
        """Test validation with non-list input"""
        from core.modules.atomic.array.chunk import ArrayChunkModule

        with pytest.raises(ValueError, match="array must be a list"):
            ArrayChunkModule(
                params={'array': "not a list", 'size': 2},
                context={}
            )


class TestArrayFlattenModule:
    """Tests for ArrayFlattenModule"""

    @pytest.mark.asyncio
    async def test_flatten_one_level(self):
        """Test flattening one level deep"""
        from core.modules.atomic.array.flatten import ArrayFlattenModule

        module = ArrayFlattenModule(
            params={'array': [[1, 2], [3, 4], [5, 6]], 'depth': 1},
            context={}
        )
        result = await module.execute()

        assert result['result'] == [1, 2, 3, 4, 5, 6]
        assert result['length'] == 6

    @pytest.mark.asyncio
    async def test_flatten_deep_nested(self):
        """Test flattening deeply nested array with infinite depth"""
        from core.modules.atomic.array.flatten import ArrayFlattenModule

        module = ArrayFlattenModule(
            params={'array': [[1, [2, [3, [4]]]]], 'depth': -1},
            context={}
        )
        result = await module.execute()

        assert result['result'] == [1, 2, 3, 4]
        assert result['length'] == 4

    @pytest.mark.asyncio
    async def test_flatten_partial_depth(self):
        """Test flattening with specific depth"""
        from core.modules.atomic.array.flatten import ArrayFlattenModule

        module = ArrayFlattenModule(
            params={'array': [[1, [2, [3]]]], 'depth': 2},
            context={}
        )
        result = await module.execute()

        assert result['result'] == [1, 2, [3]]
        assert result['length'] == 3

    @pytest.mark.asyncio
    async def test_flatten_already_flat(self):
        """Test flattening already flat array"""
        from core.modules.atomic.array.flatten import ArrayFlattenModule

        module = ArrayFlattenModule(
            params={'array': [1, 2, 3, 4], 'depth': 1},
            context={}
        )
        result = await module.execute()

        assert result['result'] == [1, 2, 3, 4]
        assert result['length'] == 4

    @pytest.mark.asyncio
    async def test_flatten_empty_array(self):
        """Test flattening empty array"""
        from core.modules.atomic.array.flatten import ArrayFlattenModule

        module = ArrayFlattenModule(
            params={'array': [], 'depth': 1},
            context={}
        )
        result = await module.execute()

        assert result['result'] == []
        assert result['length'] == 0

    @pytest.mark.asyncio
    async def test_flatten_zero_depth(self):
        """Test flattening with zero depth (no change)"""
        from core.modules.atomic.array.flatten import ArrayFlattenModule

        module = ArrayFlattenModule(
            params={'array': [[1, 2], [3, 4]], 'depth': 0},
            context={}
        )
        result = await module.execute()

        assert result['result'] == [[1, 2], [3, 4]]
        assert result['length'] == 2

    def test_flatten_invalid_array(self):
        """Test validation with non-list input"""
        from core.modules.atomic.array.flatten import ArrayFlattenModule

        with pytest.raises(ValueError, match="array must be a list"):
            ArrayFlattenModule(
                params={'array': "not a list", 'depth': 1},
                context={}
            )


class TestArrayUniqueModule:
    """Tests for array_unique module (function wrapped as class)"""

    @pytest.mark.asyncio
    async def test_unique_basic(self):
        """Test basic deduplication"""
        from core.modules.atomic.array.unique import array_unique

        # Function modules are wrapped as classes by @register_module
        module = array_unique(
            params={'array': [1, 2, 2, 3, 4, 3, 5], 'preserve_order': True},
            context={}
        )
        result = await module.execute()

        assert result['unique'] == [1, 2, 3, 4, 5]
        assert result['count'] == 5
        assert result['duplicates_removed'] == 2

    @pytest.mark.asyncio
    async def test_unique_no_duplicates(self):
        """Test array with no duplicates"""
        from core.modules.atomic.array.unique import array_unique

        module = array_unique(
            params={'array': [1, 2, 3, 4, 5], 'preserve_order': True},
            context={}
        )
        result = await module.execute()

        assert result['unique'] == [1, 2, 3, 4, 5]
        assert result['count'] == 5
        assert result['duplicates_removed'] == 0

    @pytest.mark.asyncio
    async def test_unique_all_duplicates(self):
        """Test array with all same elements"""
        from core.modules.atomic.array.unique import array_unique

        module = array_unique(
            params={'array': [1, 1, 1, 1, 1], 'preserve_order': True},
            context={}
        )
        result = await module.execute()

        assert result['unique'] == [1]
        assert result['count'] == 1
        assert result['duplicates_removed'] == 4

    @pytest.mark.asyncio
    async def test_unique_empty_array(self):
        """Test empty array"""
        from core.modules.atomic.array.unique import array_unique

        module = array_unique(
            params={'array': [], 'preserve_order': True},
            context={}
        )
        result = await module.execute()

        assert result['unique'] == []
        assert result['count'] == 0
        assert result['duplicates_removed'] == 0

    @pytest.mark.asyncio
    async def test_unique_strings(self):
        """Test deduplication with strings"""
        from core.modules.atomic.array.unique import array_unique

        module = array_unique(
            params={'array': ['a', 'b', 'a', 'c', 'b'], 'preserve_order': True},
            context={}
        )
        result = await module.execute()

        assert result['unique'] == ['a', 'b', 'c']
        assert result['count'] == 3

    @pytest.mark.asyncio
    async def test_unique_without_preserve_order(self):
        """Test deduplication without preserving order"""
        from core.modules.atomic.array.unique import array_unique

        module = array_unique(
            params={'array': [3, 1, 2, 1, 3], 'preserve_order': False},
            context={}
        )
        result = await module.execute()

        assert set(result['unique']) == {1, 2, 3}
        assert result['count'] == 3


class TestArraySortModule:
    """Tests for array_sort module (function wrapped as class)"""

    @pytest.mark.asyncio
    async def test_sort_ascending(self):
        """Test ascending sort"""
        from core.modules.atomic.array.sort import array_sort

        module = array_sort(
            params={'array': [5, 2, 8, 1, 9], 'order': 'asc'},
            context={}
        )
        result = await module.execute()

        assert result['sorted'] == [1, 2, 5, 8, 9]
        assert result['count'] == 5

    @pytest.mark.asyncio
    async def test_sort_descending(self):
        """Test descending sort"""
        from core.modules.atomic.array.sort import array_sort

        module = array_sort(
            params={'array': [5, 2, 8, 1, 9], 'order': 'desc'},
            context={}
        )
        result = await module.execute()

        assert result['sorted'] == [9, 8, 5, 2, 1]
        assert result['count'] == 5

    @pytest.mark.asyncio
    async def test_sort_default_order(self):
        """Test default ascending order"""
        from core.modules.atomic.array.sort import array_sort

        module = array_sort(
            params={'array': [3, 1, 4, 1, 5]},
            context={}
        )
        result = await module.execute()

        assert result['sorted'] == [1, 1, 3, 4, 5]

    @pytest.mark.asyncio
    async def test_sort_strings(self):
        """Test sorting strings"""
        from core.modules.atomic.array.sort import array_sort

        module = array_sort(
            params={'array': ['banana', 'apple', 'cherry'], 'order': 'asc'},
            context={}
        )
        result = await module.execute()

        assert result['sorted'] == ['apple', 'banana', 'cherry']

    @pytest.mark.asyncio
    async def test_sort_empty_array(self):
        """Test sorting empty array"""
        from core.modules.atomic.array.sort import array_sort

        module = array_sort(
            params={'array': [], 'order': 'asc'},
            context={}
        )
        result = await module.execute()

        assert result['sorted'] == []
        assert result['count'] == 0

    @pytest.mark.asyncio
    async def test_sort_single_element(self):
        """Test sorting single element array"""
        from core.modules.atomic.array.sort import array_sort

        module = array_sort(
            params={'array': [42], 'order': 'asc'},
            context={}
        )
        result = await module.execute()

        assert result['sorted'] == [42]
        assert result['count'] == 1


class TestArrayJoinModule:
    """Tests for ArrayJoinModule"""

    @pytest.mark.asyncio
    async def test_join_basic(self):
        """Test basic array joining"""
        from core.modules.atomic.array.join import ArrayJoinModule

        module = ArrayJoinModule(
            params={'array': ['apple', 'banana', 'cherry'], 'separator': ', '},
            context={}
        )
        result = await module.execute()

        assert result['result'] == 'apple, banana, cherry'

    @pytest.mark.asyncio
    async def test_join_default_separator(self):
        """Test joining with default comma separator"""
        from core.modules.atomic.array.join import ArrayJoinModule

        module = ArrayJoinModule(
            params={'array': ['a', 'b', 'c']},
            context={}
        )
        result = await module.execute()

        assert result['result'] == 'a,b,c'

    @pytest.mark.asyncio
    async def test_join_newline_separator(self):
        """Test joining with newline separator"""
        from core.modules.atomic.array.join import ArrayJoinModule

        module = ArrayJoinModule(
            params={'array': ['Line 1', 'Line 2', 'Line 3'], 'separator': '\n'},
            context={}
        )
        result = await module.execute()

        assert result['result'] == 'Line 1\nLine 2\nLine 3'

    @pytest.mark.asyncio
    async def test_join_numbers(self):
        """Test joining numbers (converts to strings)"""
        from core.modules.atomic.array.join import ArrayJoinModule

        module = ArrayJoinModule(
            params={'array': [1, 2, 3], 'separator': '-'},
            context={}
        )
        result = await module.execute()

        assert result['result'] == '1-2-3'

    @pytest.mark.asyncio
    async def test_join_empty_array(self):
        """Test joining empty array"""
        from core.modules.atomic.array.join import ArrayJoinModule

        module = ArrayJoinModule(
            params={'array': [], 'separator': ','},
            context={}
        )
        result = await module.execute()

        assert result['result'] == ''

    @pytest.mark.asyncio
    async def test_join_single_element(self):
        """Test joining single element"""
        from core.modules.atomic.array.join import ArrayJoinModule

        module = ArrayJoinModule(
            params={'array': ['only'], 'separator': ','},
            context={}
        )
        result = await module.execute()

        assert result['result'] == 'only'

    def test_join_invalid_array(self):
        """Test validation with non-list input"""
        from core.modules.atomic.array.join import ArrayJoinModule

        with pytest.raises(ValueError, match="array must be a list"):
            ArrayJoinModule(
                params={'array': "not a list", 'separator': ','},
                context={}
            )


class TestArrayDifferenceModule:
    """Tests for ArrayDifferenceModule"""

    @pytest.mark.asyncio
    async def test_difference_basic(self):
        """Test basic array difference"""
        from core.modules.atomic.array.difference import ArrayDifferenceModule

        module = ArrayDifferenceModule(
            params={'array': [1, 2, 3, 4, 5], 'subtract': [[2, 4], [5]]},
            context={}
        )
        result = await module.execute()

        assert set(result['result']) == {1, 3}
        assert result['length'] == 2

    @pytest.mark.asyncio
    async def test_difference_no_overlap(self):
        """Test difference with no overlapping elements"""
        from core.modules.atomic.array.difference import ArrayDifferenceModule

        module = ArrayDifferenceModule(
            params={'array': [1, 2, 3], 'subtract': [[4, 5, 6]]},
            context={}
        )
        result = await module.execute()

        assert set(result['result']) == {1, 2, 3}
        assert result['length'] == 3

    @pytest.mark.asyncio
    async def test_difference_complete_subtraction(self):
        """Test difference that removes all elements"""
        from core.modules.atomic.array.difference import ArrayDifferenceModule

        module = ArrayDifferenceModule(
            params={'array': [1, 2, 3], 'subtract': [[1, 2, 3]]},
            context={}
        )
        result = await module.execute()

        assert result['result'] == []
        assert result['length'] == 0

    @pytest.mark.asyncio
    async def test_difference_empty_subtract(self):
        """Test difference with empty subtract arrays"""
        from core.modules.atomic.array.difference import ArrayDifferenceModule

        module = ArrayDifferenceModule(
            params={'array': [1, 2, 3], 'subtract': []},
            context={}
        )
        result = await module.execute()

        assert set(result['result']) == {1, 2, 3}

    def test_difference_invalid_array(self):
        """Test validation with non-list input"""
        from core.modules.atomic.array.difference import ArrayDifferenceModule

        with pytest.raises(ValueError, match="array must be a list"):
            ArrayDifferenceModule(
                params={'array': "not a list", 'subtract': [[1, 2]]},
                context={}
            )


class TestArrayIntersectionModule:
    """Tests for ArrayIntersectionModule"""

    @pytest.mark.asyncio
    async def test_intersection_basic(self):
        """Test basic array intersection"""
        from core.modules.atomic.array.intersection import ArrayIntersectionModule

        module = ArrayIntersectionModule(
            params={'arrays': [[1, 2, 3, 4], [2, 3, 5], [2, 3, 6]]},
            context={}
        )
        result = await module.execute()

        assert set(result['result']) == {2, 3}
        assert result['length'] == 2

    @pytest.mark.asyncio
    async def test_intersection_two_arrays(self):
        """Test intersection of two arrays"""
        from core.modules.atomic.array.intersection import ArrayIntersectionModule

        module = ArrayIntersectionModule(
            params={'arrays': [[1, 2, 3], [2, 3, 4]]},
            context={}
        )
        result = await module.execute()

        assert set(result['result']) == {2, 3}
        assert result['length'] == 2

    @pytest.mark.asyncio
    async def test_intersection_no_common(self):
        """Test intersection with no common elements"""
        from core.modules.atomic.array.intersection import ArrayIntersectionModule

        module = ArrayIntersectionModule(
            params={'arrays': [[1, 2], [3, 4], [5, 6]]},
            context={}
        )
        result = await module.execute()

        assert result['result'] == []
        assert result['length'] == 0

    @pytest.mark.asyncio
    async def test_intersection_identical_arrays(self):
        """Test intersection of identical arrays"""
        from core.modules.atomic.array.intersection import ArrayIntersectionModule

        module = ArrayIntersectionModule(
            params={'arrays': [[1, 2, 3], [1, 2, 3], [1, 2, 3]]},
            context={}
        )
        result = await module.execute()

        assert set(result['result']) == {1, 2, 3}
        assert result['length'] == 3

    def test_intersection_invalid_single_array(self):
        """Test validation with single array"""
        from core.modules.atomic.array.intersection import ArrayIntersectionModule

        with pytest.raises(ValueError, match="arrays must be a list with at least 2 arrays"):
            ArrayIntersectionModule(
                params={'arrays': [[1, 2, 3]]},
                context={}
            )

    def test_intersection_invalid_input(self):
        """Test validation with non-list input"""
        from core.modules.atomic.array.intersection import ArrayIntersectionModule

        with pytest.raises(ValueError, match="arrays must be a list with at least 2 arrays"):
            ArrayIntersectionModule(
                params={'arrays': "not a list"},
                context={}
            )
