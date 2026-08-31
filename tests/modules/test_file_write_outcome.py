# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""What `file.write` is entitled to claim, and the line of code that earns it.

`file.write` is the worked example in the outcome-ladder brief, because it is
the shape of dishonest reporting that is hardest to see: it returned
``'bytes_written': len(content.encode(encoding))`` and every consumer read that
as "the file is this big". It is arithmetic on the input string. It is
byte-identical when the disk is full and the write silently truncates.

These tests keep two stages apart on purpose:

* :class:`TestWithoutTheStatItIsOnlyAccepted` pins the honest floor -- what this
  module may say when nothing reads the file back. If the observation is ever
  removed, refactored away, or silently starts failing, the claim must fall to
  ACCEPTED rather than keep the rung the observation used to earn.
* :class:`TestTheStatEarnsObserved` writes real files and checks the reported
  size against an independent `stat` from the test itself, so a number that
  quietly went back to being `len(content)` fails here.
"""

import inspect
import sys
from contextlib import suppress
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import core.modules.atomic.file.write as write_module
from core.engine.outcome import ClaimBy, Outcome, ceiling_for, read_envelope
from core.modules.registry import ModuleRegistry, register_module


def ensure_modules_loaded():
    from core.modules import atomic  # noqa: F401
    with suppress(Exception):
        from core.modules import third_party  # noqa: F401


ensure_modules_loaded()

MODULE_ID = "file.write"


async def run_write(**params):
    """Execute `file.write` the way the engine does and return its result dict."""
    module = ModuleRegistry.get(MODULE_ID)
    return await module(params, {}).execute()


def envelope_of(result):
    """The outcome envelope, read the way `step_executor` reads it."""
    return read_envelope(result["data"])


def effect_kinds(found):
    return [effect["kind"] for effect in found["effects"]]


def effect_named(found, kind):
    return next(effect for effect in found["effects"] if effect["kind"] == kind)


# ===========================================================================
# Stage 1 -- the honest floor
# ===========================================================================

class TestWithoutTheStatItIsOnlyAccepted:
    """No read-back, no observation. `open`/`write`/`close` is an acknowledgement."""

    @pytest.fixture
    def blinded(self, monkeypatch):
        """The measurement, unable to answer -- exactly stage 1's world."""
        monkeypatch.setattr(
            write_module,
            "_observe_size_on_disk",
            lambda path: (None, "OSError: stubbed unavailable"),
        )

    @pytest.mark.asyncio
    async def test_the_rung_falls_to_accepted(self, sandboxed_tmp_path, blinded):
        target = sandboxed_tmp_path / "floor.txt"

        result = await run_write(path=str(target), content="Hello World")

        assert result["ok"] is True
        assert target.read_text() == "Hello World"
        assert envelope_of(result)["rung"] == Outcome.ACCEPTED.value

    @pytest.mark.asyncio
    async def test_it_does_not_claim_observed_off_the_old_arithmetic(
        self, sandboxed_tmp_path, blinded
    ):
        """The regression this whole exercise exists to stop.

        `bytes_written` is still returned and still correct as what it is -- the
        encoded length of the content offered. What must never come back is a
        rung resting on it.
        """
        target = sandboxed_tmp_path / "floor.txt"

        result = await run_write(path=str(target), content="Hello World")

        assert result["data"]["bytes_written"] == len("Hello World".encode("utf-8"))
        assert result["data"]["bytes_on_disk"] is None
        assert result["data"]["bytes_added"] is None
        assert envelope_of(result)["rung"] != Outcome.OBSERVED.value

    @pytest.mark.asyncio
    async def test_the_effect_says_the_count_is_of_the_content_offered(
        self, sandboxed_tmp_path, blinded
    ):
        target = sandboxed_tmp_path / "floor.txt"

        result = await run_write(path=str(target), content="Hello World")
        found = envelope_of(result)

        offered = effect_named(found, "file_bytes_offered")
        assert offered["measured_by"] == "len(content.encode(encoding))"
        assert offered["bytes"] == 11
        assert "OFFERED" in offered["detail"]
        assert "not of the file on disk" in offered["detail"]

    @pytest.mark.asyncio
    async def test_the_missing_observation_is_recorded_rather_than_omitted(
        self, sandboxed_tmp_path, blinded
    ):
        """A gap nobody can see is the same defect one rung lower."""
        target = sandboxed_tmp_path / "floor.txt"

        found = envelope_of(await run_write(path=str(target), content="x"))

        assert "file_size_not_observed" in effect_kinds(found)
        assert effect_named(found, "file_size_not_observed")["reason"]

    @pytest.mark.asyncio
    async def test_a_stat_that_really_raises_is_not_an_error_for_the_caller(
        self, sandboxed_tmp_path, monkeypatch
    ):
        """Losing the ability to look does not undo the write.

        A real `os.stat`, refusing for this one file only -- the surrounding
        `os.path.exists` / `os.makedirs` calls still need a working one.
        """
        import os

        target = sandboxed_tmp_path / "real_failure.txt"
        real_stat = os.stat

        def selective_stat(path, *args, **kwargs):
            if str(path).endswith("real_failure.txt"):
                raise PermissionError(13, "Permission denied")
            return real_stat(path, *args, **kwargs)

        monkeypatch.setattr(os, "stat", selective_stat)

        result = await run_write(path=str(target), content="still written")
        monkeypatch.undo()

        assert result["ok"] is True
        assert target.read_text() == "still written"
        assert envelope_of(result)["rung"] == Outcome.ACCEPTED.value


# ===========================================================================
# Stage 2 -- the measurement, and the rung that follows it
# ===========================================================================

class TestTheStatEarnsObserved:
    @pytest.mark.asyncio
    async def test_a_real_write_reports_the_size_the_filesystem_reports(
        self, sandboxed_tmp_path
    ):
        target = sandboxed_tmp_path / "observed.txt"
        content = "Hello World\nsecond line\n"

        result = await run_write(path=str(target), content=content)

        # The test stats the file itself. If `bytes_on_disk` ever goes back to
        # being computed from the input, this is the assertion that catches it.
        assert result["data"]["bytes_on_disk"] == target.stat().st_size
        assert result["data"]["bytes_added"] == target.stat().st_size
        assert envelope_of(result)["rung"] == Outcome.OBSERVED.value

    @pytest.mark.asyncio
    async def test_the_observation_names_the_syscall_that_made_it(
        self, sandboxed_tmp_path
    ):
        target = sandboxed_tmp_path / "observed.txt"

        found = envelope_of(await run_write(path=str(target), content="abc"))

        observed = effect_named(found, "file_size_observed")
        assert observed["measured_by"].startswith("os.stat(path).st_size")
        assert observed["bytes_on_disk"] == 3

    @pytest.mark.asyncio
    async def test_durability_is_not_claimed_because_nothing_fsyncs(
        self, sandboxed_tmp_path
    ):
        target = sandboxed_tmp_path / "observed.txt"

        found = envelope_of(await run_write(path=str(target), content="abc"))

        assert "fsync" in effect_named(found, "file_size_observed")["detail"]
        source = inspect.getsource(write_module)
        assert "os.fsync" not in source and "flush()" not in source

    @pytest.mark.asyncio
    async def test_a_multibyte_encoding_is_measured_not_counted_in_characters(
        self, sandboxed_tmp_path
    ):
        """Three characters, sixteen bytes on disk. Only a stat knows that."""
        target = sandboxed_tmp_path / "utf16.txt"

        result = await run_write(
            path=str(target), content="héllo", encoding="utf-16"
        )

        on_disk = target.stat().st_size
        assert on_disk != len("héllo")
        assert result["data"]["bytes_on_disk"] == on_disk
        assert envelope_of(result)["rung"] == Outcome.OBSERVED.value

    @pytest.mark.asyncio
    async def test_append_measures_the_change_and_not_the_whole_file(
        self, sandboxed_tmp_path
    ):
        """Proof the number is read off the disk rather than off the input.

        The second call is handed five bytes and reports a file of ten. No
        arithmetic on that call's own parameters can produce ten.
        """
        target = sandboxed_tmp_path / "log.txt"

        first = await run_write(path=str(target), content="AAAAA", mode="append")
        second = await run_write(path=str(target), content="BBBBB", mode="append")

        assert first["data"]["bytes_on_disk"] == 5
        assert second["data"]["bytes_on_disk"] == 10
        assert second["data"]["bytes_added"] == 5
        assert second["data"]["bytes_written"] == 5
        assert envelope_of(second)["rung"] == Outcome.OBSERVED.value
        assert target.read_text() == "AAAAABBBBB"

    @pytest.mark.asyncio
    async def test_overwrite_reports_the_new_size_not_the_old_one(
        self, sandboxed_tmp_path
    ):
        target = sandboxed_tmp_path / "shrink.txt"
        target.write_text("a very long previous body")

        result = await run_write(path=str(target), content="tiny")

        assert result["data"]["bytes_on_disk"] == 4
        assert envelope_of(result)["rung"] == Outcome.OBSERVED.value


# ===========================================================================
# When the measurement contradicts the input
# ===========================================================================

class TestASizeThatDisagrees:
    """Not OBSERVED, and not FAILED either.

    `outcome.py` splits an unmet expectation on who made the claim: a caller's
    contract that broke is FAILED, an inference of ours that may simply be wrong
    is INDETERMINATE. Nobody asked `file.write` for a byte count -- the equality
    is this module's own, and it is false for correct writes under newline
    translation. So the honest answer is "we cannot say".
    """

    @pytest.fixture
    def short_write(self, monkeypatch):
        """A file that came back smaller than the bytes we handed over."""
        monkeypatch.setattr(
            write_module, "_observe_size_on_disk", lambda path: (4, None)
        )

    @pytest.mark.asyncio
    async def test_it_is_indeterminate_rather_than_observed(
        self, sandboxed_tmp_path, short_write
    ):
        target = sandboxed_tmp_path / "truncated.txt"

        found = envelope_of(await run_write(path=str(target), content="Hello World"))

        assert found["rung"] == Outcome.INDETERMINATE.value

    @pytest.mark.asyncio
    async def test_the_claim_is_attributed_to_us_which_is_why_it_is_not_failed(
        self, sandboxed_tmp_path, short_write
    ):
        target = sandboxed_tmp_path / "truncated.txt"

        found = envelope_of(await run_write(path=str(target), content="Hello World"))

        assert found["claim_by"] == ClaimBy.INFERRED.value
        assert found["rung"] != Outcome.FAILED.value

    @pytest.mark.asyncio
    async def test_both_numbers_travel_so_a_person_can_tell_which_is_wrong(
        self, sandboxed_tmp_path, short_write
    ):
        target = sandboxed_tmp_path / "truncated.txt"

        found = envelope_of(await run_write(path=str(target), content="Hello World"))

        disagreement = effect_named(found, "file_size_disagrees")
        assert disagreement["expected_bytes_added"] == 11
        assert disagreement["actual_bytes_added"] == 4
        assert "st_size" in disagreement["predicate"]

    @pytest.mark.asyncio
    async def test_the_step_still_succeeds_because_the_write_did_not_raise(
        self, sandboxed_tmp_path, short_write
    ):
        """`ok` is about the call. The rung is about reality. They are separate."""
        target = sandboxed_tmp_path / "truncated.txt"

        result = await run_write(path=str(target), content="Hello World")

        assert result["ok"] is True


# ===========================================================================
# Where the envelope sits, and how high it is allowed to climb
# ===========================================================================

class TestTheEnvelopeContract:
    @pytest.mark.asyncio
    async def test_the_envelope_is_inside_data_where_a_step_can_still_read_it(
        self, sandboxed_tmp_path
    ):
        """`to_legacy_dict` keeps `ok` and `data` and throws away every sibling."""
        from core.engine.step_executor.executor import step_outcome

        target = sandboxed_tmp_path / "reachable.txt"
        result = await run_write(path=str(target), content="abc")

        assert "outcome" in result["data"]
        rung, claim_by, _ = step_outcome(result)
        assert rung is Outcome.OBSERVED
        assert claim_by == ClaimBy.INFERRED.value

    @pytest.mark.asyncio
    async def test_it_never_claims_verified_because_it_declares_no_postcondition(
        self, sandboxed_tmp_path
    ):
        """VERIFIED is defined by a declared predicate, and there is none here.

        The claim is unchanged; only the evidence for it had to be repaired.
        This used to assert that `register_module` has no `postcondition`
        parameter -- true when it was written, and no longer: the channel now
        exists, with `derives` beside it. Having a channel is not using one.
        `file.write` passes neither, so its metadata still carries
        `postcondition: None`, `ceiling_for(None)` -- OBSERVED -- is still the
        top of this module's range, and a VERIFIED here would still be a claim
        about a predicate that does not exist.

        Asserting it off the module's own METADATA rather than off the
        decorator's signature is the durable form: it keeps failing for the
        right reason -- `file.write` declaring a predicate it does not evaluate
        -- instead of failing because the plumbing around it grew.
        """
        target = sandboxed_tmp_path / "ceiling.txt"

        found = envelope_of(await run_write(path=str(target), content="abc"))

        metadata = ModuleRegistry.get_metadata(MODULE_ID)

        assert found["postcondition"] is None
        assert metadata["postcondition"] is None
        assert "postcondition" in inspect.signature(register_module).parameters
        assert ceiling_for(metadata["postcondition"]) is Outcome.OBSERVED
        assert found["rung"] != Outcome.VERIFIED.value

    @pytest.mark.asyncio
    async def test_every_answer_carries_the_offered_count_labelled_as_offered(
        self, sandboxed_tmp_path, monkeypatch
    ):
        """The one effect that must survive every branch and every refactor."""
        target = sandboxed_tmp_path / "always.txt"

        observed = envelope_of(await run_write(path=str(target), content="Hello"))
        monkeypatch.setattr(
            write_module, "_observe_size_on_disk", lambda path: (None, "blinded")
        )
        accepted = envelope_of(await run_write(path=str(target), content="Hello"))
        monkeypatch.setattr(
            write_module, "_observe_size_on_disk", lambda path: (99, None)
        )
        indeterminate = envelope_of(await run_write(path=str(target), content="Hello"))

        assert observed["rung"] == Outcome.OBSERVED.value
        assert accepted["rung"] == Outcome.ACCEPTED.value
        assert indeterminate["rung"] == Outcome.INDETERMINATE.value
        for found in (observed, accepted, indeterminate):
            assert "file_bytes_offered" in effect_kinds(found)

    @pytest.mark.asyncio
    async def test_a_rejected_path_never_reaches_the_ladder_at_all(self, tmp_path):
        """The traversal guard still raises before anything is written."""
        from core.modules.errors import ModuleError

        with pytest.raises(ModuleError):
            await run_write(path="../../etc/passwd", content="x")
