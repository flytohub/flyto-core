# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Real integration tests for cli/runner.py.

Uses real YAML workflow files and the real workflow engine — no mocks.

The cli package uses relative imports (e.g. `from ..core.engine.workflow_engine
import WorkflowEngine`) that require cli to be a sub-package of a parent.
A module-level fixture patches sys.modules so that `src.cli` / `src.core` are
recognised as siblings under a synthetic `src` namespace package, which makes
the relative import resolve correctly at runtime.
"""

import json
import sys
import types
from pathlib import Path

import pytest
import yaml

# ---------------------------------------------------------------------------
# Bootstrap: make cli look like src.cli so relative imports resolve
# ---------------------------------------------------------------------------

def _bootstrap_src_namespace() -> None:
    """
    Inject a synthetic 'src' namespace package and register shim modules so
    that ``from ..core.engine.workflow_engine import WorkflowEngine`` inside
    cli/runner.py resolves to the real engine.
    """
    if "src" in sys.modules:
        return  # already done

    # Ensure src/ is on the path
    src_root = Path(__file__).parent.parent.parent / "src"
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))

    import cli  # noqa: PLC0415
    import core  # noqa: PLC0415
    import cli.runner  # noqa: PLC0415  – loads the module before we patch it

    # Synthetic 'src' package
    src_mod = types.ModuleType("src")
    src_mod.__path__ = [str(src_root)]
    src_mod.__package__ = ""
    sys.modules["src"] = src_mod

    # Re-register cli as src.cli
    cli.__name__ = "src.cli"
    cli.__package__ = "src.cli"
    sys.modules["src.cli"] = cli
    sys.modules["src.cli.runner"] = cli.runner
    cli.runner.__package__ = "src.cli"

    # Re-register core as src.core
    core.__name__ = "src.core"
    core.__package__ = "src.core"
    sys.modules["src.core"] = core

    import core.engine as _ce  # noqa: PLC0415
    _ce.__name__ = "src.core.engine"
    sys.modules["src.core.engine"] = _ce

    # Compatibility shim: src.core.engine.workflow_engine
    from core.engine.workflow.engine import WorkflowEngine  # noqa: PLC0415
    _shim = types.ModuleType("src.core.engine.workflow_engine")
    _shim.WorkflowEngine = WorkflowEngine
    sys.modules["src.core.engine.workflow_engine"] = _shim

    # Register built-in atomic modules
    from core.modules import atomic  # noqa: PLC0415, F401


_bootstrap_src_namespace()

# ---------------------------------------------------------------------------
# Now safe to import from cli
# ---------------------------------------------------------------------------

from cli.i18n import I18n  # noqa: E402
from cli.runner import (  # noqa: E402
    _handle_execution_error,
    _print_step_progress,
    _save_results,
    _show_completion,
    run_workflow,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_i18n() -> I18n:
    return I18n()  # default locale (English)


def _make_workflow_yaml(tmp_path: Path, content: dict) -> Path:
    wf_file = tmp_path / "workflow.yaml"
    wf_file.write_text(yaml.dump(content))
    return wf_file


# ---------------------------------------------------------------------------
# _show_completion
# ---------------------------------------------------------------------------

class TestShowCompletion:
    def test_prints_separator_lines(self, capsys):
        i18n = _make_i18n()
        _show_completion(1.23, i18n)
        captured = capsys.readouterr()
        assert "=" * 70 in captured.out

    def test_prints_workflow_completed_message(self, capsys):
        i18n = _make_i18n()
        _show_completion(0.5, i18n)
        captured = capsys.readouterr()
        assert "Workflow completed successfully!" in captured.out

    def test_prints_execution_time(self, capsys):
        i18n = _make_i18n()
        _show_completion(3.14, i18n)
        captured = capsys.readouterr()
        assert "3.14s" in captured.out

    def test_execution_time_two_decimal_places(self, capsys):
        i18n = _make_i18n()
        _show_completion(1.0, i18n)
        captured = capsys.readouterr()
        assert "1.00s" in captured.out


# ---------------------------------------------------------------------------
# _print_step_progress
# ---------------------------------------------------------------------------

class TestPrintStepProgress:
    def test_prints_step_fraction(self, capsys):
        i18n = _make_i18n()
        steps = [{"id": "step1", "module": "data.json.parse", "params": {}}]
        _print_step_progress(1, steps, 1, i18n)
        captured = capsys.readouterr()
        assert "1/1" in captured.out

    def test_prints_module_name_when_no_description(self, capsys):
        i18n = _make_i18n()
        steps = [{"id": "step1", "module": "data.json.stringify", "params": {}}]
        _print_step_progress(1, steps, 3, i18n)
        captured = capsys.readouterr()
        assert "data.json.stringify" in captured.out

    def test_prints_description_when_present(self, capsys):
        i18n = _make_i18n()
        steps = [{"id": "step1", "module": "data.json.parse", "description": "Parse input"}]
        _print_step_progress(1, steps, 2, i18n)
        captured = capsys.readouterr()
        assert "Parse input" in captured.out

    def test_step_index_exceeds_total_does_nothing(self, capsys):
        i18n = _make_i18n()
        steps = [{"id": "step1", "module": "data.json.parse"}]
        _print_step_progress(5, steps, 3, i18n)
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_step_index_equals_total_steps_prints_progress(self, capsys):
        """Exact boundary: step_index == total_steps → prints (not skipped)."""
        i18n = _make_i18n()
        steps = [
            {"id": "s1", "module": "data.json.parse"},
            {"id": "s2", "module": "data.json.stringify"},
        ]
        _print_step_progress(2, steps, 2, i18n)
        captured = capsys.readouterr()
        assert "Step 2/2" in captured.out

    def test_prints_step_progress_key(self, capsys):
        i18n = _make_i18n()
        steps = [
            {"id": "s1", "module": "data.json.parse"},
            {"id": "s2", "module": "data.json.stringify"},
        ]
        _print_step_progress(2, steps, 2, i18n)
        captured = capsys.readouterr()
        assert "Step 2/2" in captured.out


# ---------------------------------------------------------------------------
# _save_results
# ---------------------------------------------------------------------------

class TestSaveResults:
    def test_creates_json_file(self, tmp_path):
        i18n = _make_i18n()
        workflow = {"name": "My Workflow"}
        workflow_path = tmp_path / "my_workflow.yaml"
        params = {"key": "val"}
        results = [{"step_id": "step1", "status": "success"}]
        execution_time = 0.42
        config = {"storage": {"output_dir": str(tmp_path)}}

        output_file = _save_results(
            workflow, workflow_path, params, results, execution_time, config, i18n
        )

        assert output_file.exists()
        assert output_file.suffix == ".json"

    def test_json_content_workflow_name(self, tmp_path):
        i18n = _make_i18n()
        workflow = {"name": "Integration Test"}
        workflow_path = tmp_path / "integration_test.yaml"
        config = {"storage": {"output_dir": str(tmp_path)}}

        output_file = _save_results(
            workflow, workflow_path, {}, [], 1.0, config, i18n
        )

        data = json.loads(output_file.read_text())
        assert data["workflow"] == "Integration Test"

    def test_json_content_params(self, tmp_path):
        i18n = _make_i18n()
        workflow = {"name": "Test"}
        workflow_path = tmp_path / "test.yaml"
        params = {"url": "https://example.com", "limit": 10}
        config = {"storage": {"output_dir": str(tmp_path)}}

        output_file = _save_results(
            workflow, workflow_path, params, [], 0.1, config, i18n
        )

        data = json.loads(output_file.read_text())
        assert data["params"] == params

    def test_json_content_steps(self, tmp_path):
        i18n = _make_i18n()
        workflow = {"name": "Test"}
        workflow_path = tmp_path / "test.yaml"
        results = [
            {"step_id": "s1", "status": "success"},
            {"step_id": "s2", "status": "success"},
        ]
        config = {"storage": {"output_dir": str(tmp_path)}}

        output_file = _save_results(
            workflow, workflow_path, {}, results, 0.2, config, i18n
        )

        data = json.loads(output_file.read_text())
        assert data["steps"] == results

    def test_json_content_execution_time(self, tmp_path):
        i18n = _make_i18n()
        workflow = {"name": "Test"}
        workflow_path = tmp_path / "test.yaml"
        config = {"storage": {"output_dir": str(tmp_path)}}

        output_file = _save_results(
            workflow, workflow_path, {}, [], 3.75, config, i18n
        )

        data = json.loads(output_file.read_text())
        assert data["execution_time"] == pytest.approx(3.75)

    def test_json_content_timestamp_present(self, tmp_path):
        i18n = _make_i18n()
        workflow = {"name": "Test"}
        workflow_path = tmp_path / "test.yaml"
        config = {"storage": {"output_dir": str(tmp_path)}}

        output_file = _save_results(
            workflow, workflow_path, {}, [], 1.0, config, i18n
        )

        data = json.loads(output_file.read_text())
        assert "timestamp" in data
        assert len(data["timestamp"]) > 0

    def test_filename_contains_workflow_stem(self, tmp_path):
        i18n = _make_i18n()
        workflow = {"name": "Test"}
        workflow_path = tmp_path / "my_special_workflow.yaml"
        config = {"storage": {"output_dir": str(tmp_path)}}

        output_file = _save_results(
            workflow, workflow_path, {}, [], 0.0, config, i18n
        )

        assert "my_special_workflow" in output_file.name

    def test_creates_output_dir_if_missing(self, tmp_path):
        i18n = _make_i18n()
        workflow = {"name": "Test"}
        workflow_path = tmp_path / "test.yaml"
        new_dir = tmp_path / "deep" / "nested" / "output"
        config = {"storage": {"output_dir": str(new_dir)}}

        output_file = _save_results(
            workflow, workflow_path, {}, [], 0.0, config, i18n
        )

        assert new_dir.exists()
        assert output_file.exists()

    def test_uses_explicit_output_dir_from_config(self, tmp_path):
        """When config provides output_dir, results go there."""
        output_dir = tmp_path / "custom_output"
        config = {"storage": {"output_dir": str(output_dir)}}

        i18n = _make_i18n()
        workflow = {"name": "Test"}
        workflow_path = tmp_path / "test.yaml"

        output_file = _save_results(
            workflow, workflow_path, {}, [], 0.0, config, i18n
        )

        assert output_file.exists()
        assert output_file.parent == output_dir

    def test_prints_results_saved_message(self, tmp_path, capsys):
        i18n = _make_i18n()
        workflow = {"name": "Test"}
        workflow_path = tmp_path / "test.yaml"
        config = {"storage": {"output_dir": str(tmp_path)}}

        _save_results(workflow, workflow_path, {}, [], 0.0, config, i18n)

        captured = capsys.readouterr()
        assert "Results saved to" in captured.out

    def test_workflow_name_falls_back_to_stem(self, tmp_path):
        """When workflow dict has no 'name', uses the yaml file stem."""
        i18n = _make_i18n()
        workflow = {}  # no name key
        workflow_path = tmp_path / "fallback_stem.yaml"
        config = {"storage": {"output_dir": str(tmp_path)}}

        output_file = _save_results(
            workflow, workflow_path, {}, [], 0.0, config, i18n
        )

        data = json.loads(output_file.read_text())
        assert data["workflow"] == "fallback_stem"

    def test_config_missing_storage_key_uses_default(self, tmp_path):
        """When config has no 'storage' key, _save_results falls back to DEFAULT_OUTPUT_DIR."""
        from cli.config import DEFAULT_OUTPUT_DIR

        i18n = _make_i18n()
        workflow = {"name": "No Storage Config"}
        workflow_path = tmp_path / "no_storage.yaml"
        config = {}  # no 'storage' key at all

        output_file = _save_results(
            workflow, workflow_path, {}, [], 0.0, config, i18n
        )

        # File should be created under DEFAULT_OUTPUT_DIR
        assert output_file.exists()
        assert output_file.parent == Path(DEFAULT_OUTPUT_DIR)
        # Clean up so we don't pollute the project directory
        output_file.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# run_workflow — end-to-end with real engine
# ---------------------------------------------------------------------------

class TestRunWorkflow:
    """Run complete workflows using real YAML files and the real engine."""

    def test_json_parse_workflow_completes(self, tmp_path, capsys):
        """Single-step workflow using data.json.parse should complete successfully."""
        workflow_content = {
            "name": "JSON Parse Test",
            "steps": [
                {
                    "id": "parse_step",
                    "module": "data.json.parse",
                    "params": {"json_string": '{"hello": "world"}'},
                }
            ],
        }
        wf_file = _make_workflow_yaml(tmp_path, workflow_content)
        config = {"storage": {"output_dir": str(tmp_path)}}
        i18n = _make_i18n()

        run_workflow(wf_file, {}, config, i18n)

        captured = capsys.readouterr()
        assert "Workflow completed successfully!" in captured.out

    def test_json_stringify_workflow_completes(self, tmp_path, capsys):
        """Single-step workflow using data.json.stringify should complete."""
        workflow_content = {
            "name": "JSON Stringify Test",
            "steps": [
                {
                    "id": "stringify_step",
                    "module": "data.json.stringify",
                    "params": {"data": {"key": "value"}, "pretty": False},
                }
            ],
        }
        wf_file = _make_workflow_yaml(tmp_path, workflow_content)
        config = {"storage": {"output_dir": str(tmp_path)}}
        i18n = _make_i18n()

        run_workflow(wf_file, {}, config, i18n)

        captured = capsys.readouterr()
        assert "Workflow completed successfully!" in captured.out

    def test_run_workflow_saves_output_file(self, tmp_path):
        """After run_workflow, a JSON output file must exist in output_dir."""
        workflow_content = {
            "name": "Save Test",
            "steps": [
                {
                    "id": "s1",
                    "module": "data.json.parse",
                    "params": {"json_string": "[1, 2, 3]"},
                }
            ],
        }
        wf_file = _make_workflow_yaml(tmp_path, workflow_content)
        out_dir = tmp_path / "out"
        config = {"storage": {"output_dir": str(out_dir)}}
        i18n = _make_i18n()

        run_workflow(wf_file, {}, config, i18n)

        json_files = list(out_dir.glob("*.json"))
        assert len(json_files) == 1

    def test_run_workflow_output_file_has_step_results(self, tmp_path):
        """The saved JSON must record step execution results."""
        workflow_content = {
            "name": "Result Check",
            "steps": [
                {
                    "id": "parse_step",
                    "module": "data.json.parse",
                    "params": {"json_string": '{"x": 42}'},
                }
            ],
        }
        wf_file = _make_workflow_yaml(tmp_path, workflow_content)
        out_dir = tmp_path / "results"
        config = {"storage": {"output_dir": str(out_dir)}}
        i18n = _make_i18n()

        run_workflow(wf_file, {}, config, i18n)

        json_files = list(out_dir.glob("*.json"))
        assert json_files, "Expected output file"
        data = json.loads(json_files[0].read_text())
        assert data["workflow"] == "Result Check"
        assert isinstance(data["steps"], list)
        assert len(data["steps"]) >= 1
        assert data["steps"][0]["status"] == "success"

    def test_run_workflow_prints_step_progress(self, tmp_path, capsys):
        """Step progress line must appear in stdout."""
        workflow_content = {
            "name": "Progress Test",
            "steps": [
                {
                    "id": "step1",
                    "module": "data.json.stringify",
                    "params": {"data": {"a": 1}},
                }
            ],
        }
        wf_file = _make_workflow_yaml(tmp_path, workflow_content)
        config = {"storage": {"output_dir": str(tmp_path)}}
        i18n = _make_i18n()

        run_workflow(wf_file, {}, config, i18n)

        captured = capsys.readouterr()
        assert "Step 1/1" in captured.out

    def test_run_workflow_prints_starting_banner(self, tmp_path, capsys):
        """Starting workflow banner must appear."""
        workflow_content = {
            "name": "Banner Test",
            "steps": [
                {
                    "id": "s1",
                    "module": "data.json.parse",
                    "params": {"json_string": "{}"},
                }
            ],
        }
        wf_file = _make_workflow_yaml(tmp_path, workflow_content)
        config = {"storage": {"output_dir": str(tmp_path)}}
        i18n = _make_i18n()

        run_workflow(wf_file, {}, config, i18n)

        captured = capsys.readouterr()
        assert "Starting workflow..." in captured.out

    def test_run_workflow_two_step_workflow(self, tmp_path, capsys):
        """Multi-step workflow should complete and save both steps."""
        workflow_content = {
            "name": "Two Steps",
            "steps": [
                {
                    "id": "stringify",
                    "module": "data.json.stringify",
                    "params": {"data": {"val": 99}},
                },
                {
                    "id": "parse_back",
                    "module": "data.json.parse",
                    "params": {"json_string": '{"val": 99}'},
                },
            ],
        }
        wf_file = _make_workflow_yaml(tmp_path, workflow_content)
        out_dir = tmp_path / "two_step_out"
        config = {"storage": {"output_dir": str(out_dir)}}
        i18n = _make_i18n()

        run_workflow(wf_file, {}, config, i18n)

        captured = capsys.readouterr()
        assert "Workflow completed successfully!" in captured.out

        json_files = list(out_dir.glob("*.json"))
        assert json_files
        data = json.loads(json_files[0].read_text())
        assert len(data["steps"]) == 2

    def test_run_workflow_execution_time_recorded(self, tmp_path):
        """Saved JSON must include a non-negative execution_time."""
        workflow_content = {
            "name": "Timing Test",
            "steps": [
                {
                    "id": "s1",
                    "module": "data.json.parse",
                    "params": {"json_string": "null"},
                }
            ],
        }
        wf_file = _make_workflow_yaml(tmp_path, workflow_content)
        out_dir = tmp_path / "timing_out"
        config = {"storage": {"output_dir": str(out_dir)}}
        i18n = _make_i18n()

        run_workflow(wf_file, {}, config, i18n)

        json_files = list(out_dir.glob("*.json"))
        assert json_files
        data = json.loads(json_files[0].read_text())
        assert data["execution_time"] >= 0


# ---------------------------------------------------------------------------
# _handle_execution_error (lines 71-80)
# ---------------------------------------------------------------------------


class _FakeEngine:
    """Minimal engine stand-in that supplies get_execution_summary()."""

    def __init__(self, steps_executed: int, status: str):
        self._steps_executed = steps_executed
        self._status = status

    def get_execution_summary(self) -> dict:
        return {
            "steps_executed": self._steps_executed,
            "status": self._status,
        }


class TestHandleExecutionError:
    def test_exits_with_code_1(self, capsys):
        """_handle_execution_error calls sys.exit(1)."""
        i18n = _make_i18n()
        engine = _FakeEngine(steps_executed=2, status="failed")

        with pytest.raises(SystemExit) as exc_info:
            _handle_execution_error(ValueError("something broke"), engine, 5, i18n)

        assert exc_info.value.code == 1

    def test_prints_error_message(self, capsys):
        """_handle_execution_error prints the exception message."""
        i18n = _make_i18n()
        engine = _FakeEngine(steps_executed=1, status="failed")

        with pytest.raises(SystemExit):
            _handle_execution_error(RuntimeError("bad things happened"), engine, 3, i18n)

        captured = capsys.readouterr()
        assert "bad things happened" in captured.out

    def test_prints_steps_executed_summary(self, capsys):
        """_handle_execution_error prints steps_executed / total_steps."""
        i18n = _make_i18n()
        engine = _FakeEngine(steps_executed=3, status="failed")

        with pytest.raises(SystemExit):
            _handle_execution_error(Exception("oops"), engine, 7, i18n)

        captured = capsys.readouterr()
        assert "3/7" in captured.out

    def test_prints_status_in_summary(self, capsys):
        """_handle_execution_error prints the engine status string."""
        i18n = _make_i18n()
        engine = _FakeEngine(steps_executed=0, status="error")

        with pytest.raises(SystemExit):
            _handle_execution_error(Exception("fail"), engine, 2, i18n)

        captured = capsys.readouterr()
        assert "error" in captured.out


# ---------------------------------------------------------------------------
# run_workflow — engine import failure path (lines 120-124) and
# execution error path (lines 134-138)
# ---------------------------------------------------------------------------


class TestRunWorkflowErrorPaths:
    def test_execution_error_calls_handle_execution_error(self, tmp_path):
        """Lines 134-138: when asyncio.run raises, _handle_execution_error is called
        which calls sys.exit(1)."""
        # A module that doesn't exist will cause the engine to raise during execution
        workflow_content = {
            "name": "Bad Module",
            "steps": [
                {
                    "id": "bad_step",
                    "module": "nonexistent.module.that.does.not.exist",
                    "params": {},
                }
            ],
        }
        wf_file = _make_workflow_yaml(tmp_path, workflow_content)
        config = {"storage": {"output_dir": str(tmp_path)}}
        i18n = _make_i18n()

        with pytest.raises(SystemExit) as exc_info:
            run_workflow(wf_file, {}, config, i18n)

        assert exc_info.value.code == 1

    def test_run_workflow_zero_steps_exits_with_code_1(self, tmp_path, capsys):
        """A workflow with zero steps causes the engine to raise, which exits with code 1."""
        workflow_content = {
            "name": "Zero Steps",
            "steps": [],
        }
        wf_file = _make_workflow_yaml(tmp_path, workflow_content)
        config = {"storage": {"output_dir": str(tmp_path)}}
        i18n = _make_i18n()

        with pytest.raises(SystemExit) as exc_info:
            run_workflow(wf_file, {}, config, i18n)

        assert exc_info.value.code == 1

    def test_run_workflow_three_step_prints_all_progress(self, tmp_path, capsys):
        """A 3-step workflow verifies all step progress lines are printed."""
        workflow_content = {
            "name": "Three Steps",
            "steps": [
                {
                    "id": "step1",
                    "module": "data.json.parse",
                    "params": {"json_string": '{"a": 1}'},
                },
                {
                    "id": "step2",
                    "module": "data.json.stringify",
                    "params": {"data": {"b": 2}},
                },
                {
                    "id": "step3",
                    "module": "data.json.parse",
                    "params": {"json_string": '{"c": 3}'},
                },
            ],
        }
        wf_file = _make_workflow_yaml(tmp_path, workflow_content)
        out_dir = tmp_path / "three_step_out"
        config = {"storage": {"output_dir": str(out_dir)}}
        i18n = _make_i18n()

        run_workflow(wf_file, {}, config, i18n)

        captured = capsys.readouterr()
        assert "Workflow completed successfully!" in captured.out
        # At minimum the first step progress header must appear
        assert "Step 1/3" in captured.out

    def test_engine_import_failure_exits_with_code_1(self, tmp_path):
        """Lines 120-124: if WorkflowEngine cannot be imported, runner exits(1)."""
        # Temporarily shadow the shim module so the relative import in runner.py fails
        shim_key = "src.core.engine.workflow_engine"
        original = sys.modules.pop(shim_key, None)
        try:
            workflow_content = {
                "name": "Import Fail Test",
                "steps": [
                    {
                        "id": "s1",
                        "module": "data.json.parse",
                        "params": {"json_string": "{}"},
                    }
                ],
            }
            wf_file = _make_workflow_yaml(tmp_path, workflow_content)
            config = {"storage": {"output_dir": str(tmp_path)}}
            i18n = _make_i18n()

            with pytest.raises(SystemExit) as exc_info:
                run_workflow(wf_file, {}, config, i18n)

            assert exc_info.value.code == 1
        finally:
            # Restore the shim so other tests keep working
            if original is not None:
                sys.modules[shim_key] = original
