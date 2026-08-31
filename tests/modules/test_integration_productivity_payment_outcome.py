# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""What the thirteen integration / productivity / payment modules may claim.

THE GROUP-WIDE ANSWER ON EVERY SUCCESSFUL PATH IS ACCEPTED, and the test that
matters most in this file is the one that says so for all thirteen at once
(:class:`TestNothingInThisGroupSawAnything`). Each of them sends one request
and reads the reply to that same request. None reads anything back. A 201
naming a Jira issue, a `ts` from `chat.postMessage`, a PaymentIntent id from
Stripe -- every one is the peer reporting on its own work, which is
`http.request`'s settled position for every 2xx in this product.

That is not a small claim to have earned. The alternative was never OBSERVED,
it was DISPATCHED -- what the engine stamps on a module that reports nothing,
and what all thirteen said before this change.

THREE PLACES WHERE THIS GROUP HAD TO SAY MORE THAN "ACCEPTED":

  the payment module. `payment.stripe.create_payment` creates a PaymentIntent,
  which is not a charge. Its rung is the same ACCEPTED as everything else here,
  so the rung alone would be read as "the payment went through". It carries a
  `no_funds_movement_confirmed` effect whose whole job is to say otherwise, and
  :class:`TestThePaymentModuleSaysWhatItDidNotConfirm` is what keeps it there.

  the error paths of the seven `integration.*` modules, which return instead of
  raising and so can carry a rung at all. They split on the only question a
  workflow author can act on: may the write have happened? A 4xx is a named
  refusal (FAILED); a 5xx or no reply at all leaves an issue, record or message
  that may exist (INDETERMINATE), and both this module and the shared client
  retry, so it may exist more than once.

  `integration.salesforce.query` with `fetch_all=True`, where the module cannot
  tell success from failure at all. `query_all` swallows a failed page and
  returns a bare `[]`, so an expired token and a query that matched nothing
  arrive identically. That path claims INDETERMINATE, and
  :class:`TestSalesforceFetchAllCannotTellNothingFromFailure` pins both the rung
  and the defect underneath it.

THE COUNTS ARE THE OTHER RECURRING TRAP, and `TestTheCountsSayWhatTheyCount`
covers it: every list in this group is ONE PAGE, and three of the payload
fields (`total`, `has_more`, `balance`) fall back to a literal written in the
module when the peer omits them. A 0 that means "nobody said" reading the same
as a 0 that means "none" is the `database.query` row-count bug, and each effect
carries a `*_reported` flag so the two stay apart.
"""

import sys
from contextlib import suppress
from pathlib import Path

import aiohttp
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from core.engine.outcome import Outcome, read_envelope
from core.engine.step_executor.executor import (
    _SENSITIVE_KEY_PATTERN,
    _apply_outcome_contract,
    step_outcome,
)
from core.modules.items import wrap_legacy_result
from core.modules.integrations.base import APIResponse
from core.modules.integrations.base.client import BaseIntegration
from core.modules.integrations.jira.integration import JiraIntegration
from core.modules.integrations.salesforce.integration import SalesforceIntegration
from core.modules.integrations.slack.integration import SlackIntegration
from core.modules.registry import ModuleRegistry


def ensure_modules_loaded():
    from core.modules import atomic  # noqa: F401
    with suppress(Exception):
        from core.modules import third_party  # noqa: F401
    with suppress(Exception):
        from core.modules import integrations  # noqa: F401


ensure_modules_loaded()


# Not a credential. Every module in this group reads a token from a parameter
# or the environment before it builds a request; these tests hand it values
# that are obviously not credentials so the code path runs without depending on
# a developer's environment. Nothing is ever sent anywhere -- every transport
# below is replaced.
NOT_A_TOKEN = "not-a-real-token"
NOT_AN_EMAIL = "nobody@example.invalid"


ALL_MODULES = [
    "integration.jira.create_issue",
    "integration.jira.search_issues",
    "integration.salesforce.create_record",
    "integration.salesforce.query",
    "integration.salesforce.update_record",
    "integration.slack.list_channels",
    "integration.slack.send_message",
    "payment.stripe.create_payment",
    "payment.stripe.get_customer",
    "payment.stripe.list_charges",
    "productivity.airtable.create",
    "productivity.airtable.read",
    "productivity.airtable.update",
]


# ===========================================================================
# The two transports. Six modules reach `aiohttp` directly; seven go through
# `BaseIntegration`, and for those the seam is the integration method itself.
# ===========================================================================

class _Reply:
    """One aiohttp response, and the async-context shape these modules use."""

    def __init__(self, status, payload=None, text=""):
        self.status = status
        self._payload = payload
        self._text = text

    async def json(self):
        return self._payload

    async def text(self):
        return self._text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _Session:
    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return self.reply

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return self.reply

    def patch(self, url, **kwargs):
        self.calls.append(("PATCH", url, kwargs))
        return self.reply


def install_http(monkeypatch, reply):
    """Stripe and Airtable reach the network through `aiohttp.ClientSession`."""
    session = _Session(reply)
    monkeypatch.setattr(aiohttp, "ClientSession", lambda *a, **k: session)
    return session


def install_integration(monkeypatch, cls, method, response):
    """Replace one integration method, and the session it would have opened.

    The seam is deliberately the high-level method rather than `aiohttp`:
    `BaseIntegration._request` is where the SSRF guard, the credential-egress
    check, the rate limiter and the retry loop live, and a test that stubbed
    `aiohttp` underneath them would be asserting about a request path these
    tests have no business exercising. What each module can see of that path is
    exactly one `APIResponse`, so that is what is handed to it.
    """
    async def _fake(self, *args, **kwargs):
        return response

    async def _no_session(self):
        return None

    async def _no_close(self):
        return None

    monkeypatch.setattr(cls, method, _fake)
    monkeypatch.setattr(BaseIntegration, "_ensure_session", _no_session)
    monkeypatch.setattr(BaseIntegration, "close", _no_close)
    return response


async def run(module_id, params):
    """Execute a module the way the engine does, and return its payload."""
    return await ModuleRegistry.get(module_id)(params, {}).execute()


def envelope_of(result):
    """The envelope, read from where `step_executor` reads it.

    Top level, not under `data`: every module in this group returns a flat
    dict, and `_apply_outcome_contract` treats that dict as the body.
    """
    return read_envelope(result)


def effect_named(found, kind):
    return next(effect for effect in found["effects"] if effect["kind"] == kind)


def effect_kinds(found):
    return [effect["kind"] for effect in found["effects"]]


class _Attr:
    """A tiny object whose attributes are the keyword arguments given."""

    def __init__(self, **fields):
        self.__dict__.update(fields)


# ===========================================================================
# Canned replies. Trimmed to the fields each module actually reads.
# ===========================================================================

JIRA_ISSUE = {"key": "PROJ-123", "id": "10042"}

JIRA_SEARCH = {
    "total": 87,
    "issues": [
        {
            "key": "PROJ-1",
            "fields": {
                "summary": "first",
                "status": {"name": "Open"},
                "priority": {"name": "High"},
                "assignee": {"displayName": "Ada"},
            },
        },
    ],
}

SF_CREATED = {"id": "00Q5f000004abcdEAA", "success": True}

SF_QUERY = {
    "totalSize": 2,
    "done": True,
    "records": [{"Id": "001a"}, {"Id": "001b"}],
}

SLACK_POSTED = {
    "ok": True,
    "channel": "C1234567890",
    "ts": "1755000000.123456",
    "message": {"text": "Hello team!"},
}

SLACK_CHANNELS = {
    "ok": True,
    "channels": [
        {"id": "C1", "name": "general", "is_private": False, "num_members": 12},
        {"id": "C2", "name": "random", "is_private": False, "num_members": 5},
    ],
    "response_metadata": {"next_cursor": "dGVhbTpDMDYx"},
}

STRIPE_INTENT = {
    "id": "pi_3ABCdef",
    "amount": 5000,
    "currency": "usd",
    # The status a freshly created PaymentIntent actually carries. The whole
    # point of the payment tests below is that this is not a completed payment.
    "status": "requires_payment_method",
    # Shortened past the secret scanner deliberately. A realistic-length value
    # here is indistinguishable from a real one to gitleaks, and this repository
    # has no allowlist to explain the difference in -- so the fixture says what it
    # is instead of asking a config file to vouch for it. Nothing in these tests
    # reads it; the field exists because Stripe returns it.
    "client_secret": "<fake, not a secret>",
}

STRIPE_CUSTOMER = {
    "id": "cus_ABC123",
    "email": "customer@example.invalid",
    "name": "Ada Lovelace",
    "created": 1700000000,
    "balance": -250,
}

STRIPE_CHARGES = {
    "has_more": True,
    "data": [
        {
            "id": "ch_1",
            "amount": 1000,
            "currency": "usd",
            "status": "succeeded",
            "paid": True,
            "created": 1700000001,
            "description": "one",
        },
    ],
}

AIRTABLE_PAGE = {
    "records": [
        {"id": "rec1", "createdTime": "2026-01-01T00:00:00.000Z", "fields": {"Name": "Ada"}},
    ],
    "offset": "itrXXXX/recYYYY",
}

AIRTABLE_RECORD = {
    "id": "recNEW",
    "createdTime": "2026-08-31T10:00:00.000Z",
    "fields": {"Name": "Ada", "Status": "Active"},
}


# ===========================================================================
# One successful call per module, all thirteen.
# ===========================================================================

async def success_jira_create(monkeypatch):
    install_integration(monkeypatch, JiraIntegration, "create_issue",
                        APIResponse(ok=True, status=201, data=JIRA_ISSUE))
    return await run("integration.jira.create_issue", {
        "domain": "example.atlassian.net",
        "project_key": "PROJ",
        "summary": "Login button not working",
        "email": NOT_AN_EMAIL,
        "api_token": NOT_A_TOKEN,
    })


async def success_jira_search(monkeypatch):
    install_integration(monkeypatch, JiraIntegration, "search_issues",
                        APIResponse(ok=True, status=200, data=JIRA_SEARCH))
    return await run("integration.jira.search_issues", {
        "domain": "example.atlassian.net",
        "jql": "project = PROJ",
        "max_results": 50,
        "email": NOT_AN_EMAIL,
        "api_token": NOT_A_TOKEN,
    })


async def success_sf_create(monkeypatch):
    install_integration(monkeypatch, SalesforceIntegration, "create",
                        APIResponse(ok=True, status=201, data=SF_CREATED))
    return await run("integration.salesforce.create_record", {
        "instance_url": "https://example.my.salesforce.com",
        "sobject": "Lead",
        "data": {"LastName": "Doe", "Company": "Acme"},
        "access_token": NOT_A_TOKEN,
    })


async def success_sf_query(monkeypatch):
    install_integration(monkeypatch, SalesforceIntegration, "query",
                        APIResponse(ok=True, status=200, data=SF_QUERY))
    return await run("integration.salesforce.query", {
        "instance_url": "https://example.my.salesforce.com",
        "soql": "SELECT Id FROM Account LIMIT 10",
        "access_token": NOT_A_TOKEN,
    })


async def success_sf_update(monkeypatch):
    install_integration(monkeypatch, SalesforceIntegration, "update",
                        APIResponse(ok=True, status=204, data=""))
    return await run("integration.salesforce.update_record", {
        "instance_url": "https://example.my.salesforce.com",
        "sobject": "Lead",
        "record_id": "00Q5f000004abcdEAA",
        "data": {"Status": "Working"},
        "access_token": NOT_A_TOKEN,
    })


async def success_slack_send(monkeypatch):
    install_integration(monkeypatch, SlackIntegration, "send_message",
                        APIResponse(ok=True, status=200, data=SLACK_POSTED))
    return await run("integration.slack.send_message", {
        "channel": "#general",
        "text": "Hello team!",
        "token": NOT_A_TOKEN,
    })


async def success_slack_list(monkeypatch):
    install_integration(monkeypatch, SlackIntegration, "list_channels",
                        APIResponse(ok=True, status=200, data=SLACK_CHANNELS))
    return await run("integration.slack.list_channels", {"token": NOT_A_TOKEN})


async def success_stripe_create(monkeypatch):
    install_http(monkeypatch, _Reply(200, STRIPE_INTENT))
    return await run("payment.stripe.create_payment", {
        "api_key": NOT_A_TOKEN,
        "amount": 5000,
        "currency": "usd",
        "description": "Product purchase",
    })


async def success_stripe_customer(monkeypatch):
    install_http(monkeypatch, _Reply(200, STRIPE_CUSTOMER))
    return await run("payment.stripe.get_customer", {
        "api_key": NOT_A_TOKEN,
        "customer_id": "cus_ABC123",
    })


async def success_stripe_charges(monkeypatch):
    install_http(monkeypatch, _Reply(200, STRIPE_CHARGES))
    return await run("payment.stripe.list_charges", {
        "api_key": NOT_A_TOKEN,
        "limit": 10,
    })


async def success_airtable_read(monkeypatch):
    install_http(monkeypatch, _Reply(200, AIRTABLE_PAGE))
    return await run("productivity.airtable.read", {
        "api_key": NOT_A_TOKEN,
        "base_id": "appXXXXXXXXXXXXXX",
        "table_name": "Customers",
    })


async def success_airtable_create(monkeypatch):
    install_http(monkeypatch, _Reply(200, AIRTABLE_RECORD))
    return await run("productivity.airtable.create", {
        "api_key": NOT_A_TOKEN,
        "base_id": "appXXXXXXXXXXXXXX",
        "table_name": "Customers",
        "fields": {"Name": "Ada", "Status": "Active"},
    })


async def success_airtable_update(monkeypatch):
    install_http(monkeypatch, _Reply(200, AIRTABLE_RECORD))
    return await run("productivity.airtable.update", {
        "api_key": NOT_A_TOKEN,
        "base_id": "appXXXXXXXXXXXXXX",
        "table_name": "Customers",
        "record_id": "recNEW",
        "fields": {"Status": "Active"},
    })


SUCCESS = {
    "integration.jira.create_issue": success_jira_create,
    "integration.jira.search_issues": success_jira_search,
    "integration.salesforce.create_record": success_sf_create,
    "integration.salesforce.query": success_sf_query,
    "integration.salesforce.update_record": success_sf_update,
    "integration.slack.list_channels": success_slack_list,
    "integration.slack.send_message": success_slack_send,
    "payment.stripe.create_payment": success_stripe_create,
    "payment.stripe.get_customer": success_stripe_customer,
    "payment.stripe.list_charges": success_stripe_charges,
    "productivity.airtable.create": success_airtable_create,
    "productivity.airtable.read": success_airtable_read,
    "productivity.airtable.update": success_airtable_update,
}


# ===========================================================================
# The group-wide line
# ===========================================================================

class TestNothingInThisGroupSawAnything:
    """One rung for thirteen modules, and the reason it is not a higher one.

    Every module here sends one request and reads the reply to that same
    request. Reaching OBSERVED would take a second request -- a GET of the
    issue, the record, the intent -- and none of them makes one. Making that a
    parametrized test over the whole group, rather than thirteen separate
    assertions, is deliberate: the claim is about the group, and a fourteenth
    module added tomorrow has to face it.
    """

    def test_the_group_is_the_thirteen_modules_named(self):
        """A fourteenth module in these families must not slip past this file."""
        registered = {
            module_id
            for module_id in ModuleRegistry.get_all_metadata(filter_by_stability=False)
            if module_id.split(".")[0] in {"integration", "productivity", "payment"}
        }

        assert registered == set(ALL_MODULES)

    @pytest.mark.parametrize("module_id", ALL_MODULES)
    async def test_a_successful_call_reports_accepted(self, module_id, monkeypatch):
        result = await SUCCESS[module_id](monkeypatch)

        found = envelope_of(result)
        assert found is not None, f"{module_id} attached no envelope"
        assert found["rung"] == Outcome.ACCEPTED.value

    @pytest.mark.parametrize("module_id", ALL_MODULES)
    async def test_no_module_claims_observed_or_verified(self, module_id, monkeypatch):
        """The line the group holds: a 2xx is acceptance, not observation."""
        result = await SUCCESS[module_id](monkeypatch)

        assert envelope_of(result)["rung"] not in (
            Outcome.OBSERVED.value,
            Outcome.VERIFIED.value,
        )

    @pytest.mark.parametrize("module_id", ALL_MODULES)
    async def test_every_effect_names_what_measured_it(self, module_id, monkeypatch):
        """`measured_by` on every effect, and None only where nothing measured it.

        A missing key is the failure this catches: an effect that says what
        happened without saying what read it is exactly the shape nobody can
        re-check later.
        """
        result = await SUCCESS[module_id](monkeypatch)

        effects = envelope_of(result)["effects"]
        # Non-empty first, or every per-effect assertion below passes vacuously
        # and this whole class becomes a test of an empty list.
        assert effects, f"{module_id} claims a rung and shows nothing for it"
        for effect in effects:
            assert "measured_by" in effect, f"{module_id}: {effect['kind']} names no source"
            assert "detail" in effect

    @pytest.mark.parametrize("module_id", ALL_MODULES)
    async def test_the_engine_reads_accepted_and_not_the_dispatched_default(
        self, module_id, monkeypatch
    ):
        """End to end through the executor's own reader, not just the dict.

        `_apply_outcome_contract` stamps DISPATCHED on any side-effecting module
        that reported nothing, and lowers a rung its declaration cannot support.
        Neither should happen here: the rung the module claimed is the rung the
        engine reports.
        """
        result = await SUCCESS[module_id](monkeypatch)

        stamped = _apply_outcome_contract(_Attr(module_id=module_id), result)
        rung, _claim_by, _expected = step_outcome(stamped)

        assert rung is Outcome.ACCEPTED

    @pytest.mark.parametrize("module_id", ALL_MODULES)
    async def test_no_effect_field_is_named_something_the_redactor_blanks(
        self, module_id, monkeypatch
    ):
        """`_redact_sensitive_output` blanks any key matching `token`, `auth`,
        `secret` and five other patterns, wherever it appears. An effect field
        called `auth_status` would reach every hook and every stored trace as
        '[REDACTED]' -- evidence that reads as a leaked secret, which is worse
        than no evidence at all.
        """
        result = await SUCCESS[module_id](monkeypatch)

        effects = envelope_of(result)["effects"]
        assert effects
        for effect in effects:
            for key in effect:
                assert not _SENSITIVE_KEY_PATTERN.search(key), (
                    f"{module_id}: effect field {key!r} will be redacted to "
                    "'[REDACTED]' before any consumer sees it"
                )


class TestTheEnvelopeSurvivesTheWayOutOfTheStep:
    """The constraint that decides where the envelope may be written.

    `NodeExecutionResult.to_legacy_dict` returns exactly `{ok, data}` and
    discards every sibling key, so an envelope written anywhere but inside
    `data` reaches no consumer at all. This group has two return shapes and
    they take different routes to that dict:

      the seven `integration.*` modules return a flat dict WITH an `ok` key, so
      `_execute_single_mode` hands it to `wrap_legacy_result`, which sweeps
      every non-meta field -- the envelope among them -- into `data`.

      the six Stripe and Airtable modules return a flat dict with NO `ok` key,
      which `_execute_single_mode` passes through untouched.

    Both work today. Neither is obvious from reading the module, which is why
    it is asserted rather than assumed.
    """

    @pytest.mark.parametrize("module_id", ALL_MODULES)
    async def test_the_envelope_reaches_data_and_is_not_discarded(
        self, module_id, monkeypatch
    ):
        result = await SUCCESS[module_id](monkeypatch)
        stamped = _apply_outcome_contract(_Attr(module_id=module_id), result)

        if "ok" not in stamped:
            # Raw passthrough: the payload IS what downstream reads.
            assert read_envelope(stamped)["rung"] == Outcome.ACCEPTED.value
            return

        legacy = wrap_legacy_result(stamped).to_legacy_dict()

        assert legacy["ok"] is True
        assert read_envelope(legacy["data"])["rung"] == Outcome.ACCEPTED.value


# ===========================================================================
# Payment
# ===========================================================================

class TestThePaymentModuleSaysWhatItDidNotConfirm:
    """The one module in this group where ACCEPTED alone would mislead.

    `payment.stripe.create_payment` earns the same rung as everything else
    here, and on a module whose id contains the word "payment" that rung will
    be read as "the money moved". It did not: a PaymentIntent is an intent, and
    a freshly created one normally carries `requires_payment_method`. The
    disclaimer therefore rides as an EFFECT, in the same envelope, rather than
    as prose in a docstring nobody reads at 3am.
    """

    async def test_it_carries_an_effect_saying_no_funds_moved(self, monkeypatch):
        result = await success_stripe_create(monkeypatch)

        found = envelope_of(result)
        assert "no_funds_movement_confirmed" in effect_kinds(found)

    async def test_that_effect_measured_nothing_and_says_so(self, monkeypatch):
        """`measured_by: None` is the honest value. A disclaimer is not a
        measurement, and giving it a source would make it look like one.
        """
        result = await success_stripe_create(monkeypatch)

        effect = effect_named(envelope_of(result), "no_funds_movement_confirmed")
        assert effect["measured_by"] is None
        assert "NOT CONFIRMED" in effect["detail"]
        assert "charged" in effect["detail"]

    async def test_it_reports_the_intent_status_stripe_actually_sent(self, monkeypatch):
        """The field that shows the payment is unfinished, carried not hidden."""
        result = await success_stripe_create(monkeypatch)

        effect = effect_named(envelope_of(result), "no_funds_movement_confirmed")
        assert effect["intent_status"] == "requires_payment_method"

    async def test_the_created_effect_rests_on_the_server_assigned_id(self, monkeypatch):
        """What separates this from DISPATCHED: an id no input could produce."""
        result = await success_stripe_create(monkeypatch)

        effect = effect_named(envelope_of(result), "payment_intent_reported_created")
        assert effect["payment_intent_id"] == "pi_3ABCdef"
        assert "200 body" in effect["measured_by"]

    async def test_a_balance_stripe_did_not_send_is_marked_as_not_sent(self, monkeypatch):
        """`result.get('balance', 0)` writes a 0 of its own when the body has none.

        A customer balance is money. "Stripe says the balance is 0" and "this
        module filled in 0" are different facts, and only the flag keeps them
        apart -- the same trap as `database.query`'s row count.
        """
        install_http(monkeypatch, _Reply(200, {"id": "cus_ABC123", "email": None}))
        result = await run("payment.stripe.get_customer", {
            "api_key": NOT_A_TOKEN, "customer_id": "cus_ABC123",
        })

        effect = effect_named(envelope_of(result), "customer_described_by_peer")
        assert result["balance"] == 0
        assert effect["balance_reported"] is False

    async def test_a_balance_stripe_did_send_is_marked_as_sent(self, monkeypatch):
        result = await success_stripe_customer(monkeypatch)

        effect = effect_named(envelope_of(result), "customer_described_by_peer")
        assert effect["balance_reported"] is True

    async def test_the_customer_id_is_named_as_an_echo_not_as_evidence(self, monkeypatch):
        """`result['id']` for `GET /customers/cus_X` is `cus_X` -- our own input
        handed back. It would read identically if Stripe returned a stub, so
        the effect says out loud that it is not evidence.
        """
        result = await success_stripe_customer(monkeypatch)

        effect = effect_named(envelope_of(result), "customer_described_by_peer")
        assert "echo" in effect["detail"]


# ===========================================================================
# Error paths: the seven modules that return instead of raising
# ===========================================================================

RETURNING_MUTATIONS = [
    ("integration.jira.create_issue", JiraIntegration, "create_issue", success_jira_create),
    ("integration.salesforce.create_record", SalesforceIntegration, "create", success_sf_create),
    ("integration.salesforce.update_record", SalesforceIntegration, "update", success_sf_update),
    ("integration.slack.send_message", SlackIntegration, "send_message", success_slack_send),
]


async def failing_mutation(monkeypatch, module_id, cls, method, status, error="nope"):
    """The same call as the success fixture, with a failed `APIResponse`."""
    install_integration(monkeypatch, cls, method,
                        APIResponse(ok=False, status=status, error=error))
    params = {
        "integration.jira.create_issue": {
            "domain": "example.atlassian.net", "project_key": "PROJ",
            "summary": "s", "email": NOT_AN_EMAIL, "api_token": NOT_A_TOKEN,
        },
        "integration.salesforce.create_record": {
            "instance_url": "https://example.my.salesforce.com", "sobject": "Lead",
            "data": {"LastName": "Doe"}, "access_token": NOT_A_TOKEN,
        },
        "integration.salesforce.update_record": {
            "instance_url": "https://example.my.salesforce.com", "sobject": "Lead",
            "record_id": "00Q", "data": {"Status": "x"}, "access_token": NOT_A_TOKEN,
        },
        "integration.slack.send_message": {
            "channel": "#general", "text": "hi", "token": NOT_A_TOKEN,
        },
    }[module_id]
    return await run(module_id, params)


class TestAWriteThatDidNotComeBackSplitsOnWhetherItMayHaveHappened:
    """The only question a workflow author can act on after a failed write.

    FAILED and INDETERMINATE are not a strong and a weak version of the same
    answer. One says "this did not happen, fix the request"; the other says
    "something may exist, go and look before you retry". Collapsing them into
    one error state is what makes an automation retry a duplicate charge.
    """

    @pytest.mark.parametrize("module_id,cls,method,_success", RETURNING_MUTATIONS)
    async def test_a_4xx_is_failed_because_the_peer_refused_by_name(
        self, module_id, cls, method, _success, monkeypatch
    ):
        result = await failing_mutation(monkeypatch, module_id, cls, method, 400)

        assert result["ok"] is False
        assert envelope_of(result)["rung"] == Outcome.FAILED.value

    @pytest.mark.parametrize("module_id,cls,method,_success", RETURNING_MUTATIONS)
    async def test_a_5xx_is_indeterminate_because_the_write_may_have_landed(
        self, module_id, cls, method, _success, monkeypatch
    ):
        result = await failing_mutation(monkeypatch, module_id, cls, method, 503)

        assert envelope_of(result)["rung"] == Outcome.INDETERMINATE.value

    @pytest.mark.parametrize("module_id,cls,method,_success", RETURNING_MUTATIONS)
    async def test_no_reply_at_all_is_indeterminate_and_may_be_more_than_one(
        self, module_id, cls, method, _success, monkeypatch
    ):
        """`status == 0` is the literal `BaseIntegration._request` writes when it
        gives up. It is not a status: it is the absence of one, after up to
        `max_retries` POSTs any of which may have reached the server.
        """
        result = await failing_mutation(monkeypatch, module_id, cls, method, 0)

        found = envelope_of(result)
        assert found["rung"] == Outcome.INDETERMINATE.value
        detail = " ".join(effect["detail"] for effect in found["effects"])
        assert "may have reached the server" in detail
        # Nothing claims a server answered. Saying "a server chose a reply"
        # beside a status of 0 would be a false sentence about the world in the
        # one field a reader consults when the rung is not enough.
        assert "reply_read" not in " ".join(effect_kinds(found))

    async def test_slack_rejecting_inside_a_200_body_is_still_a_named_refusal(
        self, monkeypatch
    ):
        """The bug `SlackIntegration._response_is_ok` exists for, carried into
        the rung. `{"ok": false, "error": "invalid_auth"}` arrives as HTTP 200,
        so a rung read off the status line alone would call a rejected token a
        successful send. It is FAILED: Slack read the request and posted nothing.
        """
        install_integration(monkeypatch, SlackIntegration, "send_message",
                            APIResponse(ok=False, status=200, error="invalid_auth"))

        result = await run("integration.slack.send_message", {
            "channel": "#general", "text": "hi", "token": NOT_A_TOKEN,
        })

        assert envelope_of(result)["rung"] == Outcome.FAILED.value

    @pytest.mark.parametrize("module_id,cls,method,_success", RETURNING_MUTATIONS)
    async def test_the_failure_effects_survive_the_redactor_too(
        self, module_id, cls, method, _success, monkeypatch
    ):
        """The success paths are checked for this above; the failure paths carry
        different field names (`resource`, `operation`, `error`) and would be
        blanked by the same regex if any of them drifted into `auth`, `token` or
        `credential`. An error effect delivered as '[REDACTED]' is worse than
        none: it reads like a leaked secret and explains nothing.
        """
        result = await failing_mutation(monkeypatch, module_id, cls, method, 500)

        effects = envelope_of(result)["effects"]
        assert effects
        for effect in effects:
            for key in effect:
                assert not _SENSITIVE_KEY_PATTERN.search(key), (
                    f"{module_id}: failure effect field {key!r} will be redacted"
                )

    async def test_the_create_paths_warn_that_the_client_already_retried(
        self, monkeypatch
    ):
        """`retryable=False` on the Jira and Salesforce creates is only half the
        story: `_request` retries the POST itself before giving up.
        """
        result = await failing_mutation(
            monkeypatch, "integration.jira.create_issue",
            JiraIntegration, "create_issue", 0,
        )

        detail = " ".join(effect["detail"] for effect in envelope_of(result)["effects"])
        assert "more than one issue may exist" in detail


READS = [
    ("integration.jira.search_issues", JiraIntegration, "search_issues", {
        "domain": "example.atlassian.net", "jql": "project = PROJ",
        "email": NOT_AN_EMAIL, "api_token": NOT_A_TOKEN,
    }),
    ("integration.salesforce.query", SalesforceIntegration, "query", {
        "instance_url": "https://example.my.salesforce.com",
        "soql": "SELECT Id FROM Account", "access_token": NOT_A_TOKEN,
    }),
    ("integration.slack.list_channels", SlackIntegration, "list_channels", {
        "token": NOT_A_TOKEN,
    }),
]


class TestAReadThatDidNotComeBackIsFailedAndNeverIndeterminate:
    """A read alters nothing on either side, so nothing is left in doubt.

    What is missing after a refused GET is data, not certainty -- there is no
    effect out there that may or may not have happened. `github._read_refused`
    settles this the same way, and the distinction is the reason
    `engine/outcome.py` keeps two off-ladder answers instead of one.
    """

    @pytest.mark.parametrize("module_id,cls,method,params", READS)
    @pytest.mark.parametrize("status", [401, 500, 0])
    async def test_every_kind_of_refusal_is_failed(
        self, module_id, cls, method, params, status, monkeypatch
    ):
        install_integration(monkeypatch, cls, method,
                            APIResponse(ok=False, status=status, error="denied"))

        result = await run(module_id, params)

        assert result["ok"] is False
        assert envelope_of(result)["rung"] == Outcome.FAILED.value

    @pytest.mark.parametrize("module_id,cls,method,params", READS)
    async def test_the_status_travels_so_a_zero_is_visible_as_no_reply(
        self, module_id, cls, method, params, monkeypatch
    ):
        install_integration(monkeypatch, cls, method,
                            APIResponse(ok=False, status=0, error="timeout"))

        result = await run(module_id, params)

        found = envelope_of(result)
        assert all(effect["status"] == 0 for effect in found["effects"])
        detail = " ".join(effect["detail"] for effect in found["effects"])
        assert "No reply arrived at all" in detail
        # And nothing anywhere in the envelope claims a server answered, which
        # is what the reply-read effect would have said if it were unconditional.
        assert "reply_read" not in " ".join(effect_kinds(found))
        assert "chose a reply" not in detail


# ===========================================================================
# The path with no status line at all
# ===========================================================================

class TestSalesforceFetchAllCannotTellNothingFromFailure:
    """The one path in this group that cannot claim a rung on the ladder.

    `SalesforceIntegration.query_all` returns a bare `list` and its loop does
    `if not response.ok: break`, so the status line, the error and every trace
    of what happened are gone by the time the module sees the result. An
    expired token and a query that matched nothing both arrive as `[]`.

    `len([]) == 0` is a value that is identical whether or not the query ran,
    which is exactly what `outcome.py` says may not carry a rung -- so it does
    not. INDETERMINATE, and not FAILED: nobody declared the query would match
    anything, and an empty result set is an ordinary correct answer. What is
    wrong is that this module cannot tell it from a refusal.
    """

    async def _fetch_all(self, monkeypatch, records):
        async def _fake(self, soql, include_deleted=False):
            return records

        async def _no_session(self):
            return None

        async def _no_close(self):
            return None

        monkeypatch.setattr(SalesforceIntegration, "query_all", _fake)
        monkeypatch.setattr(BaseIntegration, "_ensure_session", _no_session)
        monkeypatch.setattr(BaseIntegration, "close", _no_close)

        return await run("integration.salesforce.query", {
            "instance_url": "https://example.my.salesforce.com",
            "soql": "SELECT Id FROM Account",
            "fetch_all": True,
            "access_token": NOT_A_TOKEN,
        })

    async def test_records_that_came_back_earn_accepted(self, monkeypatch):
        result = await self._fetch_all(monkeypatch, [{"Id": "001a"}, {"Id": "001b"}])

        assert envelope_of(result)["rung"] == Outcome.ACCEPTED.value

    async def test_an_empty_result_is_indeterminate_not_accepted(self, monkeypatch):
        result = await self._fetch_all(monkeypatch, [])

        assert envelope_of(result)["rung"] == Outcome.INDETERMINATE.value

    async def test_the_empty_effect_measured_nothing(self, monkeypatch):
        result = await self._fetch_all(monkeypatch, [])

        effect = effect_named(
            envelope_of(result), "records_indistinguishable_from_failure"
        )
        assert effect["measured_by"] is None

    async def test_the_step_still_reports_success_which_is_why_the_rung_matters(
        self, monkeypatch
    ):
        """Pins the defect the rung exposes, so a later fix has to face it.

        The payload says `ok: True` with `total_size: 0` for a query that may
        have been refused outright, and the step is recorded as a success. The
        envelope is the only field on that result which disagrees. The fix
        belongs in `query_all` -- it should propagate the failed `APIResponse`
        instead of swallowing it -- and when it lands, this test should change.
        """
        result = await self._fetch_all(monkeypatch, [])

        assert result["ok"] is True
        assert result["total_size"] == 0
        assert envelope_of(result)["rung"] == Outcome.INDETERMINATE.value

    async def test_the_engine_sees_the_off_ladder_answer(self, monkeypatch):
        """`step_outcome` is where a consumer meets this, and off-ladder answers
        win outright over any rung. A step that cannot say what happened must
        not be summarised as one that can.
        """
        result = await self._fetch_all(monkeypatch, [])

        stamped = _apply_outcome_contract(
            _Attr(module_id="integration.salesforce.query"), result
        )
        rung, _claim_by, _expected = step_outcome(stamped)

        assert rung is Outcome.INDETERMINATE


# ===========================================================================
# The counts
# ===========================================================================

class TestTheCountsSayWhatTheyCount:
    """Every list in this group is one page, and three numbers are defaults.

    `database.query` is the precedent: a `row_count` of 0 meaning "nothing
    matched" and one meaning "this backend reports no count" are different
    facts, and a single integer cannot carry both. The same shape appears three
    times here -- Jira's `total`, Stripe's `has_more`, Stripe's `balance` -- as
    a `dict.get(key, default)` whose default lands in the payload looking
    exactly like the peer's own value.
    """

    async def test_jira_total_is_flagged_when_jira_actually_sent_it(self, monkeypatch):
        result = await success_jira_search(monkeypatch)

        effect = effect_named(envelope_of(result), "issues_returned")
        assert effect["total_reported"] is True
        assert effect["total"] == 87

    async def test_jira_total_is_flagged_when_the_zero_was_written_here(
        self, monkeypatch
    ):
        """Newer Jira Cloud search endpoints omit `total` entirely, and
        `data.get("total", 0)` turns that into a 0 that reads like a count.
        """
        install_integration(monkeypatch, JiraIntegration, "search_issues",
                            APIResponse(ok=True, status=200, data={"issues": []}))

        result = await run("integration.jira.search_issues", {
            "domain": "example.atlassian.net", "jql": "project = PROJ",
            "email": NOT_AN_EMAIL, "api_token": NOT_A_TOKEN,
        })

        effect = effect_named(envelope_of(result), "issues_returned")
        assert result["total"] == 0
        assert effect["total_reported"] is False

    async def test_jira_page_and_total_are_different_numbers_and_both_travel(
        self, monkeypatch
    ):
        result = await success_jira_search(monkeypatch)

        effect = effect_named(envelope_of(result), "issues_returned")
        assert effect["count"] == 1
        assert effect["total"] == 87

    async def test_salesforce_marks_a_totalsize_it_did_not_receive(self, monkeypatch):
        install_integration(monkeypatch, SalesforceIntegration, "query",
                            APIResponse(ok=True, status=200, data={"records": []}))

        result = await run("integration.salesforce.query", {
            "instance_url": "https://example.my.salesforce.com",
            "soql": "SELECT Id FROM Account", "access_token": NOT_A_TOKEN,
        })

        effect = effect_named(envelope_of(result), "records_returned")
        assert effect["total_size_reported"] is False

    async def test_stripe_marks_a_has_more_it_did_not_receive(self, monkeypatch):
        install_http(monkeypatch, _Reply(200, {"data": []}))

        result = await run("payment.stripe.list_charges", {
            "api_key": NOT_A_TOKEN, "limit": 10,
        })

        effect = effect_named(envelope_of(result), "charges_returned")
        assert result["has_more"] is False
        assert effect["has_more_reported"] is False

    async def test_slack_records_the_cursor_it_does_not_follow(self, monkeypatch):
        """`count` is bounded by `limit` and there is no other field in the
        payload that says the workspace holds more. The effect is where a
        reader finds out the list is partial.
        """
        result = await success_slack_list(monkeypatch)

        effect = effect_named(envelope_of(result), "channels_returned")
        assert effect["count"] == 2
        assert effect["more_pages_available"] is True

    async def test_airtable_records_the_offset_it_does_not_follow(self, monkeypatch):
        result = await success_airtable_read(monkeypatch)

        effect = effect_named(envelope_of(result), "records_returned")
        assert effect["count"] == 1
        assert effect["more_pages_available"] is True

    async def test_airtable_says_so_when_there_is_no_further_page(self, monkeypatch):
        install_http(monkeypatch, _Reply(200, {"records": []}))

        result = await run("productivity.airtable.read", {
            "api_key": NOT_A_TOKEN, "base_id": "app", "table_name": "T",
        })

        effect = effect_named(envelope_of(result), "records_returned")
        assert effect["more_pages_available"] is False
        # An empty page is still ACCEPTED: the rung claims the peer answered,
        # and there is nothing about zero records that makes that untrue.
        assert envelope_of(result)["rung"] == Outcome.ACCEPTED.value


# ===========================================================================
# The values that are not evidence
# ===========================================================================

class TestThePayloadFieldsThatAreNotEvidence:
    """Values a module computed from its own inputs, named as such.

    `file.write` is the worked example: `bytes_written` was the length of the
    input string, identical whether the disk was full or not. The same shape
    turns up here in fields that look like they came from the peer.
    """

    async def test_the_jira_url_is_an_fstring_and_the_effect_says_so(self, monkeypatch):
        """`url` is built from the caller's own `domain` and whatever key came
        back. It is a well-formed URL even when no key did, nothing requests it,
        and nothing confirms it resolves.
        """
        result = await success_jira_create(monkeypatch)

        effect = effect_named(envelope_of(result), "issue_url_constructed")
        assert effect["measured_by"] is None
        assert result["url"].endswith("/browse/PROJ-123")

    async def test_salesforces_default_success_flag_is_marked_as_a_default(
        self, monkeypatch
    ):
        """`data.get("success", True)` puts a `true` in the payload that
        Salesforce never sent, and it reads identically to one it did.
        """
        install_integration(monkeypatch, SalesforceIntegration, "create",
                            APIResponse(ok=True, status=201, data={"id": "00Q"}))

        result = await run("integration.salesforce.create_record", {
            "instance_url": "https://example.my.salesforce.com", "sobject": "Lead",
            "data": {"LastName": "Doe"}, "access_token": NOT_A_TOKEN,
        })

        effect = effect_named(envelope_of(result), "record_reported_created")
        assert result["success"] is True
        assert effect["success_reported"] is False
        assert effect["id_reported"] is True

    async def test_the_salesforce_update_rests_on_a_status_line_and_nothing_else(
        self, monkeypatch
    ):
        """A successful Salesforce PATCH is 204 No Content. There is no body, so
        `record_id` and `fields_sent` in the effect are this module's own inputs
        -- listed for a reader, explicitly not a measurement.
        """
        result = await success_sf_update(monkeypatch)

        effect = effect_named(envelope_of(result), "record_update_accepted")
        assert effect["record_id"] == "00Q5f000004abcdEAA"
        assert effect["fields_sent"] == ["Status"]
        assert "not a measurement" in effect["detail"]

    async def test_the_airtable_update_does_not_treat_the_reply_as_a_read_back(
        self, monkeypatch
    ):
        """Airtable omits a field it holds no value for, so a field missing from
        the reply is not evidence the write failed. The two lists travel side by
        side and deliberately do not move the rung.
        """
        install_http(monkeypatch, _Reply(200, {"id": "recNEW", "fields": {}}))

        result = await run("productivity.airtable.update", {
            "api_key": NOT_A_TOKEN, "base_id": "app", "table_name": "T",
            "record_id": "recNEW", "fields": {"Notes": ""},
        })

        found = envelope_of(result)
        effect = effect_named(found, "record_update_reported")
        assert effect["fields_sent"] == ["Notes"]
        assert effect["fields_in_reply"] == []
        assert found["rung"] == Outcome.ACCEPTED.value

    async def test_slack_reports_the_channel_it_resolved_not_the_one_asked_for(
        self, monkeypatch
    ):
        """What lifts the send above DISPATCHED: `#general` went out and `C…`
        came back, so the reply is not an echo of the request.
        """
        result = await success_slack_send(monkeypatch)

        effect = effect_named(envelope_of(result), "message_reported_posted")
        assert effect["channel_requested"] == "#general"
        assert effect["channel_resolved"] == "C1234567890"
        assert effect["ts_reported"] is True

    async def test_slack_does_not_claim_a_person_saw_the_message(self, monkeypatch):
        """Delivery to a human is not on this ladder and is not implied by it."""
        result = await success_slack_send(monkeypatch)

        effect = effect_named(envelope_of(result), "message_reported_posted")
        assert "delivery to a human is not something this module can observe" in (
            effect["detail"].lower()
        )
