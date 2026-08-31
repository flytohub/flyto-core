# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Are the alarms wired? Cut each seam and require the suite to notice.

Every defect worth finding in this project has been a seam — two parts each
correct on its own, connected wrongly or not at all — and a unit test cannot see
a seam. The measured proof: a merge stacked two Escape listeners on one element
and both sides' suites passed, 7/7 and 6/6. Broken integration, everything
green.

So the tests are checked the way a smoke alarm is checked: with smoke. For each
entry in ``_seam_saw.SEAMS`` this file spawns a pytest run with that one
connection cut, and requires the named tests to FAIL. A seam whose tests still
pass has an alarm that is decorative, and this file fails instead — which is the
only way a decorative test ever gets found.

Two things this deliberately is not:

  * Not a coverage percentage. A line that is executed is not a line that is
    checked, and the number would go up while the property got weaker.

  * Not a replacement for the tests it checks. It proves they are load-bearing;
    they are still what says what the behaviour should be.

The ratchet at the bottom is the part that makes this permanent rather than a
one-off cleanup: the count of covered seams may only go up. A fix landing
without its seam is how the same class of defect returns — the fix works today,
nothing records why it must keep working, and the test guarding it is one
refactor away from looking redundant.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.core._seam_saw import ENV_VAR, SEAMS


CORE_ROOT = Path(__file__).resolve().parents[2]

#: Seams named by the 2026-08-30 audit that this suite does NOT yet cover, with
#: the reason. Listed rather than omitted: an uncovered seam somebody wrote down
#: is a gap; an uncovered seam nobody wrote down is a surprise. Moving one up
#: into SEAMS is the unit of progress here.
UNCOVERED = {
    "redaction-sinks": "cloud-side; the five persistence sinks live in flyto-cloud",
    "consumer-reads-the-rung": "no consumer reads it yet — that is the next step of this work",
    "wake-word-listener-registration": (
        "cloud-side; the listener and its router live in the Vue frontend"
    ),
    "credential-resolver-in-place-mutation": (
        "cloud-side; the resolver is in flyto-cloud services/runtime/execution"
    ),
    "checkpoint-path-traversal": "core, not yet written",
    "browser-pool-cross-execution-adoption": "core, not yet written; unfixed in both trees",
}

#: May only go up. Set to what holds the day this landed.
COVERED_SEAM_FLOOR = 8


def _run_pytest(node_ids, seam_name=None):
    """Run pytest in a child process, optionally with one seam cut."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(CORE_ROOT / "src") + os.pathsep + str(CORE_ROOT)
    env.pop("FLYTO_ENV", None)
    if seam_name:
        env[ENV_VAR] = seam_name
    else:
        env.pop(ENV_VAR, None)
    return subprocess.run(
        [
            sys.executable, "-m", "pytest", *node_ids,
            # No -x: the child must run to the end so the tally carries both
            # numbers. With it, the run stops at the first failure, `passed` is
            # 0, and the sabotage check below cannot tell a precise cut from one
            # that broke everything.
            "-q", "-p", "no:randomly", "--no-cov", "--tb=no",
            "-p", "tests.core._seam_saw",
        ],
        cwd=CORE_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )


def _tally(stdout):
    """pytest's summary line as {outcome: count}, or {} if there is not one.

    Read rather than inferred from the exit code, because the exit code cannot
    tell a test that failed from a run that never happened, and those two are
    the difference between this suite meaning something and not.
    """
    import re

    for line in reversed(stdout.strip().splitlines()):
        found = dict(
            (word, int(count))
            for count, word in re.findall(
                r"(\d+) (passed|failed|error|errors|skipped|xfailed|xpassed)", line
            )
        )
        if found:
            if "errors" in found:
                found["error"] = found.pop("errors")
            return found
    return {}


@pytest.mark.parametrize("seam", SEAMS, ids=[seam.name for seam in SEAMS])
def test_cutting_the_seam_turns_its_guards_red(seam):
    """The alarm test. Cut one connection; the named tests must notice.

    A pass here means: if somebody removes this fix in a refactor, or writes the
    obvious thing without knowing why the unobvious thing is there, at least one
    test says so. A failure means the tests around this seam are decorative.
    """
    result = _run_pytest(seam.guarded_by, seam_name=seam.name)
    report = f"--- child stdout ---\n{result.stdout[-2000:]}\n{result.stderr[-800:]}"

    # A non-zero exit is NOT enough, and assuming it was made this suite lie on
    # its first run. One cut tried to reassign `sqlite3.Connection.commit`,
    # which CPython refuses on an immutable type; the child died in
    # `pytest_configure` with INTERNALERROR, exited non-zero, and this test
    # passed while nothing whatsoever had been tested. A saw that breaks before
    # it touches the wood proves the wood is fine.
    assert "INTERNALERROR" not in result.stdout + result.stderr, (
        f"the cut for {seam.name!r} crashed instead of cutting, so nothing was "
        f"tested.\n{report}"
    )
    assert "error" not in _tally(result.stdout), (
        f"the guards for {seam.name!r} errored rather than failed — a collection "
        f"or fixture problem, not the seam being noticed.\n{report}"
    )
    assert _tally(result.stdout).get("failed"), (
        f"seam {seam.name!r} was cut and nothing noticed.\n"
        f"It carries: {seam.carries}\n"
        f"Guards that should have failed: {seam.guarded_by}\n{report}"
    )
    assert _tally(result.stdout).get("passed"), (
        f"cutting {seam.name!r} turned EVERY guard red, which is sabotage rather "
        f"than a severed seam: a cut that breaks unrelated tests proves nothing "
        f"about the connection it claims to carry.\n{report}"
    )


def test_every_guard_passes_when_nothing_is_cut():
    """The other half, and the one that stops this suite lying.

    Without it, a guard that is simply broken — a typo, a stale import, a
    fixture that always raises — would satisfy every assertion above, because a
    test that always fails "fails when the seam is cut" too. Checked once over
    the union of every guard rather than per seam, because the guards overlap
    heavily and the child runs are the expensive part.
    """
    every_guard = sorted({node for seam in SEAMS for node in seam.guarded_by})

    result = _run_pytest(every_guard)

    assert result.returncode == 0, (
        "the seam guards do not pass with nothing cut, so the cuts above prove "
        f"nothing.\n--- child stdout ---\n{result.stdout[-2000:]}"
    )


class TestTheRatchet:
    """Covered seams may only go up; uncovered ones must stay named."""

    def test_the_covered_count_has_not_gone_down(self):
        assert len(SEAMS) >= COVERED_SEAM_FLOOR, (
            f"{len(SEAMS)} seams covered, floor is {COVERED_SEAM_FLOOR}. "
            "A seam was removed. Removing one is fine when the connection it "
            "guarded no longer exists — lower the floor in the same commit and "
            "say which connection went away."
        )

    def test_every_seam_names_what_it_carries(self):
        """A seam whose sentence nobody can check is not a seam, it is a mood."""
        for seam in SEAMS:
            assert seam.carries and len(seam.carries.split()) >= 5, seam.name
            assert seam.guarded_by, seam.name

    def test_seam_names_are_unique(self):
        names = [seam.name for seam in SEAMS]
        assert len(names) == len(set(names))

    def test_uncovered_seams_carry_a_reason(self):
        """Written down is a gap. Not written down is a surprise."""
        for name, reason in UNCOVERED.items():
            assert reason and len(reason.split()) >= 3, name

    def test_a_seam_is_not_in_both_lists(self):
        assert not (set(UNCOVERED) & {seam.name for seam in SEAMS})
