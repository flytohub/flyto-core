# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Keeps the published security status page honest.

`SECURITY_STATUS.md` makes two public claims: every advisory is patched, and
every one has a regression test. A page that drifts from reality is worse than
no page — it converts an accurate reputation problem into an inaccurate
reassurance. So the claims are checked here rather than trusted:

* every advisory in the manifest names at least one regression test, and every
  named test resolves to a test node pytest can actually collect;
* the rendered page is current with the manifest;
* the manifest is internally consistent (no duplicate or malformed entries).

The collection check is the important one. Without it, renaming or deleting a
test would leave the page advertising coverage that no longer exists.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "security" / "advisories.json"
STATUS_PAGE = ROOT / "SECURITY_STATUS.md"
GENERATOR = ROOT / "scripts" / "generate_security_status.py"

REQUIRED_FIELDS = {
    "ghsa",
    "severity",
    "published",
    "affected",
    "patched",
    "summary",
    "regression_tests",
}


def advisories() -> list[dict]:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_manifest_is_well_formed():
    entries = advisories()
    assert entries, "advisory manifest is empty"

    seen = set()
    problems = []
    for entry in entries:
        missing = REQUIRED_FIELDS - set(entry)
        if missing:
            problems.append(f"{entry.get('ghsa', '?')}: missing fields {sorted(missing)}")
        ghsa = entry.get("ghsa", "")
        if not ghsa.startswith("GHSA-"):
            problems.append(f"{ghsa!r} is not a GHSA identifier")
        if ghsa in seen:
            problems.append(f"{ghsa} appears more than once")
        seen.add(ghsa)
        if entry.get("severity") not in {"critical", "high", "medium", "low"}:
            problems.append(f"{ghsa}: unexpected severity {entry.get('severity')!r}")

    assert not problems, "advisory manifest is malformed:\n  " + "\n  ".join(problems)


def test_every_advisory_names_a_regression_test():
    """An advisory without a regression test is a fix nothing would catch the
    removal of. The status page must never claim coverage that does not exist."""
    naked = [
        entry["ghsa"]
        for entry in advisories()
        if not entry.get("regression_tests")
    ]
    assert not naked, (
        "These advisories have no regression test recorded: "
        f"{naked}. Write one and add it to security/advisories.json — the "
        "status page publishes this column."
    )


@pytest.mark.parametrize(
    "reference",
    sorted({t for entry in advisories() for t in entry["regression_tests"]}),
)
def test_named_regression_test_is_collectable(reference):
    """Every reference in the manifest must resolve to a real test node.

    This is what stops the page from advertising coverage that a rename or
    deletion has silently removed.
    """
    path = ROOT / reference.split("::")[0]
    assert path.exists(), f"{reference}: file does not exist"

    result = subprocess.run(
        [sys.executable, "-m", "pytest", reference, "--collect-only", "-q", "--no-cov", "-p", "no:cacheprovider"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"{reference} did not collect — the security status page names it as the "
        f"regression test for a published advisory.\n{result.stdout[-1500:]}"
    )
    assert "no tests ran" not in result.stdout, f"{reference} collected zero tests"


def test_status_page_is_current():
    """The rendered page must match the manifest."""
    result = subprocess.run(
        [sys.executable, str(GENERATOR), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "SECURITY_STATUS.md is stale. Run "
        f"`python scripts/generate_security_status.py`.\n{result.stdout}{result.stderr}"
    )


def test_status_page_states_the_current_secure_release():
    """The headline claim readers act on: which version is safe to install."""
    page = STATUS_PAGE.read_text(encoding="utf-8")
    patched = {
        entry["patched"].lstrip(">= ").strip()
        for entry in advisories()
        if entry["patched"] != "-"
    }
    newest = max(patched, key=lambda v: tuple(int(p) for p in v.split(".") if p.isdigit()))
    assert f"Current secure release: `{newest}`" in page
