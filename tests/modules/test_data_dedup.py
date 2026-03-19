"""Tests for data.dedup module."""
import json
import os
import sys
import tempfile
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
os.environ.setdefault("FLYTO_ENV", "test")

from core.modules import atomic  # noqa: F401
from core.modules.registry import ModuleRegistry


def get_module(module_id):
    cls = ModuleRegistry.get(module_id)
    assert cls is not None, f"{module_id} not registered"
    return cls


async def run(module_id, params, ctx=None):
    cls = get_module(module_id)
    mod = cls(params, ctx or {})
    return await mod.execute()


@pytest.mark.asyncio
class TestDataDedup:
    async def test_basic_dedup_by_key(self):
        items = [
            {"url": "https://a.com", "title": "A"},
            {"url": "https://b.com", "title": "B"},
            {"url": "https://a.com", "title": "A duplicate"},
        ]
        r = await run("data.dedup", {"items": items, "keys": ["url"]})
        assert r["status"] == "success"
        assert r["total_in"] == 3
        assert r["total_out"] == 2
        assert r["duplicates"] == 1

    async def test_dedup_all_fields(self):
        items = [
            {"x": 1, "y": 2},
            {"x": 1, "y": 2},
            {"x": 1, "y": 3},
        ]
        r = await run("data.dedup", {"items": items, "keys": []})
        assert r["total_out"] == 2

    async def test_no_duplicates(self):
        items = [{"id": 1}, {"id": 2}, {"id": 3}]
        r = await run("data.dedup", {"items": items, "keys": ["id"]})
        assert r["duplicates"] == 0
        assert r["total_out"] == 3

    async def test_empty_input(self):
        r = await run("data.dedup", {"items": [], "keys": ["id"]})
        assert r["total_out"] == 0
        assert r["duplicates"] == 0

    async def test_cross_run_persistence(self):
        hash_file = tempfile.mktemp(suffix=".json")
        try:
            items1 = [{"url": "https://a.com"}, {"url": "https://b.com"}]
            r1 = await run("data.dedup", {
                "items": items1, "keys": ["url"], "hash_file": hash_file
            })
            assert r1["total_out"] == 2
            assert Path(hash_file).exists()

            # Second run — a.com and b.com should be deduped
            items2 = [{"url": "https://b.com"}, {"url": "https://c.com"}]
            r2 = await run("data.dedup", {
                "items": items2, "keys": ["url"], "hash_file": hash_file
            })
            assert r2["total_out"] == 1  # Only c.com is new
            assert r2["duplicates"] == 1
            assert r2["items"][0]["url"] == "https://c.com"
        finally:
            Path(hash_file).unlink(missing_ok=True)

    async def test_multi_key_dedup(self):
        items = [
            {"host": "a.com", "path": "/1"},
            {"host": "a.com", "path": "/2"},
            {"host": "a.com", "path": "/1"},  # duplicate
        ]
        r = await run("data.dedup", {"items": items, "keys": ["host", "path"]})
        assert r["total_out"] == 2
