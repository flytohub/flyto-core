import os
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


def test_ci_pins_compatible_pip_before_dependency_lock_generation() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    pip_pin = "python -m pip install --upgrade 'pip>=26.1.2,<26.2'"
    lock_command = "bash scripts/lock-deps.sh"

    assert pip_pin in workflow
    assert lock_command in workflow
    assert workflow.index(pip_pin) < workflow.index(lock_command)


def _dependency_wheel(directory: Path, version: str) -> None:
    name = "flyto2_lock_test_dependency"
    dist_info = f"{name}-{version}.dist-info"
    with ZipFile(directory / f"{name}-{version}-py3-none-any.whl", "w") as wheel:
        wheel.writestr(
            f"{dist_info}/METADATA",
            f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n",
        )
        wheel.writestr(
            f"{dist_info}/WHEEL",
            "Wheel-Version: 1.0\nGenerator: Flyto2 test\n"
            "Root-Is-Purelib: true\nTag: py3-none-any\n",
        )
        wheel.writestr(f"{dist_info}/RECORD", "")


def _offline_lock_project(directory: Path) -> dict:
    wheels = directory / "wheels"
    wheels.mkdir()
    for version in ("1.0.0", "2.0.0"):
        _dependency_wheel(wheels, version)
    (directory / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["setuptools>=83"]\n'
        'build-backend = "setuptools.build_meta"\n'
        '[project]\nname = "flyto2-lock-test"\nversion = "1.0.0"\n'
        'dependencies = ["flyto2-lock-test-dependency>=1"]\n'
        '[tool.setuptools]\npackages = []\n'
        '[tool.pip-tools]\nbuild-isolation = false\n',
        encoding="utf-8",
    )
    (directory / "requirements.lock").write_text(
        "# Original lock\nflyto2-lock-test-dependency==1.0.0\n",
        encoding="utf-8",
    )
    return {
        **os.environ,
        "PYTHON": sys.executable,
        "PIP_NO_INDEX": "1",
        "PIP_FIND_LINKS": str(wheels),
        "PIP_CONFIG_FILE": os.devnull,
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
    }


def test_lock_rebuild_keeps_versions_until_explicit_upgrade(tmp_path) -> None:
    env = _offline_lock_project(tmp_path)

    def rebuild(*args):
        result = subprocess.run(
            ["bash", str(ROOT / "scripts/lock-deps.sh"), *args],
            cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60,
        )
        assert result.returncode == 0, result.stderr[-2000:]
        return (tmp_path / "requirements.lock").read_bytes()

    preserved = rebuild()
    assert b"flyto2-lock-test-dependency==1.0.0" in preserved
    assert b"flyto2-lock-test-dependency==2.0.0" not in preserved
    assert rebuild() == preserved
    upgraded = rebuild("--upgrade")
    assert b"flyto2-lock-test-dependency==2.0.0" in upgraded
    assert b"flyto2-lock-test-dependency==1.0.0" not in upgraded


@pytest.mark.parametrize("args", (("--unknown",), ("--upgrade", "--unknown")))
def test_invalid_lock_options_fail_before_resolution(tmp_path, args) -> None:
    lock = tmp_path / "requirements.lock"
    lock.write_text("unchanged", encoding="utf-8")
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/lock-deps.sh"), *args],
        cwd=tmp_path,
        env={**os.environ, "PYTHON": str(tmp_path / "must-not-be-launched")},
        capture_output=True, text=True, timeout=5,
    )
    assert result.returncode == 2
    assert "Usage:" in result.stderr
    assert lock.read_text(encoding="utf-8") == "unchanged"
