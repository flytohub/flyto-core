# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""What the ai/llm modules are entitled to claim, and the line that earns it.

The whole group shares one temptation and these tests exist to keep saying no to
it: a completion coming back feels like evidence. It is not evidence about the
world. It is the provider describing its own work, which is `accepted` and never
`observed`, no matter how confident the text is or how much it cost.

So the assertions come in two shapes:

* the ceiling ones -- `TestACompletionIsNeverAnObservation` -- which fail if any
  module in the group ever starts claiming `observed` off a returned completion,
  a token count, or a model's assertion that it finished the task;
* the earned ones -- `TestCodeFixReadsTheFileBack`, `TestRedisMemory` -- where a
  real measurement exists, is made in the test independently, and the rung is
  checked against it.

Everything network-facing is stubbed. Not for speed: a test that needs an API key
to run is a test that stops running, and these are the assertions that have to
survive the next person who decides `observed` reads better on a dashboard.
"""

import asyncio
import json
import sys
import types
from contextlib import suppress
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import core.modules.atomic.ai.embed as embed_module
import core.modules.atomic.ai.extract as extract_module
import core.modules.atomic.ai.vision_analyze as vision_module
import core.modules.atomic.llm.chat as chat_module
import core.modules.atomic.llm.code_fix as code_fix_module
from core.engine.outcome import ClaimBy, Outcome, ceiling_for, read_envelope
from core.modules.registry import ModuleRegistry


def ensure_modules_loaded():
    from core.modules import atomic  # noqa: F401
    with suppress(Exception):
        from core.modules import third_party  # noqa: F401


ensure_modules_loaded()


async def run(module_id, params, context=None):
    """Execute a module the way the engine does and return its result dict."""
    module = ModuleRegistry.get(module_id)
    return await module(params, context or {}).execute()


def envelope_of(result):
    """The envelope, read from wherever `_apply_outcome_contract` would read it.

    `data` when the module returns the wrapped shape, the top level when it
    returns a flat dict -- the two shapes this group actually uses.
    """
    body = result.get("data") if isinstance(result.get("data"), dict) else result
    return read_envelope(body)


def effect_kinds(found):
    return [effect["kind"] for effect in found["effects"]]


def effect_named(found, kind):
    return next(effect for effect in found["effects"] if effect["kind"] == kind)


# ===========================================================================
# Stubs. No key, no socket, no drift with whatever is installed.
# ===========================================================================


class _FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status = status
        self.headers = {"Content-Type": "image/png"}

    async def json(self):
        return self._payload

    async def read(self):
        return b"\x89PNG-not-really"

    async def text(self):
        return json.dumps(self._payload)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeSession:
    """Enough of aiohttp.ClientSession for the four modules that use one."""

    def __init__(self, payload, status=200):
        self._payload = payload
        self._status = status

    def post(self, *args, **kwargs):
        return _FakeResponse(self._payload, self._status)

    def get(self, *args, **kwargs):
        return _FakeResponse(self._payload, self._status)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def fake_session_factory(payload, status=200):
    return lambda *args, **kwargs: _FakeSession(payload, status)


class FakeChatModel:
    """A ChatModel that answers however the test says, without a provider."""

    provider = "fake"
    model_name = "fake-1"

    def __init__(self, responses=None, raises=None):
        self._responses = list(responses or [])
        self._raises = raises
        self.calls = 0

    async def chat(self, messages, **kwargs):
        self.calls += 1
        if self._raises is not None:
            raise self._raises
        if len(self._responses) > 1:
            return self._responses.pop(0)
        return self._responses[0]


class FakeChatWrapper:
    """Stands in for the `llm.chat` module class: called, then `.execute()`d."""

    def __init__(self, result):
        self._result = result
        self.params = None

    def __call__(self, params, context):
        self.params = params
        return self

    async def execute(self):
        return self._result


def chat_response(**kwargs):
    from core.modules.atomic.llm._interfaces import ChatResponse
    return ChatResponse(**kwargs)


def tool_call(name="file--write", arguments='{"path": "x"}'):
    from core.modules.atomic.llm._interfaces import ToolCall
    return ToolCall(id="call_1", name=name, arguments=arguments)


def agent_context(chat_model, **extra):
    return {"inputs": {"model": {"__data_type__": "ai_model", "chat_model": chat_model}}, **extra}


OPENAI_COMPLETION = {
    "choices": [{"message": {"content": "the answer"}, "finish_reason": "stop"}],
    "usage": {"total_tokens": 42},
    "model": "gpt-4o",
}


# ===========================================================================
# The ceiling. The assertion the whole group exists to hold.
# ===========================================================================


class TestACompletionIsNeverAnObservation:
    """`accepted` is the top of the happy path for every provider call here.

    One test per module rather than a loop, so a failure names the module that
    started overclaiming instead of a parametrised id.
    """

    @pytest.mark.asyncio
    async def test_llm_chat_stops_at_accepted(self, monkeypatch):
        async def fake_call(*args, **kwargs):
            return {"ok": True, "response": "hi", "tokens_used": 9, "finish_reason": "stop"}

        monkeypatch.setattr(chat_module, "_call_openai", fake_call)

        found = envelope_of(await run("llm.chat", {"prompt": "hi", "api_key": "k"}))

        assert found["rung"] == Outcome.ACCEPTED.value
        assert found["rung"] != Outcome.OBSERVED.value

    @pytest.mark.asyncio
    async def test_ai_extract_stops_at_accepted(self, monkeypatch):
        payload = {
            "choices": [{"message": {"content": '{"name": "Ada"}'}}],
            "model": "gpt-4o-mini",
        }
        monkeypatch.setattr(
            extract_module.aiohttp, "ClientSession", fake_session_factory(payload)
        )

        result = await run(
            "ai.extract",
            {"text": "Ada Lovelace", "schema": {"type": "object"}, "api_key": "k"},
        )

        assert result["data"]["extracted"] == {"name": "Ada"}
        assert envelope_of(result)["rung"] == Outcome.ACCEPTED.value

    @pytest.mark.asyncio
    async def test_ai_vision_analyze_stops_at_accepted(self, monkeypatch):
        monkeypatch.setattr(
            vision_module, "guarded_client_session", fake_session_factory(OPENAI_COMPLETION)
        )

        result = await run(
            "ai.vision.analyze",
            {"image_url": "https://example.com/a.png", "api_key": "k"},
        )

        assert envelope_of(result)["rung"] == Outcome.ACCEPTED.value

    @pytest.mark.asyncio
    async def test_ai_embed_stops_at_accepted(self, monkeypatch):
        payload = {
            "data": [{"index": 0, "embedding": [0.1, 0.2, 0.3]}],
            "usage": {"total_tokens": 5},
            "model": "text-embedding-3-small",
        }
        monkeypatch.setattr(
            embed_module.aiohttp, "ClientSession", fake_session_factory(payload)
        )

        result = await run("ai.embed", {"text": "hello", "api_key": "k"})

        assert result["data"]["dimensions"] == 3
        assert envelope_of(result)["rung"] == Outcome.ACCEPTED.value

    @pytest.mark.asyncio
    async def test_local_ollama_stops_at_accepted_even_though_it_is_our_own_box(
        self, monkeypatch
    ):
        """Local changes who gets paid. It does not change who is reporting."""
        import core.modules.third_party.ai.local_ollama as ollama_module

        payload = {
            "message": {"content": "hi"},
            "model": "llama2",
            "eval_count": 7,
            "prompt_eval_count": 3,
        }
        monkeypatch.setattr(
            ollama_module, "guarded_client_session", fake_session_factory(payload)
        )

        result = await run("ai.local_ollama.chat", {"prompt": "hi"})

        assert result["response"] == "hi"
        assert envelope_of(result)["rung"] == Outcome.ACCEPTED.value

    @pytest.mark.asyncio
    async def test_the_agent_saying_it_finished_is_still_only_accepted(self):
        """The most load-bearing assertion in the file.

        `llm.agent` is the module whose output most looks like a verdict. A
        final answer is the model's ASSERTION that the task is done, and this
        module checks nothing about it.
        """
        model = FakeChatModel([chat_response(content="all done", tokens_used=11)])

        result = await run(
            "llm.agent", {"task": "do the thing"}, agent_context(model)
        )

        assert result["data"]["result"] == "all done"
        assert envelope_of(result)["rung"] == Outcome.ACCEPTED.value

    @pytest.mark.asyncio
    async def test_no_module_in_the_group_declares_a_postcondition(self):
        """VERIFIED is unreachable here, and that is the design, not an omission.

        Nothing in this group evaluates a predicate about the world, so nothing
        may declare one -- and with none declared `ceiling_for` caps the group
        at OBSERVED, which only `llm.code_fix` and `ai.memory.redis` can reach.
        """
        for module_id in (
            "llm.chat", "llm.agent", "llm.code_fix", "ai.embed", "ai.extract",
            "ai.vision.analyze", "ai.memory.redis", "ai.local_ollama.chat",
        ):
            metadata = ModuleRegistry.get_metadata(module_id)
            assert metadata["postcondition"] is None, module_id
            assert ceiling_for(metadata["postcondition"]) is Outcome.OBSERVED


class TestTheTokenCountIsNotEvidence:
    """`tokens_used` is this group's `bytes_written`: the peer's own number."""

    @pytest.mark.asyncio
    async def test_it_is_labelled_as_the_provider_s_own_billing_figure(
        self, monkeypatch
    ):
        async def fake_call(*args, **kwargs):
            return {"ok": True, "response": "hi", "tokens_used": 1234, "finish_reason": "stop"}

        monkeypatch.setattr(chat_module, "_call_openai", fake_call)

        found = envelope_of(await run("llm.chat", {"prompt": "hi", "api_key": "k"}))
        completion = effect_named(found, "completion_returned")

        assert completion["tokens_billed_by_provider"] == 1234
        assert completion["measured_by"] == "the provider's own JSON response body"
        assert "not of anything in the world" in completion["detail"]

    @pytest.mark.asyncio
    async def test_a_truncated_answer_is_recorded_rather_than_hidden(
        self, monkeypatch
    ):
        async def fake_call(*args, **kwargs):
            return {"ok": True, "response": "half an ans", "tokens_used": 2000,
                    "finish_reason": "length"}

        monkeypatch.setattr(chat_module, "_call_openai", fake_call)

        found = envelope_of(await run("llm.chat", {"prompt": "hi", "api_key": "k"}))

        assert "completion_truncated" in effect_kinds(found)
        # Still ACCEPTED: the peer answered. The fragment is a fact about the
        # answer, not about how far the effect was followed.
        assert found["rung"] == Outcome.ACCEPTED.value


# ===========================================================================
# Off the ladder: who said it, and whether we can tell
# ===========================================================================


class TestAGuardThatRefusesIsFailedNotIndeterminate:
    """Nothing left the process, and we know it. That certainty is the point."""

    @pytest.mark.asyncio
    async def test_llm_chat_missing_key(self):
        result = await run("llm.chat", {"prompt": "hi", "provider": "openai"})
        found = envelope_of(result)

        assert result["error_code"] == "MISSING_API_KEY"
        assert found["rung"] == Outcome.FAILED.value
        assert effect_named(found, "request_not_sent")["reason"] == "MISSING_API_KEY"

    @pytest.mark.asyncio
    async def test_llm_chat_unknown_provider(self):
        found = envelope_of(
            await run("llm.chat", {"prompt": "hi", "provider": "wat", "api_key": "k"})
        )

        assert found["rung"] == Outcome.FAILED.value

    @pytest.mark.asyncio
    async def test_llm_chat_ssrf_blocked_base_url(self):
        result = await run(
            "llm.chat",
            {"prompt": "hi", "api_key": "k", "base_url": "http://169.254.169.254/v1"},
        )

        assert result["error_code"] == "SSRF_BLOCKED"
        assert envelope_of(result)["rung"] == Outcome.FAILED.value

    @pytest.mark.asyncio
    async def test_the_agent_refuses_before_the_first_call(self):
        result = await run("llm.agent", {"task": ""}, {})
        found = envelope_of(result)

        assert result["error_code"] == "MISSING_TASK"
        assert found["rung"] == Outcome.FAILED.value
        assert effect_named(found, "agent_not_started")["reason"] == "MISSING_TASK"

    @pytest.mark.asyncio
    async def test_the_agent_recursion_guard(self):
        result = await run("llm.agent", {"task": "x"}, {"_agent_depth": 3})

        assert result["error_code"] == "RECURSION_LIMIT"
        assert envelope_of(result)["rung"] == Outcome.FAILED.value

    @pytest.mark.asyncio
    async def test_code_fix_without_a_key_wrote_nothing_and_says_so(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        result = await run(
            "llm.code_fix", {"issues": ["broken"], "source_files": ["a.py"]}
        )
        found = envelope_of(result)

        assert result["error_code"] == "MISSING_API_KEY"
        assert found["rung"] == Outcome.FAILED.value
        assert "nothing_requested_or_written" in effect_kinds(found)


class TestAPeerThatNeverAnsweredIsIndeterminate:
    """The textbook one. A severed channel is not a negative answer."""

    @pytest.mark.asyncio
    async def test_a_transport_failure_in_llm_chat(self, monkeypatch):
        async def explode(*args, **kwargs):
            raise TimeoutError("read timed out")

        monkeypatch.setattr(chat_module, "_call_openai", explode)

        result = await run("llm.chat", {"prompt": "hi", "api_key": "k"})
        found = envelope_of(result)

        assert result["error_code"] == "API_ERROR"
        assert found["rung"] == Outcome.INDETERMINATE.value
        assert found["rung"] != Outcome.FAILED.value
        assert effect_named(found, "no_answer_from_provider")["error_type"] == "TimeoutError"

    @pytest.mark.asyncio
    async def test_ollama_swallows_its_transport_error_and_still_says_indeterminate(self):
        """The one provider whose failure becomes a result instead of a raise.

        Without an envelope built inside `_call_ollama`, `llm_chat` would return
        this dict as-is and it would carry nothing at all.
        """
        found = read_envelope(
            await chat_module._call_ollama([], "llama2", 0.7, 10, "http://127.0.0.1:1")
        )

        assert found["rung"] == Outcome.INDETERMINATE.value

    @pytest.mark.asyncio
    async def test_a_provider_that_answered_with_an_error_is_failed_instead(self):
        """We are not guessing here: the peer gave a definite negative."""
        found = read_envelope(
            {"outcome": chat_module._provider_refused("openai", "invalid_api_key")}
        )

        assert found["rung"] == Outcome.FAILED.value
        assert effect_named(found, "provider_error")["message"] == "invalid_api_key"

    @pytest.mark.asyncio
    async def test_llm_chat_passes_the_helper_envelope_through_untouched(
        self, monkeypatch
    ):
        """The helper knows which of the two it was. The caller must not re-decide."""
        async def refused(*args, **kwargs):
            return {
                "ok": False,
                "error": "invalid_api_key",
                "outcome": chat_module._provider_refused("openai", "invalid_api_key"),
            }

        monkeypatch.setattr(chat_module, "_call_openai", refused)

        found = envelope_of(await run("llm.chat", {"prompt": "hi", "api_key": "k"}))

        assert found["rung"] == Outcome.FAILED.value
        assert "provider_error" in effect_kinds(found)


class TestTheCallerSFormatContract:
    """`response_format='json'` is somebody else's expectation, so it can fail."""

    @pytest.mark.asyncio
    async def test_prose_where_json_was_asked_for_is_failed_by_the_caller(
        self, monkeypatch
    ):
        async def prose(*args, **kwargs):
            return {"ok": True, "response": "Sure! Here is your answer.",
                    "tokens_used": 5, "finish_reason": "stop"}

        monkeypatch.setattr(chat_module, "_call_openai", prose)

        result = await run(
            "llm.chat",
            {"prompt": "hi", "api_key": "k", "response_format": "json"},
        )
        found = envelope_of(result)

        assert found["rung"] == Outcome.FAILED.value
        assert found["claim_by"] == ClaimBy.CALLER.value
        assert "parses as JSON" in found["postcondition"]
        # The step still succeeded and the raw text is still there. `ok` is
        # about the call; the rung is about the contract.
        assert result["ok"] is True
        assert result["parsed"] is None

    @pytest.mark.asyncio
    async def test_json_that_parses_does_not_climb_the_ladder(self, monkeypatch):
        """The asymmetry, pinned.

        A caller contract that breaks is FAILED -- off the ladder, so nothing
        was climbed. A caller contract that holds is still only ACCEPTED,
        because JSON-ness is a fact about the peer's own answer.
        """
        async def as_json(*args, **kwargs):
            return {"ok": True, "response": '{"decision": "yes"}',
                    "tokens_used": 5, "finish_reason": "stop"}

        monkeypatch.setattr(chat_module, "_call_openai", as_json)

        result = await run(
            "llm.chat",
            {"prompt": "hi", "api_key": "k", "response_format": "json"},
        )
        found = envelope_of(result)

        assert result["parsed"] == {"decision": "yes"}
        assert found["rung"] == Outcome.ACCEPTED.value
        assert found["rung"] != Outcome.VERIFIED.value
        assert "response_format_met" in effect_kinds(found)

    @pytest.mark.asyncio
    async def test_text_mode_never_evaluates_the_predicate_at_all(self, monkeypatch):
        async def prose(*args, **kwargs):
            return {"ok": True, "response": "not json", "tokens_used": 5,
                    "finish_reason": "stop"}

        monkeypatch.setattr(chat_module, "_call_openai", prose)

        found = envelope_of(await run("llm.chat", {"prompt": "hi", "api_key": "k"}))

        assert found["rung"] == Outcome.ACCEPTED.value
        assert "response_format_unmet" not in effect_kinds(found)


class TestEmbeddingsAreHeldToWhatTheCallerAskedFor:
    @pytest.mark.asyncio
    async def test_a_vector_per_text_is_the_contract(self, monkeypatch):
        """Two texts in, one vector out: every downstream index is now wrong."""
        payload = {
            "data": [{"index": 0, "embedding": [0.1, 0.2]}],
            "usage": {"total_tokens": 5},
            "model": "text-embedding-3-small",
        }
        monkeypatch.setattr(
            embed_module.aiohttp, "ClientSession", fake_session_factory(payload)
        )

        found = envelope_of(
            await run("ai.embed", {"text": ["a", "b"], "api_key": "k"})
        )

        assert found["rung"] == Outcome.FAILED.value
        assert found["claim_by"] == ClaimBy.CALLER.value
        unmet = effect_named(found, "embedding_count_unmet")
        assert (unmet["expected"], unmet["actual"]) == (2, 1)

    @pytest.mark.asyncio
    async def test_the_requested_width_is_the_other_contract(self, monkeypatch):
        payload = {
            "data": [{"index": 0, "embedding": [0.1, 0.2, 0.3]}],
            "usage": {"total_tokens": 5},
            "model": "text-embedding-3-small",
        }
        monkeypatch.setattr(
            embed_module.aiohttp, "ClientSession", fake_session_factory(payload)
        )

        found = envelope_of(
            await run("ai.embed", {"text": "a", "dimensions": 256, "api_key": "k"})
        )

        assert found["rung"] == Outcome.FAILED.value
        unmet = effect_named(found, "embedding_dimensions_unmet")
        assert (unmet["expected"], unmet["actual"]) == (256, 3)

    @pytest.mark.asyncio
    async def test_no_dimensions_asked_for_means_no_width_contract(self, monkeypatch):
        payload = {
            "data": [{"index": 0, "embedding": [0.1, 0.2, 0.3]}],
            "usage": {"total_tokens": 5},
            "model": "text-embedding-3-small",
        }
        monkeypatch.setattr(
            embed_module.aiohttp, "ClientSession", fake_session_factory(payload)
        )

        found = envelope_of(await run("ai.embed", {"text": "a", "api_key": "k"}))

        assert found["rung"] == Outcome.ACCEPTED.value
        assert "embedding_dimensions_unmet" not in effect_kinds(found)


class TestTheGapsAreWrittenDownRatherThanLeftBlank:
    @pytest.mark.asyncio
    async def test_ai_extract_says_the_schema_was_never_checked(self, monkeypatch):
        """The model returned JSON with none of the requested properties.

        Today that is a success with an empty-ish object. The envelope is what
        makes the missing validation visible instead of implied.
        """
        payload = {
            "choices": [{"message": {"content": '{"unrelated": 1}'}}],
            "model": "gpt-4o-mini",
        }
        monkeypatch.setattr(
            extract_module.aiohttp, "ClientSession", fake_session_factory(payload)
        )

        found = envelope_of(await run(
            "ai.extract",
            {
                "text": "x",
                "schema": {"type": "object", "properties": {"name": {"type": "string"}}},
                "api_key": "k",
            },
        ))
        gap = effect_named(found, "schema_not_evaluated")

        assert found["rung"] == Outcome.ACCEPTED.value
        assert gap["measured_by"] is None
        assert gap["extracted_keys"] == ["unrelated"]

    @pytest.mark.asyncio
    async def test_vision_says_nothing_compared_the_words_with_the_picture(
        self, monkeypatch
    ):
        monkeypatch.setattr(
            vision_module, "guarded_client_session", fake_session_factory(OPENAI_COMPLETION)
        )

        found = envelope_of(await run(
            "ai.vision.analyze",
            {"image_url": "https://example.com/a.png", "api_key": "k"},
        ))

        assert "Nothing here compares" in effect_named(found, "analysis_returned")["detail"]

    @pytest.mark.asyncio
    async def test_the_downloaded_image_is_labelled_as_an_input_measurement(
        self, monkeypatch
    ):
        """The one real measurement on this path, and it is about the INPUT.

        The anthropic branch fetches the image itself, so `len(body)` is a
        genuine measurement -- of what went in. Mislabelling it as evidence
        about the analysis is exactly the `bytes_written` mistake.
        """
        payload = {
            "content": [{"type": "text", "text": "a cat"}],
            "usage": {"input_tokens": 5, "output_tokens": 7},
            "model": "claude-sonnet-4",
        }
        monkeypatch.setattr(
            vision_module, "guarded_client_session", fake_session_factory(payload)
        )

        result = await run("ai.vision.analyze", {
            "image_url": "https://example.com/a.png",
            "provider": "anthropic", "api_key": "k",
        })
        found = envelope_of(result)
        fetched = effect_named(found, "image_fetched")

        assert result["data"]["analysis"] == "a cat"
        assert found["rung"] == Outcome.ACCEPTED.value
        assert fetched["image_bytes"] == len(b"\x89PNG-not-really")
        assert "of the INPUT, not of the effect" in fetched["detail"]

    @pytest.mark.asyncio
    async def test_the_agent_says_it_threw_the_tool_outcomes_away(self):
        """The sentence a consumer needs before trusting an agent's `accepted`."""
        model = FakeChatModel([chat_response(content="done", tokens_used=3)])

        found = envelope_of(
            await run("llm.agent", {"task": "x"}, agent_context(model))
        )
        gap = effect_named(found, "tool_outcomes_not_propagated")

        assert gap["tool_calls"] == 0
        assert "discards all of them" in gap["detail"]


# ===========================================================================
# The agent loop: where the rung stops being about a completion
# ===========================================================================


class TestAnAgentThatRanOutOfIterations:
    @pytest.mark.asyncio
    async def test_it_is_indeterminate_although_ok_is_true(self):
        """`ok: True` with a placeholder sentence for a result.

        This is the false green the rung exists to mark: downstream reads
        `result` and cannot tell it from an answer.
        """
        model = FakeChatModel([
            chat_response(content="", tokens_used=5, tool_calls=[tool_call()])
        ])

        result = await run(
            "llm.agent", {"task": "x", "max_iterations": 2}, agent_context(model)
        )
        found = envelope_of(result)

        assert result["ok"] is True
        assert result["data"]["warning"] == "max_iterations_reached"
        assert found["rung"] == Outcome.INDETERMINATE.value

    @pytest.mark.asyncio
    async def test_the_tool_calls_it_already_made_travel_with_it(self):
        """The reason it is not FAILED: some of the work demonstrably happened."""
        model = FakeChatModel([
            chat_response(content="", tokens_used=5, tool_calls=[tool_call()])
        ])

        found = envelope_of(await run(
            "llm.agent", {"task": "x", "max_iterations": 3}, agent_context(model)
        ))
        tools = effect_named(found, "tool_outcomes_not_propagated")

        assert tools["tool_calls"] == 3
        assert tools["tool_calls_reporting_error"] == 3   # no tool bound: each errored
        assert effect_named(found, "max_iterations_reached")["iterations"] == 3

    @pytest.mark.asyncio
    async def test_the_react_loop_reaches_the_same_answer(self):
        model = FakeChatModel([
            chat_response(content='Thought: hmm\nAction: nope({"a": 1})', tokens_used=2)
        ])

        result = await run(
            "llm.agent",
            {"task": "x", "agent_type": "react", "max_iterations": 2},
            agent_context(model),
        )

        assert envelope_of(result)["rung"] == Outcome.INDETERMINATE.value


class TestAnAgentWhoseModelStoppedAnswering:
    @pytest.mark.asyncio
    async def test_a_timeout_mid_run_is_indeterminate_not_failed(self):
        model = FakeChatModel(raises=asyncio.TimeoutError())

        result = await run("llm.agent", {"task": "x"}, agent_context(model))
        found = envelope_of(result)

        assert result["error_code"] == "LLM_TIMEOUT"
        assert found["rung"] == Outcome.INDETERMINATE.value
        assert "llm_call_timed_out" in effect_kinds(found)

    @pytest.mark.asyncio
    async def test_an_llm_error_carries_the_tool_count_that_makes_it_indeterminate(self):
        model = FakeChatModel(raises=RuntimeError("model exploded"))

        result = await run("llm.agent", {"task": "x"}, agent_context(model))
        found = envelope_of(result)

        assert result["error_code"] == "LLM_ERROR"
        assert found["rung"] == Outcome.INDETERMINATE.value
        assert "tool_outcomes_not_propagated" in effect_kinds(found)


# ===========================================================================
# Where a real measurement exists, and the rung that follows it
# ===========================================================================


class TestCodeFixReadsTheFileBack:
    """The only module in the group that changes anything outside a bill.

    `len(applied)` counts calls to `write_text` that returned. The read-back is
    what makes OBSERVED something other than a restatement of the input, exactly
    as `os.stat` does for `file.write`.
    """

    @pytest.fixture
    def source(self, sandboxed_tmp_path):
        path = sandboxed_tmp_path / "app.py"
        path.write_text("value = 1\n", encoding="utf-8")
        return path

    @pytest.fixture
    def model_returns_a_fix(self, monkeypatch):
        """Stub `llm.chat` in the shape `@register_module` actually leaves it.

        The exported name is a `FunctionModuleWrapper` CLASS constructed with
        `(params, context)` and driven with `.execute()`, not a coroutine --
        which is the bug this module had. The stub keeps that shape so the test
        exercises the real call convention rather than a friendlier invention.
        """
        def _install(fixes):
            monkeypatch.setattr(chat_module, "llm_chat", FakeChatWrapper({
                "ok": True,
                "response": json.dumps({"fixes": fixes}),
                "parsed": {"fixes": fixes},
                "model": "gpt-4o",
                "tokens_used": 10,
                "finish_reason": "stop",
            }))
        return _install

    def _fix(self, path):
        return {
            "file": str(path),
            "fix_type": "replace",
            "search": "value = 1",
            "replace": "value = 2",
        }

    @pytest.mark.asyncio
    async def test_an_applied_fix_that_reads_back_is_observed(
        self, source, model_returns_a_fix
    ):
        model_returns_a_fix([self._fix(source)])

        result = await run("llm.code_fix", {
            "issues": ["wrong value"], "source_files": [str(source)],
            "fix_mode": "apply", "backup": False, "api_key": "k",
        })
        found = envelope_of(result)

        # The test reads the file itself. If the read-back is ever removed and
        # the rung starts resting on len(applied), this is what catches it.
        assert source.read_text(encoding="utf-8") == "value = 2\n"
        assert found["rung"] == Outcome.OBSERVED.value
        assert found["claim_by"] == ClaimBy.INFERRED.value
        written = effect_named(found, "files_written")
        assert written["writes_attempted"] == 1 and written["read_back_matching"] == 1

    @pytest.mark.asyncio
    async def test_suggest_mode_writes_nothing_and_claims_nothing_about_disk(
        self, source, model_returns_a_fix
    ):
        model_returns_a_fix([self._fix(source)])

        result = await run("llm.code_fix", {
            "issues": ["wrong value"], "source_files": [str(source)],
            "api_key": "k",
        })
        found = envelope_of(result)

        assert source.read_text(encoding="utf-8") == "value = 1\n"
        assert found["rung"] == Outcome.ACCEPTED.value
        assert effect_named(found, "no_files_written")["fix_mode"] == "suggest"

    @pytest.mark.asyncio
    async def test_dry_run_appends_to_applied_without_touching_the_file(
        self, source, model_returns_a_fix
    ):
        """`applied` is populated under dry_run. The rung must not follow it."""
        model_returns_a_fix([self._fix(source)])

        result = await run("llm.code_fix", {
            "issues": ["wrong value"], "source_files": [str(source)],
            "fix_mode": "dry_run", "api_key": "k",
        })
        found = envelope_of(result)

        assert len(result["applied"]) == 1
        assert source.read_text(encoding="utf-8") == "value = 1\n"
        assert found["rung"] == Outcome.ACCEPTED.value

    @pytest.mark.asyncio
    async def test_a_read_back_that_cannot_answer_falls_to_indeterminate(
        self, source, model_returns_a_fix, monkeypatch
    ):
        """Losing the ability to look does not undo the write, or confirm it."""
        model_returns_a_fix([self._fix(source)])
        monkeypatch.setattr(
            code_fix_module, "_read_back",
            lambda path, expected: (None, "PermissionError: Permission denied"),
        )

        result = await run("llm.code_fix", {
            "issues": ["wrong value"], "source_files": [str(source)],
            "fix_mode": "apply", "backup": False, "api_key": "k",
        })
        found = envelope_of(result)

        assert source.read_text(encoding="utf-8") == "value = 2\n"   # it did land
        assert found["rung"] == Outcome.INDETERMINATE.value
        assert found["claim_by"] == ClaimBy.INFERRED.value
        assert effect_named(found, "write_not_confirmed")["count"] == 1

    @pytest.mark.asyncio
    async def test_content_that_disagrees_is_indeterminate_and_not_failed(
        self, source, model_returns_a_fix, monkeypatch
    ):
        """Nobody declared this equality, so a mismatch is our inference failing.

        A concurrent writer makes it false without our write having gone wrong,
        which is the split `outcome.py` draws between FAILED and INDETERMINATE.
        """
        model_returns_a_fix([self._fix(source)])
        monkeypatch.setattr(
            code_fix_module, "_read_back", lambda path, expected: (False, None)
        )

        found = envelope_of(await run("llm.code_fix", {
            "issues": ["wrong value"], "source_files": [str(source)],
            "fix_mode": "apply", "backup": False, "api_key": "k",
        }))

        assert found["rung"] == Outcome.INDETERMINATE.value
        assert found["rung"] != Outcome.FAILED.value

    @pytest.mark.asyncio
    async def test_a_write_that_landed_is_not_a_claim_that_the_code_is_correct(
        self, source, model_returns_a_fix
    ):
        """OBSERVED is about the bytes. Nothing here compiles or runs them."""
        model_returns_a_fix([{
            "file": str(source), "fix_type": "replace",
            "search": "value = 1", "replace": "value = (((",
        }])

        result = await run("llm.code_fix", {
            "issues": ["wrong value"], "source_files": [str(source)],
            "fix_mode": "apply", "backup": False, "api_key": "k",
        })
        found = envelope_of(result)

        assert source.read_text(encoding="utf-8") == "value = (((\n"
        assert found["rung"] == Outcome.OBSERVED.value
        assert "compiles, lints or runs" in effect_named(found, "files_written")["detail"]

    @pytest.mark.asyncio
    async def test_a_write_that_raised_is_not_a_file_left_alone(
        self, source, model_returns_a_fix, monkeypatch
    ):
        """The one that would have been ACCEPTED under a naive reading.

        `write_text` opens with 'w', so the file is truncated before the first
        byte goes out. A write that raises part-way leaves a damaged file, which
        is why a raised write lands in `writes` as unconfirmed rather than being
        counted as "nothing happened".
        """
        model_returns_a_fix([self._fix(source)])
        real_write_text = Path.write_text

        def explode(self, data, *args, **kwargs):
            if self.name == "app.py":
                raise OSError(28, "No space left on device")
            return real_write_text(self, data, *args, **kwargs)

        monkeypatch.setattr(Path, "write_text", explode)

        result = await run("llm.code_fix", {
            "issues": ["wrong value"], "source_files": [str(source)],
            "fix_mode": "apply", "backup": False, "api_key": "k",
        })
        found = envelope_of(result)

        assert len(result["failed"]) == 1 and result["applied"] == []
        assert found["rung"] == Outcome.INDETERMINATE.value
        assert found["rung"] != Outcome.ACCEPTED.value
        assert effect_named(found, "write_not_confirmed")["count"] == 1

    @pytest.mark.asyncio
    async def test_a_failed_llm_call_keeps_the_envelope_llm_chat_built(
        self, source, monkeypatch
    ):
        """Only `llm.chat` knows whether the peer refused or never answered."""
        monkeypatch.setattr(chat_module, "llm_chat", FakeChatWrapper({
            "ok": False, "error": "invalid_api_key",
            "error_code": "API_ERROR",
            "outcome": chat_module._provider_refused("openai", "invalid_api_key"),
        }))

        found = envelope_of(await run("llm.code_fix", {
            "issues": ["x"], "source_files": [str(source)], "api_key": "k",
        }))

        assert found["rung"] == Outcome.FAILED.value
        assert "provider_error" in effect_kinds(found)


class TestRedisMemory:
    """Rows off the wire are an observation. An empty list is not."""

    @pytest.fixture
    def fake_redis(self, monkeypatch):
        """Install a `redis.asyncio` that answers however the test says."""
        def _install(stored=None, ping_error=None, lrange_error=None):
            class Client:
                async def ping(self):
                    if ping_error:
                        raise ping_error
                    return True

                async def lrange(self, key, start, end):
                    if lrange_error:
                        raise lrange_error
                    return [json.dumps(m) for m in (stored or [])]

            package = types.ModuleType("redis")
            asyncio_module = types.ModuleType("redis.asyncio")
            asyncio_module.from_url = lambda *a, **k: Client()
            package.asyncio = asyncio_module
            monkeypatch.setitem(sys.modules, "redis", package)
            monkeypatch.setitem(sys.modules, "redis.asyncio", asyncio_module)
        return _install

    # Loopback: `enforce_outbound_service_url` refuses a host that does not
    # resolve, and the fake client below never opens a socket anyway.
    PARAMS = {"redis_url": "redis://localhost:6379", "session_id": "s1"}

    @pytest.mark.asyncio
    async def test_messages_that_came_back_are_observed(self, fake_redis):
        fake_redis(stored=[{"role": "user", "content": "hello"}])

        result = await run("ai.memory.redis", self.PARAMS)
        found = envelope_of(result)

        assert result["messages"] == [{"role": "user", "content": "hello"}]
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_named(found, "messages_read")["count"] == 1

    @pytest.mark.asyncio
    async def test_an_empty_list_is_only_accepted(self, fake_redis):
        """`len(messages) == 0` reads the same for a new session, an expired key
        and a flushed database. A value unchanged by the effect is not evidence.
        """
        fake_redis(stored=[])

        result = await run("ai.memory.redis", self.PARAMS)
        found = envelope_of(result)

        assert result["connected"] is True
        assert found["rung"] == Outcome.ACCEPTED.value
        assert found["rung"] != Outcome.OBSERVED.value

    @pytest.mark.asyncio
    async def test_load_on_start_off_claims_only_the_ping(self, fake_redis):
        fake_redis(stored=[{"role": "user", "content": "hello"}])

        found = envelope_of(
            await run("ai.memory.redis", {**self.PARAMS, "load_on_start": False})
        )

        assert found["rung"] == Outcome.ACCEPTED.value
        assert "connection_acknowledged" in effect_kinds(found)

    @pytest.mark.asyncio
    async def test_an_unreachable_store_is_indeterminate_not_an_empty_history(
        self, fake_redis
    ):
        """The silent fallback, made visible.

        `ok` is True and `messages` is `[]`, which downstream reads as "new
        conversation". There may be fifty messages in that key.
        """
        fake_redis(ping_error=ConnectionError("Connection refused"))

        result = await run("ai.memory.redis", self.PARAMS)
        found = envelope_of(result)

        assert result["ok"] is True and result["messages"] == []
        assert found["rung"] == Outcome.INDETERMINATE.value
        assert "Connection refused" in effect_named(found, "memory_not_read")["reason"]

    @pytest.mark.asyncio
    async def test_a_ping_that_worked_does_not_cover_a_read_that_did_not(
        self, fake_redis
    ):
        """`connected` and `loaded` are different facts and are kept apart."""
        fake_redis(lrange_error=ConnectionError("reset by peer"))

        result = await run("ai.memory.redis", self.PARAMS)
        found = envelope_of(result)

        assert result["connected"] is True
        assert found["rung"] == Outcome.INDETERMINATE.value
        assert effect_named(found, "memory_not_read")["connected"] is True


# ===========================================================================
# The envelope has to survive the trip out of the step
# ===========================================================================


class TestTheEnvelopeIsWhereTheStepCanReadIt:
    @pytest.mark.asyncio
    async def test_a_wrapped_result_carries_it_inside_data(self, monkeypatch):
        """`to_legacy_dict` keeps `ok` and `data` and throws away every sibling."""
        from core.engine.step_executor.executor import step_outcome

        payload = {
            "data": [{"index": 0, "embedding": [0.1]}],
            "usage": {"total_tokens": 1},
            "model": "text-embedding-3-small",
        }
        monkeypatch.setattr(
            embed_module.aiohttp, "ClientSession", fake_session_factory(payload)
        )

        result = await run("ai.embed", {"text": "a", "api_key": "k"})

        assert "outcome" in result["data"]
        rung, _, _ = step_outcome(result)
        assert rung is Outcome.ACCEPTED

    @pytest.mark.asyncio
    async def test_a_flat_result_carries_it_at_the_top_level(self, monkeypatch):
        """`wrap_legacy_result` sweeps a flat dict's fields into `data`."""
        from core.modules.items import wrap_legacy_result

        async def fake_call(*args, **kwargs):
            return {"ok": True, "response": "hi", "tokens_used": 1, "finish_reason": "stop"}

        monkeypatch.setattr(chat_module, "_call_openai", fake_call)

        result = await run("llm.chat", {"prompt": "hi", "api_key": "k"})
        wrapped = wrap_legacy_result(result)

        assert read_envelope(wrapped.first_item.json)["rung"] == Outcome.ACCEPTED.value

    @pytest.mark.asyncio
    async def test_the_engine_does_not_lower_a_claim_this_group_makes(
        self, monkeypatch
    ):
        """`cap` only bites a VERIFIED, and nothing here claims one."""
        from core.engine.step_executor.executor import _apply_outcome_contract

        async def fake_call(*args, **kwargs):
            return {"ok": True, "response": "hi", "tokens_used": 1, "finish_reason": "stop"}

        monkeypatch.setattr(chat_module, "_call_openai", fake_call)

        module = ModuleRegistry.get("llm.chat")({"prompt": "hi", "api_key": "k"}, {})
        result = _apply_outcome_contract(module, await module.execute())

        assert envelope_of(result)["rung"] == Outcome.ACCEPTED.value
