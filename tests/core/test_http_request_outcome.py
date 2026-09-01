"""What `http.request` is allowed to claim, and what it must not.

The rung is ACCEPTED and the whole point of these tests is that it stays there.
A status line is a real answer from the other side, so ACCEPTED is earned --
this module knows strictly more than one that fired and forgot. But it is the
peer's report of the peer's own work, and OBSERVED means "we saw the world
change". Nothing in `request.py` looks at the world: there is no second request,
no read-back, no comparison against anything. A 201 asserts a creation, a 202
says out loud that the work has not happened yet, and a 204 says nothing about
state at all -- and all three land on the same `is_ok` branch. The 2xx test at
request.py:427 sorts the peer's claim into two buckets; it does not check it.

So the tests below come in two halves. The first pins the rung and the shape.
The second is the one that matters: it feeds this module the replies that would
tempt a reader into promoting it -- a 202, a 201 with a Location header, a fat
JSON body -- and pins that the answer does not move. A rung that drifts upward
because a response looked convincing is the false green this ladder exists to
prevent.
"""

from typing import Any, Dict, Optional

import pytest

from core.engine.outcome import (
    ClaimBy,
    Outcome,
    ceiling_for,
    outranks,
    read_envelope,
)
from core.engine.step_executor.executor import step_outcome
from core.modules.atomic.http import request as http_module
from core.modules.items import items_to_legacy_context, wrap_legacy_result


class FakeResponse:
    """Only what `http_request` touches, and nothing it could observe with."""

    def __init__(
        self,
        status: int = 200,
        reason: str = "OK",
        headers: Optional[Dict[str, str]] = None,
        body: Any = "hello",
        url: str = "https://api.example.com/thing",
    ):
        self.status = status
        self.reason = reason
        self.headers = dict(headers or {})
        self.url = url
        self._body = body
        self.released = False

    async def read(self):
        return self._body if isinstance(self._body, bytes) else str(self._body).encode()

    async def text(self):
        return self._body if isinstance(self._body, str) else str(self._body)

    async def json(self):
        if isinstance(self._body, (dict, list)):
            return self._body
        raise ValueError("not json")

    def release(self):
        self.released = True


class _FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
def call(monkeypatch):
    """Run `http_request` against a canned response, with no socket anywhere.

    SSRF validation is switched off rather than fed a resolvable host: leaving it
    on makes this test do DNS for api.example.com, which is a network call in a
    unit test and a flake waiting to happen.
    """

    def _run(response: FakeResponse, **params):
        monkeypatch.setattr(http_module, "ssrf_protection_enabled", lambda: False)
        monkeypatch.setattr(
            http_module, "guarded_client_session", lambda **kwargs: _FakeSession()
        )

        async def _fake_request(session, method, url, **kwargs):
            return response

        monkeypatch.setattr(http_module, "guarded_aiohttp_request", _fake_request)

        merged = {"url": "https://api.example.com/thing", "method": "GET"}
        merged.update(params)
        import asyncio

        # `@register_module` has already replaced the module-level name with the
        # BaseModule subclass from `_wrap_function_as_module`
        # (registry/decorators.py:102); the coroutine itself is only reachable
        # through `__wrapped_func__`. Calling it directly is deliberate: this
        # slice is about what the function measures, and the wrapper contributes
        # nothing to that but a `self`.
        coroutine = http_module.http_request.__wrapped_func__
        return asyncio.run(coroutine({"params": merged}))

    return _run


def _envelope(result):
    return result["outcome"]


class TestTheRung:
    def test_a_200_claims_accepted(self, call):
        result = call(FakeResponse(status=200))

        assert result["ok"] is True
        assert _envelope(result)["rung"] == Outcome.ACCEPTED.value

    def test_nobody_claimed_an_expectation(self, call):
        """No caller declared one and the module infers none, so `claim_by` is
        NONE -- there is no expectation here that could have been broken."""
        assert _envelope(call(FakeResponse()))["claim_by"] == ClaimBy.NONE.value

    def test_no_postcondition_is_declared_or_evaluated(self, call):
        """None, not a plausible-sounding string. `register_module` accepts no
        `postcondition=` kwarg today, so nothing was declared; and nothing in
        this module evaluates a predicate, so nothing was evaluated either."""
        assert _envelope(call(FakeResponse()))["postcondition"] is None

    def test_no_evidence_is_referenced(self, call):
        """There is no run artifact. A ref pointing at nothing is worse than
        none, because it invites a reader to go looking."""
        assert _envelope(call(FakeResponse()))["evidence_ref"] is None

    def test_the_envelope_is_absent_from_a_non_2xx_reply(self, call):
        """A 404 comes back `ok: False`, which `wrap_legacy_result` turns into an
        ERROR result whose `data` is discarded -- so an envelope written on that
        branch could not be read by anything. See the report: the off-ladder
        rungs have nowhere to sit on this module until that changes."""
        result = call(FakeResponse(status=404, reason="Not Found"))

        assert result["ok"] is False
        assert "outcome" not in result


class TestItDoesNotClaimMoreThanItMeasured:
    """The half that has to keep working when somebody edits this module."""

    def test_accepted_is_strictly_below_observed(self):
        """Pinned as a statement about the ladder, not about this run: if a later
        change makes `outranks` treat these two as equal, the test that says the
        rung is ACCEPTED stops meaning anything."""
        assert outranks(Outcome.OBSERVED, Outcome.ACCEPTED)

    def test_it_never_reaches_the_ceiling_its_declaration_allows(self, call):
        """`ceiling_for(None)` is OBSERVED, and this module sits a rung under it.

        Worth pinning precisely because the ceiling is the tempting number: a
        reader who checks only "are we within what we're allowed to claim" would
        conclude there is headroom to spend. There is not. The ceiling is a limit
        on the claim; the evidence is what sets the claim.
        """
        rung = _envelope(call(FakeResponse()))["rung"]

        assert ceiling_for(None) is Outcome.OBSERVED
        assert outranks(ceiling_for(None), rung)

    @pytest.mark.parametrize(
        "status,reason",
        [
            (200, "OK"),
            (201, "Created"),
            (202, "Accepted"),
            (204, "No Content"),
        ],
    )
    def test_every_2xx_says_the_same_thing_about_reality(self, call, status, reason):
        """201 asserts a creation, 202 states the work has NOT happened, 204
        reports nothing about state. The module cannot tell these apart in
        evidence terms -- it read a number off a socket in every case -- so it
        must not report them differently."""
        response = FakeResponse(
            status=status, reason=reason, headers={"Location": "/things/7"}
        )

        assert _envelope(call(response))["rung"] == Outcome.ACCEPTED.value

    def test_a_convincing_body_does_not_promote_the_rung(self, call):
        """The server returning the object it says it made is still the server
        talking about itself. No read-back happened."""
        response = FakeResponse(
            status=201,
            reason="Created",
            headers={"Content-Type": "application/json"},
            body={"id": 7, "created": True, "verified": True},
        )

        assert _envelope(call(response))["rung"] == Outcome.ACCEPTED.value


class TestTheEffectsNameOnlyWhatWasMeasured:
    def test_the_status_line_is_recorded_as_read(self, call):
        effects = _envelope(call(FakeResponse(status=201, reason="Created")))["effects"]
        status_effect = next(e for e in effects if e["effect"] == "http_status_received")

        assert status_effect["status"] == 201
        assert status_effect["reason"] == "Created"

    def test_bytes_received_is_a_real_count_when_we_hold_real_bytes(self, call):
        """`response_type='binary'` is the one path where `_read_response_body`
        hands back the wire payload untouched, so `len()` is a byte count."""
        response = FakeResponse(body=b"\x00\x01\x02\x03")
        effects = _envelope(call(response, response_type="binary"))["effects"]
        body_effect = next(e for e in effects if e["effect"] == "response_body_read")

        assert body_effect["bytes_received"] == 4

    def test_bytes_received_is_none_for_decoded_text(self, call):
        """A str's length is characters. Reporting it as `bytes_received` would
        be off by a factor of up to four on non-ASCII and would read to every
        consumer as a measurement of the wire."""
        response = FakeResponse(body="héllo wörld")
        effects = _envelope(call(response, response_type="text"))["effects"]
        body_effect = next(e for e in effects if e["effect"] == "response_body_read")

        assert body_effect["bytes_received"] is None

    def test_bytes_received_is_none_for_parsed_json(self, call):
        """A parsed dict has no size. The module's own `content_length` output
        falls back to `len(str(body))` here -- the length of a Python repr --
        which is exactly the kind of number that must not become evidence."""
        response = FakeResponse(
            headers={"Content-Type": "application/json"}, body={"a": 1, "b": 2}
        )
        effects = _envelope(call(response))["effects"]
        body_effect = next(e for e in effects if e["effect"] == "response_body_read")

        assert body_effect["bytes_received"] is None

    def test_content_length_is_recorded_as_the_peers_claim(self, call):
        """Named `declared_content_length` and never `bytes_received`, because a
        header is what the peer intended to send, not what arrived. A truncated
        response has an intact Content-Length."""
        response = FakeResponse(headers={"Content-Length": "4096"}, body="short")
        effects = _envelope(call(response, response_type="text"))["effects"]
        body_effect = next(e for e in effects if e["effect"] == "response_body_read")

        assert body_effect["declared_content_length"] == 4096
        assert body_effect["bytes_received"] is None

    def test_a_malformed_content_length_header_is_not_invented_into_a_number(self):
        """`_observed_effects` is called directly here, not through the module.

        The guard being pinned is the one in `_observed_effects` itself, kept
        separate from the module-level path the next test now covers: a header
        is peer-controlled input and a bad one must produce None, not an
        exception and not a fabricated number.
        """
        response = FakeResponse(headers={"Content-Length": "not-a-number"})
        effects = http_module._observed_effects(response, "body")
        body_effect = next(e for e in effects if e["effect"] == "response_body_read")

        assert body_effect["declared_content_length"] is None

    def test_a_malformed_content_length_leaves_the_successful_response_intact(
        self, call
    ):
        """FOUND BY THIS SLICE, AND NOW FIXED -- this pins the fix.

        `_compute_content_length` called `int(header)` with no guard, so a peer
        answering 200 with `Content-Length: not-a-number` raised ValueError,
        which the broad `except Exception` in the request loop converted into a
        REQUEST_ERROR: a request that had already succeeded reported as a step
        failure, and with `retry_count` set, re-sent N pointless times. The
        header is attacker-controlled on any URL a workflow does not own, so
        that was a remote party choosing whether our step failed.

        A header that does not parse is not a number, so it is treated exactly
        as an absent one and the body is measured instead. `retry_count=3` is
        passed deliberately: `retries` is only written when `attempt > 0`, so
        `ok` true with no `retries` key is the assertion that the retry storm is
        gone -- the request was made once and answered once.

        The rung is untouched by any of this, which was always the point: what
        the module may CLAIM does not depend on whether a header parsed.
        """
        result = call(
            FakeResponse(headers={"Content-Length": "not-a-number"}, body="hello"),
            retry_count=3,
        )

        assert result["ok"] is True
        assert "error_code" not in result
        assert "retries" not in result
        assert _envelope(result)["rung"] == Outcome.ACCEPTED.value

        # Falls back to the no-header behaviour rather than to a special case:
        # the same body measured the same way it would be with no header at all.
        assert result["content_length"] == http_module._compute_content_length(
            None, "hello"
        )
        assert http_module._compute_content_length(
            "not-a-number", "hello"
        ) == http_module._compute_content_length(None, "hello")

        # Nothing else is swallowed: a header that IS a number is still used.
        assert http_module._compute_content_length("4096", "hello") == 4096

        # And the effect still refuses to invent the peer's claim.
        body_effect = next(
            e for e in _envelope(result)["effects"] if e["effect"] == "response_body_read"
        )
        assert body_effect["declared_content_length"] is None

    def test_no_effect_claims_the_resource_changed(self, call):
        """The whole registry of effect names this module may emit. Adding one
        that asserts remote state -- 'resource_created', 'row_written' -- means
        the rung has to be re-argued from evidence first."""
        response = FakeResponse(status=201, reason="Created")
        names = {e["effect"] for e in _envelope(call(response))["effects"]}

        assert names == {"http_status_received", "response_body_read"}


class TestItSurvivesTheWayThisModuleIsActuallyWrapped:
    """`http_request` returns a FLAT dict with no `data` key.

    That matters more than it looks. `wrap_legacy_result` (modules/items.py:348)
    reads `result.get("data")`, finds nothing, and sweeps every remaining
    non-meta field into the item json -- which then becomes `data` on the way
    out. So the envelope written as a top-level key arrives under `data`, where
    `read_envelope` requires it, without this module ever nesting it by hand.
    Nothing states that contract in one place, so it is pinned here: a future
    edit that gives this module a `data` key would silently strip the envelope.
    """

    def test_the_envelope_lands_under_data(self, call):
        legacy = items_to_legacy_context(wrap_legacy_result(call(FakeResponse())))
        found = read_envelope(legacy["data"])

        assert found is not None
        assert found["rung"] == Outcome.ACCEPTED.value

    def test_the_engine_reads_the_rung_off_a_wrapped_result(self, call):
        legacy = items_to_legacy_context(wrap_legacy_result(call(FakeResponse())))
        rung, claim_by, expected = step_outcome(legacy)

        assert rung is Outcome.ACCEPTED
        assert claim_by == ClaimBy.NONE.value
        assert expected is None

    def test_a_non_2xx_carries_no_rung_at_all(self, call):
        """Not a low rung -- nothing. `wrap_legacy_result` takes the ERROR branch
        and `to_legacy_dict` emits only ok/error/error_code."""
        legacy = items_to_legacy_context(
            wrap_legacy_result(call(FakeResponse(status=500, reason="Server Error")))
        )

        assert legacy["ok"] is False
        assert step_outcome(legacy) is None
