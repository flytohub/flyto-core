"""Tests for data.validate_records module."""
import os
import sys
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
os.environ.setdefault("FLYTO_ENV", "test")

from core.modules import atomic  # noqa: F401
from core.modules.registry import ModuleRegistry


async def run(module_id, params, ctx=None):
    cls = ModuleRegistry.get(module_id)
    assert cls is not None, f"{module_id} not registered"
    mod = cls(params, ctx or {})
    return await mod.execute()


@pytest.mark.asyncio
class TestDataValidateRecords:
    async def test_filter_mode_removes_invalid(self):
        items = [
            {"url": "https://a.com", "title": "Good"},
            {"url": "", "title": "Missing URL"},
            {"url": "https://b.com", "title": "Also good"},
        ]
        r = await run("data.validate_records", {
            "items": items,
            "rules": {"url": ["required", "is_url"]},
            "mode": "filter",
        })
        assert r["valid_count"] == 2
        assert r["invalid_count"] == 1
        assert len(r["items"]) == 2

    async def test_flag_mode_keeps_all(self):
        items = [
            {"price": "29.99"},
            {"price": ""},
        ]
        r = await run("data.validate_records", {
            "items": items,
            "rules": {"price": ["required"]},
            "mode": "flag",
        })
        assert len(r["items"]) == 2
        assert r["items"][0]["_valid"] is True
        assert r["items"][1]["_valid"] is False
        assert len(r["items"][1]["_errors"]) > 0

    async def test_strict_mode_raises(self):
        items = [{"name": ""}]
        with pytest.raises(ValueError, match="invalid records"):
            await run("data.validate_records", {
                "items": items,
                "rules": {"name": ["required"]},
                "mode": "strict",
            })

    async def test_is_url_validator(self):
        items = [
            {"link": "https://example.com"},
            {"link": "not-a-url"},
            {"link": "ftp://wrong.com"},
        ]
        r = await run("data.validate_records", {
            "items": items,
            "rules": {"link": ["is_url"]},
        })
        assert r["valid_count"] == 1
        assert r["invalid_count"] == 2

    async def test_is_email_validator(self):
        items = [
            {"email": "user@example.com"},
            {"email": "invalid"},
        ]
        r = await run("data.validate_records", {
            "items": items,
            "rules": {"email": ["is_email"]},
        })
        assert r["valid_count"] == 1

    async def test_min_length_validator(self):
        items = [
            {"title": "OK title here"},
            {"title": "AB"},
        ]
        r = await run("data.validate_records", {
            "items": items,
            "rules": {"title": ["min_length:3"]},
        })
        assert r["valid_count"] == 1
        assert r["invalid_count"] == 1

    async def test_is_number_validator(self):
        items = [
            {"price": 29.99},
            {"price": "19.50"},
            {"price": "free"},
        ]
        r = await run("data.validate_records", {
            "items": items,
            "rules": {"price": ["is_number"]},
        })
        assert r["valid_count"] == 2  # numeric and numeric string
        assert r["invalid_count"] == 1

    async def test_drop_fields(self):
        items = [{"url": "https://a.com", "__index": 0, "html": "<div>"}]
        r = await run("data.validate_records", {
            "items": items,
            "rules": {"url": ["required"]},
            "drop_fields": ["__index", "html"],
        })
        assert "__index" not in r["items"][0]
        assert "html" not in r["items"][0]
        assert "url" in r["items"][0]

    async def test_multiple_rules_per_field(self):
        items = [
            {"url": "https://example.com/long-path"},
            {"url": "https://x.co"},
            {"url": ""},
        ]
        r = await run("data.validate_records", {
            "items": items,
            "rules": {"url": ["required", "is_url", "min_length:15"]},
        })
        assert r["valid_count"] == 1  # Only first passes all 3 rules

    async def test_empty_input(self):
        r = await run("data.validate_records", {
            "items": [],
            "rules": {"x": ["required"]},
        })
        assert r["valid_count"] == 0
        assert r["invalid_count"] == 0

    async def test_matches_regex(self):
        items = [
            {"sku": "ABC-123"},
            {"sku": "invalid"},
        ]
        r = await run("data.validate_records", {
            "items": items,
            "rules": {"sku": ["matches:^[A-Z]+-\\d+$"]},
        })
        assert r["valid_count"] == 1
