# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Why `robotics.move`, `robotics.turn` and `robotics.stop` still claim nothing.

THE PASS THIS FILE RECORDS was asked to make these three state their own rung so
the engine's default would stop applying. It ends with no rung declared, and
this file is the reason written down, because the brief and the code disagree
about what these modules do.

WHAT THEY ACTUALLY DO, measured by running them (`TestTheStepDeclaresAndSends`):
a robotics step *builds a plan document and returns it*. `execute()` calls
`preview_plan_for_step`, wraps the result in a run-request, and returns
`{"dispatched": False, ...}` -- those words, in the payload. `modules.py` never
imports `gateway.py`, which is the module beside it that knows how to reach a
robot; the package's own docstring says why, and it is not an oversight:
flyto-core runs on a worker or a desktop, and `127.0.0.1:8766` there is not the
robot. The plan is carried out later, on the Pi, by `deploy/flyto_job_runner.py`
-- which does not even read this payload. It rebuilds the plan itself from the
authored step through `trusted_plan_for_step`. So the `request` these modules
return is never sent by anybody. Nothing leaves this machine.

WHAT THE ENGINE SAYS ABOUT THEM (`TestTheEngineStampsAnInstructionThatNeverLeft`):
`dispatched` -- "the instruction left us; nobody confirmed receipt" -- sitting in
the same dict as `dispatched: False`. On the refusal path too, where the plan
could not even be built and the payload is nothing but an error string. That is
not a rung that overstates by a little. It is a claim that a robot was told to
move by a step that told nobody anything.

WHY THE FIX IS NOT A RUNG. Every rung on the ladder is a statement about how far
an effect was followed, and these steps attempt no effect:

    dispatched      false. Nothing was sent.
    accepted        false. Nobody acknowledged anything.
    observed        false. Nothing was read back; no robot was contacted.
    verified        false, and the ceiling forbids it anyway.
    failed          false on the declaring path. The step did its whole job.
    indeterminate   the tempting one, and the one to refuse. On a robot,
                    "indeterminate" is a load-bearing word: the brief for this
                    pass defines it as a move that TIMED OUT -- the robot may
                    still be moving. Spending it on "no instruction was ever
                    sent" would fold those two into one value for an operator
                    deciding whether to walk in front of the thing. That is the
                    `unverified` mistake `engine/outcome.py` exists to undo,
                    made on the modules where it costs the most.

The honest envelope for a plan builder is no envelope, and `default_for` already
knows how to produce one: it returns None for a module that is not
side-effecting. `TestOneFlagIsTheWholeReason` measures that these three are in
the side-effecting population for exactly one reason -- `requires_credentials=True`
-- and that the flag is backed by nothing: `credential_keys` is empty,
`required_permissions` is empty, and no line in `modules.py`, `steps.py` or
`plan.py` reads a token, an env var or a socket. Set it to False and
`default_for` returns None for all three, on today's code, with no change to
`engine/outcome.py`. That is measured here, not asserted.

THAT CHANGE IS NOT IN THIS TREE. These modules are registered from the installed
`flyto_modules_robotics` package; `inspect.getsourcefile` points into
flyto-modules-robotics, a separate repository, and `requires_credentials` on a
robot-motion module is security-relevant metadata that a sweep should report
rather than flip. So all three stay on UNDECLARED, and every fact above is
pinned here so that when someone does make the change, the tests that must
change are named.

OVERLAP: `test_robotics_vision_agent_outcome.py` pins two of these facts for
`robotics.move` alone, from the other group's pass. Kept, not moved -- this file
is the robotics group's, covers all three modules and both return paths, and
duplicating one assertion is cheaper than leaving that file with a dangling
reference.

Nothing here needs a robot, a gateway or a network. `flyto_modules_robotics` is
NOT installed in CI, so every test skips without it -- via `ModuleRegistry.has`,
never `ModuleRegistry.get`, which RAISES for a module the registry does not hold
and would turn a skip into an error.
"""

import asyncio
import ast
import inspect
import sys
from contextlib import suppress
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from core.engine.outcome import (
    Outcome,
    SIDE_EFFECT_CATEGORIES,
    default_for,
    is_side_effecting,
    read_envelope,
)
from core.engine.step_executor.executor import _apply_outcome_contract, step_outcome
from core.modules.registry import ModuleRegistry


def ensure_modules_loaded():
    from core.modules import atomic  # noqa: F401 - registers every module
    with suppress(Exception):
        from core.modules import composite  # noqa: F401


ensure_modules_loaded()


GROUP = ["robotics.move", "robotics.turn", "robotics.stop"]

#: Parameters that build a plan, and the ones that cannot. The refusal is not a
#: contrived value: `_robot_id` falls back to `context['resource_id']`, and an
#: empty one makes `plan._identifier` raise `robot_id is required`. A workflow
#: step that was never dispatched to a device reaches it.
DECLARES = {
    "robotics.move": {"distance_m": 0.5},
    "robotics.turn": {"degrees": 90},
    "robotics.stop": {},
}


@pytest.fixture(autouse=True)
def _skip_without_the_extension():
    """`has`, not `get`.

    `ModuleRegistry.get` raises ValueError for a module it does not hold
    (`registry/core.py`) and never returns None, so a guard written against None
    fires as an ERROR at setup instead of a skip -- a mistake this project has
    already made once, and the reason the guard is spelled this way.
    """
    pytest.importorskip(
        "flyto_modules_robotics",
        reason="the optional robotics extension is not installed",
    )
    missing = [module_id for module_id in GROUP if not ModuleRegistry.has(module_id)]
    if missing:
        pytest.skip(f"flyto_modules_robotics registered no {missing}")


def run(module_id, params, context=None):
    """Execute a step the way the engine does, and return its raw payload."""
    module = ModuleRegistry.get(module_id)
    return asyncio.run(module(dict(params), dict(context or {})).execute())


def stamped(module_id, params, context=None):
    """The payload after the engine has applied the outcome contract to it."""
    module = ModuleRegistry.get(module_id)
    instance = module(dict(params), dict(context or {}))
    return _apply_outcome_contract(instance, asyncio.run(instance.execute()))


def source_tree(module_id):
    """The AST of the file the module is actually registered from."""
    path = inspect.getsourcefile(ModuleRegistry.get(module_id))
    return ast.parse(Path(path).read_text(encoding="utf-8")), path


# ===========================================================================
# What the step does
# ===========================================================================


class TestTheStepDeclaresAndSends:
    """The premise everything else rests on: nothing is sent from here."""

    @pytest.mark.parametrize("module_id", GROUP)
    def test_the_payload_says_it_did_not_dispatch(self, module_id):
        payload = run(module_id, DECLARES[module_id], {"resource_id": "robot-1"})

        assert payload["dispatched"] is False
        assert payload["requires_device"] == "robot-1"
        # The plan is a document naming a device, not a command to one.
        assert payload["request"]["plan"]["robot_id"] == "robot-1"

    @pytest.mark.parametrize("module_id", GROUP)
    def test_every_plan_ends_in_a_safe_stop(self, module_id):
        """The one property of the document worth asserting from here.

        Not an outcome claim -- a robot never saw it. It is what makes the
        payload legible as a plan rather than as a dispatch record.
        """
        plan = run(module_id, DECLARES[module_id], {"resource_id": "robot-1"})["request"]["plan"]

        assert plan["steps"][-1]["capability"] == "safe_stop"

    @pytest.mark.parametrize("module_id", GROUP)
    def test_the_registered_file_never_reaches_the_gateway(self, module_id):
        """Read out of the source, because this is the load-bearing claim.

        `gateway.py` sits beside `modules.py` in the same package and knows how
        to start a plan, poll a session and safe-stop it. If a step ever calls
        it, `dispatched` stops being a lie and this whole file is wrong -- so
        the import is what is asserted, not a docstring's promise.
        """
        tree, path = source_tree(module_id)
        imported = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        } | {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }

        assert not any("gateway" in name for name in imported), (
            f"{path} now imports the gateway. A step that can reach a robot may "
            f"be able to earn a rung; re-read this file before deleting it."
        )

    @pytest.mark.parametrize("module_id", GROUP)
    def test_a_step_that_names_no_device_refuses_instead(self, module_id):
        """The other return path. It builds nothing at all."""
        payload = run(module_id, DECLARES[module_id], {})

        assert payload["dispatched"] is False
        assert payload["requires_device"] == ""
        assert "robot_id is required" in payload["error"]
        assert "request" not in payload


# ===========================================================================
# What the engine says about it
# ===========================================================================


class TestTheEngineStampsAnInstructionThatNeverLeft:
    """The finding this pass was asked to confirm, confirmed by running it."""

    @pytest.mark.parametrize("module_id", GROUP)
    def test_the_module_claims_no_rung_of_its_own(self, module_id):
        payload = run(module_id, DECLARES[module_id], {"resource_id": "robot-1"})

        assert read_envelope(payload) is None, (
            f"{module_id} now reports an outcome of its own. Take it off "
            f"UNDECLARED in tests/core/test_outcome_declaration_coverage.py and "
            f"rewrite this file around whatever it measured."
        )

    @pytest.mark.parametrize("module_id", GROUP)
    def test_the_default_contradicts_the_payload_in_the_same_dict(self, module_id):
        """`dispatched: False` and `"rung": "dispatched"`, one key apart."""
        result = stamped(module_id, DECLARES[module_id], {"resource_id": "robot-1"})

        assert result["dispatched"] is False
        assert result["outcome"]["rung"] == Outcome.DISPATCHED.value
        assert result["outcome"]["effects"] == []
        assert result["outcome"]["postcondition"] is None
        # And it is what a consumer reading the step would act on.
        assert step_outcome(result)[0] is Outcome.DISPATCHED

    @pytest.mark.parametrize("module_id", GROUP)
    def test_even_the_refusal_is_stamped_dispatched(self, module_id):
        """The sharpest form of it, and the one not previously written down.

        On this path the parameters never became a plan. The payload holds an
        error string and nothing else -- no plan_id, no request, no goal -- and
        the engine still stamps "the instruction left us". For `robotics.stop`
        that reads as a safe stop having been sent to a robot by a step that
        could not work out which robot it was for.
        """
        result = stamped(module_id, DECLARES[module_id], {})

        assert result["error"]
        assert "request" not in result
        assert result["outcome"]["rung"] == Outcome.DISPATCHED.value

    @pytest.mark.parametrize("module_id", GROUP)
    def test_the_refusal_is_not_reported_as_a_failed_step(self, module_id):
        """A separate bug, pinned here because it shares the return path.

        `_execute_single_mode` wraps a result only when it carries an `ok` key
        (`step_executor/executor.py`); a dict without one is returned raw and
        the step completes successfully. The refusal payload has no `ok`, so a
        robot step that could not build a plan is a GREEN step carrying an
        `error` field -- and now a `dispatched` rung as well. Reported, not
        fixed: the shape is asserted by flyto-modules-robotics'
        `tests/test_registration.py`, so changing it is that repository's call.
        """
        payload = run(module_id, DECLARES[module_id], {})

        assert "ok" not in payload, (
            f"{module_id} now reports ok/error. If it reports ok=False the step "
            f"fails properly and this test should be deleted."
        )


# ===========================================================================
# Why no rung is written, and the one line that would end it
# ===========================================================================


class TestOneFlagIsTheWholeReason:
    """`requires_credentials=True`, declared with no credential behind it."""

    def test_robotics_is_not_a_side_effecting_category(self):
        assert "robotics" not in SIDE_EFFECT_CATEGORIES

    @pytest.mark.parametrize("module_id", GROUP)
    def test_the_flag_is_the_only_thing_putting_them_in_the_population(self, module_id):
        metadata = ModuleRegistry.get_metadata(module_id) or {}

        assert metadata["requires_credentials"] is True
        assert is_side_effecting(module_id, metadata) is True
        assert is_side_effecting(module_id, {**metadata, "requires_credentials": False}) is False

    @pytest.mark.parametrize("module_id", GROUP)
    def test_nothing_backs_the_flag(self, module_id):
        """Declared credentials: none. Declared permissions: none.

        `validator.py`'s C003 already warns about the first half of this today
        ("requires_credentials=True but no credential source declared"). The
        flag is not describing a secret this module reads -- the delivery token
        is read on the robot, by a different program.
        """
        metadata = ModuleRegistry.get_metadata(module_id) or {}

        assert not metadata.get("credential_keys")
        assert not metadata.get("required_secrets")
        assert not metadata.get("env_vars")
        assert not metadata.get("required_permissions")

    @pytest.mark.parametrize("module_id", GROUP)
    def test_the_registered_file_reads_no_secret(self, module_id):
        """Source again, because metadata is a claim and this is a measurement.

        No `os.environ`, no `getenv`, no `urllib`, no `requests` -- the plan is
        built from parameters, a uuid and a clock. `gateway.py` has all of that
        and is not imported (see the test above).
        """
        _, path = source_tree(module_id)
        text = Path(path).read_text(encoding="utf-8")

        for forbidden in ("os.environ", "getenv", "urllib", "requests", "httpx", "socket"):
            assert forbidden not in text, (
                f"{path} now touches {forbidden!r}; re-check whether "
                f"requires_credentials=True has become true."
            )

    @pytest.mark.parametrize("module_id", GROUP)
    def test_clearing_the_flag_leaves_no_rung_to_stamp(self, module_id):
        """The whole fix, measured on today's code. One line, in another repo.

        `default_for` returns None for a module that is not side-effecting and
        does not derive -- no envelope, which is the honest answer for a step
        that attempts no effect. Nothing in `engine/outcome.py` has to change.
        """
        metadata = ModuleRegistry.get_metadata(module_id) or {}

        assert default_for(module_id, metadata) is Outcome.DISPATCHED
        assert default_for(module_id, {**metadata, "requires_credentials": False}) is None

    @pytest.mark.parametrize("module_id", GROUP)
    def test_the_fix_must_not_arrive_as_a_derives_flag(self, module_id):
        """The other way to make the stamp go away, and it is a trap.

        `derives=True` reads plausible -- the plan IS the return value of a pure
        computation -- and `default_for` would stamp VERIFIED, the one rung a
        surface may render as success. "Move Robot: verified", on a step that
        contacted no robot. The guard in `default_for` is ordering alone: it
        asks about side effects first, so `derives` only bites once
        `requires_credentials` is already gone, and then it bites hard.
        """
        metadata = ModuleRegistry.get_metadata(module_id) or {}

        assert not metadata.get("derives")
        assert default_for(
            module_id, {**metadata, "requires_credentials": False, "derives": True}
        ) is Outcome.VERIFIED

    @pytest.mark.parametrize("module_id", GROUP)
    def test_no_postcondition_is_declared(self, module_id):
        """VERIFIED is unreachable while this holds, whatever else changes."""
        metadata = ModuleRegistry.get_metadata(module_id) or {}

        assert not metadata.get("postcondition"), (
            f"{module_id} declares a postcondition. Nothing in it evaluates a "
            f"predicate about a robot; name the line that does or take it back out."
        )
