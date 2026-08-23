"""Public runtime versions must follow package metadata.

The metadata-to-metadata comparison this started as could not fail for the
reason it was written: `core.__version__` is read from `importlib.metadata`, so
comparing it to `importlib.metadata` compares a value to itself. It did fail,
once, and only by accident — the wheel-boundary test regenerates `egg-info`
mid-session, so on a working copy whose editable install was stale the resolved
version changed underneath a value cached at import time.

That accident is worth keeping on purpose, because the condition behind it is
real: an editable install whose metadata no longer matches `pyproject.toml`
makes every version-dependent result in the suite describe a package that is not
the one being edited. So this now compares the runtime values against the
declared version, which is the only number that cannot drift from the source.
"""

from importlib.metadata import version
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def declared_version() -> str:
    for line in PYPROJECT.read_text(encoding="utf-8").splitlines():
        if line.startswith("version = "):
            return line.split("=", 1)[1].strip().strip('"')
    raise AssertionError("pyproject.toml declares no version")


def test_core_and_cli_versions_match_installed_package():
    import cli
    import core

    package_version = version("flyto-core")
    assert core.__version__ == package_version
    assert cli.__version__ == package_version


def test_installed_metadata_matches_the_declared_version():
    declared = declared_version()
    installed = version("flyto-core")
    assert installed == declared, (
        f"installed flyto-core metadata says {installed} but pyproject.toml "
        f"declares {declared}. An editable install goes stale when the version "
        "changes; re-run `pip install -e '.[dev]'` so every version-dependent "
        "result in this suite describes the package actually being edited."
    )
