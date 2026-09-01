# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""What the browser EXTRACTION modules are entitled to claim, and what earns it.

These eleven modules read rather than change, so the question the ladder asks
them is not "did the effect land" but "was anything actually there". The answer
that counts is a match set pulled out of the live DOM; the answer that does not
is any number the module was handed or computed about itself.

Four shapes of dishonest evidence were found in this group and each has a test
here that fails if it comes back:

* `browser.detect_list`'s ``content_found`` -- ``items >= min_items``, a caller
  THRESHOLD. Two correctly detected articles report false under the default
  ``min_items: 3``, and a rung taken from it would call two observed elements
  nothing. `browser.readability`'s ``content_found`` is the same field in the
  same disguise (``len(content) >= min_content_length``).
* `browser.find`'s ``element_ids`` -- UUIDs this process minted. Counting them
  counts our own bookkeeping.
* `browser.snapshot`'s ``path`` -- the path it was HANDED, returned without ever
  looking at the filesystem. `file.write`'s ``bytes_written``, again.
* `browser.pagination`'s ``total_items`` -- ``len(all_items)``, where
  ``all_items`` STARTS as the contents of a checkpoint file an earlier run
  wrote. A resumed run that observes nothing can report four hundred items.
  :class:`TestPaginationCheckpointItemsAreNotObserved` runs exactly that.

And two negative results are pinned as executable facts rather than left as
prose, because both are about a claim that was considered and refused:

* :class:`TestReadabilityAiFallbackIsNotObserved` -- the AI path's characters
  are a model's output, not a DOM read, so it is ACCEPTED however long the
  answer is.
* :class:`TestRobotsAllowedIsInferredWhenAbsent` -- ``allowed: true`` is a
  literal in the page script on every path where robots.txt was not parsed, so
  those paths carry ``claim_by=inferred`` and never OBSERVED.
"""

import http.server
import json
import socketserver
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import core.modules.atomic.browser.detect as detect_module
import core.modules.atomic.browser.detect_list as detect_list_module
import core.modules.atomic.browser.extract as extract_module
import core.modules.atomic.browser.extract_nested as extract_nested_module
import core.modules.atomic.browser.find as find_module
import core.modules.atomic.browser.pagination as pagination_module
import core.modules.atomic.browser.readability as readability_module
import core.modules.atomic.browser.robots as robots_module
import core.modules.atomic.browser.sitemap as sitemap_module
import core.modules.atomic.browser.snapshot as snapshot_module
import core.modules.atomic.browser.table as table_module
from core.engine.outcome import ClaimBy, Outcome, ceiling_for, read_envelope
from core.engine.step_executor.executor import step_outcome
from core.modules import atomic  # noqa: F401 - registers every module
from core.modules.registry import ModuleRegistry


GROUP = [
    "browser.extract",
    "browser.extract_nested",
    "browser.find",
    "browser.table",
    "browser.readability",
    "browser.snapshot",
    "browser.detect",
    "browser.detect_list",
    "browser.pagination",
    "browser.robots",
    "browser.sitemap",
]


# ---------------------------------------------------------------------------
# Reading a result the way step_executor reads it
# ---------------------------------------------------------------------------

def envelope_of(result):
    """The envelope, read through `read_envelope` the way a consumer would.

    Not ``result['outcome']``: a malformed rung comes back as None here, the
    same way it would reach the executor.
    """
    return read_envelope(result)


def rung_of(result):
    return envelope_of(result)["rung"]


def effect_kinds(found):
    return [effect["kind"] for effect in found["effects"]]


def effect_named(found, kind):
    return next(effect for effect in found["effects"] if effect["kind"] == kind)


async def run_module(module_id, params, context):
    """Execute a module the way the engine does, and return its result dict."""
    return await ModuleRegistry.get(module_id)(params, context).execute()


# ---------------------------------------------------------------------------
# Real browser, real origin
# ---------------------------------------------------------------------------

ARTICLE = (
    "The harbour master kept a ledger of every hull that passed the mole, and "
    "the ledger outlived him by forty years. It recorded weather, tonnage, the "
    "names of masters, and in the margins a private shorthand nobody has since "
    "decoded. Historians read it for the tonnage. Everyone else reads it for "
    "the margins, which is the usual fate of a careful record kept by someone "
    "who did not expect to be read."
)

PAGE_HTML = f"""<html><head><title>Fixture</title>
<meta property="og:title" content="Fixture Article">
</head><body>
<article id="story">
  <h1>Fixture Article</h1>
  <p>{ARTICLE}</p>
  <p>{ARTICLE}</p>
</article>
<div id="results">
  <div class="item"><h3>Alpha</h3><a href="/a">alpha link</a></div>
  <div class="item"><h3>Beta</h3><a href="/b">beta link</a></div>
  <div class="item"><h3>Gamma</h3><a href="/c">gamma link</a></div>
</div>
<div id="blanks"><div class="blank"></div><div class="blank"></div></div>
<table id="grid">
  <thead><tr><th>Name</th><th>Qty</th></tr></thead>
  <tbody>
    <tr><td>widget</td><td>3</td></tr>
    <tr><td>gadget</td><td>5</td></tr>
  </tbody>
</table>
<table id="headers-only"><thead><tr><th>Only</th></tr></thead></table>
<div id="thread">
  <div class="comment"><span class="author">ann</span><div class="body">root one</div>
    <div class="replies">
      <div class="comment"><span class="author">bob</span><div class="body">reply one</div></div>
      <div class="comment"><span class="author">cy</span><div class="body">reply two</div></div>
    </div>
  </div>
  <div class="comment"><span class="author">dee</span><div class="body">root two</div></div>
</div>
<input id="text-field" placeholder="Email">
<button id="go">Launch Sequence</button>
</body></html>"""

ROBOTS_TXT = b"""User-agent: *
Disallow: /private/
Allow: /public/
Crawl-delay: 2
Sitemap: /sitemap.xml
"""

SITEMAP_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.test/one</loc><lastmod>2026-01-01</lastmod></url>
  <url><loc>https://example.test/two</loc><priority>0.5</priority></url>
</urlset>
"""


class _SiteHandler(http.server.BaseHTTPRequestHandler):
    """Serves the fixture page plus a real robots.txt and sitemap.xml."""

    def log_message(self, *args):  # keep the test output readable
        pass

    def _send(self, code, body, content_type):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/robots.txt":
            self._send(200, ROBOTS_TXT, "text/plain")
        elif self.path == "/sitemap.xml":
            self._send(200, SITEMAP_XML, "application/xml")
        else:
            self._send(200, PAGE_HTML.encode(), "text/html")


class _BareHandler(http.server.BaseHTTPRequestHandler):
    """Serves the page, and 404s robots.txt and sitemap.xml."""

    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path in ("/robots.txt", "/sitemap.xml"):
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = PAGE_HTML.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _serve(handler):
    server = socketserver.TCPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


@pytest.fixture
def site():
    """An origin that publishes robots.txt and sitemap.xml."""
    server, url = _serve(_SiteHandler)
    try:
        yield url
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def bare_site():
    """An origin that 404s robots.txt and sitemap.xml -- an answer, not a silence."""
    server, url = _serve(_BareHandler)
    try:
        yield url
    finally:
        server.shutdown()
        server.server_close()


async def _launch_driver():
    from core.browser.driver import BrowserDriver

    driver = BrowserDriver(headless=True)
    await driver.launch(stealth=False)
    return driver


@pytest.fixture
async def browser_ctx():
    """A launched driver in an execution context, torn down after the test."""
    driver = await _launch_driver()
    try:
        yield {"browser": driver}
    finally:
        try:
            await driver.close()
        except Exception:  # noqa: BLE001 - teardown must not mask a failure
            pass


@pytest.fixture
async def loaded_ctx(browser_ctx):
    """`browser_ctx`, with the fixture page rendered into it."""
    await browser_ctx["browser"].real_page.set_content(PAGE_HTML)
    return browser_ctx


@pytest.fixture
async def blank_ctx(browser_ctx):
    """`browser_ctx` on an empty document -- the empty-read case, for real."""
    await browser_ctx["browser"].real_page.set_content("<html><body></body></html>")
    return browser_ctx


@pytest.fixture
def sandbox(sandboxed_tmp_path):
    """A directory the path-restricted browser modules are allowed to write to."""
    return sandboxed_tmp_path


# ===========================================================================
# The shape of the contract, across the whole group
# ===========================================================================

class TestTheGroupDeclares:
    def test_every_module_in_this_group_reports_an_outcome(self):
        """The list in the coverage test and the modules here say the same thing."""
        from tests.core.test_outcome_declaration_coverage import UNDECLARED

        still_listed = sorted(module_id for module_id in GROUP if module_id in UNDECLARED)
        assert not still_listed, (
            f"these were declared in this pass but are still on the UNDECLARED "
            f"list: {still_listed}"
        )

    @pytest.mark.parametrize("module_id", GROUP)
    def test_none_of_them_may_claim_verified(self, module_id):
        """No postcondition is declared, so OBSERVED is the ceiling.

        Not a policy: `verified` MEANS a postcondition was evaluated and held,
        and with none declared there is no predicate the claim could be about.
        """
        metadata = ModuleRegistry.get_metadata(module_id) or {}
        assert metadata.get("postcondition") is None
        assert ceiling_for(metadata.get("postcondition")) is Outcome.OBSERVED


# ===========================================================================
# browser.extract -- the match set is the evidence, the values are not
# ===========================================================================

class TestRungExtract:
    def test_matched_elements_are_observed(self):
        found = extract_module._extract_outcome(
            selector=".item", mode="fields", elements_matched=3, values_returned=3
        )
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_named(found, "elements_matched")["count"] == 3

    def test_no_match_is_accepted_not_observed(self):
        found = extract_module._extract_outcome(
            selector=".nope", mode="text", elements_matched=0, values_returned=0
        )
        assert found["rung"] == Outcome.ACCEPTED.value
        assert effect_named(found, "no_elements_matched")["measured_by"] is None

    def test_matches_with_no_values_stay_observed(self):
        """20 nodes holding blank text is an observation of 20 nodes.

        Folding this into ACCEPTED would erase the difference between "the
        selector is wrong" and "the selector is right and the text is empty",
        which is the one thing a caller staring at ``count: 0`` needs.
        """
        found = extract_module._extract_outcome(
            selector=".blank", mode="text", elements_matched=20, values_returned=0
        )
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_named(found, "values_returned")["count"] == 0

    def test_values_present_counts_a_dict_with_any_field(self):
        assert extract_module._values_present([{"a": None}, {"a": "x"}, None, "y"]) == 2


@pytest.mark.browser
class TestExtractAgainstRealDom:
    @pytest.mark.asyncio
    async def test_fields_mode_observes_the_matched_items(self, loaded_ctx):
        result = await run_module(
            "browser.extract",
            {"selector": ".item", "fields": {"title": {"selector": "h3"}}},
            loaded_ctx,
        )
        assert result["count"] == 3
        assert rung_of(result) == Outcome.OBSERVED.value
        assert effect_named(envelope_of(result), "elements_matched")["count"] == 3

    @pytest.mark.asyncio
    async def test_a_wrong_selector_is_accepted(self, loaded_ctx):
        result = await run_module(
            "browser.extract", {"selector": ".not-on-this-page"}, loaded_ctx
        )
        assert result["count"] == 0
        assert rung_of(result) == Outcome.ACCEPTED.value

    @pytest.mark.asyncio
    async def test_real_matches_with_blank_text_are_still_observed(self, loaded_ctx):
        """The case the rung exists to separate, driven by a real page."""
        result = await run_module("browser.extract", {"selector": ".blank"}, loaded_ctx)
        assert result["count"] == 0
        assert "hint" in result
        found = envelope_of(result)
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_named(found, "elements_matched")["count"] == 2

    @pytest.mark.asyncio
    async def test_attribute_mode_observes(self, loaded_ctx):
        result = await run_module(
            "browser.extract",
            {"selector": ".item a", "attribute": "href"},
            loaded_ctx,
        )
        assert rung_of(result) == Outcome.OBSERVED.value


class TestExtractEnvelopeSurvivesTheEngine:
    """The one structural dependency this envelope rests on.

    ``data`` here is a LIST, so `_apply_outcome_contract` declines to stamp and
    `to_legacy_dict` would discard any sibling -- but `_execute_single_mode`
    only routes through `wrap_legacy_result` when the result carries an ``ok``
    key, and this one does not. Adding ``ok`` to this module would delete its
    envelope silently, so the absence is asserted rather than assumed.
    """

    def test_step_outcome_reads_a_top_level_envelope_beside_a_list_data(self):
        result = {
            "status": "success",
            "data": ["a", "b"],
            "count": 2,
            "outcome": extract_module._extract_outcome(
                selector=".item", mode="text", elements_matched=2, values_returned=2
            ),
        }
        rung, _claim_by, _expected = step_outcome(result)
        assert rung is Outcome.OBSERVED

    @pytest.mark.browser
    @pytest.mark.asyncio
    async def test_the_result_carries_no_ok_key(self, loaded_ctx):
        result = await run_module("browser.extract", {"selector": ".item"}, loaded_ctx)
        assert "ok" not in result, (
            "browser.extract gained an `ok` key. `wrap_legacy_result` will now "
            "run and `to_legacy_dict` keeps only `data` -- which is a list here "
            "-- so the outcome envelope is discarded on the way out of the step."
        )


# ===========================================================================
# browser.find -- the handles are the evidence, the ids we minted are not
# ===========================================================================

class TestRungFind:
    def test_matched_handles_are_observed(self):
        found = find_module._find_outcome(selector=".item", elements_matched=3, ids_issued=3)
        assert found["rung"] == Outcome.OBSERVED.value

    def test_no_match_is_accepted(self):
        found = find_module._find_outcome(selector=".x", elements_matched=0, ids_issued=0)
        assert found["rung"] == Outcome.ACCEPTED.value

    def test_the_rung_does_not_rest_on_the_ids(self):
        """Ids are our own bookkeeping and cannot lift a rung on their own."""
        found = find_module._find_outcome(selector=".x", elements_matched=0, ids_issued=99)
        assert found["rung"] == Outcome.ACCEPTED.value


@pytest.mark.browser
class TestFindAgainstRealDom:
    @pytest.mark.asyncio
    async def test_found_elements_are_observed(self, loaded_ctx):
        result = await run_module("browser.find", {"selector": ".item"}, loaded_ctx)
        assert result["count"] == 3
        assert rung_of(result) == Outcome.OBSERVED.value

    @pytest.mark.asyncio
    async def test_nothing_found_is_accepted(self, loaded_ctx):
        result = await run_module("browser.find", {"selector": ".absent"}, loaded_ctx)
        assert result["count"] == 0
        assert rung_of(result) == Outcome.ACCEPTED.value


# ===========================================================================
# browser.extract_nested -- nodes walked, not roots returned
# ===========================================================================

class TestRungExtractNested:
    def test_walked_nodes_are_observed(self):
        found = extract_nested_module._nested_outcome(
            root_selector=".comment", roots=2, total_nodes=4
        )
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_named(found, "nodes_walked")["count"] == 4
        assert effect_named(found, "root_items_returned")["count"] == 2

    def test_nothing_walked_is_accepted(self):
        found = extract_nested_module._nested_outcome(
            root_selector=".comment", roots=0, total_nodes=0
        )
        assert found["rung"] == Outcome.ACCEPTED.value


@pytest.mark.browser
class TestExtractNestedAgainstRealDom:
    @pytest.mark.asyncio
    async def test_a_real_thread_is_observed_at_every_depth(self, loaded_ctx):
        result = await run_module(
            "browser.extract_nested",
            {"root_selector": ".comment", "children_selector": ".replies"},
            loaded_ctx,
        )
        assert result["count"] == 2, "two top-level comments"
        assert result["total_nodes"] == 4, "two roots and two replies"
        found = envelope_of(result)
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_named(found, "nodes_walked")["count"] == 4

    @pytest.mark.asyncio
    async def test_an_absent_structure_is_accepted(self, loaded_ctx):
        result = await run_module(
            "browser.extract_nested", {"root_selector": ".no-such-node"}, loaded_ctx
        )
        assert rung_of(result) == Outcome.ACCEPTED.value


# ===========================================================================
# browser.table -- rows read, with "was there a table at all" beside it
# ===========================================================================

class TestRungTable:
    def test_rows_read_are_observed(self):
        found = table_module._table_outcome(
            selector="table", table_index=0, rows=2, tables_found=2
        )
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_named(found, "tables_matched")["count"] == 2

    def test_a_matched_table_with_no_rows_is_accepted_and_says_so(self):
        found = table_module._table_outcome(
            selector="#headers-only", table_index=0, rows=0, tables_found=1
        )
        assert found["rung"] == Outcome.ACCEPTED.value
        detail = effect_named(found, "no_rows_read")["detail"]
        assert "produced no rows" in detail

    def test_no_table_at_all_is_accepted_and_says_something_different(self):
        found = table_module._table_outcome(
            selector="table.nope", table_index=0, rows=0, tables_found=0
        )
        assert found["rung"] == Outcome.ACCEPTED.value
        assert "No table matched" in effect_named(found, "no_rows_read")["detail"]

    def test_a_matched_table_does_not_lift_the_rung_on_its_own(self):
        """``table_index`` past the end matched a table and read nothing."""
        found = table_module._table_outcome(
            selector="table", table_index=7, rows=0, tables_found=2
        )
        assert found["rung"] == Outcome.ACCEPTED.value


@pytest.mark.browser
class TestTableAgainstRealDom:
    @pytest.mark.asyncio
    async def test_real_rows_are_observed(self, loaded_ctx):
        result = await run_module("browser.table", {"selector": "#grid"}, loaded_ctx)
        assert result["count"] == 2
        assert result["headers"] == ["Name", "Qty"]
        assert rung_of(result) == Outcome.OBSERVED.value

    @pytest.mark.asyncio
    async def test_a_header_only_table_is_accepted(self, loaded_ctx):
        result = await run_module(
            "browser.table", {"selector": "#headers-only"}, loaded_ctx
        )
        assert result["count"] == 0
        assert result["tables_found"] == 1
        found = envelope_of(result)
        assert found["rung"] == Outcome.ACCEPTED.value
        assert effect_named(found, "no_rows_read")["tables_found"] == 1

    @pytest.mark.asyncio
    async def test_an_out_of_range_index_is_accepted(self, loaded_ctx):
        result = await run_module(
            "browser.table", {"selector": "table", "table_index": 9}, loaded_ctx
        )
        assert rung_of(result) == Outcome.ACCEPTED.value


# ===========================================================================
# browser.detect_list -- the count, never the threshold
# ===========================================================================

class TestRungDetectList:
    def test_detected_items_are_observed(self):
        found = detect_list_module._detect_list_outcome(
            items=8, auto_detected=True, content_found=True,
            min_items=3, candidates_evaluated=12,
        )
        assert found["rung"] == Outcome.OBSERVED.value

    def test_nothing_detected_is_accepted(self):
        found = detect_list_module._detect_list_outcome(
            items=0, auto_detected=True, content_found=False,
            min_items=3, candidates_evaluated=12,
        )
        assert found["rung"] == Outcome.ACCEPTED.value

    def test_below_the_caller_threshold_is_still_observed(self):
        """``content_found`` is ``items >= min_items``. It is a policy, not a reading.

        Two real elements detected under ``min_items: 3`` reports
        ``content_found: false``, and a rung taken from that boolean would
        report nothing observed on a page where two nodes were plainly seen.
        """
        found = detect_list_module._detect_list_outcome(
            items=2, auto_detected=True, content_found=False,
            min_items=3, candidates_evaluated=4,
        )
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_named(found, "below_caller_threshold")["min_items"] == 3


@pytest.mark.browser
class TestDetectListAgainstRealDom:
    @pytest.mark.asyncio
    async def test_a_known_selector_is_observed(self, loaded_ctx):
        result = await run_module(
            "browser.detect_list", {"selector": ".item"}, loaded_ctx
        )
        assert result["count"] == 3
        assert rung_of(result) == Outcome.OBSERVED.value

    @pytest.mark.asyncio
    async def test_two_real_items_under_the_threshold_are_observed(self, loaded_ctx):
        """The threshold trap, on a real page: status says no_list, rung says observed."""
        result = await run_module(
            "browser.detect_list", {"selector": ".blank", "min_items": 3}, loaded_ctx
        )
        assert result["count"] == 2
        assert result["content_found"] is False
        assert result["status"] == "no_list"
        assert rung_of(result) == Outcome.OBSERVED.value

    @pytest.mark.asyncio
    async def test_an_empty_page_is_accepted(self, blank_ctx):
        result = await run_module("browser.detect_list", {}, blank_ctx)
        assert result["count"] == 0
        assert rung_of(result) == Outcome.ACCEPTED.value


# ===========================================================================
# browser.readability -- a DOM read and a generated paraphrase are not one rung
# ===========================================================================

class TestRungReadability:
    def test_extracted_characters_are_observed(self):
        found = readability_module._readability_outcome(
            method="heuristic", content_characters=900, word_count=150,
            content_found=True, min_content_length=80,
        )
        assert found["rung"] == Outcome.OBSERVED.value

    def test_nothing_extracted_is_accepted(self):
        found = readability_module._readability_outcome(
            method="heuristic", content_characters=0, word_count=0,
            content_found=False, min_content_length=80,
        )
        assert found["rung"] == Outcome.ACCEPTED.value

    def test_below_the_threshold_is_still_observed(self):
        found = readability_module._readability_outcome(
            method="heuristic", content_characters=40, word_count=7,
            content_found=False, min_content_length=80,
        )
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_named(found, "below_caller_threshold")["characters"] == 40


class TestReadabilityAiFallbackIsNotObserved:
    """The refusal worth writing down.

    The AI path's ``content`` is written by a model from ``body.innerText``. The
    page text was really fetched, but ``len()`` over a generated string measures
    the model, not the page, and marking it OBSERVED would put the same rung on
    a DOM read and on a paraphrase that can be wrong in ways nothing here checks.
    """

    def test_a_long_ai_answer_is_still_only_accepted(self):
        found = readability_module._readability_outcome(
            method="ai", content_characters=12000, word_count=2000,
            content_found=True, min_content_length=80,
        )
        assert found["rung"] == Outcome.ACCEPTED.value
        assert effect_named(found, "content_generated")["measured_by"] is None

    def test_a_failed_heuristic_with_no_ai_is_accepted(self):
        found = readability_module._readability_outcome(
            method="heuristic_failed", content_characters=0, word_count=0,
            content_found=False, min_content_length=80,
        )
        assert found["rung"] == Outcome.ACCEPTED.value


@pytest.mark.browser
class TestReadabilityAgainstRealDom:
    @pytest.mark.asyncio
    async def test_a_real_article_is_observed(self, loaded_ctx):
        result = await run_module("browser.readability", {}, loaded_ctx)
        found = envelope_of(result)
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_named(found, "content_extracted")["characters"] > 80
        assert result["extraction_method"] == "heuristic"

    @pytest.mark.asyncio
    async def test_an_empty_page_is_accepted(self, blank_ctx):
        result = await run_module("browser.readability", {}, blank_ctx)
        assert result["status"] == "no_content"
        assert rung_of(result) == Outcome.ACCEPTED.value


# ===========================================================================
# browser.snapshot -- the path was never evidence; os.stat is
# ===========================================================================

class TestRungSnapshot:
    def test_bytes_returned_inline_are_observed(self):
        found = snapshot_module._snapshot_outcome(fmt="html", captured_bytes=5000)
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_kinds(found) == ["content_captured"]

    def test_an_empty_capture_is_accepted(self):
        found = snapshot_module._snapshot_outcome(fmt="text", captured_bytes=0)
        assert found["rung"] == Outcome.ACCEPTED.value

    def test_a_file_that_matches_the_capture_is_observed(self):
        found = snapshot_module._snapshot_outcome(
            fmt="html", captured_bytes=120, path="/tmp/s.html", size_on_disk=120
        )
        assert found["rung"] == Outcome.OBSERVED.value
        assert found["claim_by"] == ClaimBy.INFERRED.value
        assert effect_named(found, "file_size_observed")["bytes_on_disk"] == 120

    def test_a_file_that_does_not_match_is_indeterminate_not_failed(self):
        found = snapshot_module._snapshot_outcome(
            fmt="html", captured_bytes=120, path="/tmp/s.html", size_on_disk=7
        )
        assert found["rung"] == Outcome.INDETERMINATE.value

    def test_a_file_that_cannot_be_stat_ed_falls_back_to_accepted(self):
        found = snapshot_module._snapshot_outcome(
            fmt="html", captured_bytes=120, path="/tmp/s.html",
            size_on_disk=None, stat_error="FileNotFoundError: no such file",
        )
        assert found["rung"] == Outcome.ACCEPTED.value
        assert effect_named(found, "file_size_not_observed")["measured_by"] is None

    def test_mhtml_on_a_non_chromium_browser_is_failed_by_the_callers_claim(self):
        found = snapshot_module._mhtml_unsupported_outcome("firefox")
        assert found["rung"] == Outcome.FAILED.value
        assert found["claim_by"] == ClaimBy.CALLER.value

    def test_the_path_alone_never_produces_a_rung(self):
        """`_snapshot_outcome` cannot be satisfied by a path with no stat behind it."""
        found = snapshot_module._snapshot_outcome(
            fmt="html", captured_bytes=99, path="/tmp/whatever.html",
        )
        assert found["rung"] == Outcome.ACCEPTED.value


@pytest.mark.browser
class TestSnapshotAgainstRealBrowser:
    @pytest.mark.asyncio
    async def test_inline_html_is_observed(self, loaded_ctx):
        result = await run_module("browser.snapshot", {"format": "html"}, loaded_ctx)
        assert result["size_bytes"] > 0
        assert rung_of(result) == Outcome.OBSERVED.value

    @pytest.mark.asyncio
    async def test_a_written_file_is_measured_independently_by_the_test(
        self, loaded_ctx, sandbox
    ):
        """The reported size is checked against the test's own os.stat.

        An echo of the input would pass a test that only read the module's own
        number back. This one asks the filesystem separately.
        """
        target = sandbox / "snap.html"
        result = await run_module(
            "browser.snapshot", {"format": "html", "path": str(target)}, loaded_ctx
        )
        found = envelope_of(result)
        assert found["rung"] == Outcome.OBSERVED.value
        reported = effect_named(found, "file_size_observed")["bytes_on_disk"]
        assert reported == target.stat().st_size
        assert reported == result["size_bytes"]

    @pytest.mark.asyncio
    async def test_an_empty_body_text_capture_is_accepted(self, blank_ctx):
        result = await run_module("browser.snapshot", {"format": "text"}, blank_ctx)
        assert result["size_bytes"] == 0
        assert rung_of(result) == Outcome.ACCEPTED.value


# ===========================================================================
# browser.detect -- confidence is not evidence; the action is a second effect
# ===========================================================================

class TestRungDetect:
    def test_a_match_with_no_action_is_observed(self):
        found = detect_module._detect_outcome(
            found=True, strategy="selector", confidence=100,
            info={"tag": "button", "visible": True}, action="none",
        )
        assert found["rung"] == Outcome.OBSERVED.value

    def test_no_match_is_accepted(self):
        found = detect_module._detect_outcome(
            found=False, strategies_tried=9, candidates=3
        )
        assert found["rung"] == Outcome.ACCEPTED.value
        assert effect_named(found, "no_element_matched")["strategies_tried"] == 9

    def test_confidence_alone_cannot_produce_a_rung(self):
        """A perfect 100 on a match that was not found is still ACCEPTED."""
        found = detect_module._detect_outcome(found=False, strategies_tried=1)
        assert found["rung"] == Outcome.ACCEPTED.value

    def test_confidence_is_labelled_as_not_a_measurement(self):
        found = detect_module._detect_outcome(
            found=True, strategy="text_contains", confidence=78,
            info={"tag": "a"}, action="none",
        )
        matched = effect_named(found, "element_matched")
        assert matched["confidence"] == 78
        assert "no rung rests on it" in matched["confidence_detail"]

    def test_a_click_lowers_the_step_to_accepted(self):
        """The element was observed. The click was not, so the step is not."""
        found = detect_module._detect_outcome(
            found=True, strategy="role", confidence=95,
            info={"tag": "button"}, action="click",
        )
        assert found["rung"] == Outcome.ACCEPTED.value
        assert effect_kinds(found) == ["element_matched", "click_dispatched"]

    def test_a_fill_that_lands_exactly_is_observed(self):
        found = detect_module._detect_outcome(
            found=True, strategy="placeholder", confidence=87, info={"tag": "input"},
            action="type", typed_characters=5, baseline="", after="hello",
            expected="hello",
        )
        assert found["rung"] == Outcome.OBSERVED.value
        assert found["claim_by"] == ClaimBy.INFERRED.value

    def test_a_fill_the_page_rewrote_is_still_observed(self):
        found = detect_module._detect_outcome(
            found=True, strategy="placeholder", confidence=87, info={"tag": "input"},
            action="type", typed_characters=10, baseline="",
            after="(555) 123-4567", expected="5551234567",
        )
        assert found["rung"] == Outcome.OBSERVED.value
        assert "field_value_differs" in effect_kinds(found)

    def test_a_fill_that_changed_nothing_is_indeterminate_not_failed(self):
        found = detect_module._detect_outcome(
            found=True, strategy="selector", confidence=100, info={"tag": "input"},
            action="type", typed_characters=5, baseline="fixed", after="fixed",
            expected="hello",
        )
        assert found["rung"] == Outcome.INDETERMINATE.value

    def test_a_field_that_cannot_be_read_back_falls_to_accepted(self):
        found = detect_module._detect_outcome(
            found=True, strategy="selector", confidence=100, info={"tag": "div"},
            action="type", typed_characters=5, baseline=None, after=None,
            expected="hello", read_error="Error: not an <input> element",
        )
        assert found["rung"] == Outcome.ACCEPTED.value
        assert effect_named(found, "field_value_not_observed")["measured_by"] is None

    def test_the_envelope_never_carries_the_text(self):
        found = detect_module._detect_outcome(
            found=True, strategy="selector", confidence=100, info={"tag": "input"},
            action="type", typed_characters=8, baseline="", after="hunter22",
            expected="hunter22",
        )
        assert "hunter22" not in json.dumps(found)


@pytest.mark.browser
class TestDetectAgainstRealDom:
    @pytest.mark.asyncio
    async def test_a_found_button_is_observed(self, loaded_ctx):
        result = await run_module(
            "browser.detect", {"text": "Launch Sequence", "timeout": 2000}, loaded_ctx
        )
        assert result["found"] is True
        assert rung_of(result) == Outcome.OBSERVED.value

    @pytest.mark.asyncio
    async def test_nothing_found_is_accepted(self, loaded_ctx):
        result = await run_module(
            "browser.detect",
            {"text": "no such control anywhere", "timeout": 500},
            loaded_ctx,
        )
        assert result["found"] is False
        assert rung_of(result) == Outcome.ACCEPTED.value

    @pytest.mark.asyncio
    async def test_a_real_fill_is_read_back_out_of_the_field(self, loaded_ctx):
        result = await run_module(
            "browser.detect",
            {
                "text": "Email", "role": "textbox", "action": "type",
                "action_value": "team@flyto2.com", "timeout": 2000,
            },
            loaded_ctx,
        )
        assert result["action_result"] == "typed"
        found = envelope_of(result)
        assert found["rung"] == Outcome.OBSERVED.value
        observed = effect_named(found, "field_value_observed")
        assert observed["characters_after"] == len("team@flyto2.com")
        assert observed["matches_expected"] is True
        # Independent of the module's own reading.
        assert (
            await loaded_ctx["browser"].page.input_value("#text-field")
            == "team@flyto2.com"
        )

    @pytest.mark.asyncio
    async def test_a_real_click_does_not_claim_to_have_been_seen(self, loaded_ctx):
        result = await run_module(
            "browser.detect",
            {"text": "Launch Sequence", "action": "click", "timeout": 2000},
            loaded_ctx,
        )
        assert result["action_result"] == "clicked"
        assert rung_of(result) == Outcome.ACCEPTED.value


# ===========================================================================
# browser.pagination -- a checkpoint is a replay, not an observation
# ===========================================================================

class TestRungPagination:
    def test_items_this_run_are_observed(self):
        found = pagination_module._pagination_outcome(
            extracted_this_run=30, restored_from_checkpoint=0,
            pages_this_run=3, stopped_reason="no_more", item_selector=".card",
        )
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_named(found, "items_extracted")["count"] == 30

    def test_no_items_and_no_error_is_accepted(self):
        found = pagination_module._pagination_outcome(
            extracted_this_run=0, restored_from_checkpoint=0,
            pages_this_run=1, stopped_reason="no_more", item_selector=".card",
        )
        assert found["rung"] == Outcome.ACCEPTED.value

    def test_no_items_and_an_exception_is_indeterminate(self):
        found = pagination_module._pagination_outcome(
            extracted_this_run=0, restored_from_checkpoint=0, pages_this_run=0,
            stopped_reason="error: extraction failed after retries",
            item_selector=".card",
        )
        assert found["rung"] == Outcome.INDETERMINATE.value

    def test_items_plus_an_exception_stays_observed_and_names_the_gap(self):
        found = pagination_module._pagination_outcome(
            extracted_this_run=12, restored_from_checkpoint=0, pages_this_run=2,
            stopped_reason="error: Timeout 30000ms exceeded", item_selector=".card",
        )
        assert found["rung"] == Outcome.OBSERVED.value
        assert "pagination_incomplete" in effect_kinds(found)


class TestPaginationCheckpointItemsAreNotObserved:
    """``total_items`` counts a file an earlier run wrote. The rung must not."""

    def test_a_resume_that_extracted_nothing_is_accepted(self):
        found = pagination_module._pagination_outcome(
            extracted_this_run=0, restored_from_checkpoint=400,
            pages_this_run=0, stopped_reason="no_more", item_selector=".card",
        )
        assert found["rung"] == Outcome.ACCEPTED.value
        restored = effect_named(found, "items_restored_from_checkpoint")
        assert restored["count"] == 400
        assert restored["measured_by"] is None

    def test_a_resume_that_did_extract_counts_only_its_own(self):
        found = pagination_module._pagination_outcome(
            extracted_this_run=10, restored_from_checkpoint=400,
            pages_this_run=1, stopped_reason="max_pages", item_selector=".card",
        )
        assert effect_named(found, "items_extracted")["count"] == 10
        assert effect_named(found, "items_restored_from_checkpoint")["count"] == 400


@pytest.mark.browser
class TestPaginationAgainstRealDom:
    @pytest.mark.asyncio
    async def test_a_single_page_of_items_is_observed(self, loaded_ctx):
        result = await run_module(
            "browser.pagination",
            {"item_selector": ".item", "mode": "next_button", "max_pages": 1},
            loaded_ctx,
        )
        assert result["total_items"] == 3
        assert rung_of(result) == Outcome.OBSERVED.value

    @pytest.mark.asyncio
    async def test_a_page_with_no_matches_is_accepted(self, loaded_ctx):
        result = await run_module(
            "browser.pagination",
            {"item_selector": ".no-such-card", "mode": "next_button", "max_pages": 1},
            loaded_ctx,
        )
        assert result["total_items"] == 0
        assert rung_of(result) == Outcome.ACCEPTED.value

    @pytest.mark.asyncio
    async def test_a_real_resume_that_observed_nothing_does_not_claim_400_items(
        self, loaded_ctx, sandbox
    ):
        """End to end, on the trap itself.

        A checkpoint holding three items is written, then pagination is pointed
        at a selector that matches nothing. ``total_items`` comes back as 3 --
        which is correct, they are in the array -- and the rung is ACCEPTED,
        because this run saw none of them.
        """
        from core.browser.checkpoint import PaginationCheckpoint

        path = sandbox / "ckpt.json"
        seed = PaginationCheckpoint(str(path), ".no-such-card", "next_button")
        seed.save(
            items=[{"n": 1}, {"n": 2}, {"n": 3}],
            pages_processed=2,
            last_url=None,
        )

        result = await run_module(
            "browser.pagination",
            {
                "item_selector": ".no-such-card",
                "mode": "next_button",
                "max_pages": 1,
                "checkpoint_path": str(path),
            },
            loaded_ctx,
        )
        assert result["resumed"] is True
        assert result["total_items"] == 3
        found = envelope_of(result)
        assert found["rung"] == Outcome.ACCEPTED.value, (
            "a resumed run that extracted nothing claimed to have observed the "
            "checkpoint's items"
        )
        assert effect_named(found, "items_restored_from_checkpoint")["count"] == 3

    @pytest.mark.asyncio
    async def test_max_items_truncating_below_the_checkpoint_does_not_go_negative(
        self, loaded_ctx, sandbox
    ):
        """``max_items`` keeps the front of the array, and the front is the replay.

        Five restored items capped at two leaves the run holding fewer items
        than it started with, so the subtraction is negative before the clamp.
        Nothing was observed, and that is what it has to say.
        """
        from core.browser.checkpoint import PaginationCheckpoint

        path = sandbox / "big.json"
        seed = PaginationCheckpoint(str(path), ".no-such-card", "next_button")
        seed.save(items=[{"n": i} for i in range(5)], pages_processed=1, last_url=None)

        result = await run_module(
            "browser.pagination",
            {
                "item_selector": ".no-such-card",
                "mode": "next_button",
                "max_items": 2,
                "checkpoint_path": str(path),
            },
            loaded_ctx,
        )
        assert result["total_items"] == 2
        found = envelope_of(result)
        assert found["rung"] == Outcome.ACCEPTED.value
        assert "items_extracted" not in effect_kinds(found)


# ===========================================================================
# browser.robots -- `allowed` is inferred wherever robots.txt was not read
# ===========================================================================

class TestRungRobots:
    def test_parsed_directives_are_observed(self):
        found = robots_module._robots_outcome(
            exists=True, fetch_failed=False, http_status=200, body_bytes=91,
            rule_count=2, sitemaps=["/sitemap.xml"], allowed=False,
            checked_url="/private/x",
        )
        assert found["rung"] == Outcome.OBSERVED.value
        assert found["claim_by"] == ClaimBy.NONE.value
        assert effect_named(found, "robots_directives_parsed")["rule_count"] == 2

    def test_a_404_is_accepted_and_the_permission_is_ours(self):
        found = robots_module._robots_outcome(
            exists=False, fetch_failed=False, http_status=404, body_bytes=0,
            rule_count=0, sitemaps=[], allowed=True, checked_url="",
        )
        assert found["rung"] == Outcome.ACCEPTED.value
        assert found["claim_by"] == ClaimBy.INFERRED.value

    def test_no_response_at_all_is_indeterminate(self):
        found = robots_module._robots_outcome(
            exists=False, fetch_failed=True, http_status=0, body_bytes=0,
            rule_count=0, sitemaps=[], allowed=True, checked_url="",
        )
        assert found["rung"] == Outcome.INDETERMINATE.value
        assert found["claim_by"] == ClaimBy.INFERRED.value


class TestRobotsAllowedIsInferredWhenAbsent:
    """The literal ``true`` in the page script, pinned.

    ``allowed`` is computed from rules on exactly one path. Everywhere else it
    is a constant written into an early return, and it reads the same for "no
    robots.txt" and for "we could not find out". The rung and ``claim_by`` are
    what keep those apart now.
    """

    @pytest.mark.parametrize(
        "fetch_failed,status,expected",
        [
            (False, 404, Outcome.ACCEPTED),
            (False, 503, Outcome.ACCEPTED),
            (True, 0, Outcome.INDETERMINATE),
        ],
    )
    def test_an_unparsed_robots_never_reaches_observed(
        self, fetch_failed, status, expected
    ):
        found = robots_module._robots_outcome(
            exists=False, fetch_failed=fetch_failed, http_status=status,
            body_bytes=0, rule_count=0, sitemaps=[], allowed=True, checked_url="",
        )
        assert found["rung"] == expected.value
        assert found["claim_by"] == ClaimBy.INFERRED.value
        assert found["effects"][0]["allowed_is_inferred"] is True

    def test_a_5xx_is_recorded_even_though_the_module_still_says_allowed(self):
        """RFC 9309 says treat a 5xx as disallow. This module does not, yet.

        Fixing that is a change to crawl policy. What is fixed here is that the
        status now reaches the envelope, so the run is no longer an unqualified
        permission.
        """
        found = robots_module._robots_outcome(
            exists=False, fetch_failed=False, http_status=503, body_bytes=0,
            rule_count=0, sitemaps=[], allowed=True, checked_url="/x",
        )
        assert effect_named(found, "no_robots_directives")["http_status"] == 503


@pytest.mark.browser
class TestRobotsAgainstRealServer:
    @pytest.mark.asyncio
    async def test_a_real_robots_txt_is_observed(self, browser_ctx, site):
        await browser_ctx["browser"].real_page.goto(site)
        result = await run_module(
            "browser.robots", {"check_url": "/private/thing"}, browser_ctx
        )
        assert result["exists"] is True
        assert result["allowed"] is False
        assert result["rule_count"] == 2
        assert result["sitemaps"] == ["/sitemap.xml"]
        assert result["crawl_delay"] == 2
        assert rung_of(result) == Outcome.OBSERVED.value

    @pytest.mark.asyncio
    async def test_a_404_robots_txt_is_accepted(self, browser_ctx, bare_site):
        await browser_ctx["browser"].real_page.goto(bare_site)
        result = await run_module("browser.robots", {}, browser_ctx)
        assert result["exists"] is False
        assert result["fetch_failed"] is False
        assert result["http_status"] == 404
        found = envelope_of(result)
        assert found["rung"] == Outcome.ACCEPTED.value
        assert found["claim_by"] == ClaimBy.INFERRED.value

    @pytest.mark.asyncio
    async def test_an_origin_that_cannot_be_fetched_is_indeterminate(self, browser_ctx):
        """``about:blank`` has origin "null"; the fetch throws rather than answering."""
        result = await run_module("browser.robots", {}, browser_ctx)
        assert result["fetch_failed"] is True
        assert rung_of(result) == Outcome.INDETERMINATE.value


# ===========================================================================
# browser.sitemap -- a 404 is an answer, a dropped connection is not
# ===========================================================================

class TestRungSitemap:
    def test_parsed_urls_are_observed(self):
        found = sitemap_module._sitemap_outcome(
            urls=2, is_index=False, status=200, fetch_failed=False, error="",
            child_sitemaps=0, child_fetch_failures=0,
        )
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_named(found, "sitemap_urls_parsed")["count"] == 2

    def test_a_404_is_accepted(self):
        found = sitemap_module._sitemap_outcome(
            urls=0, is_index=False, status=404, fetch_failed=False,
            error="HTTP 404", child_sitemaps=0, child_fetch_failures=0,
        )
        assert found["rung"] == Outcome.ACCEPTED.value

    def test_a_transport_failure_is_indeterminate_not_accepted(self):
        found = sitemap_module._sitemap_outcome(
            urls=0, is_index=False, status=0, fetch_failed=True,
            error="Failed to fetch", child_sitemaps=0, child_fetch_failures=0,
        )
        assert found["rung"] == Outcome.INDETERMINATE.value

    def test_a_filtered_away_sitemap_is_accepted(self):
        """``url_pattern`` removing every entry looks exactly like an empty one."""
        found = sitemap_module._sitemap_outcome(
            urls=0, is_index=False, status=200, fetch_failed=False, error="",
            child_sitemaps=0, child_fetch_failures=0,
        )
        assert found["rung"] == Outcome.ACCEPTED.value

    def test_an_index_whose_children_all_failed_is_accepted_with_the_count(self):
        found = sitemap_module._sitemap_outcome(
            urls=0, is_index=True, status=200, fetch_failed=False, error="",
            child_sitemaps=4, child_fetch_failures=4,
        )
        assert found["rung"] == Outcome.ACCEPTED.value
        assert effect_named(found, "no_sitemap_urls")["child_fetch_failures"] == 4


@pytest.mark.browser
class TestSitemapAgainstRealServer:
    @pytest.mark.asyncio
    async def test_a_real_sitemap_is_observed(self, browser_ctx, site):
        await browser_ctx["browser"].real_page.goto(site)
        result = await run_module("browser.sitemap", {}, browser_ctx)
        assert result["count"] == 2
        assert result["http_status"] == 200
        assert rung_of(result) == Outcome.OBSERVED.value

    @pytest.mark.asyncio
    async def test_a_pattern_that_matches_nothing_is_accepted(self, browser_ctx, site):
        await browser_ctx["browser"].real_page.goto(site)
        result = await run_module(
            "browser.sitemap", {"url_pattern": "/nothing-matches-this/"}, browser_ctx
        )
        assert result["count"] == 0
        assert result["fetch_failed"] is False
        assert rung_of(result) == Outcome.ACCEPTED.value

    @pytest.mark.asyncio
    async def test_a_404_sitemap_is_accepted_and_carries_the_status(
        self, browser_ctx, bare_site
    ):
        await browser_ctx["browser"].real_page.goto(bare_site)
        result = await run_module("browser.sitemap", {}, browser_ctx)
        assert result["http_status"] == 404
        assert result["fetch_failed"] is False
        found = envelope_of(result)
        assert found["rung"] == Outcome.ACCEPTED.value
        assert effect_named(found, "no_sitemap_urls")["http_status"] == 404

    @pytest.mark.asyncio
    async def test_an_unfetchable_origin_is_indeterminate(self, browser_ctx):
        result = await run_module("browser.sitemap", {}, browser_ctx)
        assert result["fetch_failed"] is True
        assert rung_of(result) == Outcome.INDETERMINATE.value
