# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Unit tests for the closed-loop verify modules.

Covers:
- http.batch (schema, error paths, pattern detection, measure_time)
- test.assert_status (verdict mapping, edge cases)
- test.assert_timing (verdict mapping, error paths)
- test.assert_contains (legacy `collection+value` mode AND new verdict mode)

No network — uses a local HTTP mock on a random port.
"""
from __future__ import annotations

import asyncio
import http.server
import importlib
import socketserver
import threading
import time
import urllib.parse

import pytest

# Trigger registration of all four modules.
importlib.import_module("core.modules.atomic.http.batch")
importlib.import_module("core.modules.atomic.testing.assert_status")
importlib.import_module("core.modules.atomic.testing.assert_timing")
importlib.import_module("core.modules.atomic.testing.assert_contains")

from core.modules.atomic.http.batch import http_batch as HttpBatchModule
from core.modules.atomic.testing.assert_status import AssertStatusModule
from core.modules.atomic.testing.assert_timing import AssertTimingModule
from core.modules.atomic.testing.assert_contains import AssertContainsModule


# ---------------------------------------------------------------------------
# Mock target
# ---------------------------------------------------------------------------

class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args, **kwargs):
        return

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/ok":
            return self._send(200, "welcome")
        if parsed.path == "/block":
            return self._send(403, "forbidden")
        if parsed.path == "/slow":
            time.sleep(2.5)
            return self._send(200, "slow body")
        if parsed.path == "/leak":
            return self._send(500,
                "You have an error in your SQL syntax; check the manual")
        return self._send(404, "nope")

    def _send(self, status: int, body: str):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture(scope="module")
def base_url():
    server = socketserver.TCPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


async def _run_batch(params: dict) -> dict:
    """Invoke http.batch via its registered wrapper class."""
    instance = HttpBatchModule(params=params, context={})
    return await instance.execute()


# ---------------------------------------------------------------------------
# http.batch
# ---------------------------------------------------------------------------

class TestHttpBatch:
    @pytest.mark.asyncio
    async def test_rejects_empty_requests_list(self):
        out = await _run_batch({"requests": [], "ssrf_protection": False})
        assert out["ok"] is False
        assert "requests must be a non-empty list" in out["error"]

    @pytest.mark.asyncio
    async def test_parallel_happy_path(self, base_url):
        out = await _run_batch({
            "requests": [
                {"method": "GET", "url": f"{base_url}/ok", "label": "a"},
                {"method": "GET", "url": f"{base_url}/block", "label": "b"},
            ],
            "ssrf_protection": False,
        })
        assert out["ok"] is True
        assert out["count"] == 2
        assert out["failed_count"] == 1  # /block → 403, not ok
        statuses = [r["status"] for r in out["data"]]
        assert statuses == [200, 403]

    @pytest.mark.asyncio
    async def test_measure_time_captures_real_latency(self, base_url):
        out = await _run_batch({
            "requests": [
                {"method": "GET", "url": f"{base_url}/ok"},
                {"method": "GET", "url": f"{base_url}/slow"},
            ],
            "measure_time": True,
            "ssrf_protection": False,
            "timeout": 10,
        })
        assert out["ok"] is True
        assert out["data"][0]["duration_ms"] < 500
        assert out["data"][1]["duration_ms"] >= 2000

    @pytest.mark.asyncio
    async def test_pattern_detection_reports_matching_indices(self, base_url):
        out = await _run_batch({
            "requests": [
                {"method": "GET", "url": f"{base_url}/ok"},
                {"method": "GET", "url": f"{base_url}/leak"},
            ],
            "detect_patterns": ["SQL syntax", "never-there"],
            "ssrf_protection": False,
        })
        detected = {d["pattern"]: d["matches"] for d in out["detected"]}
        assert detected["SQL syntax"] == [1]
        assert detected["never-there"] == []

    @pytest.mark.asyncio
    async def test_ssrf_guard_blocks_loopback_by_default(self):
        """With SSRF on and default env config, 127.0.0.1 is rejected."""
        # This test depends on FLYTO_ALLOW_PRIVATE_NETWORK not being 'true'.
        import os
        prev = os.environ.pop("FLYTO_ALLOW_PRIVATE_NETWORK", None)
        try:
            out = await _run_batch({
                "requests": [
                    {"method": "GET", "url": "http://127.0.0.1:1/nope"},
                ],
                "ssrf_protection": True,
            })
            assert out["ok"] is False
            assert out.get("error_code") == "SSRF_BLOCKED"
        finally:
            if prev is not None:
                os.environ["FLYTO_ALLOW_PRIVATE_NETWORK"] = prev

    @pytest.mark.asyncio
    async def test_failed_request_captured_with_error(self, base_url):
        out = await _run_batch({
            "requests": [
                {"method": "GET", "url": "http://127.0.0.1:1/dead"},
            ],
            "ssrf_protection": False,
            "timeout": 2,
        })
        # Batch overall still "ok" (finished), but the individual request errored.
        assert out["ok"] is True
        assert out["failed_count"] == 1
        entry = out["data"][0]
        assert entry["ok"] is False
        assert entry["error"]


# ---------------------------------------------------------------------------
# test.assert_status
# ---------------------------------------------------------------------------

def _make_batch(*statuses, baseline_status=200):
    """Build a fake batch output with the given per-probe statuses."""
    data = [{
        "label": f"probe_{i}" if i else "baseline",
        "method": "GET",
        "url": "http://x",
        "status": s,
        "body": "",
        "duration_ms": 10,
        "ok": 200 <= s < 300,
        "error": None,
    } for i, s in enumerate(statuses)]
    return {"ok": True, "data": data, "count": len(data), "failed_count": 0}


class TestAssertStatus:
    @pytest.mark.asyncio
    async def test_reports_exploitable_when_probes_mirror_baseline(self):
        batch = _make_batch(200, 200, 200)
        mod = AssertStatusModule(
            params={"source": batch, "baseline_index": 0, "probe_indices": [1, 2]},
            context={},
        )
        r = await mod.execute()
        assert r["verdict"] == "exploitable"
        assert r["passed"] is False

    @pytest.mark.asyncio
    async def test_reports_sanitized_when_all_blocked(self):
        batch = _make_batch(200, 403, 401)
        mod = AssertStatusModule(
            params={"source": batch, "baseline_index": 0, "probe_indices": [1, 2]},
            context={},
        )
        r = await mod.execute()
        assert r["verdict"] == "sanitized"
        assert r["passed"] is True

    @pytest.mark.asyncio
    async def test_reports_unreachable_when_baseline_errors(self):
        batch = {"ok": True, "data": [
            {"status": None, "error": "timeout", "body": "", "duration_ms": 0},
            {"status": 403, "error": None, "body": "", "duration_ms": 5},
        ]}
        mod = AssertStatusModule(
            params={"source": batch, "baseline_index": 0, "probe_indices": [1]},
            context={},
        )
        r = await mod.execute()
        assert r["verdict"] == "unreachable"

    @pytest.mark.asyncio
    async def test_defaults_probe_indices_to_non_baseline(self):
        batch = _make_batch(200, 403)
        mod = AssertStatusModule(
            params={"source": batch, "baseline_index": 0},
            context={},
        )
        r = await mod.execute()
        assert r["verdict"] == "sanitized"
        assert [p["index"] for p in r["probes"]] == [1]

    @pytest.mark.asyncio
    async def test_accepts_raw_list_not_just_wrapper(self):
        batch = _make_batch(200, 200)
        mod = AssertStatusModule(
            params={"source": batch["data"], "baseline_index": 0, "probe_indices": [1]},
            context={},
        )
        r = await mod.execute()
        assert r["verdict"] == "exploitable"

    @pytest.mark.asyncio
    async def test_empty_source_reports_unreachable(self):
        mod = AssertStatusModule(
            params={"source": []},
            context={},
        )
        r = await mod.execute()
        assert r["verdict"] == "unreachable"

    @pytest.mark.asyncio
    async def test_missing_source_raises(self):
        with pytest.raises(ValueError):
            AssertStatusModule(params={}, context={})

    @pytest.mark.asyncio
    async def test_baseline_index_out_of_range_raises(self):
        batch = _make_batch(200)
        mod = AssertStatusModule(
            params={"source": batch, "baseline_index": 5},
            context={},
        )
        with pytest.raises(ValueError):
            await mod.execute()


# ---------------------------------------------------------------------------
# test.assert_timing
# ---------------------------------------------------------------------------

def _make_timed_batch(*durations):
    data = [{
        "label": f"r_{i}",
        "status": 200,
        "body": "",
        "duration_ms": d,
        "ok": True,
        "error": None,
    } for i, d in enumerate(durations)]
    return {"ok": True, "data": data, "count": len(data)}


class TestAssertTiming:
    @pytest.mark.asyncio
    async def test_reports_exploitable_when_delta_exceeds_threshold(self):
        batch = _make_timed_batch(10, 3500)
        mod = AssertTimingModule(
            params={"source": batch, "probe_index": 1, "threshold_ms": 2000},
            context={},
        )
        r = await mod.execute()
        assert r["verdict"] == "exploitable"
        assert r["delta_ms"] == 3490

    @pytest.mark.asyncio
    async def test_reports_inconclusive_below_threshold(self):
        batch = _make_timed_batch(10, 50)
        mod = AssertTimingModule(
            params={"source": batch, "probe_index": 1, "threshold_ms": 2000},
            context={},
        )
        r = await mod.execute()
        assert r["verdict"] == "inconclusive"

    @pytest.mark.asyncio
    async def test_reports_unreachable_when_probe_errors(self):
        batch = {"ok": True, "data": [
            {"status": 200, "duration_ms": 10, "error": None, "body": ""},
            {"status": None, "duration_ms": 0, "error": "timeout", "body": ""},
        ]}
        mod = AssertTimingModule(
            params={"source": batch, "probe_index": 1, "threshold_ms": 1000},
            context={},
        )
        r = await mod.execute()
        assert r["verdict"] == "unreachable"

    @pytest.mark.asyncio
    async def test_missing_probe_index_raises(self):
        with pytest.raises(ValueError):
            AssertTimingModule(params={"source": _make_timed_batch(10)}, context={})


# ---------------------------------------------------------------------------
# test.assert_contains — both modes
# ---------------------------------------------------------------------------

class TestAssertContainsLegacy:
    """The pre-existing single-value `collection + value` mode."""

    @pytest.mark.asyncio
    async def test_value_in_list(self):
        mod = AssertContainsModule(
            params={"collection": [1, 2, 3], "value": 2}, context={})
        r = await mod.execute()
        assert r["passed"] is True

    @pytest.mark.asyncio
    async def test_missing_value_raises_assertion(self):
        mod = AssertContainsModule(
            params={"collection": [1, 2, 3], "value": 99}, context={})
        with pytest.raises(AssertionError):
            await mod.execute()

    @pytest.mark.asyncio
    async def test_substring_in_string(self):
        mod = AssertContainsModule(
            params={"collection": "hello world", "value": "world"}, context={})
        r = await mod.execute()
        assert r["passed"] is True


class TestAssertContainsVerdict:
    """The new pentest `source + patterns + on_match/on_no_match` mode."""

    @pytest.mark.asyncio
    async def test_matches_any_pattern_returns_on_match(self):
        batch = {"data": [
            {"body": "You have an error in your SQL syntax"},
            {"body": "ok"},
        ]}
        mod = AssertContainsModule(
            params={
                "source": batch,
                "patterns": ["SQL syntax", "mysql_fetch"],
                "match_mode": "any",
                "on_match": "exploitable",
                "on_no_match": "sanitized",
            },
            context={},
        )
        r = await mod.execute()
        assert r["verdict"] == "exploitable"
        assert r["matched_patterns"] == ["SQL syntax"]

    @pytest.mark.asyncio
    async def test_no_match_returns_on_no_match(self):
        batch = {"data": [{"body": "completely fine"}]}
        mod = AssertContainsModule(
            params={
                "source": batch,
                "patterns": ["SQL syntax"],
                "match_mode": "any",
                "on_match": "exploitable",
                "on_no_match": "sanitized",
            },
            context={},
        )
        r = await mod.execute()
        assert r["verdict"] == "sanitized"

    @pytest.mark.asyncio
    async def test_match_mode_all_requires_every_pattern(self):
        batch = {"data": [{"body": "SQL syntax here"}]}
        mod = AssertContainsModule(
            params={
                "source": batch,
                "patterns": ["SQL syntax", "NOT THERE"],
                "match_mode": "all",
                "on_match": "exploitable",
                "on_no_match": "sanitized",
            },
            context={},
        )
        r = await mod.execute()
        assert r["verdict"] == "sanitized"

    @pytest.mark.asyncio
    async def test_raw_list_source_also_works(self):
        mod = AssertContainsModule(
            params={
                "source": [{"body": "mysql_fetch_array"}],
                "patterns": ["mysql_fetch"],
                "on_match": "exploitable",
                "on_no_match": "sanitized",
            },
            context={},
        )
        r = await mod.execute()
        assert r["verdict"] == "exploitable"
