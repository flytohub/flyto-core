"""
Unit tests for reverse.code (Phase 3 — beautify + AST structural search).

Pure text/AST processing — no browser, no CDP, no @pytest.mark.browser. Runs
in the plain offline suite.
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
os.environ.setdefault("FLYTO_ENV", "test")

from core.modules import atomic  # noqa: F401 — triggers registration
from core.modules.errors import ModuleError
from core.modules.registry import ModuleRegistry


def get_module(mid):
    cls = ModuleRegistry.get(mid)
    assert cls is not None, f"{mid} not registered"
    return cls


async def run(params: dict) -> dict:
    cls = get_module("reverse.code")
    mod = cls(params, {})  # BaseModule.__init__ calls validate_params()
    return await mod.execute()


SAMPLE_JS = """function computeSecret(x){var y=x*2;return y;}
const login=function(u,p){return fetch('/api/login',{method:'POST'});};
const helper=(a,b)=>a+b;
class Foo{bar(){return 1;}}
var TOKEN_URL='https://example.com/token';
obj.method(1,2,3);
plainCall(4,5);
"""


class TestRegistration:
    def test_registered_no_permission_required(self):
        meta = ModuleRegistry.get_metadata("reverse.code")
        assert meta is not None
        assert meta["category"] == "reverse"
        assert meta["required_permissions"] == []


class TestBeautify:
    @pytest.mark.asyncio
    async def test_beautify_reformats_minified_source(self):
        result = await run({"action": "beautify", "source": "function a(x){var y=x*2;return y;}"})
        assert result["status"] == "success"
        assert "function a(x)" in result["formatted"]
        assert result["formatted"].count("\n") >= 2  # reformatted onto multiple lines


class TestListFunctions:
    @pytest.mark.asyncio
    async def test_finds_all_function_kinds(self):
        result = await run({"action": "list_functions", "source": SAMPLE_JS})
        assert result["status"] == "success"
        names = {f["name"] for f in result["functions"]}
        assert names == {"computeSecret", "login", "helper", "bar"}
        assert result["count"] == 4

    @pytest.mark.asyncio
    async def test_function_declaration_has_line_range(self):
        result = await run({"action": "list_functions", "source": SAMPLE_JS})
        computed = next(f for f in result["functions"] if f["name"] == "computeSecret")
        assert computed["startLine"] == 0
        assert computed["endLine"] == 0


class TestListStrings:
    @pytest.mark.asyncio
    async def test_finds_string_literals(self):
        result = await run({"action": "list_strings", "source": SAMPLE_JS})
        assert result["status"] == "success"
        values = [s["value"] for s in result["strings"]]
        assert any("api/login" in v for v in values)
        assert any("example.com/token" in v for v in values)
        assert any("POST" in v for v in values)


class TestFindCalls:
    @pytest.mark.asyncio
    async def test_finds_plain_identifier_call(self):
        result = await run({"action": "find_calls", "source": SAMPLE_JS, "function_name": "plainCall"})
        assert result["status"] == "success"
        assert result["count"] == 1
        assert result["calls"][0]["argsText"] == "(4,5)"

    @pytest.mark.asyncio
    async def test_finds_member_expression_call(self):
        result = await run({"action": "find_calls", "source": SAMPLE_JS, "function_name": "obj.method"})
        assert result["status"] == "success"
        assert result["count"] == 1
        assert result["calls"][0]["argsText"] == "(1,2,3)"

    @pytest.mark.asyncio
    async def test_no_match_returns_empty(self):
        result = await run({"action": "find_calls", "source": SAMPLE_JS, "function_name": "neverCalled"})
        assert result["status"] == "success"
        assert result["count"] == 0
        assert result["calls"] == []


class TestValidation:
    def test_missing_source_raises(self):
        cls = get_module("reverse.code")
        with pytest.raises(ValueError, match="source"):
            cls({"action": "beautify"}, {})

    def test_invalid_action_raises(self):
        cls = get_module("reverse.code")
        with pytest.raises(ValueError, match="Invalid action"):
            cls({"action": "nope", "source": "1"}, {})

    def test_find_calls_without_function_name_raises(self):
        cls = get_module("reverse.code")
        with pytest.raises(ValueError, match="function_name"):
            cls({"action": "find_calls", "source": "f()"}, {})


class TestMissingOptionalDependency:
    @pytest.mark.asyncio
    async def test_beautify_reports_install_instructions_when_jsbeautifier_absent(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "jsbeautifier", None)
        with pytest.raises(ModuleError, match=r"pip install 'flyto-core\[jsast\]'"):
            await run({"action": "beautify", "source": "a()"})

    @pytest.mark.asyncio
    async def test_list_functions_reports_install_instructions_when_tree_sitter_absent(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "tree_sitter", None)
        with pytest.raises(ModuleError, match=r"pip install 'flyto-core\[jsast\]'"):
            await run({"action": "list_functions", "source": "function a(){}"})
