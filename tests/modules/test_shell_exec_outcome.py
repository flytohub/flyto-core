# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""What shell.exec is entitled to claim, on every path it can return from.

Five return shapes, not one. The success return is the interesting rung, but
the four error returns are where an outcome contract usually rots: an envelope
added only to the happy path leaves every consumer that reads
``data['outcome']`` raising KeyError on precisely the results somebody needed
to look at. ``TestEveryReturnShapeCarriesAnEnvelope`` is the test that stops
that, and it enumerates the shapes by error_code so a sixth one added later
without an envelope fails here rather than in a consumer.

The rungs themselves are pinned individually because each is an argument, not
a lookup, and a future edit that quietly promotes one should have to delete a
test that says why it is wrong.

Every spawn below uses ``sys.executable`` rather than a bare interpreter name:
shell.exec runs children under ``build_sandbox_env``, and pinning the absolute
path keeps these tests measuring the ladder instead of the host's PATH. Its
basename is ``python``, which is on the module's own allowlist.
"""

import shlex
import sys

import pytest

from core.engine.outcome import ClaimBy, Outcome, read_envelope
from core.engine.step_executor.executor import step_outcome
from core.modules.atomic.shell.exec import shell_exec
from core.modules.items import items_to_legacy_context, wrap_legacy_result

PY = shlex.quote(sys.executable)


async def _run(**params):
    """One shell.exec call, through the wrapper the registry actually stores.

    ``execute()`` and not ``run()``: ``run()`` layers the registry's own
    300-second timeout and the policy gate over the call, neither of which is
    what these tests are about.
    """
    return await shell_exec(params, {}).execute()


def _envelope(result):
    """The envelope on a result, insisting it is well-formed.

    ``read_envelope`` returns None for a dict whose ``rung`` is not a rung, so
    a typo in the module cannot pass as a conservative claim here.
    """
    found = read_envelope(result)
    assert found is not None, f"no well-formed envelope on {result!r}"
    return found


# ---------------------------------------------------------------------------
# The rung on each of the five shapes
# ---------------------------------------------------------------------------


class TestSuccessIsObservedAndNoHigher:
    @pytest.mark.asyncio
    async def test_a_clean_exit_is_observed(self):
        """exit 0 read from the OS is a measurement, so OBSERVED is honest."""
        result = await _run(command=f'{PY} -c "print(1)"')

        assert result['ok'] is True
        assert result['exit_code'] == 0
        assert _envelope(result)['rung'] == Outcome.OBSERVED.value

    @pytest.mark.asyncio
    async def test_it_is_never_verified_because_nothing_declares_a_postcondition(self):
        """The ceiling, stated as a test rather than as a comment.

        VERIFIED is "a postcondition was evaluated and it held". This module
        has no parameter through which a caller could state one and
        ``register_module`` has no ``postcondition=`` kwarg to declare one
        with, so there is no predicate a VERIFIED could be *about*. The
        command below exits 0 having done nothing at all, which is the whole
        argument: an exit code says the process ended, not that the effect the
        caller wanted happened.
        """
        result = await _run(command=f'{PY} -c "pass"')

        found = _envelope(result)
        assert found['rung'] != Outcome.VERIFIED.value
        assert found['postcondition'] is None

    @pytest.mark.asyncio
    async def test_effects_name_what_was_witnessed_not_what_was_wanted(self):
        result = await _run(
            command=f'{PY} -c "import sys; print(\'out\'); print(\'err\', file=sys.stderr)"'
        )

        assert _envelope(result)['effects'] == ['process_exited', 'stdout', 'stderr']

    @pytest.mark.asyncio
    async def test_silent_output_is_not_claimed_as_an_effect(self):
        """A process that wrote nothing gets no stdout/stderr effect."""
        result = await _run(command=f'{PY} -c "pass"')

        assert _envelope(result)['effects'] == ['process_exited']

    @pytest.mark.asyncio
    async def test_nobody_claimed_anything_on_a_clean_exit(self):
        assert _envelope(await _run(command=f'{PY} -c "pass"'))['claim_by'] == (
            ClaimBy.NONE.value
        )


class TestNonZeroExitIsIndeterminateNotFailed:
    """The rung this slice is most likely to be argued out of later.

    A non-zero exit is measured, and it is tempting to call it FAILED because
    the module already sets ``ok`` False from the same comparison. But FAILED
    means a postcondition was evaluated and did not hold, and ``exit_code == 0``
    is the module's own inference about what the caller wanted -- which
    outcome.py answers with INDETERMINATE, and which is wrong outright for the
    allowlisted commands that use exit status as an answer.
    """

    @pytest.mark.asyncio
    async def test_a_failing_command_is_indeterminate(self):
        result = await _run(command=f'{PY} -c "import sys; sys.exit(3)"')

        assert result['ok'] is False
        assert result['exit_code'] == 3
        assert _envelope(result)['rung'] == Outcome.INDETERMINATE.value

    @pytest.mark.asyncio
    async def test_the_expectation_is_recorded_as_the_modules_own(self):
        """claim_by is what separates our inference from a caller's contract."""
        result = await _run(command=f'{PY} -c "import sys; sys.exit(1)"')

        assert _envelope(result)['claim_by'] == ClaimBy.INFERRED.value

    @pytest.mark.asyncio
    async def test_grep_style_exit_one_is_not_reported_as_a_broken_contract(self):
        """`grep` exits 1 for "no match" after running exactly as intended.

        This is the concrete reason the rung above is not FAILED. The command
        is simulated rather than shelled out to so the test does not depend on
        a grep being installed, but the exit status it produces is the same
        one grep produces, and the module cannot tell the two apart -- which
        is the point.
        """
        result = await _run(command=f'{PY} -c "import sys; sys.exit(1)"')

        assert _envelope(result)['rung'] != Outcome.FAILED.value

    @pytest.mark.asyncio
    async def test_the_effects_it_did_witness_are_still_reported(self):
        """A failing command still ran, and what it wrote was still observed."""
        result = await _run(
            command=f'{PY} -c "import sys; print(\'partial work\'); sys.exit(2)"'
        )

        assert _envelope(result)['effects'] == ['process_exited', 'stdout']


class TestRefusalsAreFailedBecauseNothingRan:
    @pytest.mark.asyncio
    async def test_a_command_off_the_allowlist(self):
        result = await _run(command='rm -rf /tmp/whatever')

        assert result['error_code'] == 'COMMAND_NOT_ALLOWED'
        found = _envelope(result)
        assert found['rung'] == Outcome.FAILED.value
        assert found['claim_by'] == ClaimBy.NONE.value

    @pytest.mark.asyncio
    async def test_an_unparseable_command_lands_on_the_same_refusal(self):
        """shlex.split raises inside _validate_command, so this is a refusal.

        Worth pinning: it is the reason the EXECUTION_ERROR handler is not the
        one that sees malformed commands.
        """
        result = await _run(command='echo "unbalanced')

        assert result['error_code'] == 'COMMAND_NOT_ALLOWED'
        assert _envelope(result)['rung'] == Outcome.FAILED.value

    @pytest.mark.asyncio
    async def test_a_working_directory_that_does_not_exist(self, tmp_path):
        result = await _run(
            command=f'{PY} -c "pass"',
            cwd=str(tmp_path / 'no-such-directory'),
        )

        assert result['error_code'] == 'INVALID_CWD'
        assert _envelope(result)['rung'] == Outcome.FAILED.value

    @pytest.mark.asyncio
    async def test_a_refusal_claims_no_effects_at_all(self):
        """Empty, and not merely small: `create_subprocess_exec` is unreached."""
        result = await _run(command='rm -rf /')

        assert _envelope(result)['effects'] == []


class TestTimeoutIsIndeterminate:
    @pytest.mark.asyncio
    async def test_a_killed_command_is_indeterminate(self):
        """We stopped waiting; the command may have already done the thing."""
        result = await _run(
            command=f'{PY} -c "import time; time.sleep(30)"',
            timeout=0.4,
        )

        assert result['error_code'] == 'TIMEOUT'
        assert _envelope(result)['rung'] == Outcome.INDETERMINATE.value

    @pytest.mark.asyncio
    async def test_it_reports_only_the_two_things_it_witnessed(self):
        result = await _run(
            command=f'{PY} -c "import time; time.sleep(30)"',
            timeout=0.4,
        )

        assert _envelope(result)['effects'] == ['process_started', 'process_killed']

    @pytest.mark.asyncio
    async def test_a_timeout_is_not_downgraded_to_a_rung(self):
        """INDETERMINATE is off the ladder, not a low place on it.

        DISPATCHED would be the tempting "safe" answer and it is a different
        claim: it says the instruction left us and stops there, when in fact a
        process ran for as long as we let it.
        """
        result = await _run(
            command=f'{PY} -c "import time; time.sleep(30)"',
            timeout=0.4,
        )

        assert _envelope(result)['rung'] not in {
            Outcome.DISPATCHED.value,
            Outcome.ACCEPTED.value,
            Outcome.OBSERVED.value,
            Outcome.VERIFIED.value,
        }


class TestExecutionErrorSplitsOnWhetherAnythingWasSpawned:
    """One return, two honest answers, decided by the `process` sentinel."""

    @pytest.mark.asyncio
    async def test_a_spawn_that_never_happened_is_failed(self, tmp_path):
        """An allowlisted basename on a path that does not exist.

        `_validate_command` only inspects the basename, so this passes the
        allowlist and then FileNotFoundError comes out of
        `create_subprocess_exec`. Nothing ran and we know it.
        """
        missing = tmp_path / 'nowhere' / 'python'
        result = await _run(command=f'{shlex.quote(str(missing))} -c "pass"')

        assert result['error_code'] == 'EXECUTION_ERROR'
        found = _envelope(result)
        assert found['rung'] == Outcome.FAILED.value
        assert found['effects'] == []

    @pytest.mark.asyncio
    async def test_a_failure_after_the_spawn_is_indeterminate(self):
        """A bogus encoding blows up .decode after the command has already run.

        The process really did execute -- the exit code was there for the
        taking -- but this return cannot report any of it, and the module must
        not claim an effect it is in the middle of failing to read.
        """
        result = await _run(
            command=f'{PY} -c "print(1)"',
            encoding='not-a-real-codec',
        )

        assert result['error_code'] == 'EXECUTION_ERROR'
        found = _envelope(result)
        assert found['rung'] == Outcome.INDETERMINATE.value
        assert found['effects'] == ['process_started']


# ---------------------------------------------------------------------------
# No holes
# ---------------------------------------------------------------------------


class TestEveryReturnShapeCarriesAnEnvelope:
    """The test that keeps the other four honest.

    A consumer reading ``data['outcome']`` KeyErrors on any return that lacks
    one, and the returns most likely to be read are the failures.
    """

    @pytest.mark.asyncio
    async def test_all_five_shapes(self, tmp_path):
        missing = shlex.quote(str(tmp_path / 'nowhere' / 'python'))
        calls = {
            'COMMAND_NOT_ALLOWED': {'command': 'rm -rf /'},
            'INVALID_CWD': {
                'command': f'{PY} -c "pass"',
                'cwd': str(tmp_path / 'no-such-directory'),
            },
            'TIMEOUT': {
                'command': f'{PY} -c "import time; time.sleep(30)"',
                'timeout': 0.4,
            },
            'EXECUTION_ERROR': {'command': f'{missing} -c "pass"'},
            None: {'command': f'{PY} -c "pass"'},
        }

        seen = {}
        for expected_code, params in calls.items():
            result = await _run(**params)
            assert result.get('error_code') == expected_code, result
            seen[expected_code] = _envelope(result)

        assert len(seen) == 5
        # Every envelope is the full five-field shape, not a bare rung.
        for found in seen.values():
            assert set(found) == {
                'rung', 'claim_by', 'postcondition', 'effects', 'evidence_ref'
            }


class TestTheStepExecutorCanReadEveryShape:
    """Reaching a consumer is a separate fact from being in the dict.

    ``step_outcome`` is the function that turns a step result into a rung, and
    it is what a ledger entry is built from. It must see all five.
    """

    @pytest.mark.asyncio
    async def test_a_refusal_reaches_step_outcome(self):
        rung, claim_by, _ = step_outcome(await _run(command='rm -rf /'))
        assert rung is Outcome.FAILED
        assert claim_by == ClaimBy.NONE.value

    @pytest.mark.asyncio
    async def test_a_timeout_reaches_step_outcome(self):
        result = await _run(
            command=f'{PY} -c "import time; time.sleep(30)"',
            timeout=0.4,
        )
        rung, _, _ = step_outcome(result)
        assert rung is Outcome.INDETERMINATE

    @pytest.mark.asyncio
    async def test_a_clean_run_reaches_step_outcome(self):
        rung, _, _ = step_outcome(await _run(command=f'{PY} -c "pass"'))
        assert rung is Outcome.OBSERVED

    @pytest.mark.asyncio
    async def test_the_envelope_lands_inside_data_after_the_legacy_wrap(self):
        """Where the contract says it must end up.

        shell.exec returns a flat dict with no ``data`` key, so
        ``wrap_legacy_result`` folds every non-meta field into the single
        item's json and ``to_legacy_dict`` hands back ``{"ok", "data"}``. The
        top-level ``outcome`` key therefore arrives exactly where every
        consumer is told to look, with no sibling-key loss.
        """
        result = await _run(command=f'{PY} -c "pass"')
        legacy = items_to_legacy_context(wrap_legacy_result(result))

        assert legacy['ok'] is True
        assert _envelope(legacy['data'])['rung'] == Outcome.OBSERVED.value

    @pytest.mark.asyncio
    async def test_an_error_return_loses_its_envelope_in_the_legacy_wrap(self):
        """A hole this slice cannot close, pinned so it is not mistaken for done.

        ``wrap_legacy_result`` turns any ``ok: False`` result into an ERROR
        NodeExecutionResult, and ``to_legacy_dict`` renders that as
        ``{ok, error, error_code}`` -- no ``data``, so the envelope on all four
        error paths is dropped before a step-level consumer sees it. The
        envelope IS still readable from the raw module result (the test above
        and ``execute_module`` both take that route), and the fix belongs in
        items.py, which this slice does not own.
        """
        result = await _run(command='rm -rf /')
        assert read_envelope(result) is not None

        legacy = items_to_legacy_context(wrap_legacy_result(result))
        assert legacy['ok'] is False
        assert 'data' not in legacy
        assert step_outcome(legacy) is None


class TestRaiseOnErrorStillRaises:
    @pytest.mark.asyncio
    async def test_the_sixth_path_returns_nothing_to_put_an_envelope_on(self):
        """With raise_on_error, a non-zero exit propagates as an exception.

        There is no dict to annotate on that path -- the envelope built for the
        result is discarded with it -- and this test exists so the next reader
        does not go looking for a sixth envelope that cannot exist.
        """
        with pytest.raises(RuntimeError, match='exit code 5'):
            await _run(
                command=f'{PY} -c "import sys; sys.exit(5)"',
                raise_on_error=True,
            )
