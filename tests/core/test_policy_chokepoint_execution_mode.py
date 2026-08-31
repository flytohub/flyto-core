"""The two module entry points that never reach the chokepoint.

``BaseModule.run`` calls ``enforce_module_policy`` and says of itself, at
``core/modules/base.py:238``, "SECURITY: single execution chokepoint. Every
module ... runs through here". ``enforce_module_policy``'s own docstring
repeats the claim: "because EVERY module ... is executed through this gate, a
denied module cannot run no matter how it was invoked."

``StepExecutor._execute_module`` falsifies both sentences twice. It reads
``execution_mode`` off the instance and, for ``"items"`` and ``"all"``, calls
``execute_item`` / ``execute_all`` directly -- never ``run()``, and so never the
gate. ``BaseModule.execute_item`` defaults to calling ``self.execute()``
straight through, so a module opts out of the security backstop by setting one
class attribute and overriding nothing.

Nothing ships in that state today: the only non-test assignment of the
attribute is the default at ``base.py:82``, and the only ``execute_item`` /
``execute_all`` definitions in shipped source are the two base-class ones. That
is what makes this cheap to close and worth closing now -- the hole is real,
the gate's own documentation denies it exists, and the first module author to
use the feature inherits it silently.
"""

import pytest

import core.module_policy as module_policy
from core.engine.step_executor import StepExecutor
from core.module_policy import ModuleFilter, ModulePolicyError
from core.modules.base import BaseModule
from core.modules.registry import ModuleRegistry


DENIED_ID = "shell.execute_command"


@pytest.fixture
def default_policy(monkeypatch):
    """Deny-by-default: no allowlist, no grants."""
    monkeypatch.delenv("FLYTO_MODULE_ALLOWLIST", raising=False)
    monkeypatch.delenv("FLYTO_MODULE_DENYLIST", raising=False)
    monkeypatch.delenv("FLYTO_GRANTED_PERMISSIONS", raising=False)
    monkeypatch.setattr(module_policy, "module_filter", ModuleFilter())


def _denied_module(mode, ran):
    """A module the policy refuses, that records if its body was reached."""

    class _Refused(BaseModule):
        module_id = DENIED_ID
        execution_mode = mode

        def validate_params(self):
            return True

        async def execute(self):
            ran.append(mode)
            return {"ok": True, "data": {"reached": True}}

        async def execute_item(self, item, index, ctx):
            ran.append(mode)
            return {"reached": True}

        async def execute_all(self, items, ctx):
            ran.append(mode)
            return []

    return _Refused


@pytest.fixture
def registered(monkeypatch):
    """Put a class under DENIED_ID for the executor's registry lookup."""

    def install(module_class):
        monkeypatch.setattr(
            ModuleRegistry,
            "get",
            staticmethod(lambda module_id: module_class if module_id == DENIED_ID else None),
        )
        monkeypatch.setattr(
            module_policy,
            "get_module_metadata",
            lambda module_id: {"required_permissions": ["subprocess.execute"], "plugin": ""},
            raising=False,
        )

    return install


async def _run(mode):
    executor = StepExecutor()
    return await executor._execute_module(
        step_id="one",
        module_id=DENIED_ID,
        params={},
        context={},
        input_items=None,
        step_trace=None,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["single", "items", "all"])
async def test_a_denied_module_is_refused_in_every_execution_mode(
    mode, default_policy, registered
):
    """The gate is about the module, not about how the executor calls it."""
    ran = []
    registered(_denied_module(mode, ran))

    with pytest.raises((ModulePolicyError, Exception)) as caught:
        await _run(mode)

    assert _is_refusal(caught.value), (
        f"execution_mode={mode!r} produced {caught.value!r}, not a policy refusal"
    )
    assert ran == [], f"execution_mode={mode!r} ran the module body before refusing"


def _is_refusal(error):
    """A refusal, however the executor wrapped it on the way out."""
    from core.engine.exceptions import is_policy_refusal

    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        if isinstance(error, ModulePolicyError) or is_policy_refusal(error):
            return True
        error = getattr(error, "__cause__", None) or getattr(error, "cause", None)
    return False
