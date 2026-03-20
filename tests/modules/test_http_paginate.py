"""Tests for http.paginate module helpers and strategy dispatch."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from core.modules.atomic.http.paginate import (
    _merge_query,
    _extract_by_path,
    _parse_link_header,
    _extract_items,
    _paginate_offset,
    _paginate_page,
    _paginate_cursor,
    _paginate_link_header,
    _STRATEGY_DISPATCH,
)


# ── _merge_query ──

class TestMergeQuery:
    def test_add_params_to_clean_url(self):
        result = _merge_query("https://api.example.com/users", {"offset": 0, "limit": 10})
        assert "offset=0" in result
        assert "limit=10" in result

    def test_merge_with_existing_params(self):
        result = _merge_query("https://api.example.com/users?foo=bar", {"page": 2})
        assert "foo=bar" in result
        assert "page=2" in result

    def test_overwrite_existing_param(self):
        result = _merge_query("https://api.example.com?page=1", {"page": 2})
        assert "page=2" in result
        assert "page=1" not in result


# ── _extract_by_path ──

class TestExtractByPath:
    def test_simple_key(self):
        assert _extract_by_path({"data": [1, 2]}, "data") == [1, 2]

    def test_nested_key(self):
        assert _extract_by_path({"meta": {"next": "abc"}}, "meta.next") == "abc"

    def test_list_index(self):
        assert _extract_by_path({"items": [10, 20, 30]}, "items.1") == 20

    def test_empty_path(self):
        assert _extract_by_path({"a": 1}, "") is None

    def test_none_data(self):
        assert _extract_by_path(None, "a") is None

    def test_missing_key(self):
        assert _extract_by_path({"a": 1}, "b") is None

    def test_deep_nested(self):
        data = {"a": {"b": {"c": 42}}}
        assert _extract_by_path(data, "a.b.c") == 42


# ── _parse_link_header ──

class TestParseLinkHeader:
    def test_standard_next_link(self):
        header = '<https://api.example.com/users?page=2>; rel="next", <https://api.example.com/users?page=5>; rel="last"'
        assert _parse_link_header(header) == "https://api.example.com/users?page=2"

    def test_no_next_link(self):
        header = '<https://api.example.com/users?page=1>; rel="prev"'
        assert _parse_link_header(header) is None

    def test_empty_header(self):
        assert _parse_link_header("") is None

    def test_single_quote_rel(self):
        header = "<https://api.example.com?page=3>; rel='next'"
        assert _parse_link_header(header) == "https://api.example.com?page=3"


# ── _extract_items ──

class TestExtractItems:
    def test_with_data_path(self):
        data = {"results": [1, 2, 3]}
        assert _extract_items(data, "results") == [1, 2, 3]

    def test_without_data_path(self):
        data = [1, 2, 3]
        assert _extract_items(data, "") == [1, 2, 3]

    def test_non_list_wraps_to_list(self):
        data = {"results": {"id": 1}}
        assert _extract_items(data, "results") == [{"id": 1}]

    def test_none_returns_empty(self):
        data = {"results": None}
        assert _extract_items(data, "results") == []

    def test_no_path_non_list(self):
        assert _extract_items({"id": 1}, "") == [{"id": 1}]


# ── Strategy dispatch ──

class TestStrategyDispatch:
    def test_all_strategies_registered(self):
        assert set(_STRATEGY_DISPATCH.keys()) == {"offset", "page", "cursor", "link_header"}

    def test_offset_points_to_correct_fn(self):
        assert _STRATEGY_DISPATCH["offset"] is _paginate_offset

    def test_page_points_to_correct_fn(self):
        assert _STRATEGY_DISPATCH["page"] is _paginate_page

    def test_cursor_points_to_correct_fn(self):
        assert _STRATEGY_DISPATCH["cursor"] is _paginate_cursor

    def test_link_header_points_to_correct_fn(self):
        assert _STRATEGY_DISPATCH["link_header"] is _paginate_link_header


# ── Strategy function tests (with mocked aiohttp session) ──

def _make_mock_session(responses):
    """Create a mock aiohttp session that returns pages of data sequentially."""
    session = AsyncMock()
    call_count = [0]

    class FakeResponse:
        def __init__(self, data, headers=None):
            self._data = data
            self.headers = headers or {}

        async def json(self):
            return self._data

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    def request_side_effect(*args, **kwargs):
        idx = min(call_count[0], len(responses) - 1)
        call_count[0] += 1
        resp_data, resp_headers = responses[idx]
        return FakeResponse(resp_data, resp_headers)

    session.request = MagicMock(side_effect=request_side_effect)
    return session


class TestPaginateOffset:
    async def test_collects_all_pages(self):
        session = _make_mock_session([
            ({"data": [1, 2, 3]}, {}),
            ({"data": [4, 5, 6]}, {}),
            ({"data": [7]}, {}),  # < page_size, stops
        ])
        items, pages = await _paginate_offset(
            session, "GET", "https://api.example.com", {}, True,
            "data", 3, 10, 0, {}, [], 0,
        )
        assert items == [1, 2, 3, 4, 5, 6, 7]
        assert pages == 3

    async def test_respects_max_pages(self):
        session = _make_mock_session([
            ({"data": [1, 2, 3]}, {}),
            ({"data": [4, 5, 6]}, {}),
        ])
        items, pages = await _paginate_offset(
            session, "GET", "https://api.example.com", {}, True,
            "data", 3, 1, 0, {}, [], 0,
        )
        assert pages == 1
        assert items == [1, 2, 3]

    async def test_custom_param_names(self):
        session = _make_mock_session([
            ({"data": [1]}, {}),
        ])
        await _paginate_offset(
            session, "GET", "https://api.example.com", {}, True,
            "data", 10, 1, 0, {"offset_param": "skip", "limit_param": "take"}, [], 0,
        )
        call_url = session.request.call_args[0][1]
        assert "skip=0" in call_url
        assert "take=10" in call_url


class TestPaginatePage:
    async def test_collects_pages(self):
        session = _make_mock_session([
            ({"results": ["a", "b"]}, {}),
            ({"results": ["c"]}, {}),
            ({"results": []}, {}),  # empty, stops
        ])
        items, pages = await _paginate_page(
            session, "GET", "https://api.example.com", {}, True,
            "results", 10, 10, 0, {}, [], 0,
        )
        assert items == ["a", "b", "c"]
        assert pages == 3

    async def test_custom_start_page(self):
        session = _make_mock_session([
            ({"r": []}, {}),
        ])
        await _paginate_page(
            session, "GET", "https://api.example.com", {}, True,
            "r", 10, 10, 0, {"start_page": 0, "page_param": "p"}, [], 0,
        )
        call_url = session.request.call_args[0][1]
        assert "p=0" in call_url


class TestPaginateCursor:
    async def test_follows_cursor(self):
        session = _make_mock_session([
            ({"items": [1], "next": "cur1"}, {}),
            ({"items": [2], "next": "cur2"}, {}),
            ({"items": [3], "next": None}, {}),
        ])
        items, pages = await _paginate_cursor(
            session, "GET", "https://api.example.com", {}, True,
            "items", 10, 10, 0, {"cursor_path": "next", "cursor_param": "after"}, [], 0,
        )
        assert items == [1, 2, 3]
        assert pages == 3

    async def test_stops_on_empty_cursor(self):
        session = _make_mock_session([
            ({"items": [1], "next": ""}, {}),
        ])
        items, pages = await _paginate_cursor(
            session, "GET", "https://api.example.com", {}, True,
            "items", 10, 10, 0, {"cursor_path": "next"}, [], 0,
        )
        assert items == [1]
        assert pages == 1


class TestPaginateLinkHeader:
    async def test_follows_link_header(self):
        session = _make_mock_session([
            ([1, 2], {"Link": '<https://api.example.com?page=2>; rel="next"'}),
            ([3, 4], {"Link": ""}),
        ])
        items, pages = await _paginate_link_header(
            session, "GET", "https://api.example.com", {}, True,
            "", 10, 10, 0, {}, [], 0,
        )
        assert items == [1, 2, 3, 4]
        assert pages == 2

    async def test_stops_when_no_next(self):
        session = _make_mock_session([
            ([1], {}),
        ])
        items, pages = await _paginate_link_header(
            session, "GET", "https://api.example.com", {}, True,
            "", 10, 10, 0, {}, [], 0,
        )
        assert items == [1]
        assert pages == 1
