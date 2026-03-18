"""
Tests for 5 new browser modules: response, table, extract_nested, cookies_file, pool

All tests run through the actual module execute() framework.
"""
import json
import pytest
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
from core.modules import atomic  # noqa: F401
from core.modules.registry import ModuleRegistry


def get_module(mid):
    cls = ModuleRegistry.get(mid)
    assert cls is not None, f"{mid} not registered"
    return cls


# ─── Registration Tests ──────────────────────────────────────────────────

class TestRegistration:
    @pytest.mark.parametrize("mid", [
        "browser.response", "browser.table", "browser.extract_nested",
        "browser.cookies_file", "browser.pool",
    ])
    def test_registered(self, mid):
        assert ModuleRegistry.get(mid) is not None


# ─── browser.table ───────────────────────────────────────────────────────

@pytest.mark.browser
class TestTableE2E:
    @pytest.fixture
    async def ctx(self):
        driver = None
        try:
            from core.browser.driver import BrowserDriver
            driver = BrowserDriver(headless=True)
            await driver.launch(stealth=False)
            yield {"browser": driver}
        finally:
            if driver:
                await driver.close()

    @pytest.mark.asyncio
    async def test_extract_table_with_headers(self, ctx):
        page = ctx["browser"].page
        await page.set_content("""
        <table>
            <thead><tr><th>Name</th><th>Age</th><th>City</th></tr></thead>
            <tbody>
                <tr><td>Alice</td><td>30</td><td>NYC</td></tr>
                <tr><td>Bob</td><td>25</td><td>LA</td></tr>
                <tr><td>Carol</td><td>35</td><td>SF</td></tr>
            </tbody>
        </table>
        """)
        mod = get_module("browser.table")({}, ctx)
        mod.validate_params()
        result = await mod.execute()

        assert result["count"] == 3
        assert result["headers"] == ["Name", "Age", "City"]
        assert result["rows"][0]["Name"] == "Alice"
        assert result["rows"][1]["Age"] == "25"
        assert result["rows"][2]["City"] == "SF"

    @pytest.mark.asyncio
    async def test_extract_table_no_headers(self, ctx):
        page = ctx["browser"].page
        await page.set_content("""
        <table>
            <tr><td>Row1A</td><td>Row1B</td></tr>
            <tr><td>Row2A</td><td>Row2B</td></tr>
            <tr><td>Row3A</td><td>Row3B</td></tr>
        </table>
        """)
        mod = get_module("browser.table")({}, ctx)
        mod.validate_params()
        result = await mod.execute()

        assert result["count"] == 3
        assert "col_0" in result["headers"]
        assert result["rows"][0]["col_0"] == "Row1A"


# ─── browser.extract_nested ─────────────────────────────────────────────

@pytest.mark.browser
class TestExtractNestedE2E:
    @pytest.fixture
    async def ctx(self):
        from core.browser.driver import BrowserDriver
        driver = BrowserDriver(headless=True)
        await driver.launch(stealth=False)
        yield {"browser": driver}
        await driver.close()

    @pytest.mark.asyncio
    async def test_nested_comments(self, ctx):
        page = ctx["browser"].page
        await page.set_content("""
        <div class="comment">
            <span class="author">Alice</span>
            <p class="body">Top level comment from Alice</p>
            <div class="replies">
                <div class="comment">
                    <span class="author">Bob</span>
                    <p class="body">Reply from Bob to Alice</p>
                    <div class="replies">
                        <div class="comment">
                            <span class="author">Carol</span>
                            <p class="body">Nested reply from Carol</p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        <div class="comment">
            <span class="author">Dave</span>
            <p class="body">Another top level comment</p>
        </div>
        """)
        mod = get_module("browser.extract_nested")({
            "root_selector": ".comment",
            "children_selector": ".replies",
            "fields": {
                "author": {"selector": ".author"},
                "text": {"selector": ".body"},
            },
        }, ctx)
        mod.validate_params()
        result = await mod.execute()

        assert result["count"] == 2, "Should find 2 root comments"
        assert result["items"][0]["author"] == "Alice"
        assert result["items"][1]["author"] == "Dave"
        # Alice's reply
        assert len(result["items"][0].get("children", [])) == 1
        assert result["items"][0]["children"][0]["author"] == "Bob"
        # Bob's nested reply
        assert len(result["items"][0]["children"][0].get("children", [])) == 1
        assert result["items"][0]["children"][0]["children"][0]["author"] == "Carol"


# ─── browser.cookies_file ───────────────────────────────────────────────

@pytest.mark.browser
class TestCookiesFileE2E:
    @pytest.fixture
    async def ctx(self):
        from core.browser.driver import BrowserDriver
        driver = BrowserDriver(headless=True)
        await driver.launch(stealth=False)
        yield {"browser": driver}
        await driver.close()

    @pytest.mark.asyncio
    async def test_export_import_roundtrip(self, ctx):
        # Set a cookie via context API (data: URLs don't support cookies)
        await ctx["browser"]._context.add_cookies([{
            "name": "test_key", "value": "test_value",
            "domain": "example.com", "path": "/",
        }])

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            cookie_path = f.name

        try:
            # Export
            exp_mod = get_module("browser.cookies_file")({"action": "export", "file_path": cookie_path}, ctx)
            exp_mod.validate_params()
            exp_result = await exp_mod.execute()
            assert exp_result["cookie_count"] >= 1
            assert Path(cookie_path).exists()

            # Verify file content
            data = json.loads(Path(cookie_path).read_text())
            assert isinstance(data, list)
            assert any(c["name"] == "test_key" for c in data)

            # Clear cookies
            await ctx["browser"]._context.clear_cookies()

            # Import
            imp_mod = get_module("browser.cookies_file")({"action": "import", "file_path": cookie_path}, ctx)
            imp_mod.validate_params()
            imp_result = await imp_mod.execute()
            assert imp_result["cookie_count"] >= 1

            # Verify cookie was restored
            cookies = await ctx["browser"]._context.cookies()
            assert any(c["name"] == "test_key" and c["value"] == "test_value" for c in cookies)
        finally:
            Path(cookie_path).unlink(missing_ok=True)


# ─── browser.pool ────────────────────────────────────────────────────────

@pytest.mark.browser
class TestPoolE2E:
    @pytest.mark.asyncio
    async def test_create_switch_close(self):
        ctx = {}
        Pool = get_module("browser.pool")

        # Create browser A
        mod_a = Pool({"action": "create", "name": "browser_a", "headless": True, "stealth": False}, ctx)
        mod_a.validate_params()
        result_a = await mod_a.execute()
        assert result_a["count"] == 1
        assert "browser" in ctx
        driver_a = ctx["browser"]

        # Create browser B
        mod_b = Pool({"action": "create", "name": "browser_b", "headless": True, "stealth": False}, ctx)
        mod_b.validate_params()
        result_b = await mod_b.execute()
        assert result_b["count"] == 2
        driver_b = ctx["browser"]
        assert driver_a is not driver_b  # Different instances

        # List
        mod_list = Pool({"action": "list"}, ctx)
        mod_list.validate_params()
        result_list = await mod_list.execute()
        assert set(result_list["pool"]) == {"browser_a", "browser_b"}

        # Switch back to A
        mod_switch = Pool({"action": "switch", "name": "browser_a"}, ctx)
        mod_switch.validate_params()
        result_switch = await mod_switch.execute()
        assert ctx["browser"] is driver_a

        # Close all
        mod_close = Pool({"action": "close_all"}, ctx)
        mod_close.validate_params()
        result_close = await mod_close.execute()
        assert result_close["count"] == 0
        assert "browser" not in ctx


# ─── browser.response (mock test — real API capture needs a live page) ──

@pytest.mark.browser
class TestResponseE2E:
    @pytest.fixture
    async def ctx(self):
        from core.browser.driver import BrowserDriver
        driver = BrowserDriver(headless=True)
        await driver.launch(stealth=False)
        yield {"browser": driver}
        await driver.close()

    @pytest.mark.asyncio
    async def test_capture_fetch_response(self, ctx):
        page = ctx["browser"].page

        # Create a page that makes a fetch call
        await page.set_content("<html><body><div id='result'></div></body></html>")

        # Start listening BEFORE the fetch
        import asyncio
        mod = get_module("browser.response")({"url_pattern": "jsonplaceholder", "wait_ms": 5000, "max_responses": 1}, ctx)
        mod.validate_params()

        # Run capture and fetch concurrently
        async def do_fetch():
            await asyncio.sleep(0.5)  # Small delay to ensure listener is ready
            await page.evaluate("""async () => {
                const resp = await fetch('https://jsonplaceholder.typicode.com/posts/1');
                const data = await resp.json();
                document.getElementById('result').textContent = data.title;
            }""")

        capture_task = asyncio.create_task(mod.execute())
        fetch_task = asyncio.create_task(do_fetch())

        result, _ = await asyncio.gather(capture_task, fetch_task)

        assert result["count"] >= 1, f"Should capture at least 1 response, got {result['count']}"
        resp = result["responses"][0]
        assert resp["status"] == 200
        assert "jsonplaceholder" in resp["url"]
        assert isinstance(resp["body"], dict)  # Should be parsed JSON
        assert resp["body"].get("id") == 1
