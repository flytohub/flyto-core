"""Browser ownership regressions for nested template execution."""

import pytest

from core.browser.driver import BrowserProfileScope
from core.modules.atomic.browser.ensure import BrowserEnsureModule  # noqa: F401
from core.modules.atomic.string.uppercase import string_uppercase  # noqa: F401
from core.modules.atomic.template.invoke import InvokeTemplate


@pytest.fixture(autouse=True)
def _allow_nested_modules(monkeypatch) -> None:
    import core.module_policy as module_policy
    from core.module_policy import ModuleFilter

    monkeypatch.delenv("FLYTO_MODULE_DENYLIST", raising=False)
    monkeypatch.setenv(
        "FLYTO_MODULE_ALLOWLIST",
        "browser.*,template.*,string.*",
    )
    monkeypatch.setattr(module_policy, "module_filter", ModuleFilter())


class _InheritedBrowser:
    def __init__(self) -> None:
        self.close_calls = 0

    async def close(self) -> None:
        self.close_calls += 1


@pytest.mark.asyncio
async def test_inner_template_does_not_close_parent_browser() -> None:
    browser = _InheritedBrowser()
    invocation = InvokeTemplate(
        params={"template_id": "child", "library_id": "child"},
        context={"browser": browser},
    )

    result = await invocation._execute_in_process(
        definition={
            "steps": [
                {
                    "id": "ensure_child_browser",
                    "module": "browser.ensure",
                    "params": {},
                }
            ]
        },
        params={},
    )

    assert result["steps"]["ensure_child_browser"]["action"] == "reused"
    assert browser.close_calls == 0


@pytest.mark.asyncio
async def test_inner_template_cannot_resolve_sibling_definition_map() -> None:
    child = {
        "steps": [
            {
                "id": "probe",
                "module": "string.uppercase",
                "params": {"text": "${template_definitions}"},
            }
        ]
    }
    invocation = InvokeTemplate(
        params={"template_id": "child", "library_id": "child"},
        context={
            "template_definitions": {
                "child": child,
                "sibling": {
                    "steps": [
                        {
                            "id": "private",
                            "module": "string.uppercase",
                            "params": {"secret": "not-a-real-credential"},
                        }
                    ]
                },
            }
        },
    )

    result = await invocation.execute()

    probe = result["result"]["steps"]["probe"]["data"]
    assert probe["original"] == "${template_definitions}"
    assert "not-a-real-credential" not in repr(result)


@pytest.mark.asyncio
async def test_runtime_resolver_preserves_declared_nested_invocation() -> None:
    parent = {
        "steps": [
            {
                "id": "invoke_grandchild",
                "module": "template.invoke:grandchild",
                "params": {
                    "template_id": "grandchild",
                    "library_id": "grandchild",
                },
            }
        ]
    }
    grandchild = {
        "steps": [
            {
                "id": "uppercase",
                "module": "string.uppercase",
                "params": {"text": "nested works"},
            }
        ]
    }
    invocation = InvokeTemplate(
        params={"template_id": "parent", "library_id": "parent"},
        context={
            "template_definitions": {
                "parent": parent,
                "grandchild": grandchild,
            }
        },
    )

    result = await invocation.execute()

    nested = result["result"]["steps"]["invoke_grandchild"]["result"]
    assert nested["steps"]["uppercase"]["data"]["result"] == "NESTED WORKS"


@pytest.mark.asyncio
async def test_inner_template_inherits_opaque_browser_profile_scope(monkeypatch) -> None:
    scope = BrowserProfileScope("account-one")
    seen = {}

    async def observe_scope(module):
        seen["scope"] = module.context.get("_browser_profile_scope")
        return {"status": "success", "action": "reused", "is_owner": False}

    monkeypatch.setattr(BrowserEnsureModule, "execute", observe_scope)
    invocation = InvokeTemplate(
        params={"template_id": "child", "library_id": "child"},
        context={"_browser_profile_scope": scope},
    )

    await invocation._execute_in_process(
        definition={
            "steps": [
                {"id": "ensure", "module": "browser.ensure", "params": {}}
            ]
        },
        params={},
    )

    assert seen["scope"] is scope
