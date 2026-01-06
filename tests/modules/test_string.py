"""
Tests for string.* modules

Tests all string manipulation modules:
- string.uppercase
- string.lowercase
- string.trim
- string.split
- string.replace
- string.reverse
- string.titlecase
"""

import pytest
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))


class TestStringUppercase:
    """Tests for string.uppercase module."""

    MODULE_ID = "string.uppercase"

    @pytest.fixture
    def module_class(self):
        from core.modules.registry import ModuleRegistry
        from core.modules import atomic
        return ModuleRegistry.get(self.MODULE_ID)

    @pytest.mark.asyncio
    async def test_basic_uppercase(self, module_class):
        """Test basic uppercase conversion."""
        instance = module_class({"text": "hello"}, {})
        result = await instance.execute()
        assert result["result"] == "HELLO"
        assert result["original"] == "hello"
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_mixed_case(self, module_class):
        """Test mixed case input."""
        instance = module_class({"text": "Hello World"}, {})
        result = await instance.execute()
        assert result["result"] == "HELLO WORLD"

    @pytest.mark.asyncio
    async def test_empty_string(self, module_class):
        """Test empty string input."""
        instance = module_class({"text": ""}, {})
        result = await instance.execute()
        assert result["result"] == ""

    @pytest.mark.asyncio
    async def test_missing_param(self, module_class):
        """Test missing text parameter."""
        instance = module_class({}, {})
        result = await instance.execute()
        assert result.get("ok") is False
        assert "error" in result


class TestStringLowercase:
    """Tests for string.lowercase module."""

    MODULE_ID = "string.lowercase"

    @pytest.fixture
    def module_class(self):
        from core.modules.registry import ModuleRegistry
        from core.modules import atomic
        return ModuleRegistry.get(self.MODULE_ID)

    @pytest.mark.asyncio
    async def test_basic_lowercase(self, module_class):
        """Test basic lowercase conversion."""
        instance = module_class({"text": "HELLO"}, {})
        result = await instance.execute()
        assert result["result"] == "hello"

    @pytest.mark.asyncio
    async def test_mixed_case(self, module_class):
        """Test mixed case input."""
        instance = module_class({"text": "Hello World"}, {})
        result = await instance.execute()
        assert result["result"] == "hello world"


class TestStringTrim:
    """Tests for string.trim module."""

    MODULE_ID = "string.trim"

    @pytest.fixture
    def module_class(self):
        from core.modules.registry import ModuleRegistry
        from core.modules import atomic
        return ModuleRegistry.get(self.MODULE_ID)

    @pytest.mark.asyncio
    async def test_trim_spaces(self, module_class):
        """Test trimming leading/trailing spaces."""
        instance = module_class({"text": "  hello  "}, {})
        result = await instance.execute()
        assert result["result"] == "hello"

    @pytest.mark.asyncio
    async def test_trim_tabs_newlines(self, module_class):
        """Test trimming tabs and newlines."""
        instance = module_class({"text": "\t\nhello\n\t"}, {})
        result = await instance.execute()
        assert result["result"] == "hello"

    @pytest.mark.asyncio
    async def test_no_trim_needed(self, module_class):
        """Test string without whitespace."""
        instance = module_class({"text": "hello"}, {})
        result = await instance.execute()
        assert result["result"] == "hello"


class TestStringSplit:
    """Tests for string.split module."""

    MODULE_ID = "string.split"

    @pytest.fixture
    def module_class(self):
        from core.modules.registry import ModuleRegistry
        from core.modules import atomic
        return ModuleRegistry.get(self.MODULE_ID)

    @pytest.mark.asyncio
    async def test_split_by_space(self, module_class):
        """Test splitting by space (default)."""
        instance = module_class({"text": "hello world foo"}, {})
        result = await instance.execute()
        assert result["parts"] == ["hello", "world", "foo"]
        assert result["length"] == 3

    @pytest.mark.asyncio
    async def test_split_by_comma(self, module_class):
        """Test splitting by comma."""
        instance = module_class({"text": "a,b,c", "delimiter": ","}, {})
        result = await instance.execute()
        assert result["parts"] == ["a", "b", "c"]

    @pytest.mark.asyncio
    async def test_split_no_delimiter(self, module_class):
        """Test string without delimiter."""
        instance = module_class({"text": "hello", "delimiter": ","}, {})
        result = await instance.execute()
        assert result["parts"] == ["hello"]
        assert result["length"] == 1


class TestStringReplace:
    """Tests for string.replace module."""

    MODULE_ID = "string.replace"

    @pytest.fixture
    def module_class(self):
        from core.modules.registry import ModuleRegistry
        from core.modules import atomic
        return ModuleRegistry.get(self.MODULE_ID)

    @pytest.mark.asyncio
    async def test_basic_replace(self, module_class):
        """Test basic string replacement."""
        instance = module_class({
            "text": "hello world",
            "search": "world",
            "replace": "flyto"
        }, {})
        result = await instance.execute()
        assert result["result"] == "hello flyto"

    @pytest.mark.asyncio
    async def test_replace_multiple(self, module_class):
        """Test replacing multiple occurrences."""
        instance = module_class({
            "text": "aaa",
            "search": "a",
            "replace": "b"
        }, {})
        result = await instance.execute()
        assert result["result"] == "bbb"

    @pytest.mark.asyncio
    async def test_replace_not_found(self, module_class):
        """Test when search string not found."""
        instance = module_class({
            "text": "hello",
            "search": "x",
            "replace": "y"
        }, {})
        result = await instance.execute()
        assert result["result"] == "hello"


class TestStringReverse:
    """Tests for string.reverse module."""

    MODULE_ID = "string.reverse"

    @pytest.fixture
    def module_class(self):
        from core.modules.registry import ModuleRegistry
        from core.modules import atomic
        return ModuleRegistry.get(self.MODULE_ID)

    @pytest.mark.asyncio
    async def test_basic_reverse(self, module_class):
        """Test basic string reversal."""
        instance = module_class({"text": "hello"}, {})
        result = await instance.execute()
        assert result["result"] == "olleh"
        assert result["length"] == 5

    @pytest.mark.asyncio
    async def test_reverse_palindrome(self, module_class):
        """Test palindrome reversal."""
        instance = module_class({"text": "racecar"}, {})
        result = await instance.execute()
        assert result["result"] == "racecar"

    @pytest.mark.asyncio
    async def test_reverse_empty(self, module_class):
        """Test empty string reversal."""
        instance = module_class({"text": ""}, {})
        result = await instance.execute()
        assert result["result"] == ""


class TestStringTitlecase:
    """Tests for string.titlecase module."""

    MODULE_ID = "string.titlecase"

    @pytest.fixture
    def module_class(self):
        from core.modules.registry import ModuleRegistry
        from core.modules import atomic
        return ModuleRegistry.get(self.MODULE_ID)

    @pytest.mark.asyncio
    async def test_basic_titlecase(self, module_class):
        """Test basic title case conversion."""
        instance = module_class({"text": "hello world"}, {})
        result = await instance.execute()
        assert result["result"] == "Hello World"

    @pytest.mark.asyncio
    async def test_titlecase_mixed(self, module_class):
        """Test mixed case input."""
        instance = module_class({"text": "hELLO wORLD"}, {})
        result = await instance.execute()
        assert result["result"] == "Hello World"

    @pytest.mark.asyncio
    async def test_titlecase_single_word(self, module_class):
        """Test single word title case."""
        instance = module_class({"text": "flyto"}, {})
        result = await instance.execute()
        assert result["result"] == "Flyto"
