"""
Tests for data.* modules

Tests all data manipulation modules:
- data.json.parse
- data.json.stringify
- data.text.template
"""

import pytest
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))


class TestDataJsonParse:
    """Tests for data.json.parse module."""

    MODULE_ID = "data.json.parse"

    @pytest.fixture
    def module_class(self):
        from core.modules.registry import ModuleRegistry
        from core.modules import atomic
        return ModuleRegistry.get(self.MODULE_ID)

    @pytest.mark.asyncio
    async def test_parse_object(self, module_class):
        """Test parsing JSON object."""
        instance = module_class({
            "json_string": '{"name": "John", "age": 30}'
        }, {})
        result = await instance.execute()
        assert result["status"] == "success"
        assert result["data"] == {"name": "John", "age": 30}

    @pytest.mark.asyncio
    async def test_parse_array(self, module_class):
        """Test parsing JSON array."""
        instance = module_class({
            "json_string": '[1, 2, 3]'
        }, {})
        result = await instance.execute()
        assert result["status"] == "success"
        assert result["data"] == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_invalid_json(self, module_class):
        """Test with invalid JSON."""
        instance = module_class({
            "json_string": 'not valid json'
        }, {})
        result = await instance.execute()
        assert result["status"] == "error"
        assert "Invalid JSON" in result["message"]

    @pytest.mark.asyncio
    async def test_missing_param(self, module_class):
        """Test missing json_string parameter."""
        instance = module_class({}, {})
        result = await instance.execute()
        assert result.get("ok") is False


class TestDataJsonStringify:
    """Tests for data.json.stringify module."""

    MODULE_ID = "data.json.stringify"

    @pytest.fixture
    def module_class(self):
        from core.modules.registry import ModuleRegistry
        from core.modules import atomic
        return ModuleRegistry.get(self.MODULE_ID)

    @pytest.mark.asyncio
    async def test_stringify_object(self, module_class):
        """Test stringifying object."""
        instance = module_class({
            "data": {"name": "John", "age": 30}
        }, {})
        result = await instance.execute()
        assert result["status"] == "success"
        import json
        assert json.loads(result["json"]) == {"name": "John", "age": 30}

    @pytest.mark.asyncio
    async def test_stringify_pretty(self, module_class):
        """Test stringifying with pretty print."""
        instance = module_class({
            "data": {"name": "John"},
            "pretty": True,
            "indent": 2
        }, {})
        result = await instance.execute()
        assert result["status"] == "success"
        assert "\n" in result["json"]

    @pytest.mark.asyncio
    async def test_stringify_array(self, module_class):
        """Test stringifying array."""
        instance = module_class({
            "data": [1, 2, 3]
        }, {})
        result = await instance.execute()
        assert result["status"] == "success"
        assert result["json"] == "[1, 2, 3]"


class TestDataTextTemplate:
    """Tests for data.text.template module."""

    MODULE_ID = "data.text.template"

    @pytest.fixture
    def module_class(self):
        from core.modules.registry import ModuleRegistry
        from core.modules import atomic
        return ModuleRegistry.get(self.MODULE_ID)

    @pytest.mark.asyncio
    async def test_basic_template(self, module_class):
        """Test basic template filling."""
        instance = module_class({
            "template": "Hello {name}, you scored {score} points!",
            "variables": {"name": "Alice", "score": 95}
        }, {})
        result = await instance.execute()
        assert result["status"] == "success"
        assert result["result"] == "Hello Alice, you scored 95 points!"

    @pytest.mark.asyncio
    async def test_missing_variable(self, module_class):
        """Test template with missing variable."""
        instance = module_class({
            "template": "Hello {name}, {missing}!",
            "variables": {"name": "Alice"}
        }, {})
        result = await instance.execute()
        assert result["status"] == "error"
        assert "Missing variable" in result["message"]

    @pytest.mark.asyncio
    async def test_no_placeholders(self, module_class):
        """Test template without placeholders."""
        instance = module_class({
            "template": "Hello World!",
            "variables": {}
        }, {})
        result = await instance.execute()
        assert result["status"] == "success"
        assert result["result"] == "Hello World!"

    @pytest.mark.asyncio
    async def test_invalid_variables_type(self, module_class):
        """Test with invalid variables type."""
        instance = module_class({
            "template": "Hello {name}",
            "variables": "not an object"
        }, {})
        result = await instance.execute()
        assert result.get("ok") is False
