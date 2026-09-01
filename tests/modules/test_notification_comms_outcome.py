# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""What the eleven modules that reach a PERSON are entitled to claim.

THE GROUP-WIDE ANSWER IS ACCEPTED, and the test that matters most in this file
is the one that says so for every send at once
(:class:`TestNothingThatReachesAPersonClaimsToHaveBeenRead`). Ten of these
eleven modules hand a message to somebody else's service and read the reply to
that same handover. A 200 from a webhook, a Telegram ``message_id``, a
``wamid``, a Twilio sid whose status is the literal word ``queued`` -- every one
of them is the peer reporting on its own work, and not one of them is a person
receiving anything. OBSERVED would need a second call that reads the channel or
the mailbox back, and none of these modules makes one.

That is not a small claim to have earned. The alternative was never OBSERVED, it
was DISPATCHED -- what the engine stamps on a module that reports nothing, and
what all eleven said before this change. "The instruction left us and nobody
confirmed anything" is untrue of a send that came back with a server-assigned
id.

THE ONE OBSERVED IN THE GROUP IS A READ, NOT A SEND. `email.read` pulls message
bytes off an IMAP server and parses them, which is a measurement of the world
in exactly the way `database.query`'s returned rows are -- and it splits three
ways for the same reason, tested in :class:`TestEmailReadHasNoSingleRung`. An
empty result is ACCEPTED, because ``len(emails) == 0`` reads the same whether
the folder is empty or the filters were wrong; and a SEARCH that did not answer
OK is INDETERMINATE, because the zero this module returns for it is a literal
written in the file rather than anything a server said.

THE ERROR PATHS ARE WHERE THE REAL DEFECTS LIVE. Five of these modules do not
raise on failure: they return ``{'status': 'error', 'sent': False}`` (or
``ok: False``) and the step is recorded as one that SUCCEEDED. Those paths now
carry FAILED or INDETERMINATE, and the split is always the same question --
could this message already be in front of somebody? A 4xx is a named refusal
and nothing happened; a 5xx, a mid-DATA disconnect and a blocked redirect hop
all leave a message that may have gone out, and every module in this group is
`retryable=True`, so calling those FAILED is how one notification becomes two.
:class:`TestTheRetryQuestionIsTheSplit` pins that for the whole group.
"""

import imaplib
import importlib
import smtplib
import sys
import types
from contextlib import suppress
from pathlib import Path

import aiohttp
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from core.engine.outcome import Outcome, read_envelope
from core.engine.step_executor.executor import _apply_outcome_contract
from core.modules.registry import ModuleRegistry
from core.utils import SSRFError


def ensure_modules_loaded():
    from core.modules import atomic  # noqa: F401
    with suppress(Exception):
        from core.modules import third_party  # noqa: F401


ensure_modules_loaded()


# Not a credential. Every module here reads a token, a password or a webhook URL
# before it builds a request; these are values that are obviously not real, so
# the code path runs without depending on a developer's environment. Nothing is
# ever sent anywhere -- every transport below is replaced.
NOT_A_TOKEN = "not-a-real-token"
NOT_A_PASSWORD = "not-a-real-password"
WEBHOOK_URL = "https://hooks.example.invalid/services/not-a-real-webhook"

# Loopback, because `enforce_outbound_host` allows it unconditionally and so no
# test in this file depends on DNS resolving anything.
LOCAL_HOST = "127.0.0.1"


# ===========================================================================
# The transports, replaced.
# ===========================================================================

class _Reply:
    """One HTTP reply, in both shapes the modules in this group consume.

    `guarded_aiohttp_request` hands back a bare response with `.release()`;
    `session.post(...)` is used as an async context manager. The same object
    answers to both.
    """

    def __init__(self, status, *, json_body=None, text_body=""):
        self.status = status
        self.headers = {}
        self._json = json_body
        self._text = text_body
        self.released = False

    async def json(self):
        return self._json

    async def text(self):
        return self._text

    def release(self):
        self.released = True

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

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return self.reply


def install_guarded(monkeypatch, module, reply, *, blocked=None, blocked_hop=None):
    """Replace the SSRF-guarded transport in a third-party webhook module.

    Three shapes, one function:

    * ordinary        -- the guard passes and the request returns `reply`.
    * `blocked`       -- `enforce_outbound_url` raises before a socket exists.
    * `blocked_hop`   -- the guard inside `guarded_aiohttp_request` raises,
                         which is what a redirect into blocked space does after
                         the POST has already left.
    """
    def _enforce(url):
        if blocked:
            raise SSRFError(blocked)
        return url

    async def _request(session, method, url, **kwargs):
        if blocked_hop:
            raise SSRFError(blocked_hop)
        return reply

    monkeypatch.setattr(module, "enforce_outbound_url", _enforce)
    monkeypatch.setattr(module, "guarded_client_session", lambda *a, **k: _Session(reply))
    monkeypatch.setattr(module, "guarded_aiohttp_request", _request)


def install_aiohttp(monkeypatch, reply):
    """For the three modules that reach `aiohttp.ClientSession` directly."""
    session = _Session(reply)
    monkeypatch.setattr(aiohttp, "ClientSession", lambda *a, **k: session)
    return session


class _SMTP:
    """A stand-in for `smtplib.SMTP`, covering both call styles in this group.

    `email.send` uses it as a plain object and calls `sendmail`; the third-party
    `notification.email.send` uses it as a context manager and calls
    `send_message`. Both return the refusal map, which is the measurement the
    envelopes in this group rest on.
    """

    def __init__(self, host, port=0, *, refused=None, raise_on_send=None,
                 raise_on_login=None):
        self.host = host
        self.port = port
        self.refused = refused or {}
        self.raise_on_send = raise_on_send
        self.raise_on_login = raise_on_login
        self.sent = []
        self.quit_called = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, *a, **k):
        return (220, b"ready")

    def login(self, user, password):
        if self.raise_on_login:
            raise self.raise_on_login
        return (235, b"ok")

    def sendmail(self, from_addr, to_addrs, message):
        if self.raise_on_send:
            raise self.raise_on_send
        self.sent.append((from_addr, list(to_addrs)))
        return dict(self.refused)

    def send_message(self, msg):
        if self.raise_on_send:
            raise self.raise_on_send
        self.sent.append(msg)
        return dict(self.refused)

    def quit(self):
        self.quit_called = True


def install_smtp(monkeypatch, **kwargs):
    holder = {}

    def _factory(host, port=0, *a, **k):
        holder["server"] = _SMTP(host, port, **kwargs)
        return holder["server"]

    monkeypatch.setattr(smtplib, "SMTP", _factory)
    return holder


RAW_EMAIL = (
    b"Subject: Deploy finished\r\n"
    b"From: robot@example.invalid\r\n"
    b"To: team@example.invalid\r\n"
    b"Date: Mon, 31 Aug 2026 10:00:00 +0000\r\n"
    b"Content-Type: text/plain; charset=utf-8\r\n"
    b"\r\n"
    b"All green.\r\n"
)


class _IMAP:
    """A stand-in for `imaplib.IMAP4_SSL`.

    `search_status` and `fetch_failures` are the two knobs the rung turns on:
    a SEARCH that does not answer OK, and ids the server names and then will
    not hand over.
    """

    def __init__(self, host, port, *, ids=(), search_status="OK", fetch_failures=()):
        self.host = host
        self.port = port
        self.ids = list(ids)
        self.search_status = search_status
        self.fetch_failures = set(fetch_failures)
        self.fetched = []

    def login(self, user, password):
        return ("OK", [b"logged in"])

    def select(self, folder):
        return ("OK", [str(len(self.ids)).encode()])

    def search(self, charset, criteria):
        if self.search_status != "OK":
            return (self.search_status, [b""])
        return ("OK", [b" ".join(self.ids)])

    def fetch(self, msg_id, spec):
        if msg_id in self.fetch_failures:
            return ("NO", [None])
        self.fetched.append((msg_id, spec))
        return ("OK", [(b"1 (RFC822 {%d}" % len(RAW_EMAIL), RAW_EMAIL)])

    def close(self):
        return ("OK", [b"closed"])

    def logout(self):
        return ("BYE", [b"bye"])


def install_imap(monkeypatch, **kwargs):
    holder = {}

    def _factory(host, port):
        holder["mail"] = _IMAP(host, port, **kwargs)
        return holder["mail"]

    monkeypatch.setattr(imaplib, "IMAP4_SSL", _factory)
    return holder


# ===========================================================================
# Running a module the way the engine does.
# ===========================================================================

#: `core.modules.atomic.communication.__init__` re-exports the registered
#: wrapper class under the same name as its submodule, so a plain
#: `from ... import slack_send` hands back the class and not the namespace whose
#: `guarded_client_session` these tests replace.
SLACK_SEND = importlib.import_module("core.modules.atomic.communication.slack_send")


def instance(module_id, params):
    return ModuleRegistry.get(module_id)(params, {})


def id_only(module_id):
    """What `_apply_outcome_contract` actually reads off a module instance.

    It wants ``module_id`` and nothing else (`executor.py`: `getattr(
    module_instance, 'module_id', '')`). Building a real instance here would
    mean re-supplying every module's required parameters to test something that
    never looks at them.
    """
    return types.SimpleNamespace(module_id=module_id)


async def run(module_id, params):
    return await instance(module_id, params).execute()


def body_of(result):
    """Where `_apply_outcome_contract` looks for the envelope.

    Inside ``data`` when the module returns one; the top level otherwise. Both
    shapes are in this group -- `teams` and `whatsapp` nest, the other nine do
    not -- and getting this wrong is the whole reason the contract insists the
    envelope lives under ``data``: `to_legacy_dict` keeps nothing else.
    """
    nested = result.get("data")
    return nested if isinstance(nested, dict) else result


def envelope_of(result):
    return read_envelope(body_of(result))


def rung_of(result):
    return envelope_of(result)["rung"]


def effect_kinds(result):
    return [effect["kind"] for effect in envelope_of(result)["effects"]]


def effect_named(result, kind):
    return next(e for e in envelope_of(result)["effects"] if e["kind"] == kind)


# ===========================================================================
# One successful call per module, all eleven.
# ===========================================================================

EMAIL_SEND_PARAMS = {
    "to": "team@example.invalid",
    "subject": "Deploy finished",
    "body": "All green.",
    "smtp_host": LOCAL_HOST,
    "smtp_port": 587,
    "smtp_user": "robot@example.invalid",
    "smtp_password": NOT_A_PASSWORD,
}

NOTIFICATION_EMAIL_PARAMS = {
    "smtp_server": LOCAL_HOST,
    "smtp_port": 587,
    "username": "robot@example.invalid",
    "password": NOT_A_PASSWORD,
    "from_email": "robot@example.invalid",
    "to_email": "team@example.invalid",
    "subject": "Deploy finished",
    "body": "All green.",
}

TWILIO_SMS_BODY = {
    "sid": "SM00000000000000000000000000000000",
    "status": "queued",
    "to": "+15550000001",
    "from": "+15550000002",
}

TWILIO_CALL_BODY = {
    "sid": "CA00000000000000000000000000000000",
    "status": "queued",
    "to": "+15550000001",
    "from": "+15550000002",
}

WHATSAPP_BODY = {
    "messaging_product": "whatsapp",
    "contacts": [{"input": "+15550000001", "wa_id": "15550000001"}],
    "messages": [{"id": "wamid.NOT_A_REAL_ID"}],
}

TELEGRAM_BODY = {"ok": True, "result": {"message_id": 4242, "chat": {"id": 123456789}}}


async def success_email_send(monkeypatch):
    install_smtp(monkeypatch)
    return await run("email.send", dict(EMAIL_SEND_PARAMS))


async def success_email_read(monkeypatch):
    install_imap(monkeypatch, ids=[b"1", b"2", b"3"])
    return await run("email.read", {
        "folder": "INBOX", "limit": 10,
        "imap_host": LOCAL_HOST, "imap_port": 993,
        "imap_user": "robot@example.invalid", "imap_password": NOT_A_PASSWORD,
    })


async def success_slack_send(monkeypatch):
    reply = _Reply(200, text_body="ok")
    monkeypatch.setattr(SLACK_SEND, "enforce_outbound_url", lambda url: url)
    monkeypatch.setattr(SLACK_SEND, "guarded_client_session", lambda *a, **k: _Session(reply))
    return await run("slack.send", {"message": "All green.", "webhook_url": WEBHOOK_URL})


async def success_notification_slack(monkeypatch):
    from core.modules.third_party.communication.messaging import slack as module
    install_guarded(monkeypatch, module, _Reply(200, text_body="ok"))
    return await run("notification.slack.send_message",
                     {"text": "All green.", "webhook_url": WEBHOOK_URL})


async def success_discord(monkeypatch):
    from core.modules.third_party.communication.messaging import discord as module
    install_guarded(monkeypatch, module, _Reply(204))
    return await run("notification.discord.send_message",
                     {"content": "All green.", "webhook_url": WEBHOOK_URL})


async def success_teams(monkeypatch):
    from core.modules.third_party.communication.messaging import teams as module
    install_guarded(monkeypatch, module, _Reply(200, text_body="1"))
    return await run("notification.teams.send_message",
                     {"message": "All green.", "webhook_url": WEBHOOK_URL})


async def success_telegram(monkeypatch):
    install_aiohttp(monkeypatch, _Reply(200, json_body=TELEGRAM_BODY))
    return await run("notification.telegram.send_message",
                     {"text": "All green.", "chat_id": "123456789", "bot_token": NOT_A_TOKEN})


async def success_whatsapp(monkeypatch):
    install_aiohttp(monkeypatch, _Reply(200, json_body=WHATSAPP_BODY))
    return await run("notification.whatsapp.send_message", {
        "phone_number_id": "1234567890", "to": "+15550000001",
        "message": "All green.", "access_token": NOT_A_TOKEN,
    })


async def success_notification_email(monkeypatch):
    install_smtp(monkeypatch)
    return await run("notification.email.send", dict(NOTIFICATION_EMAIL_PARAMS))


async def success_twilio_sms(monkeypatch):
    install_aiohttp(monkeypatch, _Reply(201, json_body=TWILIO_SMS_BODY))
    return await run("communication.twilio.send_sms", {
        "account_sid": "AC00000000000000000000000000000000",
        "auth_token": NOT_A_TOKEN,
        "from_number": "+15550000002", "to_number": "+15550000001",
        "message": "All green.",
    })


async def success_twilio_call(monkeypatch):
    install_aiohttp(monkeypatch, _Reply(201, json_body=TWILIO_CALL_BODY))
    return await run("communication.twilio.make_call", {
        "account_sid": "AC00000000000000000000000000000000",
        "auth_token": NOT_A_TOKEN,
        "from_number": "+15550000002", "to_number": "+15550000001",
        "twiml_url": "https://example.invalid/voice.xml",
    })


#: Every module in the group, and one successful call to it. `email.read` is
#: kept out of the SENDS list on purpose: it is the only read here, and it is
#: the only member allowed to claim OBSERVED.
SENDS = {
    "email.send": success_email_send,
    "slack.send": success_slack_send,
    "notification.slack.send_message": success_notification_slack,
    "notification.discord.send_message": success_discord,
    "notification.teams.send_message": success_teams,
    "notification.telegram.send_message": success_telegram,
    "notification.whatsapp.send_message": success_whatsapp,
    "notification.email.send": success_notification_email,
    "communication.twilio.send_sms": success_twilio_sms,
    "communication.twilio.make_call": success_twilio_call,
}


# ===========================================================================
# The claim the whole group makes.
# ===========================================================================

class TestNothingThatReachesAPersonClaimsToHaveBeenRead:
    """Ten sends, one rung: ACCEPTED. This is the point of the whole file."""

    @pytest.mark.parametrize("module_id", sorted(SENDS))
    @pytest.mark.asyncio
    async def test_a_successful_send_is_accepted_and_never_more(
        self, module_id, monkeypatch
    ):
        result = await SENDS[module_id](monkeypatch)
        found = envelope_of(result)

        assert found is not None, f"{module_id} attached no envelope to its happy path"
        assert found["rung"] == Outcome.ACCEPTED.value, (
            f"{module_id} claimed {found['rung']}. A 2xx from a messaging API is "
            "the peer reporting on its own work; nobody has read anything."
        )

    @pytest.mark.parametrize("module_id", sorted(SENDS))
    @pytest.mark.asyncio
    async def test_every_send_says_out_loud_that_nobody_received_it(
        self, module_id, monkeypatch
    ):
        """The effect that stops `accepted` being read as `delivered`.

        Without it the envelope is a rung and a status code, and the reader is
        left to know on their own that a 204 from a webhook is not a person.
        """
        result = await SENDS[module_id](monkeypatch)
        kinds = effect_kinds(result)

        assert any(
            kind in ("delivery_not_observed", "nobody_has_read_it") for kind in kinds
        ), f"{module_id} claims accepted without saying what it did not observe: {kinds}"

    @pytest.mark.parametrize("module_id", sorted(SENDS))
    @pytest.mark.asyncio
    async def test_the_engine_neither_stamps_over_it_nor_caps_it(
        self, module_id, monkeypatch
    ):
        """The envelope is where `_apply_outcome_contract` actually looks.

        Two ways to get this wrong and one test for both: put it outside `data`
        on a module that returns one and `to_legacy_dict` discards it; declare
        no postcondition and claim `verified` and `ceiling_for` lowers it. The
        contract runs here exactly as the executor runs it.
        """
        result = await SENDS[module_id](monkeypatch)
        before = envelope_of(result)["rung"]

        stamped = _apply_outcome_contract(id_only(module_id), result)

        assert envelope_of(stamped)["rung"] == before == Outcome.ACCEPTED.value


class TestTheRetryQuestionIsTheSplit:
    """FAILED vs INDETERMINATE, for every module that returns on failure.

    The question is never "did it work". It is "could this message already be in
    front of somebody". Every module in this group is `retryable=True`, so an
    answer of FAILED where the truth is INDETERMINATE is how one notification
    becomes two.
    """

    @pytest.mark.asyncio
    async def test_slack_names_a_4xx_as_failed(self, monkeypatch):
        from core.modules.third_party.communication.messaging import slack as module
        install_guarded(monkeypatch, module, _Reply(404, text_body="no_service"))
        result = await run("notification.slack.send_message",
                           {"text": "hi", "webhook_url": WEBHOOK_URL})

        assert rung_of(result) == Outcome.FAILED.value
        assert result["sent"] is False

    @pytest.mark.asyncio
    async def test_slack_leaves_a_5xx_indeterminate(self, monkeypatch):
        from core.modules.third_party.communication.messaging import slack as module
        install_guarded(monkeypatch, module, _Reply(503, text_body="rollup_error"))
        result = await run("notification.slack.send_message",
                           {"text": "hi", "webhook_url": WEBHOOK_URL})

        assert rung_of(result) == Outcome.INDETERMINATE.value

    @pytest.mark.asyncio
    async def test_discord_names_a_4xx_as_failed(self, monkeypatch):
        from core.modules.third_party.communication.messaging import discord as module
        install_guarded(monkeypatch, module, _Reply(404, text_body="Unknown Webhook"))
        result = await run("notification.discord.send_message",
                           {"content": "hi", "webhook_url": WEBHOOK_URL})

        assert rung_of(result) == Outcome.FAILED.value

    @pytest.mark.asyncio
    async def test_discord_leaves_a_5xx_indeterminate(self, monkeypatch):
        from core.modules.third_party.communication.messaging import discord as module
        install_guarded(monkeypatch, module, _Reply(500, text_body="oops"))
        result = await run("notification.discord.send_message",
                           {"content": "hi", "webhook_url": WEBHOOK_URL})

        assert rung_of(result) == Outcome.INDETERMINATE.value

    @pytest.mark.asyncio
    async def test_teams_names_a_4xx_as_failed(self, monkeypatch):
        from core.modules.third_party.communication.messaging import teams as module
        install_guarded(monkeypatch, module, _Reply(400, text_body="Bad payload"))
        result = await run("notification.teams.send_message",
                           {"message": "hi", "webhook_url": WEBHOOK_URL})

        assert rung_of(result) == Outcome.FAILED.value

    @pytest.mark.asyncio
    async def test_teams_leaves_a_202_indeterminate(self, monkeypatch):
        """The newer Power Automate workflow URL answers 202, and this module
        calls that an error. INDETERMINATE is what that is until the status
        test is fixed: the card was very likely accepted."""
        from core.modules.third_party.communication.messaging import teams as module
        install_guarded(monkeypatch, module, _Reply(202, text_body=""))
        result = await run("notification.teams.send_message",
                           {"message": "hi", "webhook_url": WEBHOOK_URL})

        assert rung_of(result) == Outcome.INDETERMINATE.value

    @pytest.mark.asyncio
    async def test_whatsapp_names_a_4xx_as_failed(self, monkeypatch):
        install_aiohttp(monkeypatch, _Reply(401, text_body='{"error":{"code":190}}'))
        result = await run("notification.whatsapp.send_message", {
            "phone_number_id": "1234567890", "to": "+15550000001",
            "message": "hi", "access_token": NOT_A_TOKEN,
        })

        assert rung_of(result) == Outcome.FAILED.value

    @pytest.mark.asyncio
    async def test_whatsapp_leaves_a_5xx_indeterminate(self, monkeypatch):
        install_aiohttp(monkeypatch, _Reply(500, text_body="internal"))
        result = await run("notification.whatsapp.send_message", {
            "phone_number_id": "1234567890", "to": "+15550000001",
            "message": "hi", "access_token": NOT_A_TOKEN,
        })

        assert rung_of(result) == Outcome.INDETERMINATE.value

    @pytest.mark.asyncio
    async def test_telegram_splits_on_its_own_error_code(self, monkeypatch):
        install_aiohttp(monkeypatch, _Reply(400, json_body={
            "ok": False, "error_code": 400, "description": "Bad Request: chat not found",
        }))
        refused = await run("notification.telegram.send_message",
                            {"text": "hi", "chat_id": "0", "bot_token": NOT_A_TOKEN})
        assert rung_of(refused) == Outcome.FAILED.value
        assert effect_named(refused, "message_refused_by_telegram")["error_code"] == 400

        install_aiohttp(monkeypatch, _Reply(500, json_body={
            "ok": False, "error_code": 500, "description": "Internal Server Error",
        }))
        broke = await run("notification.telegram.send_message",
                          {"text": "hi", "chat_id": "0", "bot_token": NOT_A_TOKEN})
        assert rung_of(broke) == Outcome.INDETERMINATE.value

    @pytest.mark.asyncio
    async def test_the_ceiling_does_not_turn_an_off_ladder_answer_into_a_rung(
        self, monkeypatch
    ):
        """`cap` leaves FAILED and INDETERMINATE alone, on both payload shapes.

        Worth pinning here because these two are the group's nested-``data``
        modules: an envelope written at the top level of a result that HAS a
        `data` dict is not where `_apply_outcome_contract` looks, and the bug
        would show up as the engine stamping `dispatched` over a real answer.
        """
        from core.modules.third_party.communication.messaging import teams as module
        install_guarded(monkeypatch, module, _Reply(400, text_body="Bad payload"))
        refused = await run("notification.teams.send_message",
                            {"message": "hi", "webhook_url": WEBHOOK_URL})
        stamped = _apply_outcome_contract(
            id_only("notification.teams.send_message"), refused)
        assert rung_of(stamped) == Outcome.FAILED.value

        install_aiohttp(monkeypatch, _Reply(500, text_body="internal"))
        broke = await run("notification.whatsapp.send_message", {
            "phone_number_id": "1234567890", "to": "+15550000001",
            "message": "hi", "access_token": NOT_A_TOKEN,
        })
        stamped = _apply_outcome_contract(
            id_only("notification.whatsapp.send_message"), broke)
        assert rung_of(stamped) == Outcome.INDETERMINATE.value

    @pytest.mark.asyncio
    async def test_a_blocked_url_is_failed_but_a_blocked_redirect_is_not(
        self, monkeypatch
    ):
        """One exception type, two facts, and only the guard's position tells
        them apart. Refused before a socket exists, nothing left this process.
        Refused on a redirect hop, the POST already went out and what the far
        side did with the body first is not knowable here."""
        from core.modules.third_party.communication.messaging import slack as module

        install_guarded(monkeypatch, module, _Reply(200), blocked="blocked host")
        preflight = await run("notification.slack.send_message",
                              {"text": "hi", "webhook_url": WEBHOOK_URL})
        assert rung_of(preflight) == Outcome.FAILED.value
        assert effect_named(preflight, "blocked_by_ssrf_guard")["measured_by"]

        install_guarded(monkeypatch, module, _Reply(200), blocked_hop="redirect to 169.254.169.254")
        hop = await run("notification.slack.send_message",
                        {"text": "hi", "webhook_url": WEBHOOK_URL})
        assert rung_of(hop) == Outcome.INDETERMINATE.value


# ===========================================================================
# Per-module measurements: the line each rung actually rests on.
# ===========================================================================

class TestSmtpRestsOnTheRefusalMapAndNotOnTheInputList:
    """`recipients` is the caller's own list. The refusal map is not.

    This is the `file.write` failure exactly: a value that reads identically
    whether the effect happened. `email.send` returned `recipients:
    all_recipients` and `sent: True` and called `sendmail` for its side effect,
    discarding the one thing the server said.
    """

    @pytest.mark.asyncio
    async def test_an_accepted_send_names_the_addresses_the_server_took(
        self, monkeypatch
    ):
        result = await success_email_send(monkeypatch)

        assert rung_of(result) == Outcome.ACCEPTED.value
        accepted = effect_named(result, "smtp_recipients_accepted")
        assert accepted["recipients"] == ["team@example.invalid"]
        assert "sendmail" in accepted["measured_by"]
        assert result["accepted_recipients"] == ["team@example.invalid"]
        assert result["refused_recipients"] == []

    @pytest.mark.asyncio
    async def test_a_partial_refusal_is_still_accepted_and_says_who_missed_out(
        self, monkeypatch
    ):
        """The case the old payload could not express at all.

        Some recipients refused, the rest taken: `sendmail` returns normally, so
        the step succeeds and `sent` is True. That is not wrong -- the message
        WAS accepted for the others -- and it is not the whole truth either.
        """
        install_smtp(monkeypatch, refused={
            "gone@example.invalid": (550, b"5.1.1 User unknown"),
        })
        params = dict(EMAIL_SEND_PARAMS, to="team@example.invalid,gone@example.invalid")
        result = await run("email.send", params)

        assert rung_of(result) == Outcome.ACCEPTED.value
        assert result["accepted_recipients"] == ["team@example.invalid"]
        assert result["refused_recipients"] == [{
            "recipient": "gone@example.invalid",
            "code": 550,
            "response": "5.1.1 User unknown",
        }]
        refused_effect = effect_named(result, "smtp_recipients_refused")
        assert refused_effect["count"] == 1

    @pytest.mark.asyncio
    async def test_the_notification_twin_reports_the_same_measurement(
        self, monkeypatch
    ):
        install_smtp(monkeypatch, refused={"gone@example.invalid": (550, b"5.1.1 User unknown")})
        result = await run("notification.email.send", dict(NOTIFICATION_EMAIL_PARAMS))

        assert rung_of(result) == Outcome.ACCEPTED.value
        assert result["refused_recipients"][0]["code"] == 550


class TestTheSwallowedSmtpFailureNowSaysWhatKindItWas:
    """`notification.email.send` catches every exception and returns
    ``sent: False`` with no ``ok`` key, so the step is recorded as a SUCCESS.
    The envelope is the only field that disagrees -- and it distinguishes a mail
    that never existed from one that may already have been delivered."""

    @pytest.mark.asyncio
    async def test_a_rejected_login_is_failed(self, monkeypatch):
        install_smtp(monkeypatch, raise_on_login=smtplib.SMTPAuthenticationError(
            535, b"5.7.8 Authentication credentials invalid"))
        result = await run("notification.email.send", dict(NOTIFICATION_EMAIL_PARAMS))

        assert rung_of(result) == Outcome.FAILED.value
        effect = effect_named(result, "smtp_send_refused")
        assert effect["handed_over"] is False

    @pytest.mark.asyncio
    async def test_every_recipient_refused_is_failed(self, monkeypatch):
        install_smtp(monkeypatch, raise_on_send=smtplib.SMTPRecipientsRefused(
            {"team@example.invalid": (550, b"5.1.1 User unknown")}))
        result = await run("notification.email.send", dict(NOTIFICATION_EMAIL_PARAMS))

        assert rung_of(result) == Outcome.FAILED.value
        assert effect_named(result, "smtp_send_refused")["handed_over"] is True

    @pytest.mark.asyncio
    async def test_a_disconnect_mid_send_is_indeterminate(self, monkeypatch):
        """The one that matters, and the one a bare `except Exception` gets
        wrong. `retryable=True, max_retries=2`: reporting FAILED here sends the
        message a second time to somebody who may already have it."""
        install_smtp(monkeypatch, raise_on_send=smtplib.SMTPServerDisconnected(
            "connection closed by server"))
        result = await run("notification.email.send", dict(NOTIFICATION_EMAIL_PARAMS))

        assert rung_of(result) == Outcome.INDETERMINATE.value
        effect = effect_named(result, "smtp_send_inconclusive")
        assert effect["handed_over"] is True
        assert effect["error_type"] == "SMTPServerDisconnected"

    @pytest.mark.asyncio
    async def test_a_timeout_mid_send_is_indeterminate(self, monkeypatch):
        install_smtp(monkeypatch, raise_on_send=TimeoutError("timed out"))
        result = await run("notification.email.send", dict(NOTIFICATION_EMAIL_PARAMS))

        assert rung_of(result) == Outcome.INDETERMINATE.value


class TestTeamsAnswers200ForTwoOppositeFacts:
    """The one API in this group where the status line is not an acknowledgement.

    An Office 365 connector writes ``1`` when it takes a card, and writes an
    English sentence describing a failure -- with the same 200 -- when it does
    not. This module's success test is the status line, so both are steps that
    SUCCEED. Only the rung can tell them apart, and only because the body is now
    read.
    """

    @pytest.mark.asyncio
    async def test_the_acknowledgement_body_earns_accepted(self, monkeypatch):
        result = await success_teams(monkeypatch)

        assert rung_of(result) == Outcome.ACCEPTED.value
        assert effect_named(result, "card_accepted_by_teams")["response"] == "1"

    @pytest.mark.asyncio
    async def test_a_200_that_describes_a_failure_is_indeterminate(self, monkeypatch):
        from core.modules.third_party.communication.messaging import teams as module
        install_guarded(monkeypatch, module, _Reply(200, text_body=(
            "Webhook message delivery failed with error: Microsoft Teams "
            "endpoint returned HTTP error 413"
        )))
        result = await run("notification.teams.send_message",
                           {"message": "x" * 40, "webhook_url": WEBHOOK_URL})

        # The payload still reports success -- that is the module's contract
        # with its callers and this change does not touch it. The rung is the
        # one field that declines to agree.
        assert result["ok"] is True
        assert result["data"]["status"] == "sent"
        assert rung_of(result) == Outcome.INDETERMINATE.value
        assert "413" in effect_named(result, "teams_answer_not_an_acknowledgement")["response"]


class TestWhatsAppSaysWhenMetaIsHoldingTheMessage:
    @pytest.mark.asyncio
    async def test_an_id_comes_back_and_delivery_does_not(self, monkeypatch):
        result = await success_whatsapp(monkeypatch)

        assert rung_of(result) == Outcome.ACCEPTED.value
        assert effect_named(result, "message_accepted_by_whatsapp")["message_id"] == (
            "wamid.NOT_A_REAL_ID"
        )
        assert effect_named(result, "delivery_not_observed")["measured_by"] is None

    @pytest.mark.asyncio
    async def test_held_for_quality_assessment_reaches_the_envelope(self, monkeypatch):
        """Accepted and deliberately not delivered, while `status` reads 'sent'."""
        install_aiohttp(monkeypatch, _Reply(200, json_body={
            "messages": [{
                "id": "wamid.NOT_A_REAL_ID",
                "message_status": "held_for_quality_assessment",
            }],
        }))
        result = await run("notification.whatsapp.send_message", {
            "phone_number_id": "1234567890", "to": "+15550000001",
            "message": "hi", "access_token": NOT_A_TOKEN,
        })

        assert result["data"]["status"] == "sent"
        assert rung_of(result) == Outcome.ACCEPTED.value
        assert effect_named(result, "whatsapp_message_status")["message_status"] == (
            "held_for_quality_assessment"
        )

    @pytest.mark.asyncio
    async def test_a_2xx_with_no_id_says_the_claim_is_thinner(self, monkeypatch):
        install_aiohttp(monkeypatch, _Reply(200, json_body={"messaging_product": "whatsapp"}))
        result = await run("notification.whatsapp.send_message", {
            "phone_number_id": "1234567890", "to": "+15550000001",
            "message": "hi", "access_token": NOT_A_TOKEN,
        })

        assert rung_of(result) == Outcome.ACCEPTED.value
        assert "message_accepted_without_id" in effect_kinds(result)


class TestTwilioReportsItsOwnQueue:
    """The clearest ACCEPTED in the product: the peer's word for how far it got
    is the literal string `queued`."""

    @pytest.mark.asyncio
    async def test_an_sms_is_queued_and_not_delivered(self, monkeypatch):
        result = await success_twilio_sms(monkeypatch)

        assert rung_of(result) == Outcome.ACCEPTED.value
        effect = effect_named(result, "message_accepted_by_twilio")
        assert effect["twilio_status"] == "queued"
        assert effect["sid"] == TWILIO_SMS_BODY["sid"]
        assert "status-callback" in effect_named(result, "delivery_not_observed")["detail"]

    @pytest.mark.asyncio
    async def test_a_call_is_queued_and_nobody_has_answered(self, monkeypatch):
        result = await success_twilio_call(monkeypatch)

        assert rung_of(result) == Outcome.ACCEPTED.value
        assert effect_named(result, "call_accepted_by_twilio")["twilio_status"] == "queued"
        assert "picked up" in effect_named(result, "delivery_not_observed")["detail"]


class TestEmailReadHasNoSingleRung:
    """Three paths, three different measurements -- the `database.query` shape.

    A count of messages the server actually sent is an observation. A count of
    zero is not one, and a count of zero written by this file after a SEARCH
    that never answered is not even an answer.
    """

    @pytest.mark.asyncio
    async def test_messages_that_came_back_are_observed(self, monkeypatch):
        result = await success_email_read(monkeypatch)

        assert rung_of(result) == Outcome.OBSERVED.value
        assert result["count"] == 3
        assert result["matched"] == 3
        fetched = effect_named(result, "messages_fetched")
        assert fetched["count"] == 3 and fetched["matched"] == 3
        assert "len()" in fetched["measured_by"]

    @pytest.mark.asyncio
    async def test_an_empty_folder_is_only_accepted(self, monkeypatch):
        install_imap(monkeypatch, ids=[])
        result = await run("email.read", {
            "folder": "INBOX", "imap_host": LOCAL_HOST,
            "imap_user": "robot@example.invalid", "imap_password": NOT_A_PASSWORD,
        })

        assert rung_of(result) == Outcome.ACCEPTED.value
        assert result["count"] == 0
        assert effect_named(result, "no_messages_returned")["measured_by"] is None

    @pytest.mark.asyncio
    async def test_a_search_that_did_not_answer_is_indeterminate(self, monkeypatch):
        """The bug this rung makes visible: `if status != 'OK': return []`
        hands back `ok: True, count: 0`, which is indistinguishable from an
        empty mailbox. It is not the same fact and it no longer reads as one."""
        install_imap(monkeypatch, ids=[b"1", b"2"], search_status="NO")
        result = await run("email.read", {
            "folder": "INBOX", "imap_host": LOCAL_HOST,
            "imap_user": "robot@example.invalid", "imap_password": NOT_A_PASSWORD,
        })

        assert result["ok"] is True and result["count"] == 0
        assert rung_of(result) == Outcome.INDETERMINATE.value
        assert "search_not_answered" in effect_kinds(result)

    @pytest.mark.asyncio
    async def test_messages_the_server_would_not_hand_over_are_named(self, monkeypatch):
        """Observed for what arrived, and explicit about what did not. The
        returned list is not the answer to the search, and nothing else in the
        payload says so."""
        install_imap(monkeypatch, ids=[b"1", b"2", b"3"], fetch_failures=[b"2"])
        result = await run("email.read", {
            "folder": "INBOX", "imap_host": LOCAL_HOST,
            "imap_user": "robot@example.invalid", "imap_password": NOT_A_PASSWORD,
        })

        assert rung_of(result) == Outcome.OBSERVED.value
        assert result["count"] == 2 and result["matched"] == 3
        assert effect_named(result, "messages_not_fetched")["count"] == 1

    @pytest.mark.asyncio
    async def test_reading_marks_the_messages_seen_and_the_envelope_says_so(
        self, monkeypatch
    ):
        """The side effect that is invisible in the payload. The FETCH is
        `(RFC822)`, not `(BODY.PEEK[])`, so the server sets \\Seen -- which with
        `unread_only=True` means the second run legitimately finds nothing."""
        result = await success_email_read(monkeypatch)

        effect = effect_named(result, "messages_marked_seen")
        assert effect["count"] == 3
        assert "BODY.PEEK" in effect["measured_by"]

    @pytest.mark.asyncio
    async def test_a_read_is_the_only_member_of_this_group_that_may_say_observed(
        self, monkeypatch
    ):
        read = await success_email_read(monkeypatch)
        send = await success_email_send(monkeypatch)

        assert rung_of(read) == Outcome.OBSERVED.value
        assert rung_of(send) == Outcome.ACCEPTED.value


class TestTheSlackWebhookPair:
    @pytest.mark.asyncio
    async def test_the_atomic_module_is_accepted_on_200(self, monkeypatch):
        result = await success_slack_send(monkeypatch)

        assert rung_of(result) == Outcome.ACCEPTED.value
        assert effect_named(result, "webhook_accepted_by_slack")["status"] == 200

    @pytest.mark.asyncio
    async def test_the_atomic_module_still_raises_and_so_carries_nothing(
        self, monkeypatch
    ):
        """Written down rather than papered over. `slack.send` raises on a
        non-200, so the payload is discarded and no rung can ride on it --
        including the timeout that `retryable=True, max_retries=3` will send
        again."""
        reply = _Reply(404, text_body="no_service")
        monkeypatch.setattr(SLACK_SEND, "enforce_outbound_url", lambda url: url)
        monkeypatch.setattr(SLACK_SEND, "guarded_client_session", lambda *a, **k: _Session(reply))

        with pytest.raises(RuntimeError):
            await run("slack.send", {"message": "hi", "webhook_url": WEBHOOK_URL})

    @pytest.mark.asyncio
    async def test_discord_treats_204_as_the_ordinary_acknowledgement(self, monkeypatch):
        """A Discord webhook answers 204 No Content unless the URL carries
        `?wait=true`. Both are acceptance, and a rung that recognised only 200
        would call the normal case a failure."""
        from core.modules.third_party.communication.messaging import discord as module

        install_guarded(monkeypatch, module, _Reply(204))
        no_content = await run("notification.discord.send_message",
                               {"content": "hi", "webhook_url": WEBHOOK_URL})

        install_guarded(monkeypatch, module, _Reply(200, text_body="{}"))
        with_body = await run("notification.discord.send_message",
                              {"content": "hi", "webhook_url": WEBHOOK_URL})

        assert rung_of(no_content) == rung_of(with_body) == Outcome.ACCEPTED.value


class TestTelegramIdIsNotAnObservation:
    @pytest.mark.asyncio
    async def test_the_message_id_is_carried_as_the_peers_own_report(self, monkeypatch):
        result = await success_telegram(monkeypatch)

        assert rung_of(result) == Outcome.ACCEPTED.value
        effect = effect_named(result, "message_accepted_by_telegram")
        assert effect["message_id"] == 4242
        assert "sendMessage" in effect["measured_by"]
        assert "muted chat" in effect_named(result, "nobody_has_read_it")["detail"]
