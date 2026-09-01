# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""What the file and storage modules are entitled to claim, and what earns it.

Nine modules that touch a filesystem, one that only looks like it does. The
tests are organised around the single question the outcome ladder asks --
*would this value be the same if the effect had not happened?* -- so almost
every rung below is pinned twice: once where the measurement succeeds, and once
with the measurement disabled, to prove the rung falls instead of persisting as
a decoration.

Three groups of tests are doing distinct work.

``TestEveryReturnPathCarriesAnEnvelope`` is the shape test. An envelope added
only to the happy path leaves every consumer that reads ``outcome`` raising
KeyError on precisely the results somebody needed to look at.

The per-module classes pin each rung as an argument. A future edit that quietly
promotes one should have to delete a test that says why it is wrong -- in
particular ``TestFileEditEarnsVerified``, since ``verified`` is the only rung
anything may render as done and it is reached in exactly one module here.

``TestTheSaveThatDestroyedTheNamespace`` and
``TestAnUnreadableNamespaceIsNotAnEmptyOne`` are regression tests for two real
bugs found by asking what the rung was measuring. They would both have passed
silently as ``ok: True`` before, which is what made them worth finding.
"""

import json
import os
import shutil
import stat
import sys
from contextlib import suppress
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import core.modules.atomic.file.copy as copy_module
import core.modules.atomic.file.delete as delete_module
import core.modules.atomic.file.edit as edit_module
import core.modules.atomic.file.exists as exists_module
import core.modules.atomic.file.move as move_module
import core.modules.atomic.storage.kv as kv_module
from core.engine.outcome import ClaimBy, Outcome, ceiling_for, read_envelope
from core.modules.registry import ModuleRegistry


def ensure_modules_loaded():
    from core.modules import atomic  # noqa: F401
    with suppress(Exception):
        from core.modules import third_party  # noqa: F401


ensure_modules_loaded()


async def run(module_id, **params):
    """One module call, through the wrapper the registry actually stores.

    ``execute()`` and not ``run()``: ``run()`` layers the registry's timeout and
    the policy gate over the call, neither of which is what these tests are
    about.
    """
    return await ModuleRegistry.get(module_id)(params, {}).execute()


def envelope_of(result):
    """The envelope, found where ``step_executor`` looks for it.

    ``_apply_outcome_contract`` reads ``result['data']`` when that is a dict and
    the result itself otherwise, which is the difference between the
    function-style modules here and the class-style ones. Insisting on
    well-formedness matters: ``read_envelope`` returns None for a dict whose
    ``rung`` is not a rung, so a typo in a module cannot pass here as a
    conservative claim.
    """
    body = result.get("data") if isinstance(result.get("data"), dict) else result
    found = read_envelope(body)
    assert found is not None, f"no well-formed envelope on {result!r}"
    return found


def effect_named(found, kind):
    return next(effect for effect in found["effects"] if effect["kind"] == kind)


def effect_kinds(found):
    return [effect["kind"] for effect in found["effects"]]


@pytest.fixture
def storage_dir(sandboxed_tmp_path, monkeypatch):
    """A namespace directory of our own, so tests cannot read the real one."""
    target = sandboxed_tmp_path / "kv"
    target.mkdir()
    monkeypatch.setenv("FLYTO_STORAGE_DIR", str(target))
    return target


# ===========================================================================
# The shape: every return path, not just the one that works
# ===========================================================================


class TestEveryReturnPathCarriesAnEnvelope:
    """The test that stops an envelope from existing only on the happy path."""

    @pytest.mark.asyncio
    async def test_every_file_module_success_path_has_one(self, sandboxed_tmp_path):
        source = sandboxed_tmp_path / "src.txt"
        source.write_text("hello world")

        results = [
            await run("file.read", path=str(source)),
            await run("file.exists", path=str(source)),
            await run("file.copy", source=str(source), destination=str(sandboxed_tmp_path / "c.txt")),
            await run("file.move", source=str(sandboxed_tmp_path / "c.txt"), destination=str(sandboxed_tmp_path / "m.txt")),
            await run("file.delete", file_path=str(sandboxed_tmp_path / "m.txt")),
            await run("file.delete", file_path=str(sandboxed_tmp_path / "absent"), ignore_missing=True),
            await run("file.edit", path=str(source), old_string="hello", new_string="goodbye"),
        ]

        for result in results:
            envelope_of(result)

    @pytest.mark.asyncio
    async def test_the_file_edit_failure_return_has_one(self, sandboxed_tmp_path):
        """``ok: False`` is a return path too, and the one worth inspecting."""
        source = sandboxed_tmp_path / "src.txt"
        source.write_text("hello world")

        result = await run("file.edit", path=str(source), old_string="absent", new_string="x")

        assert result["ok"] is False
        envelope_of(result)

    @pytest.mark.asyncio
    async def test_every_storage_return_path_has_one(self, storage_dir):
        """All nine: hit, miss, expired, unreadable, and the error return."""
        (storage_dir / "broken.json").write_text("{not json")

        results = [
            await run("storage.set", namespace="ns", key="k", value=1),
            await run("storage.get", namespace="ns", key="k"),
            await run("storage.get", namespace="ns", key="missing"),
            await run("storage.get", namespace="broken", key="k"),
            await run("storage.delete", namespace="ns", key="k"),
            await run("storage.delete", namespace="ns", key="k"),
            await run("storage.delete", namespace="broken", key="k"),
            # The error return: a value json cannot represent.
            await run("storage.set", namespace="ns", key="bad", value={1, 2}),
        ]

        for result in results:
            envelope_of(result)

    @pytest.mark.asyncio
    async def test_the_expired_return_has_one(self, storage_dir, monkeypatch):
        await run("storage.set", namespace="ns", key="k", value=1, ttl_seconds=60)
        # Past the TTL without waiting for it.
        monkeypatch.setattr(kv_module.time, "time", lambda: 10 ** 12)

        result = await run("storage.get", namespace="ns", key="k")

        assert result["found"] is False
        assert result["expired"] is True
        envelope_of(result)


# ===========================================================================
# file.exists -- a stat that answers, including when the answer is "no"
# ===========================================================================


class TestFileExistsIsObservedEitherWay:
    @pytest.mark.asyncio
    async def test_a_present_path_is_observed(self, sandboxed_tmp_path):
        target = sandboxed_tmp_path / "there.txt"
        target.write_text("x")

        result = await run("file.exists", path=str(target))

        assert result["data"]["exists"] is True
        assert result["data"]["is_file"] is True
        assert envelope_of(result)["rung"] == Outcome.OBSERVED.value

    @pytest.mark.asyncio
    async def test_an_absent_path_is_also_observed(self, sandboxed_tmp_path):
        """ENOENT is the filesystem answering, not the absence of an answer.

        This is the line that separates `file.exists` from `database.query`'s
        empty result set, which had to fall to ACCEPTED because `len(rows) == 0`
        reads the same whether a statement matched nothing or was discarded.
        """
        result = await run("file.exists", path=str(sandboxed_tmp_path / "nope"))

        assert result["data"]["exists"] is False
        found = envelope_of(result)
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_named(found, "path_stat_observed")["exists"] is False

    @pytest.mark.asyncio
    async def test_a_stat_that_could_not_be_asked_is_indeterminate(
        self, sandboxed_tmp_path
    ):
        """The world the old `os.path.exists` folded into a confident False.

        A parent directory we may not traverse is not evidence that the path is
        gone, and reporting the same False for it is how a permissions problem
        gets read downstream as a missing file.
        """
        if os.geteuid() == 0:
            pytest.skip("root traverses regardless of mode bits")

        locked = sandboxed_tmp_path / "locked"
        locked.mkdir()
        (locked / "inside.txt").write_text("x")
        os.chmod(locked, 0o000)
        try:
            result = await run("file.exists", path=str(locked / "inside.txt"))
        finally:
            os.chmod(locked, 0o700)

        # The reported value is unchanged for backward compatibility; the
        # envelope is the only thing that says it is a fallback.
        assert result["data"]["exists"] is False
        found = envelope_of(result)
        assert found["rung"] == Outcome.INDETERMINATE.value
        assert "PermissionError" in effect_named(found, "path_not_observable")["reason"]

    @pytest.mark.asyncio
    async def test_one_stat_means_the_three_booleans_cannot_disagree(
        self, sandboxed_tmp_path
    ):
        """Three separate os.path probes were three separate races."""
        target = sandboxed_tmp_path / "dir"
        target.mkdir()

        data = (await run("file.exists", path=str(target)))["data"]

        assert data["exists"] is True
        assert data["is_directory"] is True
        assert data["is_file"] is False


# ===========================================================================
# file.read -- the bytes are the observation
# ===========================================================================


class TestFileReadIsObserved:
    @pytest.mark.asyncio
    async def test_content_from_the_filesystem_is_observed(self, sandboxed_tmp_path):
        target = sandboxed_tmp_path / "r.txt"
        target.write_text("hello world")

        result = await run("file.read", path=str(target))

        assert result["data"]["content"] == "hello world"
        assert envelope_of(result)["rung"] == Outcome.OBSERVED.value

    @pytest.mark.asyncio
    async def test_an_empty_file_is_still_observed(self, sandboxed_tmp_path):
        """Zero here is a measurement, because the file opened.

        `database.query` had to drop an empty result set to ACCEPTED. The reason
        that does not apply here is worth a test rather than a comment: a zero
        byte count came back from a successful stat of a file that exists.
        """
        target = sandboxed_tmp_path / "empty.txt"
        target.write_text("")

        result = await run("file.read", path=str(target))

        assert result["data"]["size"] == 0
        found = envelope_of(result)
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_named(found, "file_size_observed")["bytes_on_disk"] == 0

    @pytest.mark.asyncio
    async def test_the_size_is_bytes_and_the_content_is_characters(
        self, sandboxed_tmp_path
    ):
        """The disagreement the old output offered with nothing to explain it."""
        target = sandboxed_tmp_path / "utf8.txt"
        target.write_text("héllo", encoding="utf-8")

        result = await run("file.read", path=str(target))
        found = envelope_of(result)

        assert result["data"]["size"] == 6  # bytes
        assert len(result["data"]["content"]) == 5  # characters
        assert effect_named(found, "file_content_read")["characters_returned"] == 5
        assert effect_named(found, "file_size_observed")["bytes_on_disk"] == 6


# ===========================================================================
# file.copy -- two stats of two objects
# ===========================================================================


class TestFileCopy:
    @pytest.mark.asyncio
    async def test_matching_sizes_earn_observed(self, sandboxed_tmp_path):
        source = sandboxed_tmp_path / "a.txt"
        source.write_text("hello world")
        destination = sandboxed_tmp_path / "b.txt"

        result = await run("file.copy", source=str(source), destination=str(destination))

        assert destination.read_text() == "hello world"
        found = envelope_of(result)
        assert found["rung"] == Outcome.OBSERVED.value
        assert found["claim_by"] == ClaimBy.INFERRED.value
        sizes = effect_named(found, "copy_sizes_observed")
        assert sizes["source_bytes"] == sizes["destination_bytes"] == 11

    @pytest.mark.asyncio
    async def test_a_short_copy_is_indeterminate_not_observed(
        self, sandboxed_tmp_path, monkeypatch
    ):
        """The failure the whole exercise is about, made to happen.

        `copied: True` is byte-identical in this test to the passing one above.
        The rung is the only thing that changes, which is the point.
        """
        def truncating_copy(src, dst, **kwargs):
            with open(dst, "w", encoding="utf-8") as handle:
                handle.write("hel")

        monkeypatch.setattr(copy_module.shutil, "copy2", truncating_copy)

        source = sandboxed_tmp_path / "a.txt"
        source.write_text("hello world")

        result = await run(
            "file.copy", source=str(source), destination=str(sandboxed_tmp_path / "b.txt")
        )

        assert result["copied"] is True
        found = envelope_of(result)
        assert found["rung"] == Outcome.INDETERMINATE.value
        disagreement = effect_named(found, "copy_sizes_disagree")
        assert disagreement["expected_bytes"] == 11
        assert disagreement["actual_bytes"] == 3

    @pytest.mark.asyncio
    async def test_without_the_stat_it_falls_to_accepted(
        self, sandboxed_tmp_path, monkeypatch
    ):
        """The honest floor: copy2 returning is an acknowledgement, no more."""
        monkeypatch.setattr(
            copy_module, "_size_of", lambda path: (None, "OSError: stubbed unavailable")
        )

        source = sandboxed_tmp_path / "a.txt"
        source.write_text("hello world")
        destination = sandboxed_tmp_path / "b.txt"

        result = await run("file.copy", source=str(source), destination=str(destination))

        assert destination.read_text() == "hello world"
        found = envelope_of(result)
        assert found["rung"] == Outcome.ACCEPTED.value
        assert "copy_not_observed" in effect_kinds(found)

    @pytest.mark.asyncio
    async def test_a_destination_that_cannot_be_sized_does_not_fail_the_copy(
        self, sandboxed_tmp_path, monkeypatch
    ):
        """A failure to look must not become "Failed to copy file".

        The old code called `os.path.getsize` inside the `try`, so a stat that
        raised turned a successful copy into an exception the caller had to
        debug.
        """
        real_stat = copy_module.os.stat
        destination = sandboxed_tmp_path / "b.txt"

        def blind_on_destination(path, *args, **kwargs):
            if str(path) == str(destination):
                raise OSError(5, "stubbed I/O error")
            return real_stat(path, *args, **kwargs)

        monkeypatch.setattr(copy_module.os, "stat", blind_on_destination)

        source = sandboxed_tmp_path / "a.txt"
        source.write_text("hello world")

        result = await run("file.copy", source=str(source), destination=str(destination))

        assert result["copied"] is True
        assert result["size"] is None
        assert envelope_of(result)["rung"] == Outcome.ACCEPTED.value


# ===========================================================================
# file.move -- arrived AND departed
# ===========================================================================


class TestFileMove:
    @pytest.mark.asyncio
    async def test_both_endpoints_earn_observed(self, sandboxed_tmp_path):
        source = sandboxed_tmp_path / "a.txt"
        source.write_text("hello world")
        destination = sandboxed_tmp_path / "b.txt"

        result = await run("file.move", source=str(source), destination=str(destination))

        assert destination.read_text() == "hello world"
        assert not source.exists()
        found = envelope_of(result)
        assert found["rung"] == Outcome.OBSERVED.value
        endpoints = effect_named(found, "move_endpoints_observed")
        assert endpoints["destination_present"] is True
        assert endpoints["source_gone"] is True

    @pytest.mark.asyncio
    async def test_a_move_that_did_not_happen_is_indeterminate(
        self, sandboxed_tmp_path, monkeypatch
    ):
        """`moved: True` survives; the rung does not."""
        monkeypatch.setattr(move_module.shutil, "move", lambda src, dst: dst)

        source = sandboxed_tmp_path / "a.txt"
        source.write_text("hello world")

        result = await run(
            "file.move", source=str(source), destination=str(sandboxed_tmp_path / "b.txt")
        )

        assert result["moved"] is True
        found = envelope_of(result)
        assert found["rung"] == Outcome.INDETERMINATE.value
        assert "move_endpoints_disagree" in effect_kinds(found)

    @pytest.mark.asyncio
    async def test_moving_into_a_directory_observes_where_it_landed(
        self, sandboxed_tmp_path
    ):
        """The reading that would have been true no matter what happened.

        `shutil.move` into an existing directory puts the file INSIDE it. The
        module still reports the requested `destination`, so checking that path
        would be checking that a directory which already existed still exists --
        a value unchanged by the effect, which is exactly what may not carry a
        rung. The observation follows `shutil.move`'s return value instead.
        """
        source = sandboxed_tmp_path / "a.txt"
        source.write_text("hello world")
        into = sandboxed_tmp_path / "into"
        into.mkdir()

        result = await run("file.move", source=str(source), destination=str(into))

        assert (into / "a.txt").read_text() == "hello world"
        found = envelope_of(result)
        assert found["rung"] == Outcome.OBSERVED.value
        endpoints = effect_named(found, "move_endpoints_observed")
        assert endpoints["landed_at"] == str(into / "a.txt")
        # The pre-existing reporting defect, pinned rather than hidden: the
        # `destination` field names the directory, not the file.
        assert result["destination"] == str(into)
        assert endpoints["requested_destination"] != endpoints["landed_at"]

    @pytest.mark.asyncio
    async def test_a_directory_move_is_observed_without_a_size(
        self, sandboxed_tmp_path
    ):
        """Gating on st_size would make every directory move unobservable."""
        source = sandboxed_tmp_path / "tree"
        source.mkdir()
        (source / "inner.txt").write_text("x")

        result = await run(
            "file.move", source=str(source), destination=str(sandboxed_tmp_path / "moved")
        )

        found = envelope_of(result)
        assert found["rung"] == Outcome.OBSERVED.value
        endpoints = effect_named(found, "move_endpoints_observed")
        assert endpoints["bytes_before"] is None
        assert endpoints["bytes_after"] is None


# ===========================================================================
# file.delete -- absence is observable
# ===========================================================================


class TestFileDelete:
    @pytest.mark.asyncio
    async def test_a_removed_name_is_observed(self, sandboxed_tmp_path):
        target = sandboxed_tmp_path / "gone.txt"
        target.write_text("x")

        result = await run("file.delete", file_path=str(target))

        assert not target.exists()
        assert result["deleted"] is True
        found = envelope_of(result)
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_named(found, "name_removed")["unlink_issued"] is True

    @pytest.mark.asyncio
    async def test_a_name_that_survived_the_unlink_is_indeterminate(
        self, sandboxed_tmp_path, monkeypatch
    ):
        monkeypatch.setattr(delete_module.os, "remove", lambda path: None)

        target = sandboxed_tmp_path / "stubborn.txt"
        target.write_text("x")

        result = await run("file.delete", file_path=str(target))

        assert result["deleted"] is True  # the literal, unchanged
        found = envelope_of(result)
        assert found["rung"] == Outcome.INDETERMINATE.value
        assert "name_still_present" in effect_kinds(found)

    @pytest.mark.asyncio
    async def test_the_no_op_path_observes_the_state_and_says_it_deleted_nothing(
        self, sandboxed_tmp_path
    ):
        """OBSERVED here is about the state, and the effect makes that explicit.

        A consumer must not be able to read this as "we deleted something", so
        `unlink_issued: False` rides in the effect beside the rung.
        """
        result = await run(
            "file.delete", file_path=str(sandboxed_tmp_path / "never"), ignore_missing=True
        )

        assert result["deleted"] is False
        found = envelope_of(result)
        assert found["rung"] == Outcome.OBSERVED.value
        already = effect_named(found, "name_already_absent")
        assert already["unlink_issued"] is False

    @pytest.mark.asyncio
    async def test_a_symlink_is_resolved_before_the_module_sees_it(
        self, sandboxed_tmp_path
    ):
        """Why `lexists` cannot catch a dangling link here, measured not assumed.

        It looks as though `lexists` should surface a link whose target is
        missing: `exists` resolves the link and reports the missing target, so
        the no-op path would be taken while the link itself is still there.

        It cannot, because `validate_path_with_env_config` returns
        `os.path.realpath` -- the whole path, last component included -- so the
        module is handed the resolved target and there is no symlink left for
        `lexists` to disagree about. The rung is `observed`, and the reported
        `file_path` is the target rather than the link.

        This test exists so the module docstring cannot drift back into
        claiming a mechanism the path validator rules out.
        """
        link = sandboxed_tmp_path / "dangling"
        target = sandboxed_tmp_path / "no-such-target"
        os.symlink(str(target), str(link))

        result = await run("file.delete", file_path=str(link), ignore_missing=True)

        assert result["file_path"] == str(target)
        assert result["deleted"] is False
        assert envelope_of(result)["rung"] == Outcome.OBSERVED.value
        assert os.path.lexists(link)  # the link is untouched

    @pytest.mark.asyncio
    async def test_deleting_through_a_symlink_removes_the_target_not_the_link(
        self, sandboxed_tmp_path
    ):
        """The consequence of that resolution, pinned because it is surprising.

        The sandbox check needs a canonical path -- resolving is what stops a
        link from pointing out of FLYTO_SANDBOX_DIR -- and the cost is that a
        symlink handed to this module deletes what it points at. Behaviour left
        as it is; recorded so it is a decision rather than an accident.
        """
        target = sandboxed_tmp_path / "real.txt"
        target.write_text("x")
        link = sandboxed_tmp_path / "link"
        os.symlink(str(target), str(link))

        result = await run("file.delete", file_path=str(link))

        assert not target.exists()
        assert os.path.lexists(link)  # the link survives, now dangling
        assert envelope_of(result)["rung"] == Outcome.OBSERVED.value


# ===========================================================================
# file.edit -- the one module here that reaches VERIFIED
# ===========================================================================


class TestFileEditEarnsVerified:
    """`verified` is the only rung anything may render as done. It is earned
    here by a declared postcondition and an exact read-back, and every test in
    this class exists to stop it from being earned by anything less."""

    @pytest.mark.asyncio
    async def test_the_postcondition_is_declared_on_the_module(self):
        """Without the declaration the engine caps the claim at `observed`.

        `ceiling_for(None)` is `observed`, so this is not paperwork: the
        decorator kwarg is what makes the rung reachable at all.
        """
        metadata = ModuleRegistry.get_metadata("file.edit")

        assert metadata["postcondition"] == edit_module.POSTCONDITION
        assert ceiling_for(metadata["postcondition"]) is Outcome.VERIFIED

    @pytest.mark.asyncio
    async def test_a_read_back_that_matches_is_verified(self, sandboxed_tmp_path):
        target = sandboxed_tmp_path / "code.py"
        target.write_text("def hello():\n    pass\n")

        result = await run(
            "file.edit",
            path=str(target),
            old_string="def hello():",
            new_string="def hello_world():",
        )

        assert target.read_text() == "def hello_world():\n    pass\n"
        found = envelope_of(result)
        assert found["rung"] == Outcome.VERIFIED.value
        assert found["postcondition"] == edit_module.POSTCONDITION
        assert effect_named(found, "edit_content_verified")["replacements"] == 1

    @pytest.mark.asyncio
    async def test_a_read_back_that_differs_is_failed(
        self, sandboxed_tmp_path, monkeypatch
    ):
        """A declared postcondition that was evaluated and did not hold.

        FAILED and not INDETERMINATE, unlike `file.write`'s size arithmetic:
        a text round-trip through one encoding is symmetric, so there is no
        ordinary correct edit this comparison is false for.
        """
        monkeypatch.setattr(
            edit_module, "_read_back", lambda path, encoding: ("something else", None)
        )

        target = sandboxed_tmp_path / "code.py"
        target.write_text("def hello():\n    pass\n")

        result = await run(
            "file.edit", path=str(target), old_string="hello", new_string="goodbye"
        )

        assert result["ok"] is True
        found = envelope_of(result)
        assert found["rung"] == Outcome.FAILED.value
        assert "edit_content_differs" in effect_kinds(found)

    @pytest.mark.asyncio
    async def test_without_the_read_back_it_falls_to_accepted(
        self, sandboxed_tmp_path, monkeypatch
    ):
        """The honest floor. If the read-back is ever removed or starts
        failing, the claim must fall rather than keep the rung it earned."""
        monkeypatch.setattr(
            edit_module,
            "_read_back",
            lambda path, encoding: (None, "OSError: stubbed unavailable"),
        )

        target = sandboxed_tmp_path / "code.py"
        target.write_text("def hello():\n    pass\n")

        result = await run(
            "file.edit", path=str(target), old_string="hello", new_string="goodbye"
        )

        found = envelope_of(result)
        assert found["rung"] == Outcome.ACCEPTED.value
        assert "edit_not_read_back" in effect_kinds(found)

    @pytest.mark.asyncio
    async def test_a_multibyte_edit_round_trips_and_is_verified(
        self, sandboxed_tmp_path
    ):
        """The case that would break a byte-count proxy and not this one."""
        target = sandboxed_tmp_path / "text.txt"
        target.write_text("say hello\n", encoding="utf-8")

        result = await run(
            "file.edit", path=str(target), old_string="hello", new_string="héllo — ok"
        )

        assert target.read_text(encoding="utf-8") == "say héllo — ok\n"
        assert envelope_of(result)["rung"] == Outcome.VERIFIED.value

    @pytest.mark.asyncio
    async def test_a_carriage_return_in_the_replacement_is_still_verified(
        self, sandboxed_tmp_path
    ):
        """The false red this comparison walked into once.

        `open(w)` translates `'\\n'` to `os.linesep`; `open(r)` applies
        universal newlines, which collapses `'\\r\\n'` and a bare `'\\r'` to
        `'\\n'`. They are not inverses. Measured: writing `'a\\r\\nb\\n'` and
        reading it back plainly returns `'a\\nb\\n'`, so a naive equality would
        report FAILED for a perfectly correct edit -- on the one rung that may
        render as done.

        The read-back therefore opens with `newline=''` and compares against
        the writer's own translation. Without either half this test fails.
        """
        target = sandboxed_tmp_path / "crlf.txt"
        target.write_text("line one\n", encoding="utf-8")

        result = await run(
            "file.edit",
            path=str(target),
            old_string="line one",
            new_string="line one\r\nline two\rline three",
        )

        # The bytes really are on disk with the CRs intact.
        assert b"\r\n" in target.read_bytes()
        assert envelope_of(result)["rung"] == Outcome.VERIFIED.value

    @pytest.mark.asyncio
    async def test_a_missing_old_string_is_failed_by_the_caller(
        self, sandboxed_tmp_path
    ):
        """The other half of `outcome.py`'s split: a broken CALLER contract.

        The caller asserted this string is in this file. It was not, no write
        was attempted, and `claim_by` records whose assertion broke.
        """
        target = sandboxed_tmp_path / "code.py"
        target.write_text("def hello():\n")

        result = await run(
            "file.edit", path=str(target), old_string="not in here", new_string="x"
        )

        assert result["ok"] is False
        assert target.read_text() == "def hello():\n"  # untouched
        found = envelope_of(result)
        assert found["rung"] == Outcome.FAILED.value
        assert found["claim_by"] == ClaimBy.CALLER.value


# ===========================================================================
# file.diff -- the one that only looks like it touches a filesystem
# ===========================================================================


class TestFileDiffDeclaresItDerives:
    def test_it_declares_derives_rather_than_claiming_a_rung(self):
        """`file.` is a prefix, not an effect.

        Nothing in this module opens a file. Every rung on the ladder is a
        statement about an effect, so the honest answer is the one that says
        there is none -- and it has to be declared, because "needs no contract"
        and "has not been given one yet" are otherwise the same in the data.
        """
        metadata = ModuleRegistry.get_metadata("file.diff")

        assert metadata["derives"] is True
        assert metadata["postcondition"] is None

    @pytest.mark.asyncio
    async def test_the_filename_parameter_is_a_label_and_not_a_path(self):
        """The evidence for `derives`: a path that cannot exist still works."""
        result = await run(
            "file.diff",
            original="a\n",
            modified="b\n",
            filename="/definitely/not/a/real/path.txt",
        )

        assert result["ok"] is True
        assert result["data"]["changed"] is True
        assert "/definitely/not/a/real/path.txt" in result["data"]["diff"]


# ===========================================================================
# storage -- and the two bugs found by asking what the rung measured
# ===========================================================================


class TestStorageRungs:
    @pytest.mark.asyncio
    async def test_a_write_confirmed_by_reload_is_observed(self, storage_dir):
        result = await run("storage.set", namespace="ns", key="k", value={"a": 1})

        found = envelope_of(result)
        assert found["rung"] == Outcome.OBSERVED.value
        stored = effect_named(found, "value_stored")
        assert stored["stored_at"] == result["stored_at"]
        assert stored["value_round_tripped"] is True

    @pytest.mark.asyncio
    async def test_the_timestamp_is_what_makes_the_reload_evidence(self, storage_dir):
        """A reload that merely found the key present would be satisfied by a
        value some earlier run wrote. `_stored_at` is generated in this call."""
        first = await run("storage.set", namespace="ns", key="k", value="one")
        second = await run("storage.set", namespace="ns", key="k", value="two")

        assert second["stored_at"] != first["stored_at"]
        assert (
            effect_named(envelope_of(second), "value_stored")["stored_at"]
            == second["stored_at"]
        )

    @pytest.mark.asyncio
    async def test_a_write_that_did_not_land_is_indeterminate(
        self, storage_dir, monkeypatch
    ):
        monkeypatch.setattr(kv_module, "_save_storage", lambda namespace, data: None)

        result = await run("storage.set", namespace="ns", key="k", value=1)

        assert result["ok"] is True  # the old signal, unchanged
        found = envelope_of(result)
        assert found["rung"] == Outcome.INDETERMINATE.value
        assert "value_not_confirmed" in effect_kinds(found)

    @pytest.mark.asyncio
    async def test_a_value_read_off_the_filesystem_is_observed(self, storage_dir):
        await run("storage.set", namespace="ns", key="k", value="stored")

        result = await run("storage.get", namespace="ns", key="k", default="fallback")

        assert result["found"] is True
        assert result["value"] == "stored"
        assert envelope_of(result)["rung"] == Outcome.OBSERVED.value

    @pytest.mark.asyncio
    async def test_a_clean_miss_is_observed_because_the_whole_mapping_was_searched(
        self, storage_dir
    ):
        """Not the `database.query` empty-result case: the mapping was in hand."""
        await run("storage.set", namespace="ns", key="other", value=1)

        result = await run("storage.get", namespace="ns", key="k", default="fallback")

        assert result["found"] is False
        assert result["value"] == "fallback"
        found = envelope_of(result)
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_named(found, "key_absent")["namespace_status"] == kv_module.LOADED

    @pytest.mark.asyncio
    async def test_a_delete_confirmed_by_reload_is_observed(self, storage_dir):
        await run("storage.set", namespace="ns", key="k", value=1)

        result = await run("storage.delete", namespace="ns", key="k")

        assert result["deleted"] is True
        found = envelope_of(result)
        assert found["rung"] == Outcome.OBSERVED.value
        assert "key_removed" in effect_kinds(found)

    @pytest.mark.asyncio
    async def test_a_delete_that_did_not_land_is_indeterminate(
        self, storage_dir, monkeypatch
    ):
        await run("storage.set", namespace="ns", key="k", value=1)
        monkeypatch.setattr(kv_module, "_save_storage", lambda namespace, data: None)

        result = await run("storage.delete", namespace="ns", key="k")

        assert result["deleted"] is True  # the literal, unchanged
        found = envelope_of(result)
        assert found["rung"] == Outcome.INDETERMINATE.value
        assert "key_removal_not_confirmed" in effect_kinds(found)

    @pytest.mark.asyncio
    async def test_deleting_an_absent_key_says_it_wrote_nothing(self, storage_dir):
        await run("storage.set", namespace="ns", key="other", value=1)

        result = await run("storage.delete", namespace="ns", key="k")

        assert result["deleted"] is False
        found = envelope_of(result)
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_named(found, "key_already_absent")["write_issued"] is False

    @pytest.mark.asyncio
    async def test_the_error_return_is_indeterminate(self, storage_dir):
        """A timeout is the textbook indeterminate; so is a raise mid-write."""
        result = await run("storage.set", namespace="ns", key="k", value={1, 2})

        assert result["ok"] is False
        found = envelope_of(result)
        assert found["rung"] == Outcome.INDETERMINATE.value
        assert "storage_error" in effect_kinds(found)


class TestAnUnreadableNamespaceIsNotAnEmptyOne:
    """The `database.query` empty-result trap, in another costume.

    `_load_storage` swallowed `JSONDecodeError` and returned `{}`, so a
    corrupted namespace file was indistinguishable from a key that was never
    set -- silently, for as long as the corruption lasted.
    """

    @pytest.mark.asyncio
    async def test_a_corrupt_namespace_makes_get_indeterminate_not_a_clean_miss(
        self, storage_dir
    ):
        (storage_dir / "ns.json").write_text("{not json")

        result = await run("storage.get", namespace="ns", key="k", default="fallback")

        # The reported values are unchanged; the rung is what says they are a
        # fallback rather than a finding.
        assert result["found"] is False
        assert result["value"] == "fallback"
        assert envelope_of(result)["rung"] == Outcome.INDETERMINATE.value

    @pytest.mark.asyncio
    async def test_a_namespace_holding_a_list_is_unreadable_too(self, storage_dir):
        """`.get(key)` on a list raises; it is the same "cannot read this"."""
        (storage_dir / "ns.json").write_text("[1, 2, 3]")

        result = await run("storage.get", namespace="ns", key="k")

        assert envelope_of(result)["rung"] == Outcome.INDETERMINATE.value

    @pytest.mark.asyncio
    async def test_a_corrupt_namespace_makes_delete_indeterminate(self, storage_dir):
        (storage_dir / "ns.json").write_text("{not json")

        result = await run("storage.delete", namespace="ns", key="k")

        assert result["deleted"] is False
        assert envelope_of(result)["rung"] == Outcome.INDETERMINATE.value

    @pytest.mark.asyncio
    async def test_a_missing_namespace_file_is_a_finding_and_stays_observed(
        self, storage_dir
    ):
        """ENOENT is the filesystem answering. Only a parse failure is not."""
        result = await run("storage.get", namespace="never-written", key="k")

        found = envelope_of(result)
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_named(found, "key_absent")["namespace_status"] == kv_module.ABSENT

    @pytest.mark.asyncio
    async def test_overwriting_an_unreadable_namespace_is_reported(self, storage_dir):
        """`set` still writes over a corrupt file, and now says the keys went.

        The rung stays OBSERVED because the key this call wrote really did land
        and was read back. The collateral belongs in the payload, not nowhere.
        """
        (storage_dir / "ns.json").write_text("{not json")

        result = await run("storage.set", namespace="ns", key="k", value=1)

        found = envelope_of(result)
        assert found["rung"] == Outcome.OBSERVED.value
        assert "prior_namespace_discarded" in effect_kinds(found)


class TestTheSaveThatDestroyedTheNamespace:
    """The bug, pinned so it cannot come back.

    `_save_storage` opened the file with `'w'` -- which truncates -- and handed
    the handle to `json.dump`, which serialises incrementally straight into it.
    A value `json` could not represent therefore truncated the namespace and
    raised partway through rewriting it, destroying every OTHER key. The module
    caught the exception and returned `ok: False`, which reads as "nothing
    happened".

    Measured on the original code: a namespace holding `keep` was left as
    invalid JSON containing a partial object, and the next `get` for `keep`
    returned the caller's default.
    """

    @pytest.mark.asyncio
    async def test_an_unserialisable_value_does_not_destroy_the_other_keys(
        self, storage_dir
    ):
        await run("storage.set", namespace="ns", key="keep", value="important")
        await run("storage.set", namespace="ns", key="keep2", value="also important")

        failed = await run("storage.set", namespace="ns", key="bad", value={1, 2, 3})

        assert failed["ok"] is False
        survivor = await run("storage.get", namespace="ns", key="keep")
        assert survivor["found"] is True
        assert survivor["value"] == "important"
        second = await run("storage.get", namespace="ns", key="keep2")
        assert second["found"] is True
        assert second["value"] == "also important"

    @pytest.mark.asyncio
    async def test_the_namespace_file_still_parses_after_a_failed_write(
        self, storage_dir
    ):
        await run("storage.set", namespace="ns", key="keep", value="important")

        await run("storage.set", namespace="ns", key="bad", value={1, 2, 3})

        # The measured symptom on the old code: unparseable, partial JSON.
        parsed = json.loads((storage_dir / "ns.json").read_text())
        assert set(parsed) == {"keep"}

    @pytest.mark.asyncio
    async def test_a_failed_write_leaves_no_temporary_file_behind(self, storage_dir):
        await run("storage.set", namespace="ns", key="keep", value="important")

        await run("storage.set", namespace="ns", key="bad", value={1, 2, 3})

        assert [entry.name for entry in storage_dir.iterdir()] == ["ns.json"]

    @pytest.mark.asyncio
    async def test_an_existing_namespace_keeps_its_permissions(self, storage_dir):
        """The temp-file write must not silently tighten an existing file.

        `mkstemp` creates at 0600 where `open('w')` created at 0644, so
        replacing a namespace would have changed its mode as a side effect of
        a durability fix. A fresh namespace keeps the tighter default.
        """
        await run("storage.set", namespace="ns", key="k", value=1)
        namespace = storage_dir / "ns.json"
        os.chmod(namespace, 0o644)

        await run("storage.set", namespace="ns", key="k2", value=2)

        assert stat.S_IMODE(namespace.stat().st_mode) == 0o644

    @pytest.mark.asyncio
    async def test_a_reader_never_sees_a_partial_file(self, storage_dir, monkeypatch):
        """The other half of the fix: `os.replace` publishes atomically.

        With the write going straight into the target, a reader that arrived
        mid-write saw a truncated file. Here the target is untouched until the
        rename, so the namespace on disk is always a whole version.
        """
        await run("storage.set", namespace="ns", key="keep", value="important")

        seen = []
        real_replace = kv_module.os.replace

        def watch(src, dst):
            # Whatever is at the destination the instant before publication
            # must still be the complete previous version.
            seen.append(json.loads(Path(dst).read_text()))
            return real_replace(src, dst)

        monkeypatch.setattr(kv_module.os, "replace", watch)
        await run("storage.set", namespace="ns", key="second", value="new")

        assert seen == [{"keep": {"value": "important", "_stored_at": seen[0]["keep"]["_stored_at"]}}]
