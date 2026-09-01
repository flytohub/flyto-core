# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""The agent's sub-workflow tool, which had never executed once.

`TemplateAgentTool` wraps a stored template as a tool an LLM agent can call --
flyto's equivalent of n8n's Workflow Tool. Three defects sat on top of each
other, and only the first was visible:

  1. `_execute_template` imported WorkflowEngine from `...engine`, three levels
     up from `modules/atomic/llm/`, which is `core.modules.engine` and does not
     exist. Every neighbour in the same directory writes four. So every call
     raised ModuleNotFoundError -- and `invoke`'s blanket `except Exception`
     turned it into `{"ok": False, "error": "..."}`, an ordinary-looking tool
     failure the agent reported to the model as if the template had run and
     failed. A crash that never surfaced as a crash.

  2. Behind it, the workflow was built as `{"nodes": ..., "edges": ...}`. A
     template definition holds `steps`, and the engine answers "No steps
     defined in workflow" to anything else. The wrong shape had never run.

  3. Behind that, no recursion bound. `template.invoke` caps nesting at 16 and
     raises past it; this path counted nothing, so a template whose agent has
     that same template as a tool would spawn engines until the execution
     timeout.

These tests drive the real tool over the real engine with a real module.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import core.modules  # noqa: F401,E402
from core.modules.atomic.llm._agent_tool_template import (  # noqa: E402
    TemplateAgentTool,
)
from core.modules.atomic.template.invoke import (  # noqa: E402
    _MAX_TEMPLATE_INVOKE_DEPTH,
    _TEMPLATE_INVOKE_DEPTH_CONTEXT_KEY,
)

DEFINITION = {
    "steps": [
        {"id": "s1", "module": "string.uppercase", "params": {"text": "hi"}},
    ]
}


def _tool(**context):
    return TemplateAgentTool(
        template_id="t1",
        tool_name="t1",
        tool_description="a template",
        parent_context={"template_definitions": {"t1": DEFINITION}, **context},
    )


class TestItRunsAtAll:
    @pytest.mark.asyncio
    async def test_the_template_actually_executes(self):
        """The whole regression in one assertion.

        Before this, every call returned `ok: False` with an import error
        wearing the clothes of a template that ran and failed.
        """
        result = await _tool().invoke({"text": "hi"})

        assert result["ok"] is True
        steps = result["data"]["steps"]
        assert steps["s1"]["data"]["result"] == "HI"

    @pytest.mark.asyncio
    async def test_a_template_with_no_steps_says_so(self):
        """Rather than reaching the engine and coming back with its wording."""
        tool = TemplateAgentTool(
            template_id="empty",
            tool_name="empty",
            tool_description="x",
            parent_context={"template_definitions": {"empty": {"steps": []}}},
        )

        result = await tool.invoke({})

        assert result["ok"] is False
        assert "no steps" in result["error"].lower()


class TestTheRecursionCapApplies:
    """`template.invoke` bounds nesting; this path did not.

    The counter travels in the child context under the SAME key, so a mixed
    chain -- template.invoke calling an agent whose tool is a template -- is
    counted once per level rather than resetting at each hand-off.
    """

    @pytest.mark.asyncio
    async def test_one_below_the_cap_still_runs(self):
        result = await _tool(
            **{_TEMPLATE_INVOKE_DEPTH_CONTEXT_KEY: _MAX_TEMPLATE_INVOKE_DEPTH - 1}
        ).invoke({})

        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_at_the_cap_it_refuses(self):
        result = await _tool(
            **{_TEMPLATE_INVOKE_DEPTH_CONTEXT_KEY: _MAX_TEMPLATE_INVOKE_DEPTH}
        ).invoke({})

        assert result["ok"] is False
        assert str(_MAX_TEMPLATE_INVOKE_DEPTH) in result["error"]

    @pytest.mark.asyncio
    async def test_the_child_is_counted_one_deeper(self):
        """Without this the cap never arrives: each level would read 0."""
        result = await _tool().invoke({})

        context = result["data"]["steps"]
        assert context[_TEMPLATE_INVOKE_DEPTH_CONTEXT_KEY] == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad", [-1, True, "3", 1.5])
    async def test_a_depth_that_is_not_a_count_is_refused(self, bad):
        """`True` is the one worth naming: it is an int in Python and would
        otherwise pass every comparison as 1."""
        result = await _tool(**{_TEMPLATE_INVOKE_DEPTH_CONTEXT_KEY: bad}).invoke({})

        assert result["ok"] is False
        assert "Invalid nested template invocation depth" in result["error"]


class TestTheImportIsAtTheRightDepth:
    """The defect that hid the other two, pinned where it can be seen.

    A relative import one level short resolves to `core.modules.engine`, and
    the blanket `except Exception` in `invoke` converts the resulting
    ModuleNotFoundError into an ordinary tool failure -- so the tool reported a
    template that ran and failed, on every call, for as long as this was wrong.
    """

    def test_it_imports_from_core_engine_not_core_modules_engine(self):
        source = Path(
            "src/core/modules/atomic/llm/_agent_tool_template.py"
        ).read_text(encoding="utf-8")

        assert "from ....engine.workflow.engine import WorkflowEngine" in source
        assert "from ...engine.workflow.engine import" not in source
