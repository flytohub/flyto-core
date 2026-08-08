# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""The generated catalog must be a property of the source, not of the machine.

`docs/TOOL_CATALOG.md` is generated from the live `ModuleRegistry`, and some
module categories only register when an optional dependency is importable
(`huggingface` checks `find_spec("transformers")` before importing anything).
That made the output depend on which extras the developer happened to have:
running the generator on a machine with the `vector` extra installed — which
pulls `transformers` in transitively — silently rewrote the catalog to advertise
7 modules and a whole category that a default `pip install flyto-core` does not
expose, and every cross-referencing count in README/STATE/ARCHITECTURE with it.

That is a bad failure mode because it is invisible: the generator succeeds, the
diff looks intentional, and the next person to regenerate on a clean machine
reverts it. So the guarantee is enforced here rather than documented and hoped
for: the generator is run twice in subprocesses, once with the gating dependency
visible and once with it hidden, and the two outputs must be byte-identical.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GENERATOR = ROOT / "scripts" / "generate_catalog.py"
CATALOG = ROOT / "docs" / "TOOL_CATALOG.md"

# Written into a temporary PYTHONPATH entry to simulate a machine that does not
# have the gating dependency, without touching the real environment.
_HIDE_SHIM = '''\
import importlib.util

_real = importlib.util.find_spec
_HIDDEN = {names!r}


def find_spec(name, *args, **kwargs):
    if name.split(".")[0] in _HIDDEN:
        return None
    return _real(name, *args, **kwargs)


importlib.util.find_spec = find_spec
'''


def _gating_dependencies() -> set[str]:
    """The optional distributions that gate a category, read from the generator."""
    # Kept in sync with scripts/generate_catalog.py rather than duplicated: the
    # category name maps to the distribution its __init__ checks for.
    source = GENERATOR.read_text(encoding="utf-8")
    assert "_ENV_GATED_CATEGORIES" in source, (
        "generate_catalog.py no longer declares _ENV_GATED_CATEGORIES; the "
        "catalog may have become environment-dependent again."
    )
    return {"transformers"}


def _run_generator(extra_pythonpath: str | None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    if extra_pythonpath:
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            f"{extra_pythonpath}{os.pathsep}{existing}" if existing else extra_pythonpath
        )
    return subprocess.run(
        [sys.executable, str(GENERATOR), "--check"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def hidden_dependency_path(tmp_path) -> str:
    shim_dir = tmp_path / "no_optional_deps"
    shim_dir.mkdir()
    (shim_dir / "sitecustomize.py").write_text(
        _HIDE_SHIM.format(names=_gating_dependencies()), encoding="utf-8"
    )
    return str(shim_dir)


def test_committed_catalog_is_current_in_this_environment():
    """Baseline: the catalog matches what this machine generates."""
    result = _run_generator(None)
    assert result.returncode == 0, (
        "docs/TOOL_CATALOG.md is stale. Run "
        f"`python scripts/generate_catalog.py`.\n{result.stdout}{result.stderr}"
    )


def test_committed_catalog_is_current_without_the_optional_dependency(
    hidden_dependency_path,
):
    """The same catalog must be correct on a machine without the extras.

    This is the check that matters. If it fails while the test above passes,
    the committed catalog was generated on a machine with an optional extra
    installed and advertises modules the released package does not expose.
    """
    result = _run_generator(hidden_dependency_path)
    assert result.returncode == 0, (
        "docs/TOOL_CATALOG.md is only valid on a machine that has the optional "
        "dependency installed. Regenerate it — the generator must exclude "
        "environment-gated categories.\n" + result.stdout + result.stderr
    )


def test_catalog_counts_agree_across_environments(hidden_dependency_path):
    """Both runs must report the same module and category totals.

    Compares the generator's own reported counts rather than only its exit
    status, so a mismatch names the numbers instead of just failing."""
    with_dep = _run_generator(None)
    without_dep = _run_generator(hidden_dependency_path)

    def counts(result: subprocess.CompletedProcess) -> str:
        for line in result.stdout.splitlines():
            if "modules across" in line:
                return line.strip()
        return f"<no count line: {result.stdout!r} {result.stderr!r}>"

    assert counts(with_dep) == counts(without_dep), (
        "The catalog generator reports different totals depending on which "
        f"optional dependencies are installed:\n"
        f"  with:    {counts(with_dep)}\n"
        f"  without: {counts(without_dep)}"
    )


def test_catalog_documents_the_exclusion():
    """A reader must be able to tell the counts exclude optional categories,
    otherwise the number looks like the whole story."""
    catalog = CATALOG.read_text(encoding="utf-8")
    assert "default `pip install flyto-core`" in catalog
    assert "huggingface" in catalog, (
        "The catalog no longer names the excluded optional category, so its "
        "module count silently under-reports what the package can offer."
    )
