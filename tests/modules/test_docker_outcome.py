# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""What the six `docker.*` modules are entitled to claim, and what earns it.

No daemon is required and none is used. Every test here scripts the `docker`
CLI, because what is under test is not docker -- it is which of docker's
answers this repository is allowed to call an observation. A real daemon would
make these tests slower, flakier, and unable to reach the cases that matter
most: an image store that will not answer, a `docker ps` whose output cannot be
parsed, an `--rm` container that is gone before the read-back.

The two modules to read first:

* :class:`TestDockerRunEarnsObservedFromTheReadBack` -- `docker.run` returned
  ``status = 'running' if detach else 'exited'``, which is a restatement of a
  parameter. It reads `'running'` for a container that crashed on its first
  instruction. The `docker inspect` read-back is what makes the field a
  measurement, and `test_a_container_that_died_is_not_reported_as_running` is
  the case the old literal got wrong.
* :class:`TestDockerPsSplitsOnWhatWasActuallyParsed` -- `count: 0` has two
  meanings and they are opposites.
"""

import asyncio
import sys
from contextlib import suppress
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from core.engine.outcome import ClaimBy, Outcome, read_envelope
from core.engine.step_executor.executor import step_outcome
from core.modules.registry import ModuleRegistry


def ensure_modules_loaded():
    from core.modules import atomic  # noqa: F401
    with suppress(Exception):
        from core.modules import third_party  # noqa: F401


ensure_modules_loaded()


# ---------------------------------------------------------------------------
# A scriptable `docker` CLI
# ---------------------------------------------------------------------------


class FakeProcess:
    """One scripted `docker` invocation."""

    def __init__(self, stdout=b"", stderr=b"", returncode=0, hangs=False):
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode
        self._hangs = hangs
        self.killed = False

    async def communicate(self):
        if self._hangs:
            # Long enough that only the patched wait_for below ends it.
            await asyncio.sleep(30)
        return self._stdout, self._stderr

    def kill(self):
        self.killed = True

    async def wait(self):
        return self.returncode


class FakeDocker:
    """Answers `docker` invocations from a routing table, and records them.

    Routing is on a prefix of the argv, so a test says what `docker inspect`
    replies without having to reproduce the exact flags the module builds --
    which is the point: the flags are the module's business, the answer is the
    daemon's.
    """

    def __init__(self, routes, default=None):
        self.routes = routes
        self.default = default or FakeProcess()
        self.calls = []

    async def __call__(self, *args, **kwargs):
        self.calls.append(list(args))
        for prefix, response in self.routes:
            if list(args[: len(prefix)]) == list(prefix):
                if isinstance(response, BaseException):
                    raise response
                return response
        if isinstance(self.default, BaseException):
            raise self.default
        return self.default

    def argv_for(self, *prefix):
        """Every recorded invocation starting with `prefix`."""
        return [call for call in self.calls if call[: len(prefix)] == list(prefix)]


@pytest.fixture
def fake_docker(monkeypatch):
    """Install a FakeDocker, and make the modules' own timeouts test-sized."""
    real_wait_for = asyncio.wait_for

    async def impatient_wait_for(awaitable, timeout=None):
        # The modules ask for 10-580 seconds. The number under test is never
        # the timeout itself, only what the module does when it expires.
        return await real_wait_for(awaitable, timeout=0.3)

    def install(routes, default=None):
        fake = FakeDocker(routes, default)
        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake)
        monkeypatch.setattr(asyncio, "wait_for", impatient_wait_for)
        return fake

    return install


async def run_module(module_id, **params):
    module = ModuleRegistry.get(module_id)
    return await module(params, {}).execute()


def envelope_of(result):
    """The envelope, insisting it is well-formed and inside `data`."""
    assert isinstance(result.get("data"), dict), f"no data dict on {result!r}"
    found = read_envelope(result["data"])
    assert found is not None, f"no well-formed envelope on {result['data']!r}"
    return found


def effect_kinds(found):
    return [effect["kind"] for effect in found["effects"]]


# ---------------------------------------------------------------------------
# docker.run
# ---------------------------------------------------------------------------


class TestDockerRunEarnsObservedFromTheReadBack:
    @pytest.mark.asyncio
    async def test_a_running_container_is_observed(self, fake_docker):
        fake_docker([
            (("docker", "run"), FakeProcess(stdout=b"a1b2c3d4e5f6789\n")),
            (("docker", "inspect"), FakeProcess(stdout=b"running\n")),
        ])

        result = await run_module("docker.run", image="nginx:latest")

        assert result["data"]["status"] == "running"
        assert result["data"]["status_observed"] is True
        found = envelope_of(result)
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_kinds(found) == [
            "run_command_succeeded",
            "container_state_observed",
        ]

    @pytest.mark.asyncio
    async def test_a_container_that_died_is_not_reported_as_running(self, fake_docker):
        """The case the old `status` literal got wrong, every time.

        `detach=True` used to make `status` the string 'running' with no
        syscall behind it. A detached container whose entrypoint exits
        immediately produced exactly the same field as a healthy one.
        """
        fake_docker([
            (("docker", "run"), FakeProcess(stdout=b"deadbeef0000\n")),
            (("docker", "inspect"), FakeProcess(stdout=b"exited\n")),
        ])

        result = await run_module("docker.run", image="alpine:latest", detach=True)

        assert result["data"]["status"] == "exited"
        assert envelope_of(result)["rung"] == Outcome.OBSERVED.value

    @pytest.mark.asyncio
    async def test_the_read_back_asks_about_the_id_docker_printed(self, fake_docker):
        fake = fake_docker([
            (("docker", "run"), FakeProcess(stdout=b"abcdef123456789\n")),
            (("docker", "inspect"), FakeProcess(stdout=b"running\n")),
        ])

        await run_module("docker.run", image="nginx:latest")

        inspects = fake.argv_for("docker", "inspect")
        assert len(inspects) == 1
        # The 12-character short id, which is what `container_id` reports.
        assert inspects[0][-1] == "abcdef123456"

    @pytest.mark.asyncio
    async def test_an_unreadable_container_falls_back_to_accepted(self, fake_docker):
        """`--rm` containers are gone before the read-back, and that is normal.

        A failed observation is not a failed run. The rung falls to what the
        `docker run` exit status alone supports, `status` goes back to the old
        inference, and `status_observed` says which of the two it is.
        """
        fake_docker([
            (("docker", "run"), FakeProcess(stdout=b"abcdef123456\n")),
            (
                ("docker", "inspect"),
                FakeProcess(stderr=b"Error: No such object", returncode=1),
            ),
        ])

        result = await run_module("docker.run", image="alpine", remove=True)

        assert result["ok"] is True
        assert result["data"]["status_observed"] is False
        assert result["data"]["status"] == "running"  # the inference, unchanged
        found = envelope_of(result)
        assert found["rung"] == Outcome.ACCEPTED.value
        assert effect_kinds(found) == [
            "run_command_succeeded",
            "container_state_not_observed",
        ]
        assert "No such object" in found["effects"][1]["reason"]

    @pytest.mark.asyncio
    async def test_a_foreground_run_with_no_name_has_nothing_to_inspect(self, fake_docker):
        """stdout is the container's OWN output there, not a reference.

        With `detach` false and no `--name`, there is no handle to inspect by,
        so no inspect is attempted at all and the claim stops at ACCEPTED.
        """
        fake = fake_docker([
            (("docker", "run"), FakeProcess(stdout=b"hello world\n")),
        ])

        result = await run_module("docker.run", image="alpine", detach=False)

        assert fake.argv_for("docker", "inspect") == []
        found = envelope_of(result)
        assert found["rung"] == Outcome.ACCEPTED.value
        assert "no container reference" in found["effects"][1]["reason"]

    @pytest.mark.asyncio
    async def test_a_foreground_run_with_a_name_is_inspected_by_it(self, fake_docker):
        fake = fake_docker([
            (("docker", "run"), FakeProcess(stdout=b"hello world\n")),
            (("docker", "inspect"), FakeProcess(stdout=b"exited\n")),
        ])

        result = await run_module(
            "docker.run", image="alpine", detach=False, name="one-shot",
        )

        assert fake.argv_for("docker", "inspect")[0][-1] == "one-shot"
        assert envelope_of(result)["rung"] == Outcome.OBSERVED.value

    @pytest.mark.asyncio
    async def test_a_broken_read_back_never_fails_the_run(self, fake_docker):
        """The observation runs inside the module's own `except Exception`.

        If it were allowed to raise, a container that started perfectly would be
        reported as a failed run because we could not look at it afterwards.
        """
        fake_docker([
            (("docker", "run"), FakeProcess(stdout=b"abcdef123456\n")),
            (("docker", "inspect"), OSError("docker binary vanished")),
        ])

        result = await run_module("docker.run", image="nginx")

        assert result["ok"] is True
        found = envelope_of(result)
        assert found["rung"] == Outcome.ACCEPTED.value
        assert "OSError" in found["effects"][1]["reason"]

    @pytest.mark.asyncio
    async def test_it_never_claims_verified(self, fake_docker):
        """A container observed running now may exit a millisecond later."""
        fake_docker([
            (("docker", "run"), FakeProcess(stdout=b"abcdef123456\n")),
            (("docker", "inspect"), FakeProcess(stdout=b"running\n")),
        ])

        found = envelope_of(await run_module("docker.run", image="nginx"))
        assert found["rung"] != Outcome.VERIFIED.value
        assert found["postcondition"] is None


# ---------------------------------------------------------------------------
# docker.ps
# ---------------------------------------------------------------------------


class TestDockerPsSplitsOnWhatWasActuallyParsed:
    @pytest.mark.asyncio
    async def test_parsed_containers_are_observed(self, fake_docker):
        fake_docker([(
            ("docker", "ps"),
            FakeProcess(stdout=(
                b'{"ID":"aaa","Names":"web","Image":"nginx","State":"running"}\n'
                b'{"ID":"bbb","Names":"db","Image":"postgres","State":"running"}\n'
            )),
        )])

        result = await run_module("docker.ps")

        assert result["data"]["count"] == 2
        found = envelope_of(result)
        assert found["rung"] == Outcome.OBSERVED.value
        assert found["effects"][0]["count"] == 2

    @pytest.mark.asyncio
    async def test_an_empty_answer_is_only_accepted(self, fake_docker):
        """Nothing about any container crossed the wire."""
        fake_docker([(("docker", "ps"), FakeProcess(stdout=b""))])

        result = await run_module("docker.ps")

        assert result["data"]["count"] == 0
        found = envelope_of(result)
        assert found["rung"] == Outcome.ACCEPTED.value
        assert effect_kinds(found) == ["daemon_answered_empty"]

    @pytest.mark.asyncio
    async def test_unreadable_output_is_indeterminate_not_empty(self, fake_docker):
        """The two ways to reach `count: 0`, and they mean opposite things.

        `_parse_container_line` returns `{}` for a line it cannot read and the
        caller drops it. Without this split, a stdout full of containers that
        arrived in an unexpected format reports exactly what an idle daemon
        reports.
        """
        fake_docker([(
            ("docker", "ps"),
            FakeProcess(stdout=b"not json at all\nnor is this\n"),
        )])

        result = await run_module("docker.ps")

        assert result["data"]["count"] == 0
        found = envelope_of(result)
        assert found["rung"] == Outcome.INDETERMINATE.value
        assert found["claim_by"] == ClaimBy.INFERRED.value
        assert found["effects"][0]["unreadable_lines"] == 2

    @pytest.mark.asyncio
    async def test_a_partial_read_still_reports_what_it_dropped(self, fake_docker):
        fake_docker([(
            ("docker", "ps"),
            FakeProcess(stdout=b'{"ID":"aaa","Names":"web"}\ngarbage\n'),
        )])

        found = envelope_of(await run_module("docker.ps"))

        assert found["rung"] == Outcome.OBSERVED.value
        assert found["effects"][0]["count"] == 1
        assert found["effects"][0]["unreadable_lines"] == 1


# ---------------------------------------------------------------------------
# docker.inspect_container
# ---------------------------------------------------------------------------


class TestDockerInspectNeedsAStateToHaveObservedOne:
    @pytest.mark.asyncio
    async def test_a_container_document_is_observed(self, fake_docker):
        fake_docker([(
            ("docker", "inspect"),
            FakeProcess(stdout=(
                b'[{"Id":"abcdef1234567890","Name":"/web",'
                b'"State":{"Status":"running","Running":true,"Pid":4242},'
                b'"Config":{"Image":"nginx"}}]'
            )),
        )])

        result = await run_module("docker.inspect_container", container="web")

        assert result["data"]["state"]["status"] == "running"
        found = envelope_of(result)
        assert found["rung"] == Outcome.OBSERVED.value
        assert found["effects"][0]["pid"] == 4242

    @pytest.mark.asyncio
    async def test_a_stopped_container_is_observed_just_as_much(self, fake_docker):
        """The rung is about whether a reading happened, not what it said."""
        fake_docker([(
            ("docker", "inspect"),
            FakeProcess(stdout=(
                b'[{"Id":"abc","Name":"/web",'
                b'"State":{"Status":"exited","Running":false,"ExitCode":137}}]'
            )),
        )])

        found = envelope_of(
            await run_module("docker.inspect_container", container="web")
        )
        assert found["rung"] == Outcome.OBSERVED.value
        assert found["effects"][0]["status"] == "exited"

    @pytest.mark.asyncio
    async def test_an_image_document_is_not_a_container_observation(self, fake_docker):
        """`docker inspect nginx:latest` exits 0 and returns an image.

        `_extract_inspect_data` then fills `status: ''`, `running: False`,
        `pid: 0` from its own defaults, and those four fields are
        indistinguishable from a real reading of a stopped container. Nothing
        may be observed on them.
        """
        fake_docker([(
            ("docker", "inspect"),
            FakeProcess(stdout=b'[{"Id":"sha256:abc","RepoTags":["nginx:latest"]}]'),
        )])

        result = await run_module("docker.inspect_container", container="nginx:latest")

        assert result["data"]["state"]["running"] is False  # a default, not a reading
        found = envelope_of(result)
        assert found["rung"] == Outcome.ACCEPTED.value
        assert effect_kinds(found) == ["inspected_object_is_not_a_container"]


# ---------------------------------------------------------------------------
# docker.logs
# ---------------------------------------------------------------------------


class TestDockerLogs:
    @pytest.mark.asyncio
    async def test_log_lines_are_observed(self, fake_docker):
        fake_docker([(
            ("docker", "logs"),
            FakeProcess(stdout=b"first line\nsecond line\n"),
        )])

        result = await run_module("docker.logs", container="web")

        assert result["data"]["lines"] == 2
        found = envelope_of(result)
        assert found["rung"] == Outcome.OBSERVED.value
        assert found["effects"][0]["lines"] == 2

    @pytest.mark.asyncio
    async def test_no_logs_is_only_accepted(self, fake_docker):
        """Identical whether the container is silent or the driver keeps nothing."""
        fake_docker([(("docker", "logs"), FakeProcess())])

        found = envelope_of(await run_module("docker.logs", container="web"))
        assert found["rung"] == Outcome.ACCEPTED.value

    @pytest.mark.asyncio
    async def test_a_killed_follow_is_indeterminate_not_empty(self, fake_docker):
        """The path that returns `ok: True` with no logs and no error.

        `--follow` streams until killed, so hitting the timeout is the normal
        end of a follow -- and everything the stream had read dies with the
        cancelled `communicate()`. A consumer reading `ok` and `lines` cannot
        tell this from a container that logged nothing; the envelope is the
        only thing that can.
        """
        fake_docker([(("docker", "logs"), FakeProcess(hangs=True))])

        result = await run_module("docker.logs", container="web", follow=True)

        assert result["ok"] is True
        assert result["data"]["lines"] == 0
        found = envelope_of(result)
        assert found["rung"] == Outcome.INDETERMINATE.value
        assert effect_kinds(found) == ["log_stream_started", "log_stream_killed"]

    @pytest.mark.asyncio
    async def test_the_killed_follow_reaches_a_step_consumer(self, fake_docker):
        fake_docker([(("docker", "logs"), FakeProcess(hangs=True))])

        result = await run_module("docker.logs", container="web", follow=True)
        rung, _, _ = step_outcome(result)
        assert rung is Outcome.INDETERMINATE


# ---------------------------------------------------------------------------
# docker.build
# ---------------------------------------------------------------------------


class TestDockerBuildRestsOnTheImageStoreNotTheExitCode:
    @pytest.mark.asyncio
    async def test_a_size_from_the_image_store_earns_observed(self, fake_docker):
        fake_docker([
            (
                ("docker", "build"),
                FakeProcess(stdout=b"Successfully built abc123def456\n"),
            ),
            (("docker", "image", "inspect"), FakeProcess(stdout=b"104857600\n")),
        ])

        result = await run_module("docker.build", path=".", tag="myapp:latest")

        assert result["data"]["size_bytes"] == 104857600
        assert result["data"]["size"] == "100.0 MB"
        found = envelope_of(result)
        assert found["rung"] == Outcome.OBSERVED.value
        assert effect_kinds(found) == [
            "build_command_succeeded",
            "image_present_under_tag",
        ]

    @pytest.mark.asyncio
    async def test_an_image_store_that_will_not_answer_is_accepted(self, fake_docker):
        """Exit 0 from the build alone is the daemon describing its own work."""
        fake_docker([
            (("docker", "build"), FakeProcess(stdout=b"Successfully built abc\n")),
            (
                ("docker", "image", "inspect"),
                FakeProcess(stderr=b"No such image", returncode=1),
            ),
        ])

        result = await run_module("docker.build", path=".", tag="myapp:latest")

        assert result["data"]["size_bytes"] is None
        found = envelope_of(result)
        assert found["rung"] == Outcome.ACCEPTED.value
        assert "No such image" in found["effects"][1]["reason"]

    @pytest.mark.asyncio
    async def test_a_non_numeric_size_is_not_an_observation(self, fake_docker):
        """It is still passed through to `size`, as it always was, but it is
        not a byte count and nothing may be observed on it."""
        fake_docker([
            (("docker", "build"), FakeProcess(stdout=b"Successfully built abc\n")),
            (("docker", "image", "inspect"), FakeProcess(stdout=b"<no value>\n")),
        ])

        result = await run_module("docker.build", path=".", tag="myapp:latest")

        assert result["data"]["size"] == "<no value>"
        assert result["data"]["size_bytes"] is None
        assert envelope_of(result)["rung"] == Outcome.ACCEPTED.value

    @pytest.mark.asyncio
    async def test_observed_does_not_claim_this_build_made_the_image(self, fake_docker):
        """A fully cached rebuild exits 0 having created nothing.

        The effect is named for what was measured -- an image exists under this
        tag -- and the detail says so, because `docker image inspect` cannot
        tell a new image from one that was already there.
        """
        fake_docker([
            (("docker", "build"), FakeProcess(stdout=b"CACHED [1/1]\n")),
            (("docker", "image", "inspect"), FakeProcess(stdout=b"512\n")),
        ])

        found = envelope_of(
            await run_module("docker.build", path=".", tag="myapp:latest")
        )
        assert found["effects"][1]["kind"] == "image_present_under_tag"
        assert "created it" in found["effects"][1]["detail"]
        # No image id was parseable out of that output, and that is routine.
        assert found["effects"][0]["image_id"] == ""


# ---------------------------------------------------------------------------
# docker.stop
# ---------------------------------------------------------------------------


class TestDockerStopStopsAtAccepted:
    @pytest.mark.asyncio
    async def test_a_successful_stop_is_accepted_and_no_higher(self, fake_docker):
        fake_docker([(("docker", "stop"), FakeProcess(stdout=b"my-nginx\n"))])

        result = await run_module("docker.stop", container="my-nginx")

        assert result["data"]["stopped"] is True
        found = envelope_of(result)
        assert found["rung"] == Outcome.ACCEPTED.value
        assert found["effects"][0]["measured_by"] == "exit status 0 from `docker stop`"

    @pytest.mark.asyncio
    async def test_stopped_true_is_a_literal_and_carries_no_evidence(self, fake_docker):
        """It is True on every path that returns, so it distinguishes nothing.

        The echoed reference is not evidence either: `container_id` falls back
        to the caller's own parameter when stdout is empty, which is the
        `bytes_written` shape from `file.write` exactly.
        """
        fake_docker([(("docker", "stop"), FakeProcess(stdout=b""))])

        result = await run_module("docker.stop", container="my-nginx")

        assert result["data"]["stopped"] is True
        assert result["data"]["container_id"] == "my-nginx"  # the input, echoed back
        found = envelope_of(result)
        assert found["rung"] == Outcome.ACCEPTED.value
        assert found["effects"][0]["echoed_reference"] == ""


# ---------------------------------------------------------------------------
# No holes
# ---------------------------------------------------------------------------


class TestEveryReturningPathCarriesAnEnvelope:
    """The test that keeps the rest honest.

    A consumer reading `data['outcome']` KeyErrors on any return that lacks
    one. These six modules raise `ModuleError` on failure rather than
    returning, so the returning paths are the ones enumerated here -- and every
    one of them is reached through a different daemon answer, not a different
    parameter.
    """

    @pytest.mark.asyncio
    async def test_all_of_them(self, fake_docker):
        cases = [
            ("docker.run", {"image": "nginx"}, [
                (("docker", "run"), FakeProcess(stdout=b"abc123456789\n")),
                (("docker", "inspect"), FakeProcess(stdout=b"running\n")),
            ]),
            ("docker.ps", {}, [
                (("docker", "ps"), FakeProcess(stdout=b'{"ID":"a","Names":"b"}\n')),
            ]),
            ("docker.inspect_container", {"container": "web"}, [
                (
                    ("docker", "inspect"),
                    FakeProcess(stdout=b'[{"Id":"a","State":{"Status":"running"}}]'),
                ),
            ]),
            ("docker.logs", {"container": "web"}, [
                (("docker", "logs"), FakeProcess(stdout=b"hello\n")),
            ]),
            ("docker.build", {"path": ".", "tag": "t:1"}, [
                (("docker", "build"), FakeProcess(stdout=b"Successfully built ab\n")),
                (("docker", "image", "inspect"), FakeProcess(stdout=b"10\n")),
            ]),
            ("docker.stop", {"container": "web"}, [
                (("docker", "stop"), FakeProcess(stdout=b"web\n")),
            ]),
        ]

        for module_id, params, routes in cases:
            fake_docker(routes)
            found = envelope_of(await run_module(module_id, **params))
            assert set(found) == {
                "rung", "claim_by", "postcondition", "effects", "evidence_ref"
            }, module_id
            # Nothing in this category declares a postcondition, so nothing in
            # it may be rendered as done.
            assert found["rung"] != Outcome.VERIFIED.value, module_id
            assert found["postcondition"] is None, module_id

    @pytest.mark.asyncio
    async def test_a_step_consumer_reads_the_rung_off_each_one(self, fake_docker):
        fake_docker([
            (("docker", "run"), FakeProcess(stdout=b"abc123456789\n")),
            (("docker", "inspect"), FakeProcess(stdout=b"running\n")),
        ])
        rung, claim_by, _ = step_outcome(await run_module("docker.run", image="nginx"))
        assert rung is Outcome.OBSERVED
        assert claim_by == ClaimBy.NONE.value
