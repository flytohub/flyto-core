# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Runtime-capability gates that nothing else pins.

Two objects reach modules through the execution context and carry real
authority: the browser profile scope, which decides whose persistent Chrome
profile a launch attaches to, and the template-definition resolver, which
hands out workflow definitions that may embed execution-resolved credentials.

Both are guarded the same way — the caller must present the genuine runtime
capability, not merely something shaped like one — because the context is
reachable from workflow-authored data. A mutation sweep flipped each of these
guards open and the whole suite still passed, so they are pinned here.
"""

import pytest

from core.browser.driver import (
    BrowserProfileScope,
    browser_profile_scope_from_context,
)
from core.modules.atomic.llm._agent_tool_template import TemplateAgentTool
from core.modules.atomic.template.invoke import _TemplateDefinitionResolver

# ---------------------------------------------------------------------------
# browser_profile_scope_from_context
# ---------------------------------------------------------------------------

class TestBrowserProfileScopeGate:
    def test_absent_scope_is_none(self):
        assert browser_profile_scope_from_context({}) is None

    def test_genuine_scope_passes_through(self):
        scope = BrowserProfileScope("principal-A")
        assert browser_profile_scope_from_context(
            {"_browser_profile_scope": scope}
        ) is scope

    @pytest.mark.parametrize(
        "forged",
        [
            "principal-A",
            {"principal": "principal-A"},
            123,
            ["principal-A"],
            object(),
        ],
        ids=["str", "dict", "int", "list", "object"],
    )
    def test_forged_scope_raises_rather_than_degrading_to_none(self, forged):
        """A forged scope must be an error, never a silent fall back to None.

        Returning None here would not look like a failure: it is exactly what
        an unscoped context returns, so a forged scope would quietly select
        the shared default profile instead of the caller's isolated one. The
        two outcomes have to stay distinguishable.
        """
        with pytest.raises(RuntimeError):
            browser_profile_scope_from_context(
                {"_browser_profile_scope": forged}
            )

    def test_distinct_principals_get_distinct_profile_dirs(self, tmp_path, monkeypatch):
        from pathlib import Path

        from core.browser.driver import BrowserDriver

        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

        a = BrowserDriver(profile_scope=BrowserProfileScope("principal-A"))
        b = BrowserDriver(profile_scope=BrowserProfileScope("principal-B"))
        a_again = BrowserDriver(profile_scope=BrowserProfileScope("principal-A"))

        dir_a = a._persistent_profile_dir()
        dir_b = b._persistent_profile_dir()

        assert dir_a != dir_b
        assert dir_a == a_again._persistent_profile_dir()
        # The principal must not be recoverable from the path on disk.
        assert "principal-A" not in str(dir_a)
        assert "principal-B" not in str(dir_b)


# ---------------------------------------------------------------------------
# TemplateAgentTool._load_template — opaque resolver lookup
# ---------------------------------------------------------------------------

class _Impostor:
    """Same duck type as the real resolver, without the runtime marker."""

    def __init__(self, definitions):
        self._definitions = definitions

    def resolve(self, library_id, template_id):
        return self._definitions.get(template_id)


@pytest.mark.asyncio
class TestAgentToolTemplateResolverGate:
    @staticmethod
    def _tool():
        return TemplateAgentTool(
            template_id="child",
            tool_name="child",
            tool_description="child template",
        )

    async def test_opaque_resolver_is_consulted(self):
        """The real capability is how a nested agent finds its template."""
        definition = {"steps": [{"id": "s", "module": "string.uppercase"}]}
        resolver = _TemplateDefinitionResolver({"child": definition})

        loaded = await self._tool()._load_template(
            {"_template_definition_resolver": resolver}
        )

        assert loaded == definition

    async def test_non_opaque_impostor_is_not_consulted(self):
        """An object that merely exposes resolve() must not be trusted.

        `_template_definition_resolver` is read straight off the execution
        context. If any resolve()-shaped object were honoured, workflow data
        could substitute its own definition map and decide what a template
        tool executes.
        """
        planted = {"steps": [{"id": "s", "module": "shell.exec"}]}

        loaded = await self._tool()._load_template(
            {"_template_definition_resolver": _Impostor({"child": planted})}
        )

        assert loaded is None

    async def test_impostor_does_not_shadow_the_raw_definitions(self):
        """Falling through the gate must land on the legitimate source."""
        planted = {"steps": [{"id": "s", "module": "shell.exec"}]}
        genuine = {"steps": [{"id": "s", "module": "string.uppercase"}]}

        loaded = await self._tool()._load_template(
            {
                "_template_definition_resolver": _Impostor({"child": planted}),
                "template_definitions": {"child": genuine},
            }
        )

        assert loaded == genuine

    async def test_marker_as_instance_key_is_not_a_capability(self):
        """The marker is read off the type, so a dict cannot forge it."""

        class MarkedDict(dict):
            def resolve(self, library_id, template_id):
                return {"steps": [{"id": "s", "module": "shell.exec"}]}

        forged = MarkedDict(_flyto_runtime_opaque=True)

        loaded = await self._tool()._load_template(
            {"_template_definition_resolver": forged}
        )

        assert loaded is None
