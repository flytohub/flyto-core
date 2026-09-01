# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""What the three `sandbox.execute_*` modules may claim, on both their returns.

These three have a shape that makes the envelope load-bearing rather than
decorative: BOTH of their returns say ``ok: True``. A command that ran and
exited 0 and a command that was killed half-way through look the same to any
consumer reading `ok`, and nearly the same to one reading `exit_code`, since
the timeout path writes ``-1`` -- a number this file chose, not one the kernel
reported. The rung is the only field that separates them.

Real subprocesses throughout. An exit code is a measurement precisely because
the kernel produced it, so faking it would leave the claim resting on a mock.

The argument most likely to be attacked later is in
:class:`TestANonZeroExitIsStillObserved`: `shell.exec` calls a non-zero exit
INDETERMINATE and these modules call it OBSERVED. The difference is not
carelessness, it is that `shell.exec` infers something from the exit code and
these do not -- and the test says why.
"""

import shutil
import sys
from contextlib import suppress
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from core.engine.outcome import ClaimBy, Outcome, read_envelope
from core.engine.step_executor.executor import step_outcome
from core.modules.errors import ModuleError
from core.modules.registry import ModuleRegistry


def ensure_modules_loaded():
    from core.modules import atomic  # noqa: F401
    with suppress(Exception):
        from core.modules import third_party  # noqa: F401


ensure_modules_loaded()

HAS_NODE = shutil.which("node") is not None
needs_node = pytest.mark.skipif(not HAS_NODE, reason="node is not installed")


async def run_module(module_id, **params):
    module = ModuleRegistry.get(module_id)
    return await module(params, {}).execute()


def envelope_of(result):
    assert isinstance(result.get("data"), dict), f"no data dict on {result!r}"
    found = read_envelope(result["data"])
    assert found is not None, f"no well-formed envelope on {result['data']!r}"
    return found


def effect_kinds(found):
    return [effect["kind"] for effect in found["effects"]]


# ---------------------------------------------------------------------------
# The exit code is the measurement
# ---------------------------------------------------------------------------


class TestAProcessThatExitedIsObserved:
    @pytest.mark.asyncio
    async def test_python(self):
        result = await run_module("sandbox.execute_python", code="print('hi')")

        assert result["data"]["exit_code"] == 0
        assert result["data"]["stdout"].strip() == "hi"
        found = envelope_of(result)
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_kinds(found) == ["process_exited", "stdout"]

    @pytest.mark.asyncio
    async def test_shell(self):
        result = await run_module("sandbox.execute_shell", command="echo hi")

        found = envelope_of(result)
        assert found["rung"] == Outcome.OBSERVED.value
        assert found["effects"][0]["exit_code"] == 0

    @needs_node
    @pytest.mark.asyncio
    async def test_js(self):
        result = await run_module("sandbox.execute_js", code="console.log('hi')")

        found = envelope_of(result)
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_kinds(found) == ["process_exited", "stdout"]

    @pytest.mark.asyncio
    async def test_a_silent_process_claims_no_output_it_did_not_get(self):
        """Effects name what was witnessed, so an absent stream is absent."""
        result = await run_module("sandbox.execute_python", code="pass")

        assert effect_kinds(envelope_of(result)) == ["process_exited"]

    @pytest.mark.asyncio
    async def test_stderr_is_reported_separately_from_stdout(self):
        result = await run_module(
            "sandbox.execute_python",
            code="import sys; print('out'); print('err', file=sys.stderr)",
        )

        assert effect_kinds(envelope_of(result)) == [
            "process_exited", "stdout", "stderr",
        ]

    @pytest.mark.asyncio
    async def test_the_byte_counts_are_of_what_came_back(self):
        """Not of the code we sent -- that would be `file.write`'s old bug."""
        result = await run_module(
            "sandbox.execute_python", code="print('x' * 100, end='')",
        )

        stdout_effect = envelope_of(result)["effects"][1]
        assert stdout_effect["bytes"] == 100
        assert stdout_effect["bytes"] == len(result["data"]["stdout"])


class TestANonZeroExitIsStillObserved:
    """Where these three deliberately differ from `shell.exec`.

    `shell.exec` sets ``ok: False`` from ``exit_code == 0`` and therefore has an
    inference that can be wrong -- so its non-zero path is INDETERMINATE. These
    modules make no such comparison: they hand back the status and leave `ok`
    True either way. With nothing inferred, there is nothing to be unsure of,
    and what was measured is that the process ran and ended this way.
    """

    @pytest.mark.asyncio
    async def test_a_failing_script_is_observed_not_indeterminate(self):
        result = await run_module(
            "sandbox.execute_python", code="import sys; sys.exit(3)",
        )

        assert result["ok"] is True
        assert result["data"]["exit_code"] == 3
        found = envelope_of(result)
        assert found["rung"] == Outcome.OBSERVED.value
        assert found["claim_by"] == ClaimBy.NONE.value

    @pytest.mark.asyncio
    async def test_an_uncaught_exception_is_a_faithful_report_not_a_failure(self):
        """Exit 1 with a traceback on stderr is the module working."""
        result = await run_module("sandbox.execute_python", code="raise ValueError('x')")

        assert result["data"]["exit_code"] == 1
        assert "ValueError" in result["data"]["stderr"]
        assert envelope_of(result)["rung"] == Outcome.OBSERVED.value

    @pytest.mark.asyncio
    async def test_a_shell_command_that_answers_with_its_status(self):
        """`grep`-shaped: exit 1 means "no match", not "broken"."""
        result = await run_module(
            "sandbox.execute_shell", command="exit 1",
        )

        assert result["data"]["exit_code"] == 1
        found = envelope_of(result)
        assert found["rung"] == Outcome.OBSERVED.value
        assert found["rung"] != Outcome.FAILED.value

    @pytest.mark.asyncio
    async def test_the_effect_says_it_judged_nothing(self):
        result = await run_module(
            "sandbox.execute_shell", command="exit 7",
        )

        detail = envelope_of(result)["effects"][0]["detail"]
        assert "reported, not judged" in detail


# ---------------------------------------------------------------------------
# The timeout
# ---------------------------------------------------------------------------


class TestATimeoutIsIndeterminate:
    @pytest.mark.asyncio
    async def test_python(self):
        """The return that says `ok: True` about a process we killed."""
        result = await run_module(
            "sandbox.execute_python", code="import time; time.sleep(30)", timeout=1,
        )

        assert result["ok"] is True
        found = envelope_of(result)
        assert found["rung"] == Outcome.INDETERMINATE.value
        assert effect_kinds(found) == ["process_started", "process_killed"]

    @pytest.mark.asyncio
    async def test_shell(self):
        result = await run_module(
            "sandbox.execute_shell", command="sleep 30", timeout=1,
        )

        assert envelope_of(result)["rung"] == Outcome.INDETERMINATE.value

    @needs_node
    @pytest.mark.asyncio
    async def test_js(self):
        result = await run_module(
            "sandbox.execute_js",
            code="setTimeout(() => {}, 30000)",
            timeout=1,
        )

        assert envelope_of(result)["rung"] == Outcome.INDETERMINATE.value

    @pytest.mark.asyncio
    async def test_the_minus_one_exit_code_is_not_a_measurement(self):
        """It is written in the module. The effect says so rather than hiding it.

        `wait_for` cancels `communicate()`, so the pipe buffers die with it --
        which is why `stdout` is empty here even for a script that printed
        before it was killed.
        """
        result = await run_module(
            "sandbox.execute_python",
            code="print('I ran', flush=True); import time; time.sleep(30)",
            timeout=1,
        )

        assert result["data"]["exit_code"] == -1
        assert result["data"]["stdout"] == ""
        detail = envelope_of(result)["effects"][1]["detail"]
        assert "not readings" in detail

    @pytest.mark.asyncio
    async def test_a_timeout_is_not_a_low_rung(self):
        """INDETERMINATE is off the ladder, not a modest place on it.

        DISPATCHED would be the tempting "safe" answer and it says something
        different and false: that the instruction left us and stopped there,
        when a process ran for as long as we allowed it and its side effects
        stand.
        """
        result = await run_module(
            "sandbox.execute_shell", command="sleep 30", timeout=1,
        )

        assert envelope_of(result)["rung"] not in {
            Outcome.DISPATCHED.value,
            Outcome.ACCEPTED.value,
            Outcome.OBSERVED.value,
            Outcome.VERIFIED.value,
        }

    @pytest.mark.asyncio
    async def test_a_killed_run_writes_its_side_effects_anyway(self, tmp_path):
        """The concrete reason the timeout is not FAILED and not DISPATCHED.

        The file is on disk after the kill. Something happened; we simply
        cannot say how much of it.
        """
        marker = tmp_path / "written-before-the-kill"
        code = (
            "open(%r, 'w').write('x')\n"
            "import time; time.sleep(30)\n" % str(marker)
        )

        result = await run_module("sandbox.execute_python", code=code, timeout=2)

        assert marker.exists()
        assert envelope_of(result)["rung"] == Outcome.INDETERMINATE.value


# ---------------------------------------------------------------------------
# No holes
# ---------------------------------------------------------------------------


class TestBothReturnsCarryAFullEnvelope:
    @pytest.mark.asyncio
    async def test_every_returning_path_of_every_module(self):
        cases = [
            ("sandbox.execute_python", {"code": "print(1)"}),
            ("sandbox.execute_python",
             {"code": "import time; time.sleep(30)", "timeout": 1}),
            ("sandbox.execute_shell", {"command": "echo 1"}),
            ("sandbox.execute_shell", {"command": "sleep 30", "timeout": 1}),
        ]
        if HAS_NODE:
            cases += [
                ("sandbox.execute_js", {"code": "console.log(1)"}),
                ("sandbox.execute_js",
                 {"code": "setTimeout(() => {}, 30000)", "timeout": 1}),
            ]

        for module_id, params in cases:
            found = envelope_of(await run_module(module_id, **params))
            assert set(found) == {
                "rung", "claim_by", "postcondition", "effects", "evidence_ref"
            }, (module_id, params)
            # None of the three declares a postcondition, so none of them may
            # be rendered as done.
            assert found["rung"] != Outcome.VERIFIED.value, (module_id, params)
            assert found["postcondition"] is None, (module_id, params)

    @pytest.mark.asyncio
    async def test_the_raising_path_has_no_dict_to_annotate(self):
        """Written down so the next reader does not hunt for a third envelope.

        A validation failure raises `ModuleError`; the result dict that would
        have carried an envelope never exists.
        """
        with pytest.raises(ModuleError):
            await run_module("sandbox.execute_python", code="   ")

    @pytest.mark.asyncio
    async def test_both_rungs_reach_a_step_consumer(self):
        ran = await run_module("sandbox.execute_shell", command="echo 1")
        killed = await run_module(
            "sandbox.execute_shell", command="sleep 30", timeout=1,
        )

        assert step_outcome(ran)[0] is Outcome.OBSERVED
        assert step_outcome(killed)[0] is Outcome.INDETERMINATE
