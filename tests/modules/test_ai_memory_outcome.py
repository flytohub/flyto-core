# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Why all five ai-memory sub-nodes stayed on the undeclared list.

This is the browser.hover file for a whole group: no rung was added anywhere in
it, and these tests are the measurements that say why, pinned so the next person
does not have to re-derive them before deciding the same thing -- or has a
failing test in hand the day one of them stops being true.

`ai.memory`, `ai.memory.entity`, `ai.memory.vector`, `ai.model` and `ai.tool`
are all `NodeType.AI_SUB_NODE`: they are configuration providers wired to
`llm.agent` over a RESOURCE edge. Between them they open zero sockets, read zero
files and write zero durable state. Every field any of them returns is either a
parameter the caller handed in, or a literal written in the module's own source.
Run the ONE RULE over any of them -- would this value be the same if the effect
had not happened -- and the answer is yes for every field, because there is no
effect. That is `browser.viewport`'s echoed parameters and `browser.storage`'s
literal `True`, five times over.

They were in the outcome population only because `is_side_effecting` keys on the
category prefix and `ai` is in `SIDE_EFFECT_CATEGORIES` -- correctly, for
`ai.embed` and `llm.chat`, which do spend money. So `default_for` stamped all
five `dispatched`, one rung above what happened: no instruction left us.

THAT HAS SINCE BEEN CORRECTED, and this file's conclusion is what corrected it.
The fix was the metadata question this docstring named: all five now declare
`derives=True`, which `default_for` reads as "not on the ladder" and stamps
nothing for -- the honest envelope for a config builder being no envelope at
all. `ai.memory.redis` deliberately does not declare it; it really does connect,
and it reports its own rung. The tests below still assert these five are in the
side-effecting *population*, because they are: the category heuristic has not
changed and should not, or `ai.embed` would fall out of it with them.

WHAT THE MEASUREMENTS ACTUALLY FOUND, which is the part worth keeping:

  * `ai.memory` cannot load history. It reads `context['memory_messages']`, and
    nothing in `src/` ever writes that key. `messages` is exactly the caller's
    own `initial_messages` parameter, always.
  * `ai.memory.entity` and `ai.memory.vector` return no `messages` key at all,
    and `llm.agent._resolve_memory` reads nothing else. Wiring either one to an
    agent contributes an empty history -- the agent behaves exactly as if no
    memory node were connected.
  * the `__methods__` dict all four memory modules return names functions by
    string. Nothing in the repository resolves those names, and `llm.agent`
    never writes back to memory. The write half of every memory module in this
    group is unreachable from a workflow.

None of that is a rung. An envelope saying `indeterminate` on every ai.memory
step would be exactly the mistake browser.hover's withdrawn `:hover` predicate
would have been: it would mark the correct runs -- a buffer memory correctly
initialised from `initial_messages` -- as unknowable, when they are fully
determined. These are bugs to report, and they are reported; they are not rungs.
"""

import asyncio
import sys
from contextlib import suppress
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from core.engine.outcome import (  # noqa: E402
    ENVELOPE_KEY,
    Outcome,
    default_for,
    is_side_effecting,
    read_envelope,
)
from core.modules.registry import ModuleRegistry  # noqa: E402


def ensure_modules_loaded():
    from core.modules import atomic  # noqa: F401
    with suppress(Exception):
        from core.modules import third_party  # noqa: F401


ensure_modules_loaded()


#: The five this pass was asked to judge.
GROUP = ("ai.memory", "ai.memory.entity", "ai.memory.vector", "ai.model", "ai.tool")

#: The four of GROUP that really are pure configuration providers, and so
#: declare `derives=True` and are stamped nothing at all.
#:
#: `ai.model` is deliberately not among them. It was given the same flag on the
#: same reasoning, and an audit hook caught it resolving the host whenever
#: `base_url` is set -- `socket.getaddrinfo`, followed by `ok: False` when the
#: name does not resolve. A result that depends on the network is not computed
#: from its inputs, so it keeps the `dispatched` default.
DERIVING = ("ai.memory", "ai.memory.entity", "ai.memory.vector", "ai.tool")

SRC_ROOT = Path(__file__).parent.parent.parent / "src" / "core"


async def run(module_id, params, context=None):
    """Execute a module the way the engine does and return its result dict."""
    module = ModuleRegistry.get(module_id)
    return await module(params, context or {}).execute()


def envelope_of(result):
    """The envelope, read from wherever `_apply_outcome_contract` would read it."""
    body = result.get("data") if isinstance(result.get("data"), dict) else result
    return read_envelope(body)


def source_files_mentioning(needle):
    """Every file under src/core whose text contains `needle`, with line numbers."""
    hits = []
    for path in SRC_ROOT.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if needle in line:
                hits.append(f"{path.relative_to(SRC_ROOT)}:{number}")
    return sorted(hits)


# ===========================================================================
# The floor. What these five get today, and that none of them claims more.
# ===========================================================================


class TestTheGroupClaimsNothingOfItsOwn:
    """The state this pass deliberately left in place.

    Not a placeholder: if any of the five later attaches an envelope, this fails
    and the person who attached it has to come back to this file and say which
    measurement earned it. That is the whole reason a refusal is written down
    rather than simply not done.

    The class was called ...AndIsStampedDispatched while that was true of all
    five. Four of them are stamped nothing now, and `ai.model` is the one still
    stamped `dispatched` -- for a measured reason rather than for want of
    looking.
    """

    @pytest.mark.parametrize("module_id", GROUP)
    def test_the_engine_default_matches_what_the_module_actually_reaches(self, module_id):
        metadata = ModuleRegistry.get_metadata(module_id) or {}
        assert is_side_effecting(module_id, metadata), (
            f"{module_id} left the outcome population; the coverage list entry "
            "for it is now stale"
        )
        expected = None if module_id in DERIVING else Outcome.DISPATCHED
        assert default_for(module_id, metadata) is expected, (
            "a config builder that dispatches nothing must be stamped nothing, "
            "and a module that resolves a hostname must not be."
        )

    @pytest.mark.parametrize("module_id", GROUP)
    def test_no_postcondition_is_declared(self, module_id):
        """`verified` is unreachable for all five, and must stay that way.

        Nothing in this group evaluates a predicate about an effect. A
        `postcondition=` appearing on one of these decorators without a
        read-back behind it would move the lie one level up, exactly as
        `database.query`'s docstring puts it.
        """
        metadata = ModuleRegistry.get_metadata(module_id) or {}
        assert metadata.get("postcondition") is None
        # `derives=True` is the fix rather than the trap it was when this test
        # was written: it could reach VERIFIED then, and reaches no rung at all
        # today, so it is no longer a route to the green tick this test blocks.
        # `postcondition` is that route, and it stays shut for all five.
        assert metadata.get("derives") is (module_id in DERIVING)

    @pytest.mark.asyncio
    async def test_none_of_them_attaches_an_envelope_of_its_own(self):
        results = {
            "ai.memory": await run("ai.memory", {"memory_type": "buffer"}),
            "ai.memory.entity": await run("ai.memory.entity", {"extraction_model": "llm"}),
            "ai.memory.vector": await run("ai.memory.vector", {"embedding_model": "local"}),
            "ai.model": await run(
                "ai.model", {"provider": "openai", "model": "gpt-4o", "api_key": "sk-test"}
            ),
            "ai.tool": await run("ai.tool", {"module_id": "http.request"}),
        }
        for module_id, result in results.items():
            assert envelope_of(result) is None, (
                f"{module_id} now reports an outcome -- name the measurement here "
                "and take it off the coverage list"
            )
            assert ENVELOPE_KEY not in result


# ===========================================================================
# ai.memory -- the ONE RULE, applied to a module that has no store to read.
# ===========================================================================


def where(mentions):
    """The files a scan landed in, without the line numbers.

    `source_files_mentioning` returns "path:line", and pinning the line makes
    every one of these tests fail the moment anything is inserted above the
    site -- which is exactly what adding a nine-line comment to five decorators
    did. The claim being defended is "this name is touched in these files, this
    many times", and none of that is the line number.
    """
    return [mention.split(":")[0] for mention in mentions]


class TestBufferMemoryIsAnEchoOfItsOwnParameter:
    """`messages` is the caller's `initial_messages`. That is the whole finding.

    The tempting rung here is `observed`, off `len(messages) > 0` -- the shape
    `ai.memory.redis` earns honestly, because its list came off a wire. This one
    did not come off anything. It is the argument, handed back.
    """

    @pytest.mark.asyncio
    async def test_messages_are_the_parameter_unchanged(self):
        history = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
        result = await run("ai.memory", {"memory_type": "buffer", "initial_messages": history})
        assert result["messages"] == history

    @pytest.mark.asyncio
    async def test_an_empty_context_and_a_populated_one_are_indistinguishable(self):
        """The ONE RULE, run as an experiment rather than asserted.

        Two executions, identical parameters, contexts that differ in everything
        except the one key this module reads. Same `messages` both times: no
        value in the result carries information about anything outside the call.
        """
        params = {"memory_type": "buffer", "initial_messages": [{"role": "user", "content": "x"}]}
        bare = await run("ai.memory", params, {})
        furnished = await run(
            "ai.memory",
            params,
            {"inputs": {"memory": {"messages": [{"role": "user", "content": "stored"}]}},
             "_entity_store": {"entities": {}},
             "vars": {"anything": "at all"}},
        )
        assert bare["messages"] == furnished["messages"] == params["initial_messages"]

    def test_nothing_in_src_ever_writes_the_key_it_reads(self):
        """`context['memory_messages']` has exactly one mention: the read.

        This is what makes the echo permanent rather than incidental. The day
        somebody writes that key, this test fails and the refusal above is worth
        re-opening -- at that point `messages` would carry state from an earlier
        step and a rung becomes a real question.
        """
        mentions = source_files_mentioning("memory_messages")
        assert where(mentions) == ["modules/atomic/ai/memory.py"], (
            f"memory_messages is now touched in more than one place: {mentions}"
        )

    @pytest.mark.asyncio
    async def test_summary_memory_is_buffer_memory(self):
        """A defect, pinned. `summary` is an offered option with no code path.

        `memory_type='summary'` reaches the same two lines as `buffer` -- there
        is no summarisation anywhere in the module. A workflow that picks it gets
        an unbounded raw history and no error. Asserted rather than xfailed so
        that implementing it is a deliberate edit to this file.
        """
        history = [{"i": n} for n in range(30)]
        summary = await run("ai.memory", {"memory_type": "summary", "initial_messages": history})
        buffer = await run("ai.memory", {"memory_type": "buffer", "initial_messages": history})
        assert summary["messages"] == buffer["messages"] == history

    @pytest.mark.asyncio
    async def test_the_window_is_the_one_thing_it_actually_computes(self):
        """Not evidence of anything external, but it is real and it works."""
        history = [{"i": n} for n in range(10)]
        result = await run(
            "ai.memory",
            {"memory_type": "window", "window_size": 3, "initial_messages": history},
        )
        assert result["messages"] == history[-3:]


# ===========================================================================
# ai.memory.entity -- a literal, shaped by a parameter.
# ===========================================================================


class TestEntityMemoryReturnsALiteral:
    @pytest.mark.asyncio
    async def test_entities_are_empty_buckets_named_by_the_parameter(self):
        """`{t: {} for t in entity_types}`, written in the module, every run.

        `entities` is not a reading of a knowledge base -- there is no knowledge
        base. The keys come from the caller's `entity_types`; the values are the
        same empty dict literal on every execution. `browser.storage`'s `True`.
        """
        result = await run(
            "ai.memory.entity",
            {"extraction_model": "llm", "entity_types": ["person", "product"]},
        )
        assert result["entities"] == {"person": {}, "product": {}}
        assert result["relationships"] == []
        assert result["entity_store"]["mentions"] == []

    def test_nothing_in_src_ever_writes_the_key_it_reads(self):
        mentions = source_files_mentioning("_entity_store")
        assert where(mentions) == ["modules/atomic/ai/memory_entity.py"], (
            f"_entity_store is now touched in more than one place: {mentions}"
        )

    @pytest.mark.asyncio
    async def test_extraction_model_is_stored_and_never_consulted(self):
        """No LLM, no SpaCy, no regex. The choice is written to `config` only.

        All three options produce byte-identical output apart from the echoed
        string, which is the clearest possible statement that no extraction
        happens in this module.
        """
        outputs = {}
        for choice in ("llm", "spacy", "regex"):
            result = await run("ai.memory.entity", {"extraction_model": choice})
            assert result["config"]["extraction_model"] == choice
            outputs[choice] = (result["entities"], result["relationships"])
        assert len(set(map(str, outputs.values()))) == 1


# ===========================================================================
# ai.memory.vector -- an object is constructed; nothing is embedded.
# ===========================================================================


class TestVectorMemoryOpensNoChannel:
    @pytest.mark.asyncio
    async def test_execute_never_generates_an_embedding(self):
        """The spy that settles it: `generate` raises, and the module succeeds.

        `EmbeddingGenerator.__init__` assigns three attributes. Nothing is
        loaded, no key is checked, no request is made -- so there is no provider
        acknowledgement to build even an `accepted` on.
        """
        from core.modules.atomic.vector.embeddings import EmbeddingGenerator

        def explode(self, text):
            raise AssertionError("ai.memory.vector called the embedding provider")

        original = EmbeddingGenerator.generate
        EmbeddingGenerator.generate = explode
        try:
            result = await run("ai.memory.vector", {"embedding_model": "text-embedding-3-small"})
        finally:
            EmbeddingGenerator.generate = original

        assert result["ok"] is True
        assert result["embedder"]._client is None
        assert result["vector_store"] == {"embeddings": [], "messages": [], "metadata": []}

    def test_nothing_in_src_ever_writes_the_key_it_reads(self):
        mentions = source_files_mentioning("_vector_store")
        assert where(mentions) == ["modules/atomic/ai/memory_vector.py"], (
            f"_vector_store is now touched in more than one place: {mentions}"
        )

    @pytest.mark.asyncio
    async def test_the_local_option_becomes_the_model_name(self):
        """A defect, pinned. Picking 'Local Model' asks for a model called 'local'.

        `embedding_model='local'` is the select's own option value. The module
        maps it to `provider='local'` but passes the same string on as `model`,
        so `EmbeddingGenerator._generate_local` would eventually call
        `SentenceTransformer('local')`. `_get_default_model()` exists and returns
        `all-MiniLM-L6-v2` for this provider; passing `None` instead would reach
        it. Not fixed here -- it is a behaviour change, not an outcome one -- and
        asserted so the fix has to come through this file.
        """
        result = await run("ai.memory.vector", {"embedding_model": "local"})
        assert result["embedder"].provider == "local"
        assert result["embedder"].model == "local"


# ===========================================================================
# ai.model -- a client object, and no call through it.
# ===========================================================================


class TestModelBuildsAClientAndTalksToNobody:
    @pytest.mark.asyncio
    async def test_the_chat_model_is_constructed_and_never_used(self):
        """`create_chat_model` stores parameters. `chat()` is what makes a request.

        So `ai.model` returning `ok: True` says the caller's configuration was
        well-formed and a key was found somewhere. It says nothing about the key
        being valid, the model existing, or the endpoint answering -- all of
        which are discovered at `llm.agent` time, one step later.
        """
        from core.modules.atomic.llm._chat_models import OpenAIChatModel

        async def explode(self, *args, **kwargs):
            raise AssertionError("ai.model called the provider")

        original = OpenAIChatModel.chat
        OpenAIChatModel.chat = explode
        try:
            result = await run(
                "ai.model",
                {"provider": "openai", "model": "gpt-4o", "api_key": "sk-not-a-real-key"},
            )
        finally:
            OpenAIChatModel.chat = original

        assert result["ok"] is True
        assert isinstance(result["chat_model"], OpenAIChatModel)
        assert result["chat_model"].model_name == "gpt-4o"

    @pytest.mark.asyncio
    async def test_a_syntactically_valid_but_worthless_key_is_accepted(self):
        """The measurement that would have to exist for a rung, and does not.

        Nothing distinguishes this run from one with a working key. `provider`,
        `model` and `config` are the parameters handed back; there is no reading
        that would differ if the provider did not exist at all.
        """
        params = {"provider": "anthropic", "model": "claude-3-5-sonnet-20241022",
                  "api_key": "definitely-not-a-key", "temperature": 0.5}
        result = await run("ai.model", params)
        assert result["ok"] is True
        assert result["provider"] == params["provider"]
        assert result["model"] == params["model"]
        assert result["config"]["temperature"] == params["temperature"]

    @pytest.mark.asyncio
    async def test_the_refusals_are_refusals_and_carry_no_payload(self):
        """Three `ok: False` paths, and why none of them got a FAILED envelope.

        See `TestAnErrorPathCannotCarryAnEnvelope` below: the engine discards the
        payload of an `ok: False` result before any consumer sees it, so an
        envelope written here would be provably unreadable.
        """
        result = await run("ai.model", {"provider": "openai", "model": "gpt-4o"})
        assert result == {
            "ok": False,
            "error": "API key not provided for openai",
            "error_code": "MISSING_API_KEY",
        }


# ===========================================================================
# ai.tool -- one registry lookup, and a lazily-built wrapper.
# ===========================================================================


class TestToolChecksTheRegistryAndNothingElse:
    @pytest.mark.asyncio
    async def test_the_wrapper_is_lazy_so_even_the_metadata_is_unread(self):
        """`_metadata is None` after a successful execute.

        `registry.has()` is a membership test on an in-process dict. It is a
        precondition about our own state, not an observation of an effect, and a
        `postcondition=` built on it would be asserting the wrong thing entirely:
        that the module id resolves says nothing about the agent receiving the
        tool, which is the only effect there is and happens in another step.
        """
        result = await run("ai.tool", {"module_id": "http.request"})
        assert result["ok"] is True
        assert result["module_id"] == "http.request"
        assert result["tool"]._metadata is None
        assert result["tool"].name == "http--request"

    @pytest.mark.asyncio
    async def test_a_missing_module_is_refused_before_anything_is_built(self):
        result = await run("ai.tool", {"module_id": "no.such.module"})
        assert result["ok"] is False
        assert result["error_code"] == "MODULE_NOT_FOUND"
        assert "tool" not in result

    @pytest.mark.asyncio
    async def test_an_empty_module_id_is_refused(self):
        result = await run("ai.tool", {"module_id": ""})
        assert result["ok"] is False
        assert result["error_code"] == "MISSING_MODULE_ID"


# ===========================================================================
# The two facts about the surrounding code that decided the refusals.
# ===========================================================================


class TestAnErrorPathCannotCarryAnEnvelope:
    """Why "every return path" produced no error-path envelopes in this group.

    The rule is right and this group cannot satisfy it from inside a module.
    `wrap_legacy_result` turns an `ok: False` dict into an ERROR result whose
    data is `[[]]` -- every field of the payload, envelope included, is dropped
    -- and `executor.py` then raises `StepExecutionError` from the message and
    code alone. An envelope written beside `error_code` would never be read by
    anything.

    Recorded here rather than acted on: making failure envelopes survive is a
    change to `modules/items.py` and `step_executor/`, both out of scope for this
    pass, and it is the same change for all 483 modules rather than five.
    """

    def test_the_payload_of_a_failed_result_is_discarded(self):
        from core.modules.items import ExecutionStatus, wrap_legacy_result

        wrapped = wrap_legacy_result({
            "ok": False,
            "error": "API key not provided for openai",
            "error_code": "MISSING_API_KEY",
            ENVELOPE_KEY: {"rung": Outcome.FAILED.value, "claim_by": "none",
                           "postcondition": None, "effects": [], "evidence_ref": None},
        })

        assert wrapped.status is ExecutionStatus.ERROR
        assert wrapped.data == [[]]
        assert wrapped.error.code == "MISSING_API_KEY"


class TestEntityAndVectorMemoryReachTheAgentAsNothing:
    """The consumer-side half of the finding, pinned against the real reader.

    `llm.agent._resolve_memory` reads one key, `messages`. Neither
    `ai.memory.entity` nor `ai.memory.vector` returns one. Both satisfy the
    `__data_type__ == 'ai_memory'` check, so the agent logs "Using ai.memory with
    0 messages" and proceeds with an empty history -- the empty result read as
    fact, arriving from a store that was never consulted rather than one that
    could not be reached.

    Fixing it means teaching `_resolve_memory` to turn an entity store into
    context and to run a similarity search for vector memory. That is a feature
    in `llm/agent.py`, outside this group and far outside an outcome pass.
    """

    @pytest.mark.asyncio
    async def test_entity_memory_yields_no_history(self):
        from core.modules.atomic.llm.agent import _resolve_memory

        memory = await run("ai.memory.entity", {"extraction_model": "llm"})
        assert "messages" not in memory
        assert _resolve_memory({"inputs": {"memory": memory}}) == []

    @pytest.mark.asyncio
    async def test_vector_memory_yields_no_history(self):
        from core.modules.atomic.llm.agent import _resolve_memory

        memory = await run("ai.memory.vector", {"embedding_model": "text-embedding-3-small"})
        assert "messages" not in memory
        assert _resolve_memory({"inputs": {"memory": memory}}) == []

    @pytest.mark.asyncio
    async def test_buffer_memory_does_reach_the_agent(self):
        """The contrast that makes the two above a defect rather than a design."""
        from core.modules.atomic.llm.agent import _resolve_memory

        history = [{"role": "user", "content": "hi"}]
        memory = await run("ai.memory", {"memory_type": "buffer", "initial_messages": history})
        assert _resolve_memory({"inputs": {"memory": memory}}) == history


class TestTheWriteHalfOfEveryMemoryModuleIsUnreachable:
    """`__methods__` names functions by string, and nothing resolves the names.

    All four memory modules -- the three in this group and `ai.memory.redis` --
    return a `__methods__` dict mapping 'add_message' to a source-level function
    name. Nothing in `src/` reads `__methods__`, and `llm.agent` only ever reads
    history (`_resolve_memory`) and never writes any back. So no workflow can
    add a message to any memory in this product; the helpers below `__methods__`
    are exercised only by tests calling them directly.

    This is the strongest reason `ai.memory` cannot climb the ladder: there is no
    write for a read-back to observe.
    """

    def test_nothing_consumes_the_methods_dict(self):
        mentions = source_files_mentioning("__methods__")
        assert where(mentions) == [
            "modules/atomic/ai/memory.py",
            "modules/atomic/ai/memory_entity.py",
            "modules/atomic/ai/memory_redis.py",
            "modules/atomic/ai/memory_vector.py",
        ], f"__methods__ now has a reader or another producer: {mentions}"

    def test_the_agent_reads_history_and_never_writes_it(self):
        agent_source = (SRC_ROOT / "modules" / "atomic" / "llm" / "agent.py").read_text(
            encoding="utf-8"
        )
        assert agent_source.count("_resolve_memory") == 2  # the def and the one call
        assert "add_message" not in agent_source


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
