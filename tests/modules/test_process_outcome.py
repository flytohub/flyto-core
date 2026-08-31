# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""What `process.start`, `process.stop` and `process.list` may claim.

Real children, not fakes. Process state is one of the few things in this
product that is genuinely observable -- an exit code comes from the kernel and
`os.kill(pid, 0)` asks the process table -- so mocking it away would test the
mock instead of the thing the rung rests on. Every process spawned here is
`sys.executable`, and every test tears its children down.

The argument these tests exist to pin, module by module:

* `process.start` is the one place in this group where a CALLER states what
  success means. `wait_for_output` is a predicate the caller wrote and the
  module evaluates, so the three answers to it are attributable to the caller:
  seen -> OBSERVED, process died first -> FAILED, timer expired ->
  INDETERMINATE. Without that parameter nothing is evaluated at all and the
  honest claim is only ACCEPTED, however confident the `ok: True` looks.
* `process.stop` runs two different mechanisms under one id. A registered child
  is reaped and its exit status read; an unregistered pid is only signalled.
  Those are OBSERVED and ACCEPTED and they must not be flattened together.
* `process.list` is OBSERVED only when it probed something.
"""

import asyncio
import os
import signal
import sys
from contextlib import suppress
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from core.engine.outcome import ClaimBy, Outcome, read_envelope
from core.engine.step_executor.executor import step_outcome
from core.modules.atomic.process.start import get_process_registry
from core.modules.items import items_to_legacy_context, wrap_legacy_result
from core.modules.registry import ModuleRegistry


def ensure_modules_loaded():
    from core.modules import atomic  # noqa: F401
    with suppress(Exception):
        from core.modules import third_party  # noqa: F401


ensure_modules_loaded()

PY = sys.executable


async def run_module(module_id, **params):
    module = ModuleRegistry.get(module_id)
    return await module(params, {}).execute()


def envelope_of(result):
    """The envelope on a flat-dict module result, insisting it is well-formed."""
    found = read_envelope(result)
    assert found is not None, f"no well-formed envelope on {result!r}"
    return found


def effect_kinds(found):
    return [effect["kind"] for effect in found["effects"]]


@pytest.fixture(autouse=True)
def clean_registry():
    """Leave no child of one test alive to be counted by the next."""
    registry = get_process_registry()
    registry.clear()
    yield registry
    for info in list(registry.values()):
        # os.kill on the pid, not `process.kill()`: the transport belongs to a
        # loop that pytest-asyncio has already closed by teardown.
        pid = info.get("pid")
        if pid:
            with suppress(Exception):
                os.kill(pid, signal.SIGKILL)
    registry.clear()


# ---------------------------------------------------------------------------
# process.start
# ---------------------------------------------------------------------------


class TestStartWithoutAnExpectationIsOnlyAccepted:
    @pytest.mark.asyncio
    async def test_a_spawn_with_nothing_to_check_is_accepted(self):
        result = await run_module(
            "process.start",
            command=f'{PY} -c "import time; time.sleep(30)"',
            name="sleeper",
        )

        assert result["ok"] is True
        assert result["pid"] > 0
        found = envelope_of(result)
        assert found["rung"] == Outcome.ACCEPTED.value
        assert effect_kinds(found) == ["process_spawned"]
        assert found["claim_by"] == ClaimBy.NONE.value

    @pytest.mark.asyncio
    async def test_a_command_that_cannot_run_still_reaches_this_return(self):
        """The reason ACCEPTED is the ceiling and not OBSERVED.

        `create_subprocess_shell` spawns a shell, and the shell exits 127 on a
        missing binary -- after the pid exists. This module never looks, so a
        command that could not possibly have run returns `ok: True` with a pid,
        indistinguishable from a healthy start. The rung is what says so.
        """
        result = await run_module(
            "process.start",
            command="definitely-not-a-real-binary-xyzzy",
            name="doomed",
        )

        assert result["ok"] is True
        assert envelope_of(result)["rung"] == Outcome.ACCEPTED.value

    @pytest.mark.asyncio
    async def test_the_effect_says_the_pid_proves_only_the_spawn(self):
        result = await run_module(
            "process.start",
            command=f'{PY} -c "import time; time.sleep(30)"',
        )

        effect = envelope_of(result)["effects"][0]
        assert effect["pid"] == result["pid"]
        assert "exits 127" in effect["detail"]


class TestStartWithAnExpectationIsClaimedByTheCaller:
    @pytest.mark.asyncio
    async def test_the_expected_output_is_observed(self):
        result = await run_module(
            "process.start",
            command=f'{PY} -u -c "print(\'ready on 8080\'); import time; time.sleep(30)"',
            name="server",
            wait_for_output="ready on",
            wait_timeout=15,
        )

        assert result["ok"] is True
        found = envelope_of(result)
        assert found["rung"] == Outcome.OBSERVED.value
        assert found["claim_by"] == ClaimBy.CALLER.value
        assert effect_kinds(found) == ["process_spawned", "expected_output_seen"]

    @pytest.mark.asyncio
    async def test_the_predicate_that_was_evaluated_travels_with_it(self):
        """`postcondition` is the human-readable predicate, not a promise.

        Carrying it does not make the claim VERIFIED: `register_module`
        declares no postcondition for this module, so `ceiling_for` caps it at
        OBSERVED -- which is right, because the predicate is whatever string
        the caller passed, not a property of having started a process.
        """
        result = await run_module(
            "process.start",
            command=f'{PY} -u -c "print(\'listening\'); import time; time.sleep(30)"',
            wait_for_output="listening",
            wait_timeout=15,
        )

        found = envelope_of(result)
        assert "'listening'" in found["postcondition"]
        assert found["rung"] != Outcome.VERIFIED.value

    @pytest.mark.asyncio
    async def test_a_process_that_exits_first_is_a_broken_contract(self):
        """FAILED, and claimed by the caller -- the split `outcome.py` describes.

        The caller said what starting meant. The process is gone and cannot
        ever print it, so the question is settled and settled badly. Nothing
        here is an inference of ours.

        The command holds the stdout pipe open in a background child on
        purpose. `process.start` chooses between this return and WAIT_TIMEOUT
        on `process.returncode is not None`, and a plain `sys.exit(3)` races
        the event loop's child watcher: end-of-file can reach the read loop
        before the watcher has recorded the status. Blocking the pipe forces
        the one-second readline timeout, whose branch checks the returncode
        explicitly, so which return is taken is decided rather than raced.
        """
        result = await run_module(
            "process.start",
            command=f'{PY} -c "import time; time.sleep(2)" & exit 3',
            wait_for_output="ready on",
            wait_timeout=15,
        )

        assert result["error_code"] == "PROCESS_EXITED_EARLY"
        found = envelope_of(result)
        assert found["rung"] == Outcome.FAILED.value
        assert found["claim_by"] == ClaimBy.CALLER.value
        assert found["effects"][0]["exit_code"] == 3

    @pytest.mark.asyncio
    async def test_a_wait_that_ran_out_is_indeterminate_not_failed(self):
        """The process is still running. It may print the string next second.

        A slow-booting dev server is the ordinary case, and FAILED here would
        put a red mark on one that came up a moment after we stopped watching.
        """
        result = await run_module(
            "process.start",
            command=f'{PY} -c "import time; time.sleep(30)"',
            wait_for_output="never appears",
            wait_timeout=1,
        )

        assert result["error_code"] == "WAIT_TIMEOUT"
        found = envelope_of(result)
        assert found["rung"] == Outcome.INDETERMINATE.value
        assert found["claim_by"] == ClaimBy.CALLER.value
        assert effect_kinds(found) == ["process_started", "process_not_reaped"]
        with suppress(Exception):
            os.kill(result["pid"], signal.SIGKILL)

    @pytest.mark.asyncio
    async def test_the_timeout_does_not_claim_the_child_is_alive(self):
        """`returncode is None` is set by a watcher that can lag a real exit."""
        result = await run_module(
            "process.start",
            command=f'{PY} -c "import time; time.sleep(30)"',
            wait_for_output="never appears",
            wait_timeout=1,
        )

        detail = envelope_of(result)["effects"][1]["detail"]
        assert "Not proof the child is alive" in detail
        with suppress(Exception):
            os.kill(result["pid"], signal.SIGKILL)


class TestStartRefusalsSpawnedNothing:
    @pytest.mark.asyncio
    async def test_a_missing_working_directory_is_failed_with_no_effects(self, tmp_path):
        result = await run_module(
            "process.start",
            command=f'{PY} -c "pass"',
            cwd=str(tmp_path / "no-such-directory"),
        )

        assert result["error_code"] == "INVALID_CWD"
        found = envelope_of(result)
        assert found["rung"] == Outcome.FAILED.value
        # Empty, and not merely small: this returns before the spawn.
        assert found["effects"] == []


# ---------------------------------------------------------------------------
# process.stop
# ---------------------------------------------------------------------------


class TestStoppingARegisteredChildIsObserved:
    @pytest.mark.asyncio
    async def test_the_exit_status_is_what_earns_the_rung(self):
        """`await process.wait()` returns only once the child is reaped.

        An exit code is unobtainable while a process is still running, which is
        what makes this different from the signal-only path below.
        """
        started = await run_module(
            "process.start",
            command=f'{PY} -c "import time; time.sleep(30)"',
            name="victim",
        )

        result = await run_module("process.stop", process_id=started["process_id"])

        assert result["ok"] is True
        assert result["count"] == 1
        assert result["stopped"][0]["exit_code"] is not None
        found = envelope_of(result)
        assert found["rung"] == Outcome.OBSERVED.value
        assert found["effects"][0]["kind"] == "processes_reaped"
        assert found["effects"][0]["count"] == 1

    @pytest.mark.asyncio
    async def test_an_unknown_process_id_signalled_nothing(self):
        result = await run_module("process.stop", process_id="no-such-process")

        assert result["error_code"] == "NOT_FOUND"
        found = envelope_of(result)
        assert found["rung"] == Outcome.FAILED.value
        assert found["effects"] == []

    @pytest.mark.asyncio
    async def test_a_name_that_matched_nothing_did_nothing(self):
        """`ok: True, count: 0` is otherwise indistinguishable from success."""
        result = await run_module("process.stop", stop_all=True)

        assert result["ok"] is True
        assert result["count"] == 0
        found = envelope_of(result)
        assert found["rung"] == Outcome.DISPATCHED.value
        assert effect_kinds(found) == ["no_process_matched"]

    @pytest.mark.asyncio
    async def test_no_identifier_at_all_is_failed(self):
        result = await run_module("process.stop")

        assert result["error_code"] == "NO_IDENTIFIER"
        found = envelope_of(result)
        assert found["rung"] == Outcome.FAILED.value
        assert found["effects"] == []

    @pytest.mark.asyncio
    async def test_a_registry_entry_with_no_process_object_is_failed(self, clean_registry):
        """Nothing was signalled, so nothing may be claimed for it."""
        clean_registry["ghost-1"] = {"name": "ghost", "pid": 1}

        result = await run_module("process.stop", process_id="ghost-1")

        assert result["ok"] is False
        assert result["count"] == 0
        found = envelope_of(result)
        assert found["rung"] == Outcome.FAILED.value
        assert effect_kinds(found) == ["stop_failed"]

    @pytest.mark.asyncio
    async def test_a_mixed_batch_has_no_single_rung(self, clean_registry):
        """One child reaped, one entry that could not be touched.

        Neither half is the answer: OBSERVED would hide the failure and FAILED
        would deny the reaping. INDETERMINATE with both counts is what is true.
        """
        started = await run_module(
            "process.start",
            command=f'{PY} -c "import time; time.sleep(30)"',
            name="real",
        )
        clean_registry["ghost-1"] = {"name": "ghost", "pid": 1}

        result = await run_module("process.stop", stop_all=True)

        assert result["count"] == 1
        assert len(result["failed"]) == 1
        found = envelope_of(result)
        assert found["rung"] == Outcome.INDETERMINATE.value
        assert effect_kinds(found) == ["processes_reaped", "stop_failed"]
        assert started["process_id"] not in clean_registry


class TestSignallingAnUnregisteredPidIsWeaker:
    @pytest.mark.asyncio
    async def test_sigkill_is_only_accepted(self):
        """`os.kill` returning means the signal was queued, not that it landed.

        Nothing looks afterwards on this path -- so however likely death is,
        the module did not measure it.
        """
        child = await asyncio.create_subprocess_exec(
            PY, "-c", "import time; time.sleep(30)",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            result = await run_module("process.stop", pid=child.pid, force=True)

            assert result["ok"] is True
            found = envelope_of(result)
            assert found["rung"] == Outcome.ACCEPTED.value
            assert effect_kinds(found) == ["signal_accepted"]
        finally:
            with suppress(Exception):
                child.kill()
            await child.wait()

    @pytest.mark.asyncio
    async def test_a_pid_that_is_gone_afterwards_is_observed(self):
        """The probe that was already in `_kill_pid_directly`, now reported.

        `os.kill(pid, 0)` raising ProcessLookupError is the OS saying no
        process holds that number. That is a reading of the process table, and
        it is the only evidence of death anywhere on this path.
        """
        child = await asyncio.create_subprocess_exec(
            PY, "-c", "import time; time.sleep(30)",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        pid = child.pid
        try:
            result = await run_module(
                "process.stop", pid=pid, signal="SIGTERM", timeout=1,
            )
            # Reap it so the probe inside the module saw a real disappearance
            # rather than a zombie this test left behind.
            await child.wait()

            found = envelope_of(result)
            assert found["rung"] in {
                Outcome.OBSERVED.value, Outcome.ACCEPTED.value,
            }
            if found["rung"] == Outcome.OBSERVED.value:
                assert found["effects"][0]["kind"] == "process_gone"
                assert "ProcessLookupError" in found["effects"][0]["measured_by"]
            else:
                # A zombie answers `os.kill(pid, 0)`, so on a platform where the
                # child had not been reaped in time the honest answer is the
                # weaker one -- which is exactly what the module says.
                assert found["effects"][0]["kind"] == "signal_accepted"
        finally:
            with suppress(Exception):
                child.kill()
            with suppress(Exception):
                await child.wait()

    @pytest.mark.asyncio
    async def test_a_pid_that_does_not_exist_signalled_nothing(self):
        # 2**22 is above every default pid_max, so nothing holds it.
        result = await run_module("process.stop", pid=4194303)

        assert result["error_code"] == "NOT_FOUND"
        found = envelope_of(result)
        assert found["rung"] == Outcome.FAILED.value
        assert found["effects"] == []


# ---------------------------------------------------------------------------
# process.list
# ---------------------------------------------------------------------------


class TestListIsObservedOnlyWhenItProbed:
    @pytest.mark.asyncio
    async def test_probing_a_live_child_is_observed(self):
        await run_module(
            "process.start",
            command=f'{PY} -c "import time; time.sleep(30)"',
            name="listed",
        )

        result = await run_module("process.list")

        assert result["running"] == 1
        found = envelope_of(result)
        assert found["rung"] == Outcome.OBSERVED.value
        assert found["effects"][0]["probed"] == 1
        assert "os.kill(pid, 0)" in found["effects"][0]["measured_by"]

    @pytest.mark.asyncio
    async def test_reading_the_registry_without_probing_is_only_dispatched(self):
        """`include_status` false means nothing outside this process is asked.

        Every field returned then is our own bookkeeping repeated back, and
        `status` is the literal 'unknown'.
        """
        await run_module(
            "process.start",
            command=f'{PY} -c "import time; time.sleep(30)"',
            name="listed",
        )

        result = await run_module("process.list", include_status=False)

        assert result["count"] == 1
        found = envelope_of(result)
        assert found["rung"] == Outcome.DISPATCHED.value
        assert effect_kinds(found) == ["registry_read_only"]

    @pytest.mark.asyncio
    async def test_an_empty_registry_measured_nothing(self):
        result = await run_module("process.list")

        assert result["count"] == 0
        found = envelope_of(result)
        assert found["rung"] == Outcome.DISPATCHED.value
        assert found["effects"][0]["entries"] == 0

    @pytest.mark.asyncio
    async def test_the_probe_records_what_it_cannot_tell_apart(self):
        """Pid reuse and zombies both defeat `os.kill(pid, 0)`.

        The rung stands -- a syscall did answer -- but a consumer reading
        `running: 1` deserves to find the limit written down beside it.
        """
        await run_module(
            "process.start",
            command=f'{PY} -c "import time; time.sleep(30)"',
        )

        detail = envelope_of(await run_module("process.list"))["effects"][0]["detail"]
        assert "pids are reused" in detail
        assert "zombie" in detail


# ---------------------------------------------------------------------------
# No holes
# ---------------------------------------------------------------------------


class TestEveryReturnShapeCarriesAnEnvelope:
    @pytest.mark.asyncio
    async def test_start_has_one_on_all_four_returning_shapes(self, tmp_path):
        # Sets rather than single codes for the two wait paths: the module
        # chooses between them on a `returncode` the event loop's child watcher
        # may not have recorded yet, and which of the two a given run takes is
        # not what this test is about. That every one of them carries a full
        # envelope is.
        cases = [
            ({"INVALID_CWD"}, {
                "command": f'{PY} -c "pass"',
                "cwd": str(tmp_path / "nope"),
            }),
            ({"PROCESS_EXITED_EARLY", "WAIT_TIMEOUT"}, {
                "command": f'{PY} -c "import sys; sys.exit(1)"',
                "wait_for_output": "never",
                "wait_timeout": 2,
            }),
            ({"WAIT_TIMEOUT", "PROCESS_EXITED_EARLY"}, {
                "command": f'{PY} -c "import time; time.sleep(30)"',
                "wait_for_output": "never",
                "wait_timeout": 1,
            }),
            ({None}, {"command": f'{PY} -c "import time; time.sleep(30)"'}),
        ]

        for expected_codes, params in cases:
            result = await run_module("process.start", **params)
            assert result.get("error_code") in expected_codes, result
            found = envelope_of(result)
            assert set(found) == {
                "rung", "claim_by", "postcondition", "effects", "evidence_ref"
            }, expected_codes
            assert found["rung"] != Outcome.VERIFIED.value, expected_codes
            if result.get("pid"):
                with suppress(Exception):
                    os.kill(result["pid"], signal.SIGKILL)

    @pytest.mark.asyncio
    async def test_stop_has_one_on_all_five_returning_shapes(self):
        child = await asyncio.create_subprocess_exec(
            PY, "-c", "import time; time.sleep(30)",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            started = await run_module(
                "process.start",
                command=f'{PY} -c "import time; time.sleep(30)"',
                name="shape",
            )
            calls = [
                {"process_id": "no-such-process"},          # NOT_FOUND
                {},                                          # NO_IDENTIFIER
                {"pid": 4194303},                            # NOT_FOUND, direct
                {"pid": child.pid, "force": True},           # direct kill
                {"process_id": started["process_id"]},       # registered stop
                {"stop_all": True},                          # nothing matched
            ]
            for params in calls:
                found = envelope_of(await run_module("process.stop", **params))
                assert set(found) == {
                    "rung", "claim_by", "postcondition", "effects", "evidence_ref"
                }, params
                assert found["rung"] != Outcome.VERIFIED.value, params
        finally:
            with suppress(Exception):
                child.kill()
            await child.wait()


class TestTheStepExecutorCanReadTheseShapes:
    @pytest.mark.asyncio
    async def test_an_accepted_start_reaches_step_outcome(self):
        result = await run_module(
            "process.start",
            command=f'{PY} -c "import time; time.sleep(30)"',
        )
        rung, _, _ = step_outcome(result)
        assert rung is Outcome.ACCEPTED

    @pytest.mark.asyncio
    async def test_the_envelope_survives_the_legacy_wrap_on_a_success(self):
        """process.start returns a flat dict, so `wrap_legacy_result` folds it
        into the single item's json and it lands inside `data` -- which is
        where every consumer is told to look."""
        result = await run_module(
            "process.start",
            command=f'{PY} -c "import time; time.sleep(30)"',
        )
        legacy = items_to_legacy_context(wrap_legacy_result(result))

        assert legacy["ok"] is True
        assert read_envelope(legacy["data"])["rung"] == Outcome.ACCEPTED.value

    @pytest.mark.asyncio
    async def test_an_error_return_loses_its_envelope_in_the_legacy_wrap(self, tmp_path):
        """A hole this slice cannot close, pinned so it is not mistaken for done.

        `wrap_legacy_result` turns `ok: False` into an ERROR result, and
        `to_legacy_dict` renders that as `{ok, error, error_code}` with no
        `data` -- so the envelope on every failure path is dropped before a
        step-level consumer sees it. It is still readable from the raw module
        result, and the fix belongs in `items.py`, which this slice does not own.
        """
        result = await run_module(
            "process.start",
            command=f'{PY} -c "pass"',
            cwd=str(tmp_path / "nope"),
        )
        assert read_envelope(result) is not None

        legacy = items_to_legacy_context(wrap_legacy_result(result))
        assert legacy["ok"] is False
        assert "data" not in legacy
        assert step_outcome(legacy) is None
