import importlib
from pathlib import Path

import pytest

from src.cli.workflow import list_workflows, sanitize_workflow_path

cli_main = importlib.import_module("src.cli.main")


def _write_workflow(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("name: boundary-test\nsteps: []\n", encoding="utf-8")
    return path


def test_resolves_relative_yaml_with_traversal(monkeypatch, tmp_path):
    workflow = _write_workflow(tmp_path / "outside" / "workflow.yaml")
    working_dir = tmp_path / "working" / "nested"
    working_dir.mkdir(parents=True)
    monkeypatch.chdir(working_dir)

    selected = Path("../../outside/./workflow.yaml")

    assert sanitize_workflow_path(selected) == workflow.resolve()


@pytest.mark.parametrize("suffix", [".yaml", ".yml"])
def test_accepts_absolute_yaml_workflow(tmp_path, suffix):
    workflow = _write_workflow(tmp_path / f"workflow{suffix}")

    assert sanitize_workflow_path(workflow) == workflow.resolve()


@pytest.mark.parametrize("name", ["missing.yaml", "directory.yaml"])
def test_rejects_missing_or_non_file_paths(tmp_path, name):
    selected = tmp_path / name
    if name == "directory.yaml":
        selected.mkdir()

    with pytest.raises(ValueError):
        sanitize_workflow_path(selected)


@pytest.mark.parametrize("name", ["workflow.json", "workflow.txt", "workflow"])
def test_rejects_unsupported_suffixes(tmp_path, name):
    selected = _write_workflow(tmp_path / name)

    with pytest.raises(ValueError, match=r"\.yaml or \.yml"):
        sanitize_workflow_path(selected)


def test_accepts_yaml_symlink_to_yaml_file(tmp_path):
    target = _write_workflow(tmp_path / "target.yml")
    selected = tmp_path / "selected.yaml"
    selected.symlink_to(target)

    assert sanitize_workflow_path(selected) == target.resolve()


def test_rejects_yaml_symlink_to_non_yaml_file(tmp_path):
    target = _write_workflow(tmp_path / "target.txt")
    selected = tmp_path / "selected.yaml"
    selected.symlink_to(target)

    with pytest.raises(ValueError, match="Resolved workflow path"):
        sanitize_workflow_path(selected)


def test_list_workflows_filters_non_file_and_non_yaml_targets(monkeypatch, tmp_path):
    valid = _write_workflow(tmp_path / "valid.yaml")
    (tmp_path / "directory.yaml").mkdir()
    non_yaml_target = _write_workflow(tmp_path / "target.txt")
    (tmp_path / "redirect.yaml").symlink_to(non_yaml_target)
    monkeypatch.setattr("src.cli.workflow.WORKFLOWS_DIR", tmp_path)

    assert list_workflows() == [valid.resolve()]


def test_non_interactive_invalid_path_exits_before_read_or_run(
    monkeypatch, tmp_path, capsys
):
    selected = tmp_path / "missing.yaml"
    run_called = False

    def unexpected_run(*args, **kwargs):
        nonlocal run_called
        run_called = True

    monkeypatch.setattr(cli_main, "run_workflow", unexpected_run)
    monkeypatch.setattr("sys.argv", ["flyto", "run", str(selected)])

    with pytest.raises(SystemExit) as exc_info:
        cli_main.main()

    assert exc_info.value.code == 1
    assert not run_called
    assert "Invalid workflow file" in capsys.readouterr().out


def test_non_interactive_runs_with_canonical_workflow_path(monkeypatch, tmp_path):
    workflow = _write_workflow(tmp_path / "outside" / "workflow.yaml")
    working_dir = tmp_path / "working"
    working_dir.mkdir()
    monkeypatch.chdir(working_dir)
    received = []

    monkeypatch.setattr(
        cli_main,
        "run_workflow",
        lambda workflow_path, *args: received.append(workflow_path),
    )
    monkeypatch.setattr("sys.argv", ["flyto", "run", "../outside/workflow.yaml"])

    cli_main.main()

    assert received == [workflow.resolve()]


def test_non_interactive_rejects_path_invalidated_before_execution(
    monkeypatch, tmp_path, capsys
):
    workflow = _write_workflow(tmp_path / "workflow.yaml")
    run_called = False

    def invalidate_path(loaded_workflow, args):
        workflow.unlink()
        return {}

    def unexpected_run(*args, **kwargs):
        nonlocal run_called
        run_called = True

    monkeypatch.setattr(cli_main, "merge_params", invalidate_path)
    monkeypatch.setattr(cli_main, "run_workflow", unexpected_run)
    monkeypatch.setattr("sys.argv", ["flyto", "run", str(workflow)])

    with pytest.raises(SystemExit) as exc_info:
        cli_main.main()

    assert exc_info.value.code == 1
    assert not run_called
    assert "Invalid workflow file" in capsys.readouterr().out


def test_interactive_custom_path_exits_before_read_or_run(
    monkeypatch, tmp_path, capsys
):
    selected = tmp_path / "missing.yml"
    run_called = False

    def unexpected_run(*args, **kwargs):
        nonlocal run_called
        run_called = True

    monkeypatch.setattr(cli_main, "select_language", lambda: "en")
    monkeypatch.setattr(cli_main, "clear_screen", lambda: None)
    monkeypatch.setattr(cli_main, "print_logo", lambda i18n: None)
    monkeypatch.setattr(cli_main, "load_config", lambda: {})
    monkeypatch.setattr(cli_main, "select_workflow", lambda i18n: selected)
    monkeypatch.setattr(cli_main, "run_workflow", unexpected_run)
    monkeypatch.setattr("sys.argv", ["flyto"])

    with pytest.raises(SystemExit) as exc_info:
        cli_main.main()

    assert exc_info.value.code == 1
    assert not run_called
    assert "Invalid workflow file" in capsys.readouterr().out


def test_interactive_runs_with_canonical_workflow_path(monkeypatch, tmp_path):
    workflow = _write_workflow(tmp_path / "outside" / "workflow.yml")
    working_dir = tmp_path / "working"
    working_dir.mkdir()
    monkeypatch.chdir(working_dir)
    received = []

    monkeypatch.setattr(cli_main, "select_language", lambda: "en")
    monkeypatch.setattr(cli_main, "clear_screen", lambda: None)
    monkeypatch.setattr(cli_main, "print_logo", lambda i18n: None)
    monkeypatch.setattr(cli_main, "load_config", lambda: {})
    monkeypatch.setattr(
        cli_main, "select_workflow", lambda i18n: Path("../outside/workflow.yml")
    )
    monkeypatch.setattr(cli_main, "collect_params", lambda workflow, i18n: {})
    monkeypatch.setattr(
        cli_main,
        "run_workflow",
        lambda workflow_path, *args: received.append(workflow_path),
    )
    monkeypatch.setattr("sys.argv", ["flyto"])

    cli_main.main()

    assert received == [workflow.resolve()]


def test_interactive_rejects_path_invalidated_before_execution(
    monkeypatch, tmp_path, capsys
):
    workflow = _write_workflow(tmp_path / "workflow.yml")
    run_called = False

    def invalidate_path(loaded_workflow, i18n):
        workflow.unlink()
        return {}

    def unexpected_run(*args, **kwargs):
        nonlocal run_called
        run_called = True

    monkeypatch.setattr(cli_main, "select_language", lambda: "en")
    monkeypatch.setattr(cli_main, "clear_screen", lambda: None)
    monkeypatch.setattr(cli_main, "print_logo", lambda i18n: None)
    monkeypatch.setattr(cli_main, "load_config", lambda: {})
    monkeypatch.setattr(cli_main, "select_workflow", lambda i18n: workflow)
    monkeypatch.setattr(cli_main, "collect_params", invalidate_path)
    monkeypatch.setattr(cli_main, "run_workflow", unexpected_run)
    monkeypatch.setattr("sys.argv", ["flyto"])

    with pytest.raises(SystemExit) as exc_info:
        cli_main.main()

    assert exc_info.value.code == 1
    assert not run_called
    assert "Invalid workflow file" in capsys.readouterr().out
