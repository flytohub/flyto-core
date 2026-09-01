# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""What an LLM agent is told about how far its tool's effect was followed.

A module invoked as an agent TOOL never touches the step executor -- the tool
wrapper builds the class and calls `run()` directly -- so the outcome contract
had never run on one. Measured by spying on `_apply_outcome_contract`: same
module, same params, TOOL path 0 calls, STEP path 1 call.

The visible consequence was a differential rather than a plain absence. A
module that writes its own envelope reached the model with a rung BY ACCIDENT,
because the envelope rides inside `data` and the whole dict is serialized into
the tool message; a module that reports nothing reached it with no rung at all.
And the rung that did arrive was unlabeled: the model saw `"rung": "observed"`
with nothing anywhere telling it what the ladder is.

These tests pin the three things that fixes it, and the one thing that must NOT
happen while fixing it.
"""

import ast
import asyncio
import inspect
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import core.modules  # noqa: F401,E402
from core.engine.outcome import Outcome  # noqa: E402
from core.engine.step_executor.executor import step_outcome  # noqa: E402
from core.modules.atomic.llm._agent_tool import ModuleAgentTool  # noqa: E402
from core.modules.atomic.llm._resilience import (  # noqa: E402
    rung_line,
    truncate_tool_result,
)
from core.modules.atomic.llm._tools import (  # noqa: E402
    OUTCOME_VOCABULARY,
    build_agent_system_prompt,
)


@pytest.fixture
def sandbox(monkeypatch):
    path = tempfile.mkdtemp()
    monkeypatch.setenv("FLYTO_SANDBOX_DIR", path)
    return Path(path)


async def _invoke(module_id, arguments):
    tool = ModuleAgentTool(module_id=module_id, description="x", parent_context={})
    return await tool.invoke(arguments)


def _rung(result):
    found = step_outcome(result)
    return found[0].value if found else None


class TestTheToolPathDoesNotInventADispatch:
    """The one thing that must not happen, and nearly did.

    Applying `_apply_outcome_contract` directly here reads as the obvious fix
    and stamps `dispatched` on every `ok: False` result this path produces --
    module not found, capability policy block, path traversal guard, parameter
    validation. Nothing was dispatched in any of them; the module was never
    reached. On the step path that stamp is harmless because
    `wrap_legacy_result` raises straight afterwards and the result is thrown
    away. Here there is no raise, so the stamp is what the model reads.
    """

    @pytest.mark.asyncio
    async def test_a_module_that_does_not_exist_did_not_dispatch(self):
        result = await _invoke("file.nosuchthing", {})

        assert result["ok"] is False
        assert _rung(result) == Outcome.FAILED.value

    @pytest.mark.asyncio
    async def test_a_call_the_sandbox_refused_did_not_dispatch(self, sandbox):
        result = await _invoke("file.write", {"path": "/etc/passwd", "content": "x"})

        assert result["ok"] is False
        assert _rung(result) == Outcome.FAILED.value

    @pytest.mark.asyncio
    async def test_no_failing_tool_call_is_ever_stamped_dispatched(self, sandbox):
        """The property, over every failure this path can produce."""
        failures = [
            ("file.nosuchthing", {}),
            ("file.write", {"path": "/etc/passwd", "content": "x"}),
            ("http.request", {}),
        ]
        for module_id, arguments in failures:
            result = await _invoke(module_id, arguments)
            assert result["ok"] is False
            assert _rung(result) != Outcome.DISPATCHED.value, (
                f"{module_id} was reported as having dispatched an instruction "
                "that never left"
            )


class TestTheRungReachesTheToolResult:
    @pytest.mark.asyncio
    async def test_a_module_with_a_read_back_keeps_its_own_rung(self, sandbox):
        result = await _invoke(
            "file.write", {"path": str(sandbox / "a.txt"), "content": "hi"}
        )

        assert result["ok"] is True
        assert _rung(result) == Outcome.OBSERVED.value

    @pytest.mark.asyncio
    async def test_a_pure_computation_gets_no_rung_and_no_line(self):
        """Most of the registry computes. A line on every string operation
        would cost tokens on every later turn and teach the model to skip the
        field on the turns where it matters."""
        result = await _invoke("string.uppercase", {"text": "hi"})

        assert result["ok"] is True
        assert _rung(result) is None
        assert rung_line(result) == ""


class TestTheLineSurvivesTruncation:
    """Position is the whole point of the line.

    `truncate_tool_result` is a raw slice at the tail and the envelope is
    normally the LAST key in `data`, so on a large result the string "rung" is
    simply absent from what the model sees. The ladder disappeared exactly on
    the results a model is least able to check for itself.
    """

    def test_a_large_result_loses_its_envelope_but_keeps_the_line(self):
        big = {
            "ok": True,
            "data": {
                "text": "x" * 9000,
                "outcome": {
                    "rung": "indeterminate",
                    "claim_by": "inferred",
                    "postcondition": None,
                    "effects": [{"kind": "x"}],
                },
            },
        }

        line = rung_line(big)
        content = line + truncate_tool_result(big)

        assert "rung" not in content[len(line):], (
            "the fixture is too small to truncate the envelope away"
        )
        assert content.startswith("outcome: indeterminate")
        assert "do NOT simply retry" in content or "Do NOT" in content

    def test_the_verified_line_names_the_predicate(self):
        found = {
            "ok": True,
            "data": {
                "outcome": {
                    "rung": "verified",
                    "claim_by": "inferred",
                    "postcondition": "the file re-read equals what was written",
                    "effects": [],
                },
            },
        }

        line = rung_line(found)

        assert line.startswith("outcome: verified")
        assert "the file re-read equals what was written" in line


class TestTheModelIsGivenTheVocabulary:
    """A rung the model has no definition for is a word, not a signal."""

    def test_the_system_prompt_defines_every_rung(self):
        prompt = build_agent_system_prompt("You are a helpful agent.", [])

        for rung in (
            "verified", "observed", "accepted",
            "dispatched", "failed", "indeterminate",
        ):
            assert rung in prompt, f"the prompt never defines {rung}"

    def test_it_says_which_one_means_done(self):
        assert "Only `verified`" in OUTCOME_VOCABULARY

    def test_it_tells_the_model_not_to_retry_an_indeterminate_effect(self):
        """The sentence the whole ladder is for.

        A model that reads `indeterminate` as failure retries, and retrying is
        exactly what must not happen: the request was already in the other
        side's hands when the connection broke, so a retry may send the message
        or take the payment a second time.
        """
        assert "Do not retry" in OUTCOME_VOCABULARY
        assert "repeats it" in OUTCOME_VOCABULARY


class TestTheLineIsActuallyWired:
    """The gap the seam found in this file's own first draft.

    Every test above exercises `rung_line` directly, so deleting the call from
    `agent.py` left all ten of them green -- the helper was tested and the
    wiring was not. This walks the syntax tree of the agent loop and requires
    that every result which reaches `truncate_tool_result` is prefixed by the
    line first.

    Structural rather than behavioural on purpose: driving the real loop needs
    a model provider, and the three call sites are in three different loops
    (tool-calling, its snapshot injection, and ReAct). The property being
    defended is positional -- the line must be OUTSIDE the truncation -- and
    the tree is where position lives.
    """

    def _tree(self):
        from core.modules.atomic.llm import agent as agent_module

        return ast.parse(inspect.getsource(agent_module))

    def test_every_truncated_tool_result_is_prefixed_with_its_rung(self):
        offenders = []
        for node in ast.walk(self._tree()):
            if not isinstance(node, ast.BinOp) and not isinstance(node, ast.Call):
                continue
            if isinstance(node, ast.Call):
                continue
            calls = {
                child.func.id
                for child in ast.walk(node)
                if isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
            }
            if "truncate_tool_result" in calls and "rung_line" not in calls:
                offenders.append(ast.unparse(node))

        bare = []
        for node in ast.walk(self._tree()):
            if isinstance(node, ast.Assign):
                value = node.value
                if (
                    isinstance(value, ast.Call)
                    and isinstance(value.func, ast.Name)
                    and value.func.id == "truncate_tool_result"
                ):
                    bare.append(ast.unparse(node))

        assert not offenders, offenders
        assert not bare, (
            f"these send a tool result to the model with no outcome line: {bare}"
        )

    def test_all_three_loops_are_covered(self):
        """Three call sites, and a fourth appearing without the prefix is the
        thing this notices."""
        prefixed = [
            node
            for node in ast.walk(self._tree())
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "rung_line"
        ]

        assert len(prefixed) == 3, (
            f"expected the three tool-result sites, found {len(prefixed)}"
        )
