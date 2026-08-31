# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""What robotics, vision and agent modules may claim, and the line that earns it.

Three families, one temptation each, and the tests are grouped by the temptation
rather than by the module:

* `TestAModelsOpinionIsNeverAMeasurement` -- vision.compare returns
  `recommendation: 'PASS'` from a visual regression gate that compares no
  pixels, and vision.analyze returns confident prose about a screenshot it may
  not have looked at. If either ever climbs to `observed`, these fail.

* `TestAnAgentSayingItIsDoneIsNotEvidence` -- agent.autonomous decides
  `goal_achieved` by scanning the model's own text for the word "finished".
  There is a test here that feeds it "I have not finished this yet" and pins
  both halves of the truth: the field says True, and the rung does not move.

* `TestTheLoopWasCutOff` -- agent.tool_use returns `ok: True` and a sentence
  that reads like an answer when max_iterations runs out, after N real tools
  have already changed real things. That path is `indeterminate` and the tool
  count travels with it.

* `TestRoboticsDeclaresAndDoesNotDispatch` -- the one finding that could not be
  fixed from this repository, pinned so it cannot quietly stop being true.

Every provider call is stubbed. Not for speed: a test that needs an API key is a
test that stops running, and these are the assertions that have to survive the
next person who thinks `observed` reads better on a dashboard.
"""

import asyncio
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import core.utils as core_utils
from core.engine.outcome import LADDER, Outcome, read_envelope, rung_index
from core.modules.registry import ModuleRegistry


def ensure_modules_loaded():
    from core.modules import atomic  # noqa: F401
    from core.modules import composite  # noqa: F401


ensure_modules_loaded()


GROUP = [
    "vision.analyze",
    "vision.compare",
    "agent.autonomous",
    "agent.chain",
    "agent.tool_use",
]


async def run(module_id, params, context=None):
    """Execute a module the way the engine does and return its result dict."""
    module = ModuleRegistry.get(module_id)
    return await module(params, context or {}).execute()


def envelope_of(result):
    """The envelope, read from wherever `_apply_outcome_contract` would read it.

    `data` when the module returns the wrapped shape, the top level when it
    returns a flat dict -- both shapes appear in this group.
    """
    body = result.get("data") if isinstance(result.get("data"), dict) else result
    return read_envelope(body)


def rung_of(result):
    return envelope_of(result)["rung"]


def effect_kinds(result):
    return [effect["kind"] for effect in envelope_of(result)["effects"]]


def effect_named(result, kind):
    return next(e for e in envelope_of(result)["effects"] if e["kind"] == kind)


# ===========================================================================
# Stubs
# ===========================================================================


class _FakeHttpxResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def fake_httpx_client(payload=None, raises=None):
    """Stand-in for `core.utils.guarded_httpx_client`, used by both vision modules."""

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, **kwargs):
            if raises is not None:
                raise raises
            return _FakeHttpxResponse(payload)

    def factory(**kwargs):
        return _Client()

    return factory


def openai_completion(text, usage=None):
    body = {"choices": [{"message": {"content": text}}]}
    if usage is not None:
        body["usage"] = usage
    return body


class _FakeAiohttpResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status = status

    async def json(self):
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def fake_aiohttp_session(responses):
    """A ClientSession whose successive POSTs return `responses` in order."""

    class _Session:
        def __init__(self, *args, **kwargs):
            self._queue = list(responses)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        def post(self, url, **kwargs):
            return _FakeAiohttpResponse(self._queue.pop(0))

    return _Session


def openai_tool_call_turn(name, arguments, call_id="call_1"):
    return {
        "choices": [{
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": call_id,
                    "function": {"name": name, "arguments": json.dumps(arguments)},
                }],
            },
            "finish_reason": "tool_calls",
        }],
        "model": "gpt-4o",
    }


def openai_final_turn(text):
    return {
        "choices": [{
            "message": {"role": "assistant", "content": text},
            "finish_reason": "stop",
        }],
        "model": "gpt-4o",
    }


@pytest.fixture
def no_openai_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


# ===========================================================================
# vision.*  --  a model's opinion is never a measurement
# ===========================================================================


class TestAModelsOpinionIsNeverAMeasurement:
    def test_a_regression_pass_is_only_accepted(self, monkeypatch):
        """The one that matters. PASS on a visual gate that diffs no pixels."""
        monkeypatch.setattr(
            core_utils,
            "guarded_httpx_client",
            fake_httpx_client(openai_completion(json.dumps({
                "similarity_score": 99,
                "has_differences": False,
                "differences": [],
                "summary": "identical",
                "recommendation": "PASS",
            }))),
        )
        result = asyncio.run(run("vision.compare", {
            "image_before": "https://example.test/a.png",
            "image_after": "https://example.test/b.png",
            "api_key": "sk-test",
            "threshold": 5,
        }))

        assert result["recommendation"] == "PASS"
        assert rung_of(result) == Outcome.ACCEPTED.value
        # The verdict is labelled an opinion in the envelope, on the very path
        # where the payload looks most like a test result.
        assert "regression_verdict_is_model_opinion" in effect_kinds(result)

    def test_an_unparseable_answer_is_still_accepted(self, monkeypatch):
        """The peer answered. That it answered unreadably is a payload problem."""
        monkeypatch.setattr(
            core_utils,
            "guarded_httpx_client",
            fake_httpx_client(openai_completion("they look about the same to me")),
        )
        result = asyncio.run(run("vision.compare", {
            "image_before": "https://example.test/a.png",
            "image_after": "https://example.test/b.png",
            "api_key": "sk-test",
        }))

        assert result["recommendation"] == "REVIEW_NEEDED"
        assert result["similarity_score"] is None
        assert rung_of(result) == Outcome.ACCEPTED.value
        assert "vision_comparison_unparseable" in effect_kinds(result)

    def test_a_non_numeric_score_no_longer_becomes_an_api_error(self, monkeypatch):
        """A model returning "95" used to take the whole call down.

        `'95' >= 95` raises TypeError, the bare `except Exception` caught it, and
        a provider that answered correctly was reported as API_ERROR -- an
        unreachable-provider code for a reachable provider. It is now treated as
        the absent field it effectively is, and the envelope says the verdict
        came from a default rather than from a comparison.
        """
        monkeypatch.setattr(
            core_utils,
            "guarded_httpx_client",
            fake_httpx_client(openai_completion(json.dumps({
                "similarity_score": "95",
                "has_differences": False,
                "summary": "close enough",
            }))),
        )
        result = asyncio.run(run("vision.compare", {
            "image_before": "https://example.test/a.png",
            "image_after": "https://example.test/b.png",
            "api_key": "sk-test",
        }))

        assert result["ok"] is True
        assert result.get("error_code") is None
        assert rung_of(result) == Outcome.ACCEPTED.value
        assert "similarity_score_defaulted" in effect_kinds(result)

    def test_a_completion_about_an_image_is_accepted_not_observed(self, monkeypatch):
        monkeypatch.setattr(
            core_utils,
            "guarded_httpx_client",
            fake_httpx_client(openai_completion("No bugs found.", usage={"total_tokens": 812})),
        )
        result = asyncio.run(run("vision.analyze", {
            "image": "https://example.test/form.png",
            "prompt": "find visual bugs",
            "analysis_type": "bug_detection",
            "output_format": "text",
            "api_key": "sk-test",
        }))

        assert result["analysis"] == "No bugs found."
        assert rung_of(result) == Outcome.ACCEPTED.value
        billed = effect_named(result, "vision_tokens_billed_by_provider")
        assert billed["total_tokens"] == 812

    def test_a_missing_usage_block_is_not_a_billed_zero(self, monkeypatch):
        """`tokens_used` of 0 has two meanings; only the envelope keeps them apart.

        The same shape as `file.write`'s `bytes_written`: a number that reads
        identically whether the effect happened or not.
        """
        monkeypatch.setattr(
            core_utils,
            "guarded_httpx_client",
            fake_httpx_client(openai_completion("looks fine")),
        )
        result = asyncio.run(run("vision.analyze", {
            "image": "https://example.test/a.png",
            "prompt": "describe",
            "output_format": "text",
            "api_key": "sk-test",
        }))

        assert result["tokens_used"] == 0
        assert rung_of(result) == Outcome.ACCEPTED.value
        assert "vision_tokens_not_reported" in effect_kinds(result)
        assert "vision_tokens_billed_by_provider" not in effect_kinds(result)


class TestNothingSentIsNotTheSameAsNothingKnown:
    def test_a_missing_key_never_reached_the_provider(self, no_openai_key):
        result = asyncio.run(run("vision.analyze", {
            "image": "https://example.test/a.png",
            "prompt": "describe",
        }))
        assert result["error_code"] == "MISSING_API_KEY"
        assert rung_of(result) == Outcome.FAILED.value
        assert "vision_request_not_sent" in effect_kinds(result)

    def test_an_unreadable_image_never_reached_the_provider(self, tmp_path, monkeypatch):
        # Inside the sandbox root, so the path guard lets it through and the
        # module reaches its own "file not found" branch -- which is the one
        # under test. A path OUTSIDE the root raises PathTraversalError out of
        # `_prepare_image` before any of this, and an exception carries no
        # envelope; that is a different path and not this claim.
        monkeypatch.setenv("FLYTO_SANDBOX_DIR", str(tmp_path))
        result = asyncio.run(run("vision.analyze", {
            "image": str(tmp_path / "absent.png"),
            "prompt": "describe",
            "api_key": "sk-test",
        }))
        assert result["error_code"] == "IMAGE_ERROR"
        assert rung_of(result) == Outcome.FAILED.value

    def test_a_provider_error_object_is_failed_not_indeterminate(self, monkeypatch):
        """An error body removes exactly the uncertainty a timeout has."""
        monkeypatch.setattr(
            core_utils,
            "guarded_httpx_client",
            fake_httpx_client({"error": {"message": "model not found"}}),
        )
        result = asyncio.run(run("vision.analyze", {
            "image": "https://example.test/a.png",
            "prompt": "describe",
            "api_key": "sk-test",
        }))
        assert result["error_code"] == "OPENAI_ERROR"
        assert rung_of(result) == Outcome.FAILED.value
        assert effect_named(result, "vision_provider_error")["provider_message"] == (
            "model not found"
        )

    def test_a_connection_that_never_came_up_is_failed(self, monkeypatch):
        import httpx

        monkeypatch.setattr(
            core_utils,
            "guarded_httpx_client",
            fake_httpx_client(raises=httpx.ConnectError("refused")),
        )
        result = asyncio.run(run("vision.analyze", {
            "image": "https://example.test/a.png",
            "prompt": "describe",
            "api_key": "sk-test",
        }))
        assert rung_of(result) == Outcome.FAILED.value

    def test_a_read_timeout_is_indeterminate(self, monkeypatch):
        """The textbook one: it may have been received, processed and billed."""
        import httpx

        monkeypatch.setattr(
            core_utils,
            "guarded_httpx_client",
            fake_httpx_client(raises=httpx.ReadTimeout("timed out")),
        )
        result = asyncio.run(run("vision.compare", {
            "image_before": "https://example.test/a.png",
            "image_after": "https://example.test/b.png",
            "api_key": "sk-test",
        }))
        assert rung_of(result) == Outcome.INDETERMINATE.value

    def test_the_ssrf_guard_refusing_is_failed(self, monkeypatch):
        """The guard runs in the transport, so no bytes reach the peer."""
        monkeypatch.setattr(
            core_utils,
            "guarded_httpx_client",
            fake_httpx_client(raises=core_utils.SSRFError("blocked")),
        )
        result = asyncio.run(run("vision.analyze", {
            "image": "https://example.test/a.png",
            "prompt": "describe",
            "api_key": "sk-test",
        }))
        assert rung_of(result) == Outcome.FAILED.value


# ===========================================================================
# agent.tool_use  --  the loop that actually changes things
# ===========================================================================


class TestTheLoopWasCutOff:
    def test_a_final_answer_is_accepted_and_carries_the_tool_count(self, monkeypatch):
        import core.modules.third_party.ai.agents.tool_use as tool_use_module

        async def fake_execute_tool(name, args, ctx):
            return {"ok": True, "data": {"wrote": args}}

        monkeypatch.setattr(tool_use_module, "execute_tool", fake_execute_tool)
        monkeypatch.setattr(
            tool_use_module.aiohttp,
            "ClientSession",
            fake_aiohttp_session([
                openai_tool_call_turn("file--write", {"path": "/tmp/x"}),
                openai_final_turn("Wrote the file."),
            ]),
        )

        result = asyncio.run(run("agent.tool_use", {
            "prompt": "write a file",
            "tools": [{"name": "file--write", "description": "write"}],
            "api_key": "sk-test",
            "max_iterations": 5,
        }))

        assert rung_of(result) == Outcome.ACCEPTED.value
        tally = effect_named(result, "tool_outcomes_not_propagated")
        assert tally["tool_calls"] == 1
        assert tally["tool_calls_that_raised"] == 0

    def test_max_iterations_is_indeterminate_not_a_result(self, monkeypatch):
        """`ok` is True and `result` reads like an answer. The rung must disagree.

        Three tools already ran. Nothing in this module can say what they left
        behind, which is the definition of indeterminate -- and it is why
        `accepted` here would turn "we stopped counting" into "it is done".
        """
        import core.modules.third_party.ai.agents.tool_use as tool_use_module

        async def fake_execute_tool(name, args, ctx):
            return {"ok": True, "data": {}}

        monkeypatch.setattr(tool_use_module, "execute_tool", fake_execute_tool)
        monkeypatch.setattr(
            tool_use_module.aiohttp,
            "ClientSession",
            fake_aiohttp_session([
                openai_tool_call_turn("file--write", {"n": i}) for i in range(3)
            ]),
        )

        result = asyncio.run(run("agent.tool_use", {
            "prompt": "keep going",
            "tools": [{"name": "file--write", "description": "write"}],
            "api_key": "sk-test",
            "max_iterations": 3,
        }))

        assert result["ok"] is True
        assert "maximum iterations" in result["data"]["result"]
        assert rung_of(result) == Outcome.INDETERMINATE.value
        assert effect_named(result, "tool_outcomes_not_propagated")["tool_calls"] == 3

    def test_a_tool_that_raised_is_counted_separately_from_one_that_said_no(
        self, monkeypatch
    ):
        import core.modules.third_party.ai.agents.tool_use as tool_use_module

        calls = {"n": 0}

        async def fake_execute_tool(name, args, ctx):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("boom")
            return {"ok": False, "error": "nope"}

        monkeypatch.setattr(tool_use_module, "execute_tool", fake_execute_tool)
        monkeypatch.setattr(
            tool_use_module.aiohttp,
            "ClientSession",
            fake_aiohttp_session([
                openai_tool_call_turn("file--write", {}, call_id="a"),
                openai_tool_call_turn("file--write", {}, call_id="b"),
                openai_final_turn("gave up"),
            ]),
        )

        result = asyncio.run(run("agent.tool_use", {
            "prompt": "try",
            "tools": [{"name": "file--write", "description": "write"}],
            "api_key": "sk-test",
            "max_iterations": 5,
        }))

        tally = effect_named(result, "tool_outcomes_not_propagated")
        assert tally["tool_calls"] == 2
        assert tally["tool_calls_that_raised"] == 1
        assert tally["tool_calls_reporting_not_ok"] == 1
        # Still ACCEPTED: the rung is about the completion, and the failing
        # tools are visible in the effect rather than smuggled into the rung.
        assert rung_of(result) == Outcome.ACCEPTED.value


# ===========================================================================
# agent.autonomous / agent.chain  --  saying it is done is not evidence
# ===========================================================================


def _patch_llm(monkeypatch, module_id, outputs):
    """Replace `_call_llm` on the registered class with a scripted sequence.

    The last scripted output repeats once the queue empties, so a test can
    script fewer turns than the agent's iteration ceiling without the stub
    becoming the thing that ends the loop.
    """
    cls = ModuleRegistry.get(module_id)
    queue = list(outputs)
    last = outputs[-1] if outputs else ""

    async def fake_call_llm(self, messages):
        return queue.pop(0) if queue else last

    monkeypatch.setattr(cls, "_call_llm", fake_call_llm, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    return cls


class TestAnAgentSayingItIsDoneIsNotEvidence:
    def test_goal_achieved_is_true_for_an_agent_reporting_failure(self, monkeypatch):
        """The bug, pinned: "I have not finished this yet" contains "finished".

        Both halves are asserted deliberately. The field is left as it was --
        swapping one heuristic for a slightly better one keeps its air of
        measurement -- and the rung is required not to move because of it.
        """
        _patch_llm(monkeypatch, "agent.autonomous", ["I have not finished this yet."])

        result = asyncio.run(run("agent.autonomous", {
            "goal": "do the thing",
            "max_iterations": 3,
        }))

        assert result["goal_achieved"] is True          # the field lies
        assert rung_of(result) == Outcome.ACCEPTED.value  # the rung does not
        assert "goal_achieved_is_a_substring_match" in effect_kinds(result)

    def test_the_rung_is_the_same_whether_the_agent_claimed_success_or_not(
        self, monkeypatch
    ):
        """N completions came back either way. Nothing else happened either way."""
        _patch_llm(monkeypatch, "agent.autonomous", ["Task achieved."])
        claimed = asyncio.run(run("agent.autonomous", {"goal": "g", "max_iterations": 2}))

        _patch_llm(monkeypatch, "agent.autonomous", ["still thinking", "still thinking"])
        exhausted = asyncio.run(run("agent.autonomous", {"goal": "g", "max_iterations": 2}))

        assert claimed["goal_achieved"] is True
        assert exhausted["goal_achieved"] is False
        assert rung_of(claimed) == rung_of(exhausted) == Outcome.ACCEPTED.value
        assert effect_named(claimed, "reasoning_completions_returned")["stopped_on"] == (
            "keyword_scan"
        )
        assert effect_named(exhausted, "reasoning_completions_returned")["stopped_on"] == (
            "iteration_ceiling"
        )

    def test_zero_iterations_is_not_an_acceptance(self, monkeypatch):
        """`max_iterations: 0` returns the success shape having asked nobody.

        The schema says `min: 1` and nothing enforces it -- this class does not
        opt into `auto_validate_schema` -- so `range(0)` is reachable and yields
        `result: ""`, which reads downstream like an empty answer. ACCEPTED
        there would claim a provider acknowledged a request that was never
        built.
        """
        _patch_llm(monkeypatch, "agent.autonomous", ["never called"])

        result = asyncio.run(run("agent.autonomous", {
            "goal": "do the thing",
            "max_iterations": 0,
        }))

        assert result["iterations"] == 0
        assert result["result"] == ""
        assert rung_of(result) == Outcome.FAILED.value
        assert "agent_loop_never_ran" in effect_kinds(result)

    def test_a_chain_counts_completions_not_the_steps_it_was_handed(self, monkeypatch):
        _patch_llm(monkeypatch, "agent.chain", ["one", "two"])

        result = asyncio.run(run("agent.chain", {
            "input": "seed",
            "chain_steps": ["a {input}", "b {previous}"],
        }))

        assert rung_of(result) == Outcome.ACCEPTED.value
        returned = effect_named(result, "chain_completions_returned")
        assert returned["steps_requested"] == 2
        assert returned["completions_with_text"] == 2

    def test_a_blank_step_is_named_and_still_accepted(self, monkeypatch):
        """The provider answered; it answered with nothing. Two different facts."""
        _patch_llm(monkeypatch, "agent.chain", ["one", ""])

        result = asyncio.run(run("agent.chain", {
            "input": "seed",
            "chain_steps": ["a {input}", "b {previous}"],
        }))

        assert rung_of(result) == Outcome.ACCEPTED.value
        assert "chain_step_returned_no_text" in effect_kinds(result)
        assert effect_named(result, "chain_step_returned_no_text")["blank_completions"] == 1


# ===========================================================================
# The ceiling for the whole group
# ===========================================================================


class TestNothingInThisGroupObservesAnything:
    """Not one module here measures the world. The next person must delete a test.

    Every rung in this group comes from a provider's response or from a guard
    that returned before one. There is no read-back, no stat, no second look at
    anything the effect touched -- so `observed` and `verified` are unreachable,
    and a module that starts claiming either has stopped describing what its
    code does.
    """

    @pytest.mark.parametrize("module_id", GROUP)
    def test_no_module_declares_a_postcondition_it_cannot_evaluate(self, module_id):
        metadata = ModuleRegistry.get_metadata(module_id) or {}
        assert not metadata.get("postcondition"), (
            f"{module_id} declares a postcondition. Nothing in this group "
            f"evaluates a predicate; a declaration without one moves the same "
            f"guess a rung higher and calls it proof."
        )

    @pytest.mark.parametrize("module_id", GROUP)
    def test_no_module_builds_an_envelope_above_accepted(self, module_id):
        """Read out of the source, so it fails on the line that adds the claim."""
        import ast
        import inspect

        source_file = inspect.getsourcefile(ModuleRegistry.get(module_id))
        tree = ast.parse(Path(source_file).read_text(encoding="utf-8"))

        claimed = {
            node.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "Outcome"
        }
        too_high = {
            name for name in claimed
            if rung_index(getattr(Outcome, name, None)) is not None
            and rung_index(getattr(Outcome, name)) > rung_index(Outcome.ACCEPTED)
        }
        assert not too_high, (
            f"{module_id} names {sorted(too_high)}. Nothing in this file "
            f"measures the world; name the line that would earn it or claim lower."
        )

    def test_accepted_really_is_below_observed(self):
        """The ceiling above means nothing if the ladder stops agreeing."""
        assert rung_index(Outcome.ACCEPTED) < rung_index(Outcome.OBSERVED)
        assert LADDER[-1] is Outcome.VERIFIED


# ===========================================================================
# robotics.*  --  the finding this repository cannot fix
# ===========================================================================


class TestRoboticsDeclaresAndDoesNotDispatch:
    """A step that builds a plan is stamped `dispatched` by the engine default.

    `robotics.move` is registered from the installed `flyto_modules_robotics`
    package, so it is out of this tree's reach. It is pinned here anyway,
    because the contradiction is sharp enough to be worth catching if anyone
    changes either side: the module's own payload says `dispatched: False` in so
    many words, and `default_for` -- reached only via `requires_credentials`,
    since `robotics` is not in SIDE_EFFECT_CATEGORIES -- stamps `dispatched`
    beside it.
    """

    @pytest.fixture(autouse=True)
    def _skip_without_the_extension(self):
        # `has`, not `get`: `ModuleRegistry.get` RAISES ValueError for a module
        # it does not hold (`registry/core.py:675`) and never returns None, so
        # the guard written against a None fired as an ERROR instead of a skip
        # whenever the registry did not hold `robotics.move` -- which is what
        # `tests/core/test_plugin_policy_scope.py` leaves behind when it runs
        # first in the same process.
        if not ModuleRegistry.has("robotics.move"):
            pytest.skip("flyto_modules_robotics is not installed")

    def test_the_module_says_it_did_not_dispatch(self):
        module = ModuleRegistry.get("robotics.move")
        payload = asyncio.run(
            module({"distance_m": 0.5}, {"resource_id": "robot-1"}).execute()
        )
        assert payload["dispatched"] is False
        assert read_envelope(payload) is None, (
            "robotics.move now reports an outcome of its own; take it off "
            "UNDECLARED and delete this test."
        )

    def test_the_engine_stamps_a_rung_the_step_did_not_reach(self):
        from core.engine.step_executor.executor import _apply_outcome_contract

        module = ModuleRegistry.get("robotics.move")
        instance = module({"distance_m": 0.5}, {"resource_id": "robot-1"})
        stamped = _apply_outcome_contract(instance, asyncio.run(instance.execute()))

        assert stamped["dispatched"] is False
        assert stamped["outcome"]["rung"] == Outcome.DISPATCHED.value, (
            "The default changed. If robotics steps now get no rung, that is the "
            "fix this test was written to wait for -- delete it."
        )
