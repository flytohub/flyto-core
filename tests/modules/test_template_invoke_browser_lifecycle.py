"""Browser ownership regressions for nested template execution."""

import pytest

from core.modules.atomic.browser.ensure import BrowserEnsureModule  # noqa: F401
from core.modules.atomic.template.invoke import InvokeTemplate


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
