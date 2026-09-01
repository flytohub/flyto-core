# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""What the six `core.* / auth.* / ui.* / verify.*` modules may claim, and why none of it is OBSERVED.

THE GROUP-WIDE ANSWER IS ACCEPTED, and
:class:`TestNothingInThisGroupSaysItSawAnything` pins it for all six at once.
Every module here sends one request -- or, in `ui.evaluate`'s case, delegates
one -- and reads the reply to that same request. Not one of them reads anything
back. A token in a JSON body, ten search results, a Figma node, an OpenAI
completion: each is the far end describing work it says it did, which is
`http.request`'s settled position for every 2xx in this product and what all
thirteen `api.*` modules concluded (`tests/modules/test_api_outcome.py`).

That is still worth having, because the alternative was never OBSERVED. It was
DISPATCHED -- what `default_for` stamps on a module that reports nothing, and
what all six said before this change. "The instruction left us and nobody
confirmed anything" is untrue of a call that came back 200 with a node in it.

WHERE THE GROUP EARNS ITS KEEP IS OFF THE LADDER, on the paths nobody writes
tests for:

  nothing was sent at all                FAILED
      Four of the six return an error before opening a socket -- no API key, no
      credentials, an SSRF-blocked URL. Without an envelope the engine stamps
      those `dispatched`, which asserts an instruction left this machine when
      none did. Three of them (the search modules) also return no `ok` key, so
      the step is recorded a SUCCESS and a setup guide flows downstream shaped
      like search results.

  the peer named a refusal               FAILED
  the peer said nothing at all           INDETERMINATE
      `auth.oauth2` is where this split is load-bearing. It is
      `retryable=True, max_retries=2` and it consumes single-use grants, so
      "the provider answered 400" and "the provider answered 503" cannot be the
      same answer: the second may have spent the code that the retry will be
      told is invalid.

  the reply did not contain what was asked for   FAILED, claim_by=caller
      `verify.figma` asked for a node id and got a reply without one. See
      :class:`TestFigmaNoLongerReturnsAnEmptyNodeAsAPlainSuccess` -- that path
      used to be `ok: True` with `{'style': {}}` in it.

TWO REAL BUGS came out of writing these, and both are pinned below rather than
described:

  * `ui.evaluate` could never run. Its first statement imported
    `.._import_helper`, a module that does not exist anywhere in the tree, so
    every call raised ModuleNotFoundError before reading a parameter.
    :class:`TestUIEvaluateRunsAtAll` is the regression test.
  * `verify.figma` returned an empty node as a success when Figma's reply
    carried nothing for the requested id.
"""

import asyncio
import importlib
import json
import re
import sys
from pathlib import Path

import aiohttp
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from core.engine.outcome import ClaimBy, Outcome, envelope, read_envelope
from core.engine.step_executor.executor import (
    _apply_outcome_contract,
    _unconfirmed_outcome,
    step_outcome,
)
from core.utils import SSRFError

oauth2 = importlib.import_module('core.modules.atomic.auth.oauth2')
search = importlib.import_module('core.modules.third_party.developer.http.search')
figma = importlib.import_module('core.modules.atomic.verify.figma')
ui_evaluate_mod = importlib.import_module('core.modules.atomic.ui.evaluate')
vision_analyze_mod = importlib.import_module('core.modules.atomic.vision.analyze')

from core.constants import APIEndpoints, EnvVars  # noqa: E402

# Not a credential. Every module in this group reads a key from a parameter or
# the environment before it builds a request; these tests hand it a value that
# is obviously not one so the code path runs without depending on a developer's
# real environment. Nothing here is ever sent anywhere -- every transport is
# replaced below.
NOT_A_KEY = "not-a-real-key"


# ===========================================================================
# Transports, replaced.
# ===========================================================================

class _AioReply:
    """One aiohttp response, in the two shapes this group's modules use."""

    def __init__(self, status=200, payload=None, content_type='application/json'):
        self.status = status
        self._payload = payload if payload is not None else {}
        self.headers = {'Content-Type': content_type}
        self.released = False

    async def json(self):
        return self._payload

    async def text(self):
        return json.dumps(self._payload)

    def release(self):
        self.released = True

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class _AioSession:
    """A session whose get/post return a prepared reply and record the call."""

    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def get(self, url, **kwargs):
        self.calls.append(('GET', url, kwargs))
        return self.reply

    def post(self, url, **kwargs):
        self.calls.append(('POST', url, kwargs))
        return self.reply


def _aio_session_factory(reply, captured):
    def factory(*args, **kwargs):
        session = _AioSession(reply)
        captured.append(session)
        return session

    return factory


# ===========================================================================
# auth.oauth2
# ===========================================================================

def _run_oauth2(params):
    return oauth2.auth_oauth2(params, {}).execute()


BASE_OAUTH_PARAMS = {
    'token_url': 'https://example.com/exchange',
    'grant_type': 'authorization_code',
    'client_id': 'test-client',
    'code': 'a-code',
}


def _oauth2_transport(monkeypatch, *, reply=None, raises=None):
    """Replace the three seams between this module and the network."""
    monkeypatch.setattr(oauth2, 'enforce_outbound_url', lambda url: url)

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(oauth2, 'guarded_client_session', lambda **kwargs: _Session())

    async def fake_request(session, method, url, **kwargs):
        if raises is not None:
            raise raises
        return reply

    monkeypatch.setattr(oauth2, 'guarded_aiohttp_request', fake_request)


class TestOAuth2SaysHowFarTheExchangeGot:
    @pytest.mark.asyncio
    async def test_a_reply_with_a_grant_is_accepted_and_no_higher(self, monkeypatch):
        """The rung the whole group settles on, on the module that mints credentials.

        Not OBSERVED: nothing in this module presents the credential to a
        resource server, so "a token that works" was never seen. What was seen
        is a provider saying it issued one.
        """
        _oauth2_transport(monkeypatch, reply=_AioReply(200, {
            'access_token': 'x' * 20, 'token_type': 'Bearer', 'expires_in': 3600,
        }))

        result = await _run_oauth2(BASE_OAUTH_PARAMS)

        found = read_envelope(result)
        assert result['ok'] is True
        assert found['rung'] == Outcome.ACCEPTED.value
        assert found['postcondition'] is None
        effect = found['effects'][1]
        assert effect['carries_access_grant'] is True
        assert effect['expires_in'] == 3600

    @pytest.mark.asyncio
    async def test_a_2xx_with_no_grant_in_it_is_still_only_accepted(self, monkeypatch):
        """The path that proves the rung does not rest on the token.

        `data.get('access_token', '')` yields '' for a 200 whose body carries no
        credential, and the module returns ok=True with an empty string. The
        rung is unchanged -- a reply arrived either way -- and the difference is
        recorded as the fact it is, where a consumer can see it.
        """
        _oauth2_transport(monkeypatch, reply=_AioReply(200, {'token_type': 'Bearer'}))

        result = await _run_oauth2(BASE_OAUTH_PARAMS)

        found = read_envelope(result)
        assert result['ok'] is True
        assert result['access_token'] == ''
        assert found['rung'] == Outcome.ACCEPTED.value
        assert found['effects'][1]['carries_access_grant'] is False

    @pytest.mark.asyncio
    async def test_a_4xx_is_failed_because_the_provider_named_the_refusal(self, monkeypatch):
        _oauth2_transport(monkeypatch, reply=_AioReply(400, {'error': 'invalid_grant'}))

        result = await _run_oauth2(BASE_OAUTH_PARAMS)

        found = read_envelope(result)
        assert result['ok'] is False
        assert found['rung'] == Outcome.FAILED.value
        assert found['effects'][1]['error_named_in_body'] is True

    @pytest.mark.asyncio
    async def test_the_refusal_envelope_does_not_carry_the_error_body(self, monkeypatch):
        """The envelope is part of the result, so the redaction rule binds it too.

        `tests/core/test_reported_security_advisories.py` asserts a token
        endpoint's error body appears nowhere in `repr(result)`. An effect field
        holding `data['error']` would have reopened that hole from inside the
        outcome contract, which is why the effect carries a boolean.
        """
        _oauth2_transport(monkeypatch, reply=_AioReply(400, {
            'error': 'secret-service-value',
            'error_description': 'sensitive internal response',
        }))

        result = await _run_oauth2(BASE_OAUTH_PARAMS)

        assert 'secret-service-value' not in repr(result)
        assert 'sensitive internal response' not in repr(result)

    @pytest.mark.asyncio
    async def test_a_5xx_is_indeterminate_because_a_single_use_grant_may_be_spent(
        self, monkeypatch
    ):
        """The split that makes `retryable=True` safe to read.

        A 400 and a 503 both used to be one `TOKEN_ENDPOINT_ERROR`. They are not
        one fact: the provider that answered 400 said it issued nothing, and the
        provider that answered 503 said nothing at all -- and an
        authorization_code is single-use, so the retry this module is configured
        for may be spending a code the first attempt already consumed.
        """
        _oauth2_transport(monkeypatch, reply=_AioReply(503, {}))

        result = await _run_oauth2(BASE_OAUTH_PARAMS)

        found = read_envelope(result)
        assert result['ok'] is False
        assert found['rung'] == Outcome.INDETERMINATE.value
        assert found['effects'][1]['reason'] == 'server_error'

    @pytest.mark.asyncio
    @pytest.mark.parametrize(('raises', 'reason'), [
        (asyncio.TimeoutError(), 'timeout'),
        (aiohttp.ClientError('connection reset'), 'transport_error'),
        (SSRFError('blocked redirect hop'), 'ssrf_blocked_redirect'),
        (RuntimeError('something else entirely'), 'unexpected_error'),
    ])
    async def test_every_way_of_not_getting_an_answer_is_indeterminate(
        self, monkeypatch, raises, reason
    ):
        """Four handlers, one honest answer: we do not know what the provider did.

        The textbook indeterminate is the timeout, and the other three are the
        same fact arriving differently. None of them may claim FAILED: the POST
        may have been received in full.
        """
        _oauth2_transport(monkeypatch, raises=raises)

        result = await _run_oauth2(BASE_OAUTH_PARAMS)

        found = read_envelope(result)
        assert result['ok'] is False
        assert found['rung'] == Outcome.INDETERMINATE.value
        assert found['effects'][-1]['reason'] == reason

    @pytest.mark.asyncio
    async def test_a_url_blocked_before_the_session_is_failed_and_says_nothing_was_sent(
        self, monkeypatch
    ):
        """The same exception type as the test above, and deliberately not the same rung.

        `enforce_outbound_url` runs before a session exists, so nothing left
        this machine -- a fact the default stamp (`dispatched`) would state
        backwards. The in-flight SSRFError cannot claim this, because the
        initial URL passed this same check and what the guard blocks in there is
        a redirect hop: the POST was already sent.
        """
        def blocked(url):
            raise SSRFError('metadata endpoint')

        monkeypatch.setattr(oauth2, 'enforce_outbound_url', blocked)

        def forbidden_session(**kwargs):
            raise AssertionError('a session was opened for a blocked target')

        monkeypatch.setattr(oauth2, 'guarded_client_session', forbidden_session)

        result = await _run_oauth2(BASE_OAUTH_PARAMS)

        found = read_envelope(result)
        assert found['rung'] == Outcome.FAILED.value
        assert found['effects'][0]['kind'] == 'request_not_sent'

    @pytest.mark.asyncio
    async def test_the_envelope_survives_the_engine_and_reaches_step_outcome(
        self, monkeypatch
    ):
        """A flat-dict module's envelope has to land where the engine reads it.

        `auth.oauth2` returns no `data` key, so `wrap_legacy_result` sweeps its
        fields into `data` and the envelope rides along. This asserts the whole
        path: the contract-applier neither overwrites nor caps it, and
        `step_outcome` returns the module's own claim.
        """
        _oauth2_transport(monkeypatch, reply=_AioReply(200, {'access_token': 'x' * 12}))

        result = await _run_oauth2(BASE_OAUTH_PARAMS)
        stamped = _apply_outcome_contract(oauth2.auth_oauth2({}, {}), result)

        rung, claim_by, _ = step_outcome(stamped)
        assert rung is Outcome.ACCEPTED
        assert claim_by == ClaimBy.NONE.value


# ===========================================================================
# core.api.google_search / serpapi_search / tavily_search
# ===========================================================================

class TestSearchModulesReportTheReplyAndNotTheResults:
    @pytest.mark.asyncio
    async def test_google_results_are_accepted_and_the_count_is_only_recorded(
        self, monkeypatch
    ):
        """ACCEPTED, and the count does not lift it.

        `database.query` earns OBSERVED from `len(rows)` because the rows ARE
        the state a SELECT went to look at. A search API's `items` array is a
        document the vendor composed about a query it ran for us, so the count
        is a measurement of the reply, not of the world. It rides in the effect
        where a consumer can read it, and decides nothing.
        """
        monkeypatch.setenv(EnvVars.GOOGLE_API_KEY, NOT_A_KEY)
        monkeypatch.setenv(EnvVars.GOOGLE_SEARCH_ENGINE_ID, 'cx-1')
        reply = _AioReply(200, {
            'items': [
                {'title': 'One', 'link': 'https://example.com/1', 'snippet': 'a'},
                {'title': 'Two', 'link': 'https://example.com/2', 'snippet': 'b'},
            ],
            'searchInformation': {'totalResults': '2'},
        })
        monkeypatch.setattr(
            search.aiohttp, 'ClientSession', _aio_session_factory(reply, []))

        result = await search.GoogleSearchAPIModule({'keyword': 'flyto'}, {}).execute()

        found = read_envelope(result)
        assert result['count'] == 2
        assert found['rung'] == Outcome.ACCEPTED.value
        assert found['effects'][0]['results_in_reply'] == 2

    @pytest.mark.asyncio
    async def test_zero_results_is_the_same_rung_and_a_different_recorded_fact(
        self, monkeypatch
    ):
        """An empty array does not lower the rung, because the rung is not about it.

        This is the case that would have been wrong in both directions. Claiming
        OBSERVED on `len(results)` would rest a rung on a 0 that reads
        identically for a query that matched nothing and for a renamed response
        key. Lowering the rung for an empty reply would state that the API
        answered less than it did.
        """
        monkeypatch.setenv(EnvVars.GOOGLE_API_KEY, NOT_A_KEY)
        monkeypatch.setenv(EnvVars.GOOGLE_SEARCH_ENGINE_ID, 'cx-1')
        monkeypatch.setattr(
            search.aiohttp, 'ClientSession',
            _aio_session_factory(_AioReply(200, {}), []))

        result = await search.GoogleSearchAPIModule({'keyword': 'flyto'}, {}).execute()

        found = read_envelope(result)
        assert result['count'] == 0
        assert found['rung'] == Outcome.ACCEPTED.value
        assert found['effects'][0]['results_in_reply'] == 0

    @pytest.mark.asyncio
    async def test_a_refused_search_is_failed(self, monkeypatch):
        """FAILED, not INDETERMINATE: a read leaves no effect in doubt.

        Nothing was written at either end, so what is missing is data and not
        certainty. `integrations/outcomes.py::read_refused` reaches the same
        answer from the same argument.
        """
        monkeypatch.setenv(EnvVars.GOOGLE_API_KEY, NOT_A_KEY)
        monkeypatch.setenv(EnvVars.GOOGLE_SEARCH_ENGINE_ID, 'cx-1')
        monkeypatch.setattr(
            search.aiohttp, 'ClientSession',
            _aio_session_factory(
                _AioReply(403, {'error': {'message': 'quota exceeded'}}), []))

        result = await search.GoogleSearchAPIModule({'keyword': 'flyto'}, {}).execute()

        found = read_envelope(result)
        assert result['status'] == 'error'
        assert found['rung'] == Outcome.FAILED.value
        assert found['effects'][0]['status'] == 403

    @pytest.mark.asyncio
    @pytest.mark.parametrize(('module_name', 'env_keys', 'service'), [
        ('GoogleSearchAPIModule',
         (EnvVars.GOOGLE_API_KEY, EnvVars.GOOGLE_SEARCH_ENGINE_ID), 'google'),
        ('SerpAPISearchModule', (EnvVars.SERPAPI_KEY,), 'serpapi'),
        ('TavilySearchModule', (EnvVars.TAVILY_API_KEY,), 'tavily'),
    ])
    async def test_an_unconfigured_search_says_nothing_was_sent(
        self, monkeypatch, module_name, env_keys, service
    ):
        """The three returns the engine would otherwise stamp `dispatched`.

        These carry no `ok` key, so the step is recorded a SUCCESS and a setup
        guide flows downstream in the shape of a search result. Nothing here
        makes that return an error -- that is a behaviour change three modules
        wide -- but the rung now says what it is: no request was built and none
        was sent.
        """
        for key in env_keys:
            monkeypatch.delenv(key, raising=False)

        def forbidden_session(*args, **kwargs):
            raise AssertionError('a session was opened without credentials')

        monkeypatch.setattr(search.aiohttp, 'ClientSession', forbidden_session)

        module = getattr(search, module_name)
        result = await module({'keyword': 'flyto'}, {}).execute()

        found = read_envelope(result)
        assert result['status'] == 'error'
        assert found['rung'] == Outcome.FAILED.value
        assert found['effects'][0]['kind'] == 'request_not_sent'
        assert found['effects'][0]['service'] == service

    @pytest.mark.asyncio
    async def test_tavily_and_serpapi_answer_the_same_way_as_google(self, monkeypatch):
        """One argument, three modules: same transport shape, same rung."""
        monkeypatch.setenv(EnvVars.SERPAPI_KEY, NOT_A_KEY)
        monkeypatch.setenv(EnvVars.TAVILY_API_KEY, NOT_A_KEY)

        monkeypatch.setattr(
            search.aiohttp, 'ClientSession',
            _aio_session_factory(_AioReply(200, {
                'organic_results': [{'title': 'a', 'link': 'u', 'snippet': 's'}]}), []))
        serp = await search.SerpAPISearchModule({'keyword': 'flyto'}, {}).execute()

        captured = []
        monkeypatch.setattr(
            search.aiohttp, 'ClientSession',
            _aio_session_factory(_AioReply(200, {
                'results': [{'title': 'a', 'url': 'u', 'content': 'c'}]}), captured))
        tavily = await search.TavilySearchModule({'keyword': 'flyto'}, {}).execute()

        assert read_envelope(serp)['rung'] == Outcome.ACCEPTED.value
        assert read_envelope(tavily)['rung'] == Outcome.ACCEPTED.value
        assert captured[0].calls[0][1] == APIEndpoints.TAVILY_BASE_URL

    @pytest.mark.asyncio
    async def test_the_envelope_lands_where_the_engine_looks_for_it(self, monkeypatch):
        """These three return `data` as a LIST, which decides where the envelope goes.

        `_apply_outcome_contract` writes to `result['data']` only when it is a
        dict and to the top level otherwise, so for a module whose `data` is an
        array of search results the top level is both the only place an envelope
        fits and the place the engine would have stamped its default. This pins
        that they agree.
        """
        monkeypatch.setenv(EnvVars.TAVILY_API_KEY, NOT_A_KEY)
        monkeypatch.setattr(
            search.aiohttp, 'ClientSession',
            _aio_session_factory(_AioReply(200, {'results': []}), []))

        result = await search.TavilySearchModule({'keyword': 'flyto'}, {}).execute()
        stamped = _apply_outcome_contract(
            search.TavilySearchModule({'keyword': 'flyto'}, {}), result)

        assert stamped['outcome']['rung'] == Outcome.ACCEPTED.value
        rung, _, _ = step_outcome(stamped)
        assert rung is Outcome.ACCEPTED


# ===========================================================================
# verify.figma
# ===========================================================================

class _HttpxReply:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError('unexpected non-2xx in a test that does not use one')

    def json(self):
        return self._payload


class _HttpxClient:
    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.reply


def _figma_transport(monkeypatch, payload):
    import core.utils as utils_module
    client = _HttpxClient(_HttpxReply(payload))
    monkeypatch.setattr(utils_module, 'guarded_httpx_client', lambda *a, **k: client)
    return client


async def _run_figma(params):
    module = figma.VerifyFigmaModule(params, {})
    module.validate_params()
    return await module.execute()


NODE_PAYLOAD = {
    'id': '1:2',
    'name': 'Primary Button',
    'type': 'FRAME',
    'cornerRadius': 8,
    'absoluteBoundingBox': {'width': 120, 'height': 40},
}


class TestFigmaReadsOneReplyAndSaysSo:
    @pytest.mark.asyncio
    async def test_a_node_that_came_back_is_accepted(self, monkeypatch):
        _figma_transport(monkeypatch, {'nodes': {'1:2': {'document': NODE_PAYLOAD}}})

        result = await _run_figma({
            'file_id': 'abc', 'node_id': '1:2', 'token': NOT_A_KEY})

        found = read_envelope(result['data'])
        assert result['ok'] is True
        assert found['rung'] == Outcome.ACCEPTED.value
        assert found['claim_by'] == ClaimBy.CALLER.value
        assert found['effects'][0]['node_id'] == '1:2'

    @pytest.mark.asyncio
    async def test_a_whole_file_fetch_claims_nothing_on_the_callers_behalf(
        self, monkeypatch
    ):
        """No node was named, so no caller contract is in play: claim_by is none."""
        _figma_transport(monkeypatch, {'document': NODE_PAYLOAD})

        result = await _run_figma({'file_id': 'abc', 'token': NOT_A_KEY})

        found = read_envelope(result['data'])
        assert found['rung'] == Outcome.ACCEPTED.value
        assert found['claim_by'] == ClaimBy.NONE.value

    @pytest.mark.asyncio
    async def test_a_named_node_that_was_found_is_accepted_and_not_verified(
        self, monkeypatch
    ):
        """`find_by_name` really does evaluate a predicate, and it is still not VERIFIED.

        A caller named a node, the module walked the tree and the node was
        there. That is the closest anything in this group comes to a
        postcondition -- and it is a selector over data Figma handed us, not a
        check that an effect of ours landed. The rung stays where the evidence
        is: one reply, read once.
        """
        _figma_transport(monkeypatch, {'document': {
            'id': '0:0', 'name': 'Document', 'type': 'DOCUMENT',
            'children': [NODE_PAYLOAD],
        }})

        result = await _run_figma({
            'file_id': 'abc', 'node_name': 'Primary Button', 'token': NOT_A_KEY})

        found = read_envelope(result['data'])
        assert result['data']['node']['id'] == '1:2'
        assert found['rung'] == Outcome.ACCEPTED.value
        assert found['claim_by'] == ClaimBy.CALLER.value
        assert found['postcondition'] is None

    @pytest.mark.asyncio
    async def test_a_named_node_that_was_not_in_the_file_is_failed_by_the_caller(
        self, monkeypatch
    ):
        """The caller declared the expectation, so the unmet one is FAILED.

        `engine/outcome.py` splits failed from indeterminate on exactly this:
        an expectation of ours that may be wrong is indeterminate, and a
        contract the caller wrote is failed.
        """
        _figma_transport(monkeypatch, {'document': NODE_PAYLOAD})

        result = await _run_figma({
            'file_id': 'abc', 'node_name': 'Nowhere', 'token': NOT_A_KEY})

        found = read_envelope(result)
        assert result['ok'] is False
        assert found['rung'] == Outcome.FAILED.value
        assert found['claim_by'] == ClaimBy.CALLER.value
        assert found['effects'][0]['target'] == 'Nowhere'


class TestFigmaNoLongerReturnsAnEmptyNodeAsAPlainSuccess:
    @pytest.mark.asyncio
    async def test_a_node_id_missing_from_the_reply_no_longer_looks_like_success(
        self, monkeypatch
    ):
        """The bug this work found, pinned.

        `nodes.get(node_id, {}).get('document', {})` is `{}` for an id Figma did
        not return, `parse_node({})` makes an id-less node with no style, and
        the module returned `ok: True` with it -- indistinguishable, to a
        consumer, from a component that genuinely has no style overrides.

        `ok` stays True on purpose. Turning this into an error would change what
        every workflow using this module does; the rung makes the same fact
        visible without deciding that for anyone, and the engine degrades the
        step's ledger entry on its own.
        """
        _figma_transport(monkeypatch, {'nodes': {}})

        result = await _run_figma({
            'file_id': 'abc', 'node_id': '9:9', 'token': NOT_A_KEY})

        found = read_envelope(result['data'])
        assert result['ok'] is True
        assert result['data']['style'] == {}
        assert found['rung'] == Outcome.FAILED.value
        assert found['claim_by'] == ClaimBy.CALLER.value
        assert found['effects'][0]['target'] == '9:9'

    @pytest.mark.asyncio
    async def test_a_reply_with_no_document_is_the_same_shape_and_the_same_answer(
        self, monkeypatch
    ):
        _figma_transport(monkeypatch, {})

        result = await _run_figma({'file_id': 'abc', 'token': NOT_A_KEY})

        found = read_envelope(result['data'])
        assert result['ok'] is True
        assert found['rung'] == Outcome.FAILED.value
        assert found['effects'][0]['target'] == 'abc'

    @pytest.mark.asyncio
    async def test_the_engine_stops_calling_that_step_a_clean_success(self, monkeypatch):
        """The half of the fix that lives in the engine, exercised end to end.

        A FAILED rung on an `ok: True` result is what
        `_record_unconfirmed_outcome` reads to mark the step PARTIAL. Without
        the envelope this step is a plain green tick over an empty style dict.
        """
        _figma_transport(monkeypatch, {'nodes': {}})

        result = await _run_figma({
            'file_id': 'abc', 'node_id': '9:9', 'token': NOT_A_KEY})

        reason = _unconfirmed_outcome(result)
        assert reason is not None
        assert "outcome='failed'" in reason


# ===========================================================================
# ui.evaluate
# ===========================================================================

def _vision_returns(monkeypatch, payload):
    async def fake_vision(context):
        return payload

    monkeypatch.setattr(vision_analyze_mod, 'vision_analyze', fake_vision)


def _vision_raises(monkeypatch, error):
    async def fake_vision(context):
        raise error

    monkeypatch.setattr(vision_analyze_mod, 'vision_analyze', fake_vision)


UI_PARAMS = {'screenshot': './shot.png', 'api_key': NOT_A_KEY}

GOOD_ANALYSIS = json.dumps({
    'overall_score': 82,
    'scores': {'usability': 82},
    'strengths': ['clear hierarchy'],
    'issues': [],
    'recommendations': [],
    'summary': 'Solid.',
})


async def _run_ui(params):
    return await ui_evaluate_mod.ui_evaluate(params, {}).execute()


class TestUIEvaluateRunsAtAll:
    @pytest.mark.asyncio
    async def test_the_module_reaches_its_first_parameter(self, monkeypatch):
        """Regression test for a module that could never execute.

        The first statement of `ui_evaluate` imported
        `core.modules.atomic._import_helper`, which does not exist anywhere in
        the tree, so every call raised ModuleNotFoundError before reading a
        parameter. Nothing else in this file could have been true while that
        line was there.
        """
        _vision_returns(monkeypatch, {
            'ok': True, 'analysis': GOOD_ANALYSIS, 'structured': None,
            'model': 'gpt-4o', 'tokens_used': 1234,
        })

        result = await _run_ui(UI_PARAMS)

        assert result['ok'] is True
        assert result['overall_score'] == 82


class TestUIEvaluateReportsTheDelegationAndNotTheScore:
    @pytest.mark.asyncio
    async def test_a_successful_evaluation_is_accepted(self, monkeypatch):
        """ACCEPTED is the literal definition of what happened here.

        "The other side acknowledged taking it": `vision.analyze` reported
        success on its own work. This module issues no request of its own, so
        there is nothing above that available to it.
        """
        _vision_returns(monkeypatch, {
            'ok': True, 'analysis': GOOD_ANALYSIS, 'structured': None,
            'model': 'gpt-4o', 'tokens_used': 1234,
        })

        result = await _run_ui(UI_PARAMS)

        found = read_envelope(result)
        assert found['rung'] == Outcome.ACCEPTED.value
        assert found['effects'][0]['provider_usage_units'] == 1234
        assert found['effects'][0]['analysis_chars'] == len(GOOD_ANALYSIS)

    @pytest.mark.asyncio
    async def test_an_unparseable_reply_scores_zero_and_the_rung_does_not_move(
        self, monkeypatch
    ):
        """The `bytes_written` test, applied to a score.

        `_parse_evaluation` falls back to `overall_score = 0`, so `passed=False`
        is produced identically by a model that judged the screenshot harshly
        and by a reply this module could not read. A rung resting on `passed`
        would be resting on a value that says nothing about whether the call
        happened, so it rests on the reply having arrived instead.
        """
        _vision_returns(monkeypatch, {
            'ok': True, 'analysis': 'nothing parseable here', 'structured': None,
            'model': 'gpt-4o', 'tokens_used': 7,
        })

        result = await _run_ui(UI_PARAMS)

        found = read_envelope(result)
        assert result['passed'] is False
        assert result['overall_score'] == 0
        assert found['rung'] == Outcome.ACCEPTED.value

    @pytest.mark.asyncio
    async def test_no_api_key_says_nothing_was_sent(self, monkeypatch):
        monkeypatch.delenv('OPENAI_API_KEY', raising=False)

        def forbidden(context):
            raise AssertionError('the vision call was made without a key')

        monkeypatch.setattr(vision_analyze_mod, 'vision_analyze', forbidden)

        result = await _run_ui({'screenshot': './shot.png'})

        found = read_envelope(result)
        assert found['rung'] == Outcome.FAILED.value
        assert found['effects'][0]['kind'] == 'request_not_sent'

    @pytest.mark.asyncio
    async def test_a_raise_around_the_call_is_indeterminate(self, monkeypatch):
        """The handler spans the POST, so a raise says nothing about how far it got.

        Expensive to get wrong in the direction of FAILED: a retry buys a second
        completion for a call that may already have been billed.
        """
        _vision_raises(monkeypatch, RuntimeError('boom'))

        result = await _run_ui(UI_PARAMS)

        found = read_envelope(result)
        assert found['rung'] == Outcome.INDETERMINATE.value

    @pytest.mark.asyncio
    @pytest.mark.parametrize(('error_code', 'rung'), [
        ('MISSING_API_KEY', Outcome.FAILED),
        ('IMAGE_ERROR', Outcome.FAILED),
        ('OPENAI_ERROR', Outcome.FAILED),
        ('API_ERROR', Outcome.INDETERMINATE),
        ('SOMETHING_NEW', Outcome.INDETERMINATE),
    ])
    async def test_a_nested_failure_is_placed_by_its_error_code(
        self, monkeypatch, error_code, rung
    ):
        """Two of these never sent a request; one was refused; two are unknown.

        The codes are read out of `vision.analyze` rather than guessed, and the
        unknown ones fall to INDETERMINATE -- which is what an unplaceable
        failure of a paid API call is.
        """
        _vision_returns(monkeypatch, {'ok': False, 'error': 'x', 'error_code': error_code})

        result = await _run_ui(UI_PARAMS)

        assert read_envelope(result)['rung'] == rung.value

    @pytest.mark.asyncio
    async def test_an_envelope_from_the_nested_module_wins_over_our_inference(
        self, monkeypatch
    ):
        """Forward compatibility, and the right precedence.

        `vision.analyze` is still on the undeclared list. When it grows an
        envelope, the module that made the call is the one entitled to say how
        far it got, and this module must stop inferring. Pinning it now means
        the handover needs no change here.
        """
        theirs = envelope(Outcome.INDETERMINATE, claim_by=ClaimBy.INFERRED,
                          effects=[{'kind': 'their_own_fact'}])
        _vision_returns(monkeypatch, {
            'ok': False, 'error': 'x', 'error_code': 'MISSING_API_KEY', 'outcome': theirs})

        result = await _run_ui(UI_PARAMS)

        found = read_envelope(result)
        assert found == theirs
        assert found['effects'][0]['kind'] == 'their_own_fact'


# ===========================================================================
# The group-wide claim
# ===========================================================================

GROUP_SOURCES = {
    'auth.oauth2': 'core/modules/atomic/auth/oauth2.py',
    'core.api.*': 'core/modules/third_party/developer/http/search.py',
    'ui.evaluate': 'core/modules/atomic/ui/evaluate.py',
    'verify.figma': 'core/modules/atomic/verify/figma.py',
}

#: The six, by the id the registry knows them under. Three of them share the
#: one source file above.
GROUP_MODULE_IDS = (
    'auth.oauth2',
    'core.api.google_search',
    'core.api.serpapi_search',
    'core.api.tavily_search',
    'ui.evaluate',
    'verify.figma',
)


class TestNothingInThisGroupSaysItSawAnything:
    @pytest.mark.parametrize('module_id', sorted(GROUP_SOURCES))
    def test_no_source_file_here_constructs_an_observed_or_verified_rung(self, module_id):
        """The claim these six modules make, asserted as a property of the source.

        Every module in this group sends one request and reads the reply to that
        same request. None reads anything back, so OBSERVED -- "we saw the world
        change" -- is not available to any of them, and VERIFIED needs a
        postcondition none of them declares.

        A static check rather than a runtime one because it covers the paths a
        test has not been written for yet. Anyone adding an OBSERVED claim here
        has to delete this test, which is the conversation worth forcing: it
        would mean this group had grown a second look at something, and the
        argument for it belongs in the same commit.
        """
        source = (Path(__file__).parent.parent.parent / 'src' /
                  GROUP_SOURCES[module_id]).read_text(encoding='utf-8')
        constructed = re.findall(r'Outcome\.(OBSERVED|VERIFIED)\b', source)
        assert not constructed, (
            f'{module_id} now builds {constructed} -- if it grew a read-back, say '
            'what it measures and delete this test; if it did not, the rung is a '
            'claim the code cannot support'
        )

    @pytest.mark.parametrize('module_id', sorted(GROUP_MODULE_IDS))
    def test_none_of_them_declares_a_postcondition_it_does_not_evaluate(self, module_id):
        """VERIFIED is unreachable here, and the declaration is what would fake it.

        `ceiling_for` caps an undeclared module at OBSERVED, so a
        `postcondition=` on any of these would raise the ceiling on EVERY path
        through them at once -- including the ones that measured nothing --
        while adding no predicate. `verify.figma` is the tempting one:
        `find_by_name` really does evaluate something. It evaluates a selector
        over data we were handed, not a check that anything we did took effect.

        Read off the registry rather than the source, so it is the declaration
        the engine actually consults that is being asserted about.
        """
        from core.modules.registry import ModuleRegistry

        metadata = ModuleRegistry.get_metadata(module_id) or {}
        assert metadata, f'{module_id} is not registered'
        assert not metadata.get('postcondition')
        assert not metadata.get('derives')
