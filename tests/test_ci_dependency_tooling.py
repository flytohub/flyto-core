from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


def test_ci_pins_compatible_pip_before_dependency_lock_generation() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    pip_pin = "python -m pip install --upgrade 'pip<26.2'"
    lock_command = "bash scripts/lock-deps.sh"

    assert pip_pin in workflow
    assert lock_command in workflow
    assert workflow.index(pip_pin) < workflow.index(lock_command)
