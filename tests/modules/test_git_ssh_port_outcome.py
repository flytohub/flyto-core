# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""What the git, ssh and port modules are entitled to claim, and what earns it.

Three categories that look unrelated and share one problem: each of them had a
number in its payload that a reader would take for evidence, and in each case
the number was measured on the wrong side of the effect.

* ``ssh.sftp_upload`` returned ``size_bytes`` from ``os.path.getsize`` of the
  LOCAL file -- ``file.write``'s ``bytes_written`` defect exactly, with a network
  in the middle. ``sftp.put`` returns ``None`` and nothing was read back.
* ``git.commit`` returned a commit sha, which looks like the strongest evidence
  in the group and is not: ``rev-parse HEAD`` answers "what is HEAD" and HEAD
  resolves in any repository with any history. The tests below pin that the sha
  is read on BOTH sides of the commit, because only the pair is a change.
* ``port.check`` and ``port.wait`` reported ``open: False`` for a RST and for a
  timeout alike, so "measured closed" and "nobody answered" were one value.

The suite is organised so each module's honest FLOOR is a separate class from
what its measurement earns, following ``test_file_write_outcome.py``. If an
observation is ever removed, refactored away, or starts failing silently, the
floor tests say what the claim must fall back to instead of the rung quietly
surviving the thing that justified it.

Real resources wherever the thing being measured is real: real git repositories
driven by the real ``git`` binary, real listening sockets on loopback. asyncssh
is not installed in this environment and an SSH server is not something a unit
test should need, so those three modules run against a fake whose only job is to
reproduce the shapes asyncssh returns -- crucially including the ones that are
easy to forget, like ``exit_status`` being ``None``.
"""

import asyncio
import os
import socket
import subprocess
import sys
import types
from contextlib import suppress
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import core.modules.atomic.git.commit as commit_module
import core.modules.atomic.port.check as port_check_module
import core.modules.atomic.port.wait as port_wait_module
from core.engine.outcome import ClaimBy, Outcome, ceiling_for, read_envelope
from core.engine.step_executor.executor import step_outcome
from core.modules.registry import ModuleRegistry


def ensure_modules_loaded():
    from core.modules import atomic  # noqa: F401
    with suppress(Exception):
        from core.modules import third_party  # noqa: F401


ensure_modules_loaded()


async def run_module(module_id, **params):
    """Execute a module the way the engine does and return its raw result."""
    module = ModuleRegistry.get(module_id)
    return await module(params, {}).execute()


def envelope_of(result):
    """The envelope, read exactly where ``_apply_outcome_contract`` looks for it.

    ``body = result.get('data') if isinstance(result.get('data'), dict) else result``
    is the engine's own rule (executor.py). Reading it the same way here is what
    makes these tests catch an envelope written somewhere the engine will never
    find -- which is the failure mode ``to_legacy_dict`` makes silent, since it
    keeps ``data`` and discards every sibling.
    """
    body = result.get("data") if isinstance(result.get("data"), dict) else result
    found = read_envelope(body)
    assert found is not None, f"no well-formed envelope on {result!r}"
    return found


def rung_of(result):
    return Outcome(envelope_of(result)["rung"])


def effect_kinds(found):
    return [effect["kind"] for effect in found["effects"]]


def effect_named(found, kind):
    return next(effect for effect in found["effects"] if effect["kind"] == kind)


# ===========================================================================
# git -- real repositories, driven by the real git binary
# ===========================================================================

def git(repo, *args):
    """Run git in the test's own right, independently of the module."""
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=False,
    )


@pytest.fixture
def repo(sandboxed_tmp_path):
    """An initialised repository with one file staged and nothing committed."""
    path = sandboxed_tmp_path / "repo"
    path.mkdir()
    git(path, "init", "-q")
    git(path, "config", "user.email", "test@example.invalid")
    git(path, "config", "user.name", "Test")
    (path / "a.txt").write_text("one\n")
    return path


def head_of(repo_path):
    result = git(repo_path, "rev-parse", "--verify", "HEAD")
    return result.stdout.strip() if result.returncode == 0 else None


class TestGitCommitEarnsObservedFromTwoReads:
    """The rung rests on HEAD moving, never on a single post-commit sha."""

    @pytest.mark.asyncio
    async def test_a_root_commit_is_observed_with_no_baseline_sha(self, repo):
        """HEAD resolving to nothing and then to a commit is a measured change.

        The first commit in a fresh repository has no baseline to differ from,
        and that absence is a real reading rather than a missing one -- the same
        judgement ``file.write`` makes about a FileNotFoundError meaning a
        baseline of zero bytes.
        """
        result = await run_module(
            "git.commit", repo_path=str(repo), message="first", add_all=True
        )

        assert result["ok"] is True
        assert rung_of(result) is Outcome.OBSERVED
        moved = effect_named(envelope_of(result), "git_head_moved")
        assert moved["head_before"] is None
        assert moved["head_after"] == head_of(repo)

    @pytest.mark.asyncio
    async def test_a_later_commit_reports_the_sha_head_actually_moved_from(self, repo):
        """The baseline is checked against git run by the test, not by the module."""
        await run_module("git.commit", repo_path=str(repo), message="first", add_all=True)
        first = head_of(repo)

        (repo / "a.txt").write_text("one\ntwo\n")
        result = await run_module(
            "git.commit", repo_path=str(repo), message="second", add_all=True
        )

        assert rung_of(result) is Outcome.OBSERVED
        assert result["data"]["head_before"] == first
        assert result["data"]["commit_hash"] == head_of(repo)
        assert result["data"]["commit_hash"] != first

    @pytest.mark.asyncio
    async def test_the_claim_is_inferred_and_names_the_predicate(self, repo):
        """Nobody asked for "HEAD moves"; recording whose predicate it is matters.

        It keeps the OBSERVED case and the INDETERMINATE case below attributable
        to the same author, which is what stops a reader treating the failure of
        this module's own guess as a caller's broken contract.
        """
        result = await run_module(
            "git.commit", repo_path=str(repo), message="first", add_all=True
        )
        found = envelope_of(result)

        assert found["claim_by"] == ClaimBy.INFERRED.value
        assert "rev-parse" in found["postcondition"]

    @pytest.mark.asyncio
    async def test_root_commit_reports_files_changed_zero_and_says_it_is_not_a_count(
        self, repo
    ):
        """The number a rung must not rest on, pinned as unusable.

        ``git diff --stat HEAD~1 HEAD`` has no HEAD~1 on a root commit, so
        ``files_changed`` is 0 for a commit that created a file. That is the
        ``database.query`` defect shape -- a count identical whether the effect
        was enormous or absent -- and the only thing that keeps it readable is
        ``diffstat_available`` travelling beside it.
        """
        result = await run_module(
            "git.commit", repo_path=str(repo), message="first", add_all=True
        )

        assert result["data"]["files_changed"] == 0
        diffstat = effect_named(envelope_of(result), "git_commit_diffstat")
        assert diffstat["diffstat_available"] is False
        assert diffstat["measured_by"] is None
        # ...and the rung came from the other effect, not this one.
        assert rung_of(result) is Outcome.OBSERVED

    @pytest.mark.asyncio
    async def test_a_later_commit_does_report_a_real_diffstat(self, repo):
        await run_module("git.commit", repo_path=str(repo), message="first", add_all=True)
        (repo / "a.txt").write_text("one\ntwo\n")

        result = await run_module(
            "git.commit", repo_path=str(repo), message="second", add_all=True
        )

        diffstat = effect_named(envelope_of(result), "git_commit_diffstat")
        assert diffstat["diffstat_available"] is True
        assert result["data"]["files_changed"] == 1


class TestGitCommitWithoutTheReadBackItIsOnlyAccepted:
    """The honest floor. Take the measurement away and the rung must fall."""

    @pytest.mark.asyncio
    async def test_an_unreadable_head_falls_to_accepted(self, repo, monkeypatch):
        async def blind(_repo_path):
            return None

        monkeypatch.setattr(commit_module, "_head_sha", blind)
        result = await run_module(
            "git.commit", repo_path=str(repo), message="first", add_all=True
        )

        assert result["ok"] is True
        assert rung_of(result) is Outcome.ACCEPTED
        assert "git_head_not_read_back" in effect_kinds(envelope_of(result))
        assert result["data"]["commit_hash"] == "unknown"

    @pytest.mark.asyncio
    async def test_head_that_did_not_move_is_indeterminate_not_failed(
        self, repo, monkeypatch
    ):
        """git exiting 0 with an unmoved HEAD contradicts this module's own guess.

        FAILED would assert the commit did not happen, and nothing evaluated
        that. The predicate is ours, so being wrong about it is INDETERMINATE --
        the split ``outcome.py`` makes on who made the claim.
        """
        async def frozen(_repo_path):
            return "a" * 40

        monkeypatch.setattr(commit_module, "_head_sha", frozen)
        result = await run_module(
            "git.commit", repo_path=str(repo), message="first", add_all=True
        )

        assert rung_of(result) is Outcome.INDETERMINATE
        assert envelope_of(result)["claim_by"] == ClaimBy.INFERRED.value
        assert "git_head_did_not_move" in effect_kinds(envelope_of(result))


class TestGitCommitRefusals:
    @pytest.mark.asyncio
    async def test_nothing_to_commit_is_failed(self, repo):
        await run_module("git.commit", repo_path=str(repo), message="first", add_all=True)

        result = await run_module(
            "git.commit", repo_path=str(repo), message="again", add_all=True
        )

        assert result["error_code"] == "NOTHING_TO_COMMIT"
        assert rung_of(result) is Outcome.FAILED

    @pytest.mark.asyncio
    async def test_a_path_that_is_not_a_repository_is_failed(self, sandboxed_tmp_path):
        plain = sandboxed_tmp_path / "plain"
        plain.mkdir()

        result = await run_module("git.commit", repo_path=str(plain), message="x")

        assert result["error_code"] == "NOT_A_REPO"
        assert rung_of(result) is Outcome.FAILED
        assert effect_named(envelope_of(result), "git_repo_absent")["measured_by"] is None

    @pytest.mark.asyncio
    async def test_an_exception_mid_commit_is_indeterminate(self, repo, monkeypatch):
        """The one error path here that is not FAILED, and it must stay that way.

        An exception can land after ``git commit`` has moved the ref, so whether
        a commit object exists is exactly what is not known. The other refusals
        are git reporting that it declined, which is a stronger statement.
        """
        async def explode(_repo_path):
            raise RuntimeError("ref read exploded")

        monkeypatch.setattr(commit_module, "_head_sha", explode)
        result = await run_module(
            "git.commit", repo_path=str(repo), message="first", add_all=True
        )

        assert result["error_code"] == "COMMIT_ERROR"
        assert rung_of(result) is Outcome.INDETERMINATE


class TestGitClone:
    """`git clone` refuses a non-empty destination, which is what makes a sha
    read out of one an observation with no baseline needed."""

    @pytest.fixture
    def source(self, sandboxed_tmp_path):
        path = sandboxed_tmp_path / "source"
        path.mkdir()
        git(path, "init", "-q")
        git(path, "config", "user.email", "test@example.invalid")
        git(path, "config", "user.name", "Test")
        (path / "f.txt").write_text("content\n")
        git(path, "add", "-A")
        git(path, "commit", "-qm", "initial")
        return path

    @pytest.mark.asyncio
    async def test_a_clone_with_history_is_observed(self, source, sandboxed_tmp_path):
        destination = sandboxed_tmp_path / "clone"

        result = await run_module(
            "git.clone", url=str(source), destination=str(destination)
        )

        assert result["ok"] is True, result.get("error")
        assert rung_of(result) is Outcome.OBSERVED
        # The sha the module reports is the one an independent git agrees on.
        assert result["data"]["commit"] == head_of(destination)
        assert head_of(destination) == head_of(source)

    @pytest.mark.asyncio
    async def test_cloning_an_empty_repository_is_only_accepted(
        self, sandboxed_tmp_path
    ):
        """Success with an unborn HEAD, reported as what it is.

        Smoothing this into the OBSERVED case would make "the remote had no
        commits" indistinguishable from "we confirmed the history landed", on a
        path where the module's own sentinel string is sitting in the sha field.
        """
        empty = sandboxed_tmp_path / "empty"
        empty.mkdir()
        git(empty, "init", "-q")
        destination = sandboxed_tmp_path / "empty-clone"

        result = await run_module(
            "git.clone", url=str(empty), destination=str(destination)
        )

        assert result["ok"] is True
        assert result["data"]["commit"] == "unknown"
        assert rung_of(result) is Outcome.ACCEPTED
        assert "git_clone_not_read_back" in effect_kinds(envelope_of(result))

    @pytest.mark.asyncio
    async def test_the_sentinel_string_is_never_read_as_a_sha(self, sandboxed_tmp_path):
        """`unknown` is a string in a field typed 'string'; only the pattern saves it."""
        empty = sandboxed_tmp_path / "empty2"
        empty.mkdir()
        git(empty, "init", "-q")

        result = await run_module(
            "git.clone", url=str(empty), destination=str(sandboxed_tmp_path / "c2")
        )

        assert rung_of(result) is not Outcome.OBSERVED

    @pytest.mark.asyncio
    async def test_a_refused_url_is_failed(self, sandboxed_tmp_path):
        result = await run_module(
            "git.clone",
            url="ext::sh -c id",
            destination=str(sandboxed_tmp_path / "never"),
        )

        assert result["error_code"] == "UNSAFE_URL"
        assert rung_of(result) is Outcome.FAILED

    @pytest.mark.asyncio
    async def test_a_clone_git_rejected_is_failed(self, sandboxed_tmp_path):
        result = await run_module(
            "git.clone",
            url=str(sandboxed_tmp_path / "does-not-exist"),
            destination=str(sandboxed_tmp_path / "nope"),
        )

        assert result["error_code"] == "CLONE_FAILED"
        assert rung_of(result) is Outcome.FAILED


class TestGitDiff:
    """A read, so the question is whether the answer is in the payload."""

    @pytest.fixture
    def committed(self, repo):
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "initial")
        return repo

    @pytest.mark.asyncio
    async def test_a_diff_with_content_is_observed(self, committed):
        (committed / "a.txt").write_text("one\nchanged\n")

        result = await run_module("git.diff", repo_path=str(committed))

        assert rung_of(result) is Outcome.OBSERVED
        assert result["data"]["files_changed"] == 1
        returned = effect_named(envelope_of(result), "git_diff_returned")
        assert returned["diff_characters"] == len(result["data"]["diff"])
        assert returned["numstat_available"] is True

    @pytest.mark.asyncio
    async def test_an_empty_diff_is_only_accepted(self, committed):
        """The floor, and the case most likely to be argued up to OBSERVED.

        An empty diff string is byte-identical to what a module that never ran
        would return, which is the test this contract applies to every value. A
        consumer wanting "there are definitely no changes" is asking for a rung
        this code does not reach.
        """
        result = await run_module("git.diff", repo_path=str(committed))

        assert result["ok"] is True
        assert result["data"]["diff"] == ""
        assert rung_of(result) is Outcome.ACCEPTED
        assert "git_diff_empty" in effect_kinds(envelope_of(result))

    @pytest.mark.asyncio
    async def test_a_bad_ref_is_failed(self, committed):
        result = await run_module(
            "git.diff", repo_path=str(committed), ref1="no-such-ref"
        )

        assert result["error_code"] == "DIFF_FAILED"
        assert rung_of(result) is Outcome.FAILED

    @pytest.mark.asyncio
    async def test_not_a_repository_is_failed(self, sandboxed_tmp_path):
        plain = sandboxed_tmp_path / "plain-diff"
        plain.mkdir()

        result = await run_module("git.diff", repo_path=str(plain))

        assert rung_of(result) is Outcome.FAILED


# ===========================================================================
# port -- real sockets on loopback
# ===========================================================================

@pytest.fixture
def listening_port():
    """A real listening socket, so `connected` is a real completed handshake."""
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(8)
    yield server.getsockname()[1]
    server.close()


@pytest.fixture
def closed_port():
    """A port nothing is listening on, bound and released so it is really free."""
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


class TestPortCheckSeparatesAnAnswerFromSilence:
    @pytest.mark.asyncio
    async def test_an_open_port_is_observed(self, listening_port):
        result = await run_module(
            "port.check", port=[listening_port], host="127.0.0.1"
        )

        assert result["results"][0]["verdict"] == "connected"
        assert rung_of(result) is Outcome.OBSERVED

    @pytest.mark.asyncio
    async def test_a_refused_port_is_observed_too(self, closed_port):
        """A RST is the host answering, so "closed" here is measured, not assumed."""
        result = await run_module("port.check", port=[closed_port], host="127.0.0.1")

        assert result["results"][0]["open"] is False
        assert result["results"][0]["verdict"] == "refused"
        assert rung_of(result) is Outcome.OBSERVED

    @pytest.mark.asyncio
    async def test_a_multi_homed_host_still_measures_a_closed_port(self, closed_port):
        """The case that decided where the definite/indefinite line goes.

        `localhost` resolves to ::1 and 127.0.0.1; asyncio flattens the two
        ConnectionRefusedErrors into one bare OSError with no errno. Keying the
        rung on the exception TYPE would report the single most common check in
        this product -- a closed port on localhost -- as unmeasured, while the
        identical check against 127.0.0.1 measured it fine. That would be a rung
        tracking name resolution rather than the world.
        """
        result = await run_module("port.check", port=[closed_port], host="localhost")

        assert result["results"][0]["verdict"] in {"refused", "unreachable"}
        assert rung_of(result) is Outcome.OBSERVED

    @pytest.mark.asyncio
    async def test_a_port_that_never_answers_is_indeterminate(
        self, listening_port, monkeypatch
    ):
        """The whole reason `verdict` exists. Silence is not a closed port."""
        async def hang(*_args, **_kwargs):
            await asyncio.sleep(30)

        monkeypatch.setattr(port_check_module.asyncio, "open_connection", hang)
        result = await run_module(
            "port.check", port=[listening_port], host="127.0.0.1", connect_timeout=0.05
        )

        assert result["results"][0]["open"] is False
        assert result["results"][0]["verdict"] == "timeout"
        assert rung_of(result) is Outcome.INDETERMINATE
        assert "ports_gave_no_answer" in effect_kinds(envelope_of(result))


class TestPortCheckExpectationIsTheCallersContract:
    @pytest.mark.asyncio
    async def test_an_expectation_that_held_is_observed_by_the_caller(
        self, listening_port
    ):
        result = await run_module(
            "port.check", port=[listening_port], host="127.0.0.1", expect_open=True
        )

        found = envelope_of(result)
        assert Outcome(found["rung"]) is Outcome.OBSERVED
        assert found["claim_by"] == ClaimBy.CALLER.value
        assert found["postcondition"] == "every requested port accepts a TCP connection"

    @pytest.mark.asyncio
    async def test_an_expectation_contradicted_by_a_measurement_is_failed(
        self, listening_port, closed_port
    ):
        result = await run_module(
            "port.check",
            port=[listening_port, closed_port],
            host="127.0.0.1",
            expect_open=True,
        )

        assert result["ok"] is False
        assert rung_of(result) is Outcome.FAILED
        assert envelope_of(result)["claim_by"] == ClaimBy.CALLER.value

    @pytest.mark.asyncio
    async def test_an_expectation_contradicted_only_by_silence_is_not_failed(
        self, listening_port, monkeypatch
    ):
        """The distinction the rung exists to protect.

        FAILED asserts the caller's contract was tested and broke. A dropped
        packet did not test it -- the port may well be open behind a firewall --
        so marking this FAILED would put a broken-contract flag on a port nobody
        measured.
        """
        async def hang(*_args, **_kwargs):
            await asyncio.sleep(30)

        monkeypatch.setattr(port_check_module.asyncio, "open_connection", hang)
        result = await run_module(
            "port.check",
            port=[listening_port],
            host="127.0.0.1",
            connect_timeout=0.05,
            expect_open=True,
        )

        assert result["ok"] is False
        assert rung_of(result) is Outcome.INDETERMINATE

    @pytest.mark.asyncio
    async def test_expecting_closed_and_measuring_closed_is_observed(self, closed_port):
        result = await run_module(
            "port.check", port=[closed_port], host="127.0.0.1", expect_open=False
        )

        assert result["ok"] is True
        assert rung_of(result) is Outcome.OBSERVED

    @pytest.mark.asyncio
    async def test_no_ports_requested_is_indeterminate_not_a_quiet_success(self):
        """Vacuous truth is the quietest false green there is.

        With no ports, `ok` is True and any `expect_open` "holds" over the empty
        set. Nothing was probed, so nothing supports it.
        """
        result = await run_module("port.check", port=[], expect_open=True)

        assert result["ok"] is True
        assert rung_of(result) is Outcome.INDETERMINATE
        assert "no_ports_probed" in effect_kinds(envelope_of(result))

    @pytest.mark.asyncio
    async def test_a_host_the_guard_refuses_is_failed(self, monkeypatch):
        monkeypatch.delenv("FLYTO_ALLOW_PORT_SCAN", raising=False)

        result = await run_module("port.check", port=[80], host="10.0.0.1")

        assert result["error_code"] == "SSRF_BLOCKED"
        assert rung_of(result) is Outcome.FAILED
        assert "port_scan_refused" in effect_kinds(envelope_of(result))


class TestPortWait:
    @pytest.mark.asyncio
    async def test_a_port_that_opened_is_observed(self, listening_port):
        result = await run_module(
            "port.wait", port=listening_port, host="127.0.0.1", timeout=5
        )

        assert result["ok"] is True
        assert result["last_verdict"] == "connected"
        assert rung_of(result) is Outcome.OBSERVED

    @pytest.mark.asyncio
    async def test_a_port_measured_closed_is_observed(self, closed_port):
        result = await run_module(
            "port.wait",
            port=closed_port,
            host="127.0.0.1",
            timeout=5,
            expect_closed=True,
        )

        assert result["ok"] is True
        assert result["last_verdict"] == "refused"
        assert rung_of(result) is Outcome.OBSERVED

    @pytest.mark.asyncio
    async def test_waiting_for_closed_and_getting_silence_is_indeterminate(
        self, closed_port, monkeypatch
    ):
        """The asymmetry that makes `expect_closed` the weaker of the two waits.

        A wait for OPEN ends on a handshake, which is a measurement whatever
        preceded it. A wait for CLOSED ends on the ABSENCE of one -- and a
        firewall that started dropping packets ends it exactly the way a clean
        shutdown does. ok stays True; the rung is the only thing that says the
        state was never observed.
        """
        async def silent(_host, _port):
            return False, "timeout"

        monkeypatch.setattr(port_wait_module, "_check_port", silent)
        result = await run_module(
            "port.wait",
            port=closed_port,
            host="127.0.0.1",
            timeout=5,
            expect_closed=True,
        )

        assert result["ok"] is True
        assert rung_of(result) is Outcome.INDETERMINATE

    @pytest.mark.asyncio
    async def test_a_timeout_is_the_callers_broken_contract(self, closed_port):
        """FAILED here while `port.check`'s silence is INDETERMINATE, on purpose.

        The predicates differ and each rung matches its own. `port.check`
        asserts a STATE, which a dropped packet does not falsify. This asserts a
        TIME-BOUNDED EVENT, and whether a connection succeeded is always
        observable from this side because success is positive evidence -- so the
        window elapsing without one falsifies it literally.
        """
        result = await run_module(
            "port.wait", port=closed_port, host="127.0.0.1", timeout=0.3, interval=50
        )

        assert result["ok"] is False
        found = envelope_of(result)
        assert Outcome(found["rung"]) is Outcome.FAILED
        assert found["claim_by"] == ClaimBy.CALLER.value
        assert found["postcondition"] == "the port accepts a TCP connection within 0.3s"

    @pytest.mark.asyncio
    async def test_a_timeout_no_longer_reports_the_port_as_available(self, closed_port):
        """The inverted field this work found.

        `'available': not expect_closed` meant a wait for a port to OPEN that
        timed out returned available: True, in the same dict as an error saying
        the port never became available -- and `available` is the field a
        consumer is most likely to branch on.
        """
        result = await run_module(
            "port.wait", port=closed_port, host="127.0.0.1", timeout=0.3, interval=50
        )

        assert result["available"] is False
        assert result["attempts"] >= 1

    @pytest.mark.asyncio
    async def test_a_timeout_waiting_for_close_reports_the_port_still_available(
        self, listening_port
    ):
        """The same inversion from the other side, where it read as a success."""
        result = await run_module(
            "port.wait",
            port=listening_port,
            host="127.0.0.1",
            timeout=0.3,
            interval=50,
            expect_closed=True,
        )

        assert result["ok"] is False
        assert result["available"] is True
        assert rung_of(result) is Outcome.FAILED

    @pytest.mark.asyncio
    async def test_a_window_that_expired_before_any_probe_is_indeterminate(
        self, closed_port
    ):
        """Nothing was tested, so nothing failed."""
        result = await run_module(
            "port.wait", port=closed_port, host="127.0.0.1", timeout=0
        )

        assert result["attempts"] == 0
        assert rung_of(result) is Outcome.INDETERMINATE
        assert "port_never_probed" in effect_kinds(envelope_of(result))


# ===========================================================================
# ssh -- a fake asyncssh, because the shapes are what matter
# ===========================================================================

class FakeSFTPNoSuchFile(Exception):
    pass


class FakeSFTPError(Exception):
    pass


class FakePermissionDenied(Exception):
    pass


class FakeDisconnectError(Exception):
    pass


class FakeAttrs:
    def __init__(self, size):
        self.size = size


class FakeCompletedProcess:
    def __init__(self, stdout="", stderr="", exit_status=0):
        self.stdout = stdout
        self.stderr = stderr
        self.exit_status = exit_status


class FakeSFTP:
    """The SFTP half. `stat_queue` is a list of results-or-exceptions, popped in
    order, so the pre-transfer stat and the post-transfer read-back can be given
    different answers -- which is the only way to test the read-back at all."""

    def __init__(self, *, stat_queue=None, on_put=None, on_get=None):
        self.stat_queue = list(stat_queue or [])
        self.on_put = on_put
        self.on_get = on_get
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def stat(self, path):
        self.calls.append(("stat", path))
        if not self.stat_queue:
            raise FakeSFTPNoSuchFile(f"no such file: {path}")
        answer = self.stat_queue.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    async def put(self, local_path, remote_path):
        self.calls.append(("put", local_path, remote_path))
        if self.on_put is not None:
            self.on_put(local_path, remote_path)

    async def get(self, remote_path, local_path):
        self.calls.append(("get", remote_path, local_path))
        if self.on_get is not None:
            self.on_get(remote_path, local_path)


class FakeConnection:
    def __init__(self, *, run_result=None, sftp=None):
        self.run_result = run_result
        self.sftp = sftp

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def run(self, command, check=False):
        if isinstance(self.run_result, Exception):
            raise self.run_result
        if callable(self.run_result):
            return await self.run_result(command)
        return self.run_result

    def start_sftp_client(self):
        return self.sftp


def fake_asyncssh(*, connect_result):
    """A module object with only the names these three modules actually touch."""
    module = types.ModuleType("asyncssh")
    module.SFTPNoSuchFile = FakeSFTPNoSuchFile
    module.SFTPError = FakeSFTPError
    module.PermissionDenied = FakePermissionDenied
    module.DisconnectError = FakeDisconnectError
    module.import_private_key = lambda key: key

    def connect(**_opts):
        if isinstance(connect_result, Exception):
            raise connect_result
        return connect_result

    module.connect = connect
    return module


@pytest.fixture
def install_asyncssh(monkeypatch):
    """Put a fake asyncssh where the deferred `import asyncssh` will find it."""
    def install(**kwargs):
        module = fake_asyncssh(**kwargs)
        monkeypatch.setitem(sys.modules, "asyncssh", module)
        return module

    return install


SSH_CREDS = {"host": "127.0.0.1", "username": "tester", "password": "hunter2"}


class TestSSHExecReadsARemoteExitStatus:
    @pytest.mark.asyncio
    async def test_exit_zero_is_observed(self, install_asyncssh):
        install_asyncssh(
            connect_result=FakeConnection(
                run_result=FakeCompletedProcess(stdout="ok\n", exit_status=0)
            )
        )

        result = await run_module("ssh.exec", command="true", **SSH_CREDS)

        assert rung_of(result) is Outcome.OBSERVED
        assert result["data"]["exit_status_reported"] is True
        completed = effect_named(envelope_of(result), "ssh_command_completed")
        assert completed["exit_status"] == 0

    @pytest.mark.asyncio
    async def test_a_nonzero_exit_is_indeterminate_and_ok_stays_true(
        self, install_asyncssh
    ):
        """The rung is the ONLY place this module states the command failed.

        Unlike `shell.exec`, `ok` here is True for every exit status, so a
        remote command that exited 1 comes back looking like a success with a
        number in it. INDETERMINATE rather than FAILED for `shell.exec`'s
        reason: a restart that stopped a service and failed to start it exits
        non-zero having changed the host, so neither "it worked" nor "nothing
        happened" is supportable.
        """
        install_asyncssh(
            connect_result=FakeConnection(
                run_result=FakeCompletedProcess(stderr="boom\n", exit_status=1)
            )
        )

        result = await run_module("ssh.exec", command="false", **SSH_CREDS)

        assert result["ok"] is True
        assert rung_of(result) is Outcome.INDETERMINATE
        assert envelope_of(result)["claim_by"] == ClaimBy.INFERRED.value
        assert "ssh_nonzero_exit" in effect_kinds(envelope_of(result))

    @pytest.mark.asyncio
    async def test_a_missing_exit_status_is_indeterminate_not_a_clean_zero(
        self, install_asyncssh
    ):
        """The bug this found, pinned so the payload cannot lie on its own.

        `exit_code = result.exit_status or 0` turns asyncssh's None -- the
        channel closed without the remote sending a status -- into a literal 0
        beside ok: True. The 0 is still there for callers that type the field as
        an int; what stops it being read as success is the rung and
        `exit_status_reported`.
        """
        install_asyncssh(
            connect_result=FakeConnection(
                run_result=FakeCompletedProcess(exit_status=None)
            )
        )

        result = await run_module("ssh.exec", command="whatever", **SSH_CREDS)

        assert result["data"]["exit_code"] == 0          # the laundering, unchanged
        assert result["data"]["exit_status_reported"] is False
        assert rung_of(result) is Outcome.INDETERMINATE
        assert "ssh_exit_status_missing" in effect_kinds(envelope_of(result))


class TestSSHExecSplitsFailedFromIndeterminate:
    """`command_sent` is the difference between "retry is free" and "retry may
    run this twice", and one `except` clause cannot recover it after the fact."""

    @pytest.mark.asyncio
    async def test_no_credentials_is_failed(self, install_asyncssh):
        install_asyncssh(connect_result=FakeConnection())

        result = await run_module(
            "ssh.exec", host="127.0.0.1", username="tester", command="true"
        )

        assert result["error_code"] == "MISSING_CREDENTIALS"
        assert rung_of(result) is Outcome.FAILED

    @pytest.mark.asyncio
    async def test_authentication_refused_is_failed(self, install_asyncssh):
        install_asyncssh(connect_result=FakePermissionDenied("bad password"))

        result = await run_module("ssh.exec", command="true", **SSH_CREDS)

        assert result["error_code"] == "AUTH_FAILED"
        assert rung_of(result) is Outcome.FAILED
        assert effect_named(
            envelope_of(result), "ssh_authentication_refused"
        )["command_sent"] is False

    @pytest.mark.asyncio
    async def test_an_unreachable_host_is_failed(self, install_asyncssh):
        install_asyncssh(connect_result=OSError("no route to host"))

        result = await run_module("ssh.exec", command="true", **SSH_CREDS)

        assert result["error_code"] == "CONNECTION_ERROR"
        assert rung_of(result) is Outcome.FAILED

    @pytest.mark.asyncio
    async def test_the_same_error_after_the_command_was_sent_is_indeterminate(
        self, install_asyncssh
    ):
        """Same exception type, same handler, opposite answer."""
        install_asyncssh(
            connect_result=FakeConnection(run_result=OSError("connection reset"))
        )

        result = await run_module("ssh.exec", command="true", **SSH_CREDS)

        assert result["error_code"] == "CONNECTION_ERROR"
        assert rung_of(result) is Outcome.INDETERMINATE
        assert effect_named(
            envelope_of(result), "ssh_connection_error"
        )["command_sent"] is True

    @pytest.mark.asyncio
    async def test_a_timeout_is_indeterminate(self, install_asyncssh):
        """The textbook case named in outcome.py: it may still be running there."""
        async def never_returns(_command):
            await asyncio.sleep(30)

        install_asyncssh(connect_result=FakeConnection(run_result=never_returns))

        result = await run_module(
            "ssh.exec", command="sleep 60", timeout=0.05, **SSH_CREDS
        )

        assert result["error_code"] == "TIMEOUT"
        assert rung_of(result) is Outcome.INDETERMINATE

    @pytest.mark.asyncio
    async def test_a_disconnect_mid_command_is_indeterminate(self, install_asyncssh):
        install_asyncssh(
            connect_result=FakeConnection(run_result=FakeDisconnectError("bye"))
        )

        result = await run_module("ssh.exec", command="true", **SSH_CREDS)

        assert result["error_code"] == "DISCONNECT"
        assert rung_of(result) is Outcome.INDETERMINATE


class TestSFTPUploadWithoutTheStatItIsOnlyAccepted:
    """The honest floor: `sftp.put` returns None and `size_bytes` is local."""

    @pytest.mark.asyncio
    async def test_a_stat_that_fails_leaves_the_upload_accepted(
        self, install_asyncssh, sandboxed_tmp_path
    ):
        source = sandboxed_tmp_path / "payload.bin"
        source.write_bytes(b"x" * 64)
        sftp = FakeSFTP(stat_queue=[FakeSFTPError("stat denied")])
        install_asyncssh(connect_result=FakeConnection(sftp=sftp))

        result = await run_module(
            "ssh.sftp_upload",
            local_path=str(source),
            remote_path="/remote/payload.bin",
            **SSH_CREDS,
        )

        # A stat that raises is a failure to LOOK, never a failed upload.
        assert result["ok"] is True
        assert rung_of(result) is Outcome.ACCEPTED
        assert result["data"]["remote_size_bytes"] is None
        assert "sftp_remote_not_read_back" in effect_kinds(envelope_of(result))

    @pytest.mark.asyncio
    async def test_the_offered_size_is_labelled_as_not_a_measurement(
        self, install_asyncssh, sandboxed_tmp_path
    ):
        """`file.write`'s lesson, restated where it was repeated."""
        source = sandboxed_tmp_path / "payload.bin"
        source.write_bytes(b"x" * 64)
        install_asyncssh(
            connect_result=FakeConnection(
                sftp=FakeSFTP(stat_queue=[FakeSFTPError("denied")])
            )
        )

        result = await run_module(
            "ssh.sftp_upload",
            local_path=str(source),
            remote_path="/remote/payload.bin",
            **SSH_CREDS,
        )

        offered = effect_named(envelope_of(result), "sftp_bytes_offered")
        assert offered["bytes"] == 64
        assert "os.path.getsize(local_path)" in offered["measured_by"]


class TestSFTPUploadStatEarnsObserved:
    @pytest.mark.asyncio
    async def test_a_matching_remote_size_is_observed(
        self, install_asyncssh, sandboxed_tmp_path
    ):
        source = sandboxed_tmp_path / "payload.bin"
        source.write_bytes(b"x" * 64)
        # stat_queue holds only the post-transfer read-back: overwrite defaults
        # to True, so the pre-transfer existence check is skipped.
        install_asyncssh(
            connect_result=FakeConnection(sftp=FakeSFTP(stat_queue=[FakeAttrs(64)]))
        )

        result = await run_module(
            "ssh.sftp_upload",
            local_path=str(source),
            remote_path="/remote/payload.bin",
            **SSH_CREDS,
        )

        assert rung_of(result) is Outcome.OBSERVED
        assert result["data"]["remote_size_bytes"] == 64
        assert envelope_of(result)["claim_by"] == ClaimBy.INFERRED.value

    @pytest.mark.asyncio
    async def test_a_truncated_remote_file_is_indeterminate_not_observed(
        self, install_asyncssh, sandboxed_tmp_path
    ):
        """The case the old code reported as a clean success.

        A remote disk that filled mid-write returns the same `size_bytes` as a
        perfect upload, because that number never came from the remote.
        """
        source = sandboxed_tmp_path / "payload.bin"
        source.write_bytes(b"x" * 64)
        install_asyncssh(
            connect_result=FakeConnection(sftp=FakeSFTP(stat_queue=[FakeAttrs(9)]))
        )

        result = await run_module(
            "ssh.sftp_upload",
            local_path=str(source),
            remote_path="/remote/payload.bin",
            **SSH_CREDS,
        )

        assert rung_of(result) is Outcome.INDETERMINATE
        disagrees = effect_named(envelope_of(result), "sftp_remote_size_disagrees")
        assert disagrees["expected_bytes"] == 64
        assert disagrees["actual_bytes"] == 9

    @pytest.mark.asyncio
    async def test_a_size_free_stat_falls_back_to_accepted(
        self, install_asyncssh, sandboxed_tmp_path
    ):
        source = sandboxed_tmp_path / "payload.bin"
        source.write_bytes(b"x" * 8)
        install_asyncssh(
            connect_result=FakeConnection(sftp=FakeSFTP(stat_queue=[FakeAttrs(None)]))
        )

        result = await run_module(
            "ssh.sftp_upload",
            local_path=str(source),
            remote_path="/remote/payload.bin",
            **SSH_CREDS,
        )

        assert rung_of(result) is Outcome.ACCEPTED


class TestSFTPUploadRefusals:
    @pytest.mark.asyncio
    async def test_a_missing_local_file_is_failed(
        self, install_asyncssh, sandboxed_tmp_path
    ):
        install_asyncssh(connect_result=FakeConnection(sftp=FakeSFTP()))

        result = await run_module(
            "ssh.sftp_upload",
            local_path=str(sandboxed_tmp_path / "absent.bin"),
            remote_path="/remote/absent.bin",
            **SSH_CREDS,
        )

        assert result["error_code"] == "FILE_NOT_FOUND"
        assert rung_of(result) is Outcome.FAILED

    @pytest.mark.asyncio
    async def test_refusing_to_overwrite_is_the_callers_contract(
        self, install_asyncssh, sandboxed_tmp_path
    ):
        """The one predicate here a caller actually wrote.

        `overwrite=False` was evaluated against a real stat of the remote and it
        did not hold. Attributing that to the CALLER is what tells a reader this
        is a contract and not a malfunction.
        """
        source = sandboxed_tmp_path / "payload.bin"
        source.write_bytes(b"x" * 4)
        sftp = FakeSFTP(stat_queue=[FakeAttrs(999)])
        install_asyncssh(connect_result=FakeConnection(sftp=sftp))

        result = await run_module(
            "ssh.sftp_upload",
            local_path=str(source),
            remote_path="/remote/payload.bin",
            overwrite=False,
            **SSH_CREDS,
        )

        assert result["error_code"] == "FILE_EXISTS"
        found = envelope_of(result)
        assert Outcome(found["rung"]) is Outcome.FAILED
        assert found["claim_by"] == ClaimBy.CALLER.value
        # and nothing was sent
        assert not any(call[0] == "put" for call in sftp.calls)

    @pytest.mark.asyncio
    async def test_a_transfer_that_broke_after_it_started_is_indeterminate(
        self, install_asyncssh, sandboxed_tmp_path
    ):
        """A partial file may be sitting on the remote under the destination name."""
        source = sandboxed_tmp_path / "payload.bin"
        source.write_bytes(b"x" * 16)

        def explode(_local, _remote):
            raise FakeSFTPError("write failed halfway")

        install_asyncssh(
            connect_result=FakeConnection(sftp=FakeSFTP(on_put=explode))
        )

        result = await run_module(
            "ssh.sftp_upload",
            local_path=str(source),
            remote_path="/remote/payload.bin",
            **SSH_CREDS,
        )

        assert rung_of(result) is Outcome.INDETERMINATE
        assert effect_named(
            envelope_of(result), "sftp_protocol_error"
        )["transfer_started"] is True

    @pytest.mark.asyncio
    async def test_a_connection_that_never_came_up_is_failed(
        self, install_asyncssh, sandboxed_tmp_path
    ):
        source = sandboxed_tmp_path / "payload.bin"
        source.write_bytes(b"x" * 16)
        install_asyncssh(connect_result=OSError("no route to host"))

        result = await run_module(
            "ssh.sftp_upload",
            local_path=str(source),
            remote_path="/remote/payload.bin",
            **SSH_CREDS,
        )

        assert rung_of(result) is Outcome.FAILED
        assert effect_named(
            envelope_of(result), "sftp_connection_error"
        )["transfer_started"] is False


class TestSFTPDownloadComparesTwoMeasurements:
    @staticmethod
    def writer(payload):
        def on_get(_remote, local_path):
            Path(local_path).write_bytes(payload)
        return on_get

    @pytest.mark.asyncio
    async def test_matching_sizes_are_observed(
        self, install_asyncssh, sandboxed_tmp_path
    ):
        install_asyncssh(
            connect_result=FakeConnection(
                sftp=FakeSFTP(
                    stat_queue=[FakeAttrs(32)], on_get=self.writer(b"y" * 32)
                )
            )
        )
        destination = sandboxed_tmp_path / "down" / "file.bin"

        result = await run_module(
            "ssh.sftp_download",
            remote_path="/remote/file.bin",
            local_path=str(destination),
            **SSH_CREDS,
        )

        assert rung_of(result) is Outcome.OBSERVED
        assert result["data"]["size_bytes"] == 32
        assert result["data"]["remote_size_bytes"] == 32
        assert destination.stat().st_size == 32

    @pytest.mark.asyncio
    async def test_a_truncated_download_is_indeterminate(
        self, install_asyncssh, sandboxed_tmp_path
    ):
        """Most likely truncation, and there is a real race that produces it too.

        The remote file can be rewritten between the stat and the get, so a
        correct download can land here -- which is why the predicate being this
        module's own makes it INDETERMINATE rather than FAILED.
        """
        install_asyncssh(
            connect_result=FakeConnection(
                sftp=FakeSFTP(
                    stat_queue=[FakeAttrs(32)], on_get=self.writer(b"y" * 7)
                )
            )
        )

        result = await run_module(
            "ssh.sftp_download",
            remote_path="/remote/file.bin",
            local_path=str(sandboxed_tmp_path / "short.bin"),
            **SSH_CREDS,
        )

        assert rung_of(result) is Outcome.INDETERMINATE
        disagrees = effect_named(envelope_of(result), "sftp_sizes_disagree")
        assert (disagrees["expected_bytes"], disagrees["actual_bytes"]) == (32, 7)

    @pytest.mark.asyncio
    async def test_no_remote_size_leaves_the_local_read_with_nothing_to_check(
        self, install_asyncssh, sandboxed_tmp_path
    ):
        """`file.write`'s append mode without a baseline, and the same answer.

        The local size is a real measurement; without an expectation it says how
        big the file is, not that this transfer is why -- `get` overwrites, so
        something may have been there already.
        """
        install_asyncssh(
            connect_result=FakeConnection(
                sftp=FakeSFTP(
                    stat_queue=[FakeAttrs(None)], on_get=self.writer(b"y" * 5)
                )
            )
        )

        result = await run_module(
            "ssh.sftp_download",
            remote_path="/remote/file.bin",
            local_path=str(sandboxed_tmp_path / "nosize.bin"),
            **SSH_CREDS,
        )

        assert rung_of(result) is Outcome.ACCEPTED
        assert "sftp_remote_size_unknown" in effect_kinds(envelope_of(result))

    @pytest.mark.asyncio
    async def test_a_missing_remote_file_is_failed(
        self, install_asyncssh, sandboxed_tmp_path
    ):
        install_asyncssh(connect_result=FakeConnection(sftp=FakeSFTP(stat_queue=[])))

        result = await run_module(
            "ssh.sftp_download",
            remote_path="/remote/absent.bin",
            local_path=str(sandboxed_tmp_path / "absent.bin"),
            **SSH_CREDS,
        )

        assert result["error_code"] == "FILE_NOT_FOUND"
        assert rung_of(result) is Outcome.FAILED

    @pytest.mark.asyncio
    async def test_a_download_that_broke_mid_transfer_is_indeterminate(
        self, install_asyncssh, sandboxed_tmp_path
    ):
        """What it leaves behind is a truncated file on THIS disk."""
        def explode(_remote, _local):
            raise FakeSFTPError("read failed halfway")

        install_asyncssh(
            connect_result=FakeConnection(
                sftp=FakeSFTP(stat_queue=[FakeAttrs(32)], on_get=explode)
            )
        )

        result = await run_module(
            "ssh.sftp_download",
            remote_path="/remote/file.bin",
            local_path=str(sandboxed_tmp_path / "broken.bin"),
            **SSH_CREDS,
        )

        assert rung_of(result) is Outcome.INDETERMINATE
        assert effect_named(
            envelope_of(result), "sftp_protocol_error"
        )["transfer_started"] is True


# ===========================================================================
# The engine's view of all eight
# ===========================================================================

class TestTheEngineCanReadWhatTheseModulesWrote:
    """An envelope the engine cannot find is an envelope that does not exist.

    `to_legacy_dict` returns exactly {ok, data} and discards every sibling, so a
    rung written outside `data` on a module that HAS a data dict is dropped on
    the way out of the step. These check the two shapes actually used here
    against `step_outcome`, which is what the executor calls.
    """

    @pytest.mark.asyncio
    async def test_a_nested_envelope_reaches_step_outcome(self, repo):
        result = await run_module(
            "git.commit", repo_path=str(repo), message="first", add_all=True
        )

        found = step_outcome(result)
        assert found is not None
        assert found[0] is Outcome.OBSERVED

    @pytest.mark.asyncio
    async def test_a_flat_envelope_reaches_step_outcome(self, listening_port):
        result = await run_module(
            "port.check", port=[listening_port], host="127.0.0.1"
        )

        found = step_outcome(result)
        assert found is not None
        assert found[0] is Outcome.OBSERVED

    @pytest.mark.asyncio
    async def test_none_of_these_modules_declares_a_postcondition(self):
        """So the ceiling is OBSERVED, and it is a ceiling nothing here reaches past.

        Every rung in this group comes from a measurement rather than a declared
        predicate. If someone later adds `postcondition=` to one of these
        decorators, that raises its ceiling to VERIFIED -- and this test is the
        place they have to come and think about whether the module evaluates
        anything that would deserve it.
        """
        for module_id in (
            "git.clone", "git.commit", "git.diff",
            "port.check", "port.wait",
            "ssh.exec", "ssh.sftp_download", "ssh.sftp_upload",
        ):
            metadata = ModuleRegistry.get_metadata(module_id) or {}
            assert metadata.get("postcondition") is None, module_id
            assert ceiling_for(metadata.get("postcondition")) is Outcome.OBSERVED
