"""
Unit tests for reverse.sourcemap (VLQ Source Map v3 resolution).

Pure text/decoding — no browser, no CDP, no @pytest.mark.browser. Runs in
the plain offline suite. The fixture's `mappings` string is built by hand
(via a small local VLQ encoder, independent of the module's decoder) with
manually-tracked deltas, so expected values below are computed by hand, not
copied from the implementation.
"""
import os
import sys
import base64
import json
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
os.environ.setdefault("FLYTO_ENV", "test")

from core.modules import atomic  # noqa: F401 — triggers registration
from core.modules.registry import ModuleRegistry


def get_module(mid):
    cls = ModuleRegistry.get(mid)
    assert cls is not None, f"{mid} not registered"
    return cls


async def run(params: dict) -> dict:
    cls = get_module("reverse.sourcemap")
    mod = cls(params, {})
    return await mod.execute()


# ─── Test-only VLQ encoder (independent of the module's decoder) ─────────

_B64_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"


def _encode_vlq(value: int) -> str:
    vlq = (-value << 1) | 1 if value < 0 else (value << 1)
    out = []
    while True:
        digit = vlq & 0x1F
        vlq >>= 5
        if vlq > 0:
            digit |= 0x20
        out.append(_B64_CHARS[digit])
        if vlq == 0:
            break
    return "".join(out)


def _encode_segment(values) -> str:
    return "".join(_encode_vlq(v) for v in values)


# Two generated lines, three segments. Deltas tracked by hand:
#   seg1 (line 0): genCol=2,  srcIdx=0, srcLine=0, srcCol=0, name=0 ("app")
#     — starts at column 2 (not 0) so a lookup before it (0,0) has no
#       covering segment, giving a real "no match" case to test.
#   seg2 (line 0): genCol=10 (delta 10-2=8), srcIdx=0 (delta 0), srcLine=0 (delta 0),
#                  srcCol=9 (delta +9), no name
#   seg3 (line 1): genCol=0 (resets), srcIdx=1 (delta +1), srcLine=2 (delta +2),
#                  srcCol=4 (delta 4-9=-5), name=1 ("helper", delta +1)
_MAPPINGS = (
    _encode_segment([2, 0, 0, 0, 0]) + "," + _encode_segment([8, 0, 0, 9])
    + ";" + _encode_segment([0, 1, 2, -5, 1])
)

SOURCE_MAP = {
    "version": 3,
    "sourceRoot": "src/",
    "sources": ["original/app.js", "original/util.js"],
    "sourcesContent": ["function app() {}\n", None],
    "names": ["app", "helper"],
    "mappings": _MAPPINGS,
}
SOURCE_MAP_TEXT = json.dumps(SOURCE_MAP)


class TestRegistration:
    def test_registered_no_permission_required(self):
        meta = ModuleRegistry.get_metadata("reverse.sourcemap")
        assert meta is not None
        assert meta["category"] == "reverse"
        assert meta["required_permissions"] == []


class TestResolve:
    @pytest.mark.asyncio
    async def test_resolves_first_segment_on_first_line(self):
        result = await run({"action": "resolve", "source_map": SOURCE_MAP_TEXT, "generated_line": 0, "generated_column": 2})
        assert result["status"] == "success"
        assert result["source"] == "src/original/app.js"
        assert result["originalLine"] == 0
        assert result["originalColumn"] == 0
        assert result["name"] == "app"

    @pytest.mark.asyncio
    async def test_resolves_second_segment_same_line(self):
        result = await run({"action": "resolve", "source_map": SOURCE_MAP_TEXT, "generated_line": 0, "generated_column": 10})
        assert result["status"] == "success"
        assert result["source"] == "src/original/app.js"
        assert result["originalLine"] == 0
        assert result["originalColumn"] == 9
        assert result["name"] is None

    @pytest.mark.asyncio
    async def test_resolves_segment_on_second_generated_line(self):
        result = await run({"action": "resolve", "source_map": SOURCE_MAP_TEXT, "generated_line": 1, "generated_column": 0})
        assert result["status"] == "success"
        assert result["source"] == "src/original/util.js"
        assert result["originalLine"] == 2
        assert result["originalColumn"] == 4
        assert result["name"] == "helper"

    @pytest.mark.asyncio
    async def test_nearest_preceding_segment_within_a_line(self):
        # Column 15 has no exact segment on line 0 — nearest preceding is genCol=10.
        result = await run({"action": "resolve", "source_map": SOURCE_MAP_TEXT, "generated_line": 0, "generated_column": 15})
        assert result["status"] == "success"
        assert result["originalColumn"] == 9

    @pytest.mark.asyncio
    async def test_location_before_any_segment_returns_null(self):
        # The first segment starts at generated column 2 — column 0 has no
        # covering segment.
        result = await run({"action": "resolve", "source_map": SOURCE_MAP_TEXT, "generated_line": 0, "generated_column": 0})
        assert result["status"] == "success"
        assert result["source"] is None
        assert result["originalLine"] is None
        assert result["originalColumn"] is None
        assert result["name"] is None

    @pytest.mark.asyncio
    async def test_resolves_inline_data_uri_source_map(self):
        encoded = base64.b64encode(SOURCE_MAP_TEXT.encode("utf-8")).decode("ascii")
        data_uri = f"data:application/json;charset=utf-8;base64,{encoded}"
        result = await run({"action": "resolve", "source_map": data_uri, "generated_line": 0, "generated_column": 2})
        assert result["status"] == "success"
        assert result["source"] == "src/original/app.js"
        assert result["name"] == "app"

    @pytest.mark.asyncio
    async def test_default_generated_column_is_zero(self):
        # Line 1's only segment sits exactly at column 0 — omitting
        # generated_column must default to 0 to resolve it, proving the
        # default is actually applied (not e.g. None, which would break the
        # bisect comparison).
        result = await run({"action": "resolve", "source_map": SOURCE_MAP_TEXT, "generated_line": 1})
        assert result["status"] == "success"
        assert result["source"] == "src/original/util.js"
        assert result["originalColumn"] == 4


class TestListSources:
    @pytest.mark.asyncio
    async def test_lists_sources_with_source_root_prepended(self):
        result = await run({"action": "list_sources", "source_map": SOURCE_MAP_TEXT})
        assert result["status"] == "success"
        sources = {s["source"]: s["hasContent"] for s in result["sources"]}
        assert sources == {
            "src/original/app.js": True,
            "src/original/util.js": False,
        }


class TestGetOriginalSource:
    @pytest.mark.asyncio
    async def test_returns_embedded_content_by_path(self):
        result = await run({
            "action": "get_original_source",
            "source_map": SOURCE_MAP_TEXT,
            "source": "src/original/app.js",
        })
        assert result["status"] == "success"
        assert result["content"] == "function app() {}\n"

    @pytest.mark.asyncio
    async def test_returns_embedded_content_by_index(self):
        result = await run({
            "action": "get_original_source",
            "source_map": SOURCE_MAP_TEXT,
            "source": "0",
        })
        assert result["status"] == "success"
        assert result["content"] == "function app() {}\n"

    @pytest.mark.asyncio
    async def test_reports_when_content_not_embedded(self):
        result = await run({
            "action": "get_original_source",
            "source_map": SOURCE_MAP_TEXT,
            "source": "src/original/util.js",
        })
        assert result["status"] == "success"
        assert result["content"] is None
        assert "not embedded" in result["error"]

    @pytest.mark.asyncio
    async def test_reports_unknown_source(self):
        result = await run({
            "action": "get_original_source",
            "source_map": SOURCE_MAP_TEXT,
            "source": "does/not/exist.js",
        })
        assert result["status"] == "success"
        assert result["content"] is None
        assert "Unknown source" in result["error"]


class TestValidation:
    def test_missing_source_map_raises(self):
        cls = get_module("reverse.sourcemap")
        with pytest.raises(ValueError, match="source_map"):
            cls({"action": "resolve", "generated_line": 0}, {})

    def test_invalid_action_raises(self):
        cls = get_module("reverse.sourcemap")
        with pytest.raises(ValueError, match="Invalid action"):
            cls({"action": "nope", "source_map": "{}"}, {})

    def test_resolve_without_generated_line_raises(self):
        cls = get_module("reverse.sourcemap")
        with pytest.raises(ValueError, match="generated_line"):
            cls({"action": "resolve", "source_map": "{}"}, {})

    def test_get_original_source_without_source_raises(self):
        cls = get_module("reverse.sourcemap")
        with pytest.raises(ValueError, match="source"):
            cls({"action": "get_original_source", "source_map": "{}"}, {})

    @pytest.mark.asyncio
    async def test_malformed_json_raises(self):
        cls = get_module("reverse.sourcemap")
        mod = cls({"action": "resolve", "source_map": "not json", "generated_line": 0}, {})
        with pytest.raises(ValueError, match="Invalid source map"):
            await mod.execute()
