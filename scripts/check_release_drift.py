#!/usr/bin/env python3
"""Refuse a version that already shipped different code.

The failure this exists to prevent has happened to every package in this
stack. `main` accumulates real changes, the version in `pyproject.toml` still
names a release that was cut before them, and the artifact on PyPI silently
stops being the thing the repository describes. Nothing in CI noticed, because
every check ran against the working tree, which was correct the whole time.

The rule is narrow on purpose:

    if a tag `v<version>` exists, the packaged source at HEAD must be
    byte-identical to that tag's

If the tag does not exist, the version is ahead of every release and there is
nothing to contradict — that is the normal state between cutting a version and
pushing its tag, so it passes.

This does not require a release. It requires that the version number stop
claiming to be one that shipped something else.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
# What a wheel actually carries, plus the file that declares how. Docs,
# handoffs and CI config are deliberately out: changing them does not change
# the artifact, and failing on them would train everyone to bump the version
# for a typo fix, which is how a version number stops meaning anything.
PACKAGED_PATHS = ("src", "pyproject.toml", "MANIFEST.in")


def declared_version() -> str:
    for line in PYPROJECT.read_text(encoding="utf-8").splitlines():
        if line.startswith("version = "):
            return line.split("=", 1)[1].strip().strip('"')
    raise SystemExit("check_release_drift: no version in pyproject.toml")


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ("git", *args), cwd=ROOT, capture_output=True, text=True, check=False
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    version = declared_version()
    tag = f"v{version}"

    if _git("rev-parse", "--verify", "--quiet", f"{tag}^{{commit}}").returncode != 0:
        print(f"release drift: PASS ({version} is unreleased; no {tag} tag)")
        return 0

    existing = [path for path in PACKAGED_PATHS if (ROOT / path).exists()]
    changed = _git("diff", "--name-only", tag, "HEAD", "--", *existing)
    if changed.returncode != 0:
        # A shallow clone without tag history cannot answer the question. Say
        # so rather than reporting a pass it did not earn.
        print("release drift: INCONCLUSIVE (cannot diff against " f"{tag})")
        print(changed.stderr.strip())
        return 1

    files = [line for line in changed.stdout.splitlines() if line.strip()]
    if not files:
        print(f"release drift: PASS ({version} matches {tag})")
        return 0

    print(f"release drift: FAIL — packaged source changed since {tag} was cut")
    for path in files[:20]:
        print(f"  {path}")
    if len(files) > 20:
        print(f"  ... and {len(files) - 20} more")
    print(
        f"\nThe wheel published as {version} does not contain these changes, so "
        f"anyone installing {version} gets something this repository no longer\n"
        "describes. Bump the version in pyproject.toml."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
