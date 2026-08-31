# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""What the thirteen `api.*` modules are entitled to claim, and why it is one rung.

THE GROUP-WIDE ANSWER IS ACCEPTED, and the test that matters most in this file
is the one that says so for all thirteen at once
(:class:`TestNothingInThisGroupClaimsToHaveSeenAnything`). Every module here
sends one request and reads the reply to that same request. None of them reads
anything back. A 200 with a repository in it, a 201 naming an issue GitHub says
it just created, a `usage` block counting tokens, `updatedCells: 12` from
Sheets -- every one of those is the peer reporting on its own work, which is
`http.request`'s settled position for every 2xx in this product and the
definition of taking somebody's word for it.

That is not a small claim to have earned. The alternative was never OBSERVED,
it was DISPATCHED -- what the engine stamps on a module that reports nothing,
and what all thirteen said before this change. "The instruction left us and
nobody confirmed anything" is untrue of a call that came back 201 with a
server-assigned issue number in it.

THE ERROR PATHS ARE WHERE THE GROUP SPLITS, and where the real defect lives.
The five GitHub modules do not raise on a non-2xx: they return
``{'status': 'error', ...}`` with no ``ok`` key, so the step is recorded as a
SUCCESS and a 404 flows downstream as if it were a repository. Those paths now
carry FAILED (GitHub refused; nothing happened) or INDETERMINATE (GitHub broke
mid-POST; the issue may exist and a retry may make a second one), and
:class:`TestGitHubErrorPathsSayWhatWentWrong` pins the split. The other eight
modules raise on error, so their payload is discarded and no rung can ride on
it; that gap is written down in each module's docstring rather than papered
over with a rung nothing would ever read.
"""

import sys
import types
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
from core.modules.registry import ModuleRegistry


def ensure_modules_loaded():
    from core.modules import atomic  # noqa: F401
    with suppress(Exception):
        from core.modules import third_party  # noqa: F401


ensure_modules_loaded()

# Not a credential. Every module in this group reads a token from a parameter or
# the environment before it builds a request; these tests hand it a value that
# is obviously not one so the code path runs without depending on a developer's
# real environment. Nothing here is ever sent anywhere -- the transport is
# replaced below.
NOT_A_TOKEN = "not-a-real-token"


# ===========================================================================
# The transports, replaced. Each module talks to exactly one of these three.
# ===========================================================================

class _Reply:
    """One aiohttp response, and the async-context shape the modules use."""

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


def install_http(monkeypatch, reply):
    """Every module here reaches the network through `aiohttp.ClientSession`."""
    session = _Session(reply)
    monkeypatch.setattr(aiohttp, "ClientSession", lambda *a, **k: session)
    return session


class _SheetsRequest:
    def __init__(self, response):
        self._response = response

    def execute(self):
        return self._response


class _SheetsService:
    """`service.spreadsheets().values().get(...).execute()`, and the update twin."""

    def __init__(self, response):
        self._response = response
        self.calls = []

    def spreadsheets(self):
        return self

    def values(self):
        return self

    def get(self, **kwargs):
        self.calls.append(("get", kwargs))
        return _SheetsRequest(self._response)

    def update(self, **kwargs):
        self.calls.append(("update", kwargs))
        return _SheetsRequest(self._response)


def install_sheets(monkeypatch, response):
    """Stand in for `googleapiclient`, which this checkout does not install.

    `google.oauth2` IS installed, so `Credentials.from_service_account_info` is
    a real function that would demand real key material. It is replaced too --
    a test that needed a service-account key to run would be a test nobody could
    run, and a key in a fixture is the thing AGENTS.md forbids outright.
    """
    service_account = pytest.importorskip(
        "google.oauth2.service_account", reason="needs the google-auth extra"
    )

    class _Credentials:
        @staticmethod
        def from_service_account_info(info, scopes=None):
            return object()

    monkeypatch.setattr(service_account, "Credentials", _Credentials)

    service = _SheetsService(response)
    discovery = types.ModuleType("googleapiclient.discovery")
    discovery.build = lambda *a, **k: service
    package = types.ModuleType("googleapiclient")
    package.discovery = discovery
    monkeypatch.setitem(sys.modules, "googleapiclient", package)
    monkeypatch.setitem(sys.modules, "googleapiclient.discovery", discovery)
    return service


class _Attr:
    """A tiny object whose attributes are the keyword arguments given."""

    def __init__(self, **fields):
        self.__dict__.update(fields)


def install_openai(monkeypatch, *, completion=None, image_data=None):
    """A stand-in `openai`, for the two modules that use the SDK not aiohttp."""
    module = types.ModuleType("openai")

    class _Completions:
        async def create(self, **kwargs):
            module.chat_call = kwargs
            return completion

    class _AsyncOpenAI:
        def __init__(self, **kwargs):
            module.client_kwargs = kwargs
            self.chat = _Attr(completions=_Completions())

    class _Image:
        @staticmethod
        async def acreate(**kwargs):
            module.image_call = kwargs
            return _Attr(data=image_data or [])

    module.AsyncOpenAI = _AsyncOpenAI
    module.Image = _Image
    module.api_key = None
    monkeypatch.setitem(sys.modules, "openai", module)
    return module


async def run(module_id, params):
    """Execute a module the way the engine does, and return its payload."""
    return await ModuleRegistry.get(module_id)(params, {}).execute()


def envelope_of(result):
    """The envelope, read from where `step_executor` reads it.

    Top level, not under `data`: every module in this group returns a flat dict
    with no `ok` key, which `_execute_single_mode` passes through untouched and
    `_apply_outcome_contract` treats as the body.
    """
    return read_envelope(result)


def effect_named(found, kind):
    return next(effect for effect in found["effects"] if effect["kind"] == kind)


def effect_kinds(found):
    return [effect["kind"] for effect in found["effects"]]


# ===========================================================================
# Canned replies. Trimmed to the fields each module actually reads.
# ===========================================================================

REPO_BODY = {
    "name": "Hello-World",
    "full_name": "octocat/Hello-World",
    "description": "My first repository",
    "stargazers_count": 80,
    "forks_count": 9,
    "html_url": "https://github.com/octocat/Hello-World",
}

ISSUE_BODY = {"number": 1347, "html_url": "https://github.com/octocat/Hello-World/issues/1347"}

PR_BODY = {"number": 42, "html_url": "https://github.com/octocat/Hello-World/pull/42"}

ISSUE_LIST = [
    {"number": 1, "title": "first", "state": "open", "html_url": "u", "labels": [], "user": {"login": "a"}},
    {"number": 2, "title": "second", "state": "open", "html_url": "u", "labels": [], "user": {"login": "b"}},
]

REPO_LIST = [{"name": "one", "full_name": "octocat/one"}, {"name": "two", "full_name": "octocat/two"}]

ANTHROPIC_BODY = {
    "content": [{"type": "text", "text": "Paris."}],
    "model": "claude-sonnet-4-6-20260101",
    "stop_reason": "end_turn",
    "usage": {"input_tokens": 14, "output_tokens": 3},
}

GEMINI_BODY = {
    "candidates": [
        {"content": {"parts": [{"text": "42."}]}, "finishReason": "STOP"},
    ],
    "usageMetadata": {"promptTokenCount": 7, "candidatesTokenCount": 2},
    "modelVersion": "gemini-2.5-pro-002",
}

NOTION_PAGE = {
    "id": "59833787-2cf9-4fdf-8782-e53db20768a5",
    "url": "https://www.notion.so/59833787",
    "created_time": "2026-08-31T10:00:00.000Z",
}

NOTION_QUERY = {"results": [{"id": "a"}, {"id": "b"}], "has_more": False}

SHEET_VALUES = {
    "range": "Sheet1!A1:C3",
    "majorDimension": "ROWS",
    "values": [["Name", "Email"], ["Ada", "ada@example.invalid"], ["Grace", "grace@example.invalid"]],
}

SHEET_UPDATE = {
    "spreadsheetId": "1BxiMVs0",
    "updatedRange": "Sheet1!A1:B3",
    "updatedRows": 3,
    "updatedColumns": 2,
    "updatedCells": 6,
}


# ===========================================================================
# One successful call per module, all thirteen.
# ===========================================================================

async def success_get_repo(monkeypatch):
    install_http(monkeypatch, _Reply(200, REPO_BODY))
    return await run("api.github.get_repo", {"owner": "octocat", "repo": "Hello-World", "token": NOT_A_TOKEN})


async def success_list_issues(monkeypatch):
    install_http(monkeypatch, _Reply(200, ISSUE_LIST))
    return await run("api.github.list_issues", {"owner": "octocat", "repo": "Hello-World", "token": NOT_A_TOKEN})


async def success_list_repos(monkeypatch):
    install_http(monkeypatch, _Reply(200, REPO_LIST))
    return await run("api.github.list_repos", {"owner": "octocat", "token": NOT_A_TOKEN})


async def success_create_issue(monkeypatch):
    install_http(monkeypatch, _Reply(201, ISSUE_BODY))
    return await run(
        "api.github.create_issue",
        {"owner": "octocat", "repo": "Hello-World", "title": "Bug", "token": NOT_A_TOKEN},
    )


async def success_create_pr(monkeypatch):
    install_http(monkeypatch, _Reply(201, PR_BODY))
    return await run(
        "api.github.create_pr",
        {
            "owner": "octocat",
            "repo": "Hello-World",
            "title": "Add feature",
            "head": "feature/x",
            "token": NOT_A_TOKEN,
        },
    )


async def success_anthropic(monkeypatch):
    install_http(monkeypatch, _Reply(200, ANTHROPIC_BODY))
    return await run(
        "api.anthropic.chat",
        {"api_key": NOT_A_TOKEN, "messages": [{"role": "user", "content": "capital of France?"}]},
    )


async def success_gemini(monkeypatch):
    install_http(monkeypatch, _Reply(200, GEMINI_BODY))
    return await run(
        "api.google_gemini.chat",
        {"api_key": NOT_A_TOKEN, "prompt": "meaning of life?", "model": "gemini-2.5-pro"},
    )


async def success_notion_create(monkeypatch):
    install_http(monkeypatch, _Reply(200, NOTION_PAGE))
    return await run(
        "api.notion.create_page",
        {"api_key": NOT_A_TOKEN, "database_id": "db", "properties": {"Name": {"title": []}}},
    )


async def success_notion_query(monkeypatch):
    install_http(monkeypatch, _Reply(200, NOTION_QUERY))
    return await run("api.notion.query_database", {"api_key": NOT_A_TOKEN, "database_id": "db"})


async def success_sheets_read(monkeypatch):
    install_sheets(monkeypatch, SHEET_VALUES)
    return await run(
        "api.google_sheets.read",
        {
            "credentials": {"type": "service_account", "client_email": "unit-test@example.invalid"},
            "spreadsheet_id": "1BxiMVs0",
            "range": "Sheet1!A1:C3",
        },
    )


async def success_sheets_write(monkeypatch):
    install_sheets(monkeypatch, SHEET_UPDATE)
    return await run(
        "api.google_sheets.write",
        {
            "credentials": {"type": "service_account", "client_email": "unit-test@example.invalid"},
            "spreadsheet_id": "1BxiMVs0",
            "range": "Sheet1!A1",
            "values": [["Name", "Email"], ["Ada", "ada@example.invalid"], ["Grace", "g@example.invalid"]],
        },
    )


async def success_openai_chat(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", NOT_A_TOKEN)
    install_openai(
        monkeypatch,
        completion=_Attr(
            choices=[_Attr(message=_Attr(content="Hello."), finish_reason="stop")],
            model="gpt-4o-2026-05-01",
            usage=_Attr(prompt_tokens=11, completion_tokens=2, total_tokens=13),
        ),
    )
    return await run("api.openai.chat", {"prompt": "hi", "model": "gpt-4o"})


async def success_openai_image(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", NOT_A_TOKEN)
    install_openai(
        monkeypatch,
        image_data=[_Attr(url="https://example.invalid/a.png", revised_prompt="a cat, refined")],
    )
    return await run("api.openai.image", {"prompt": "a cat", "model": "dall-e-3"})


SUCCESS = {
    "api.anthropic.chat": success_anthropic,
    "api.github.create_issue": success_create_issue,
    "api.github.create_pr": success_create_pr,
    "api.github.get_repo": success_get_repo,
    "api.github.list_issues": success_list_issues,
    "api.github.list_repos": success_list_repos,
    "api.google_gemini.chat": success_gemini,
    "api.google_sheets.read": success_sheets_read,
    "api.google_sheets.write": success_sheets_write,
    "api.notion.create_page": success_notion_create,
    "api.notion.query_database": success_notion_query,
    "api.openai.chat": success_openai_chat,
    "api.openai.image": success_openai_image,
}

ALL_MODULES = sorted(SUCCESS)


# ===========================================================================
# The group-wide claim
# ===========================================================================

class TestNothingInThisGroupClaimsToHaveSeenAnything:
    """One request, its reply, no read-back. ACCEPTED, thirteen times.

    This is the class to break if somebody later teaches one of these modules
    to read its effect back -- and breaking it should require saying so out
    loud, because the alternative is the failure this whole contract exists to
    stop: a rung that rests on a peer's account of its own work.
    """

    def test_the_group_is_all_thirteen_api_modules(self):
        """A fourteenth `api.*` module must not slip past this file unnoticed."""
        registered = {
            module_id
            for module_id in ModuleRegistry.get_all_metadata(filter_by_stability=False)
            if module_id.split(".")[0] == "api"
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
        """The trap that cost this group its token counts, pinned.

        `_redact_sensitive_output` blanks any key matching `token`, `secret`,
        `auth`, and five other patterns. A usage effect with an `input_tokens`
        field would reach every hook and every stored trace as '[REDACTED]' --
        evidence that reads as a redacted secret, which is worse than no
        evidence at all. The counts ride as `input_count` with `unit: tokens`
        instead, and this test is what keeps them there.
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


# ===========================================================================
# GitHub: the five modules whose error paths return instead of raising
# ===========================================================================

class TestGitHubErrorPathsSayWhatWentWrong:
    """The half of this group that had no voice at all, and needed one most.

    These five return `{'status': 'error'}` with no `ok` key, so the engine
    records the step as a SUCCESS and a 404 flows downstream as though it were
    a repository. The envelope is the only field on that payload that disagrees.
    """

    async def test_a_404_on_a_read_is_failed(self, monkeypatch):
        install_http(monkeypatch, _Reply(404, text="Not Found"))

        result = await run(
            "api.github.get_repo",
            {"owner": "octocat", "repo": "nope", "token": NOT_A_TOKEN},
        )

        assert result["status"] == "error"
        assert envelope_of(result)["rung"] == Outcome.FAILED.value

    async def test_the_step_still_reports_success_which_is_why_the_rung_matters(
        self, monkeypatch
    ):
        """Pins the defect this rung exposes, so a later fix has to face it.

        There is no `ok: False` here, so nothing about this payload says the
        read failed except the outcome. If somebody later makes these modules
        raise or return `ok: False`, this test fails -- and that is the moment
        to notice the envelope goes away with it, exactly as `http.request`
        documents on its own non-2xx branch.
        """
        install_http(monkeypatch, _Reply(404, text="Not Found"))

        result = await run(
            "api.github.get_repo",
            {"owner": "octocat", "repo": "nope", "token": NOT_A_TOKEN},
        )

        assert "ok" not in result
        rung, _claim_by, _expected = step_outcome(result)
        assert rung is Outcome.FAILED

    @pytest.mark.parametrize(
        "module_id, params",
        [
            ("api.github.list_issues", {"owner": "octocat", "repo": "x", "token": NOT_A_TOKEN}),
            ("api.github.list_repos", {"owner": "octocat", "token": NOT_A_TOKEN}),
        ],
    )
    async def test_a_refused_list_is_failed_not_indeterminate(
        self, module_id, params, monkeypatch
    ):
        """A read changes nothing, so nothing is left in doubt."""
        install_http(monkeypatch, _Reply(403, text="rate limited"))

        result = await run(module_id, params)

        assert envelope_of(result)["rung"] == Outcome.FAILED.value

    @pytest.mark.parametrize("status", [400, 401, 403, 404, 422, 429])
    async def test_a_4xx_on_a_create_is_failed_because_nothing_was_created(
        self, status, monkeypatch
    ):
        install_http(monkeypatch, _Reply(status, text="rejected"))

        result = await run(
            "api.github.create_issue",
            {"owner": "octocat", "repo": "x", "title": "t", "token": NOT_A_TOKEN},
        )

        found = envelope_of(result)
        assert found["rung"] == Outcome.FAILED.value
        assert effect_named(found, "github_create_rejected")["resource"] == "issue"

    @pytest.mark.parametrize("status", [500, 502, 503, 504])
    async def test_a_5xx_on_a_create_is_indeterminate_because_it_may_have_happened(
        self, status, monkeypatch
    ):
        """The distinction a retry depends on.

        GitHub took the POST off the wire and then broke. The issue may exist.
        Calling this FAILED would tell a person nothing was created when
        something may have been -- and `retryable=False` on this module is the
        same judgement, made by whoever wrote it, about the same case.
        """
        install_http(monkeypatch, _Reply(status, text="server error"))

        result = await run(
            "api.github.create_issue",
            {"owner": "octocat", "repo": "x", "title": "t", "token": NOT_A_TOKEN},
        )

        found = envelope_of(result)
        assert found["rung"] == Outcome.INDETERMINATE.value
        assert "may or may not exist" in effect_named(found, "github_create_unconfirmed")["detail"]

    async def test_a_5xx_on_a_pull_request_is_indeterminate_too(self, monkeypatch):
        install_http(monkeypatch, _Reply(503, text="unavailable"))

        result = await run(
            "api.github.create_pr",
            {
                "owner": "octocat",
                "repo": "x",
                "title": "t",
                "head": "h",
                "token": NOT_A_TOKEN,
            },
        )

        assert envelope_of(result)["rung"] == Outcome.INDETERMINATE.value

    async def test_an_off_ladder_rung_reaches_the_engine_as_off_ladder(self, monkeypatch):
        """`cap` must not quietly turn these into a rung.

        A ceiling lowers an over-claim; it does not convert `failed` into
        `accepted`. This is the one place in the group where that matters.
        """
        install_http(monkeypatch, _Reply(500, text="boom"))

        result = await run(
            "api.github.create_pr",
            {"owner": "o", "repo": "r", "title": "t", "head": "h", "token": NOT_A_TOKEN},
        )
        stamped = _apply_outcome_contract(_Attr(module_id="api.github.create_pr"), result)

        rung, _claim_by, _expected = step_outcome(stamped)
        assert rung is Outcome.INDETERMINATE


class TestWhatTheGitHubSuccessEffectsActuallyMeasure:
    async def test_the_created_issue_number_is_named_as_the_peers_assertion(
        self, monkeypatch
    ):
        """The hardest case in the group, and the reason it is still ACCEPTED.

        1347 is not a number this module could have produced from its inputs,
        so it is real evidence that something happened on the other side -- and
        it is GitHub describing GitHub's own work, with no read-back anywhere,
        so it is not an observation.
        """
        result = await success_create_issue(monkeypatch)
        effect = effect_named(envelope_of(result), "issue_reported_created")

        assert effect["number"] == 1347
        assert "201 body GitHub returned" in effect["measured_by"]
        assert "not observed" in effect["detail"]

    async def test_the_issue_count_says_it_is_one_page(self, monkeypatch):
        """`count` is len() of a reply, not a property of the repository."""
        result = await success_list_issues(monkeypatch)
        effect = effect_named(envelope_of(result), "issues_returned")

        assert effect["count"] == 2 == result["count"]
        assert "not how many the repository" in effect["detail"]

    async def test_the_status_line_is_what_lifts_it_off_dispatched(self, monkeypatch):
        result = await success_get_repo(monkeypatch)
        effect = effect_named(envelope_of(result), "github_reply_read")

        assert effect["status"] == 200
        assert "response.status" in effect["measured_by"]


# ===========================================================================
# The two modules that echo an input back and could be mistaken for evidence
# ===========================================================================

class TestAnEchoIsLabelledAnEcho:
    """`file.write`'s `bytes_written`, twice, in this group.

    Both modules return a `model` field that is the caller's own parameter
    copied through -- identical whether the vendor answered or not. Neither
    rung rests on it, and the effect says out loud that it was not measured, so
    the next reader cannot mistake it for a peer statement the way `bytes_written`
    was mistaken for a file size.
    """

    async def test_gemini_says_its_model_field_is_the_requested_one(self, monkeypatch):
        result = await success_gemini(monkeypatch)
        found = envelope_of(result)

        echoed = effect_named(found, "model_echoed_from_request")
        assert echoed["model"] == "gemini-2.5-pro" == result["model"]
        assert echoed["measured_by"] is None
        assert "model_named_by_peer" not in effect_kinds(found)

    async def test_dall_e_says_the_same_of_its_own(self, monkeypatch):
        result = await success_openai_image(monkeypatch)

        echoed = effect_named(envelope_of(result), "model_echoed_from_request")
        assert echoed["model"] == "dall-e-3" == result["model"]
        assert echoed["measured_by"] is None

    async def test_anthropic_reads_its_model_from_the_reply_instead(self, monkeypatch):
        """The contrast that makes the label mean something.

        Anthropic's module reads `model` out of the response, so it can differ
        from what was asked for -- and here it does.
        """
        result = await success_anthropic(monkeypatch)

        named = effect_named(envelope_of(result), "model_named_by_peer")
        assert named["model"] == "claude-sonnet-4-6-20260101"
        assert "body Anthropic returned" in named["measured_by"]

    async def test_openai_chat_reads_its_model_from_the_reply_too(self, monkeypatch):
        result = await success_openai_chat(monkeypatch)

        named = effect_named(envelope_of(result), "model_named_by_peer")
        assert named["model"] == "gpt-4o-2026-05-01"
        assert result["model"] == "gpt-4o-2026-05-01"


class TestTheUsageBlockIsTheVendorsOwnAccount:
    @pytest.mark.parametrize(
        "runner, input_count, output_count, stop",
        [
            (success_anthropic, 14, 3, "end_turn"),
            (success_gemini, 7, 2, "STOP"),
            (success_openai_chat, 11, 2, "stop"),
        ],
    )
    async def test_the_counts_are_carried_under_names_that_survive_redaction(
        self, runner, input_count, output_count, stop, monkeypatch
    ):
        result = await runner(monkeypatch)
        usage = effect_named(envelope_of(result), "model_usage_reported")

        assert (usage["input_count"], usage["output_count"]) == (input_count, output_count)
        assert usage["unit"] == "tokens"
        assert usage["stop"] == stop

    async def test_a_missing_usage_block_is_none_and_not_a_zero(self, monkeypatch):
        """Gemini omits `usageMetadata` on some replies.

        0 would be a number written in the module; None is the honest value for
        a count that never arrived. This is the `database.query` fabricated-zero
        lesson applied before it could become a bug.
        """
        body = {k: v for k, v in GEMINI_BODY.items() if k != "usageMetadata"}
        install_http(monkeypatch, _Reply(200, body))

        result = await run(
            "api.google_gemini.chat",
            {"api_key": NOT_A_TOKEN, "prompt": "hi", "model": "gemini-2.5-pro"},
        )
        usage = effect_named(envelope_of(result), "model_usage_reported")

        assert usage["input_count"] is None
        assert usage["output_count"] is None
        assert envelope_of(result)["rung"] == Outcome.ACCEPTED.value


# ===========================================================================
# Sheets and Notion
# ===========================================================================

class TestGoogleSheetsCountsAreGooglesCounts:
    async def test_an_update_carries_the_count_google_reported(self, monkeypatch):
        result = await success_sheets_write(monkeypatch)
        effect = effect_named(envelope_of(result), "update_reported_by_peer")

        assert effect["count_reported"] is True
        assert effect["cells"] == 6 == result["updated_cells"]
        assert "not observed" in effect["detail"]

    async def test_a_reply_without_updated_cells_says_the_zero_is_a_literal(
        self, monkeypatch
    ):
        """`database.query`'s bug, caught in a second module before it bit.

        `result.get('updatedCells', 0)` cannot tell "Google says nothing
        changed" from "Google reported no count". The output keeps the 0 --
        consumers do arithmetic on it -- and the envelope records which one it
        was, so no rung ever rests on the fabricated number.
        """
        install_sheets(monkeypatch, {"spreadsheetId": "1BxiMVs0", "updatedRange": "Sheet1!A1"})

        result = await run(
            "api.google_sheets.write",
            {
                "credentials": {"type": "service_account", "client_email": "t@example.invalid"},
                "spreadsheet_id": "1BxiMVs0",
                "range": "Sheet1!A1",
                "values": [["a"]],
            },
        )
        found = envelope_of(result)

        assert result["updated_cells"] == 0
        effect = effect_named(found, "update_uncounted")
        assert effect["count_reported"] is False
        assert effect["cells"] is None
        assert effect["measured_by"] is None
        assert found["rung"] == Outcome.ACCEPTED.value

    async def test_a_read_says_its_row_count_includes_the_header(self, monkeypatch):
        """The one place `row_count` and `len(data)` legitimately disagree."""
        result = await success_sheets_read(monkeypatch)
        effect = effect_named(envelope_of(result), "rows_returned")

        assert result["row_count"] == 3
        assert len(result["data"]) == 2
        assert effect["count"] == 3
        assert effect["header_row_consumed"] is True
        assert effect["range_reported_by_peer"] == "Sheet1!A1:C3"

    async def test_without_a_header_the_count_and_the_rows_agree(self, monkeypatch):
        """The module's second return path, and the flag that tells them apart."""
        install_sheets(monkeypatch, SHEET_VALUES)

        result = await run(
            "api.google_sheets.read",
            {
                "credentials": {"type": "service_account", "client_email": "t@example.invalid"},
                "spreadsheet_id": "1BxiMVs0",
                "range": "Sheet1!A1:C3",
                "include_header": False,
            },
        )
        effect = effect_named(envelope_of(result), "rows_returned")

        assert "data" not in result
        assert result["row_count"] == 3 == effect["count"]
        assert effect["header_row_consumed"] is False

    async def test_an_empty_range_is_still_accepted_and_says_why(self, monkeypatch):
        """Sheets omits `values` entirely rather than sending an empty array."""
        install_sheets(monkeypatch, {"range": "Sheet1!Z1:Z9"})

        result = await run(
            "api.google_sheets.read",
            {
                "credentials": {"type": "service_account", "client_email": "t@example.invalid"},
                "spreadsheet_id": "1BxiMVs0",
                "range": "Sheet1!Z1:Z9",
            },
        )
        found = envelope_of(result)

        assert result["row_count"] == 0
        assert found["rung"] == Outcome.ACCEPTED.value
        assert effect_named(found, "rows_returned")["count"] == 0


class TestNotion:
    async def test_a_created_page_is_the_peers_assertion_with_an_id(self, monkeypatch):
        result = await success_notion_create(monkeypatch)
        effect = effect_named(envelope_of(result), "page_reported_created")

        assert effect["page_id"] == NOTION_PAGE["id"] == result["page_id"]
        assert "not an observation" in effect["detail"]

    async def test_a_query_count_is_the_size_of_one_page(self, monkeypatch):
        result = await success_notion_query(monkeypatch)
        effect = effect_named(envelope_of(result), "pages_returned")

        assert effect["count"] == 2 == result["count"]
        assert effect["has_more"] is False
        assert "not a total" in effect["detail"]

    async def test_has_more_travels_with_the_count(self, monkeypatch):
        """A count beside `has_more: true` is a page, and the effect says so."""
        install_http(monkeypatch, _Reply(200, {"results": [{"id": "a"}], "has_more": True}))

        result = await run("api.notion.query_database", {"api_key": NOT_A_TOKEN, "database_id": "db"})

        assert effect_named(envelope_of(result), "pages_returned")["has_more"] is True


# ===========================================================================
# A bug this exercise found, pinned so the fix has somewhere to land
# ===========================================================================

class TestDallEIsCallingASurfaceTheSdkRemoved:
    """`api.openai.image` cannot succeed against the installed SDK.

    It calls `openai.Image.acreate`, removed in openai>=1.0, while the chat
    module beside it uses `openai.AsyncOpenAI`. Every call raises
    `APIRemovedInV1`, which the module's blanket `except Exception` turns into
    `RuntimeError("DALL-E API error: ...")`. The success path -- envelope
    included -- is unreachable today.

    This is not fixed here: the replacement is `client.images.generate`, and
    nothing in this checkout can test that against the real service, so it is
    reported rather than guessed at. The test is written so it fails the day
    somebody does fix it, which is the right time to revisit it.
    """

    async def test_the_real_sdk_refuses_the_call(self, monkeypatch):
        openai = pytest.importorskip("openai")
        if int(openai.__version__.split(".")[0]) < 1:
            pytest.skip("pre-1.0 SDK still has openai.Image")

        monkeypatch.setenv("OPENAI_API_KEY", NOT_A_TOKEN)

        with pytest.raises(RuntimeError) as raised:
            await run("api.openai.image", {"prompt": "a cat"})

        assert "no longer supported" in str(raised.value)
