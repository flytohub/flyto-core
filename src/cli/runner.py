"""
CLI Workflow Runner

Executes workflows and displays progress.
"""

import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import yaml

from .config import CLI_LINE_WIDTH, DEFAULT_OUTPUT_DIR, Colors
from .i18n import I18n


def _show_completion(execution_time: float, i18n: I18n) -> None:
    """Print the workflow-completed banner and execution time."""
    print()
    print("=" * CLI_LINE_WIDTH)
    print(Colors.OKGREEN + Colors.BOLD +
          i18n.t('cli.workflow_completed') + Colors.ENDC)
    print("=" * CLI_LINE_WIDTH)
    print(f"{i18n.t('cli.execution_time')}: {execution_time:.2f}s")


def _save_results(
    workflow: Dict[str, Any],
    workflow_path: Path,
    params: Dict[str, Any],
    results: list,
    execution_time: float,
    config: Dict[str, Any],
    i18n: I18n,
) -> Path:
    """Save execution results to a JSON file and print the path. Returns the output file path."""
    output_dir = Path(config.get('storage', {}).get('output_dir',
                                                     str(DEFAULT_OUTPUT_DIR)))
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = output_dir / f"workflow_{workflow_path.stem}_{timestamp}.json"

    output_data = {
        'workflow': workflow.get('name', workflow_path.stem),
        'params': params,
        'steps': results,
        'execution_time': execution_time,
        'timestamp': timestamp
    }

    with open(output_file, 'w') as f:
        json.dump(output_data, f, indent=2)

    print(f"{i18n.t('cli.results_saved')}: {output_file}")

    return output_file


def _handle_execution_error(
    exec_error: Exception,
    engine: Any,
    total_steps: int,
    i18n: I18n,
) -> None:
    """Print error details and execution summary, then exit."""
    print(f"\n{Colors.FAIL}{Colors.BOLD}"
          f"{i18n.t('status.error')}{Colors.ENDC}")
    print(f"{Colors.FAIL}Error: {str(exec_error)}{Colors.ENDC}")

    summary = engine.get_execution_summary()
    print(f"\n{Colors.WARNING}Execution Summary:{Colors.ENDC}")
    print(f"  Steps executed: {summary['steps_executed']}/{total_steps}")
    print(f"  Status: {summary['status']}")

    sys.exit(1)


def _print_step_progress(
    step_index: int,
    steps: list,
    total_steps: int,
    i18n: I18n,
) -> None:
    """Print progress line for a workflow step."""
    if step_index > total_steps:
        return
    progress = i18n.t('cli.step_progress', current=step_index, total=total_steps)
    step = steps[step_index - 1] if step_index <= len(steps) else {}
    description = step.get('description', '') or step.get('module', 'unknown')
    print(f"\n{Colors.OKCYAN}[{progress}]{Colors.ENDC} {description}")


def run_workflow(
    workflow_path: Path,
    params: Dict[str, Any],
    config: Dict[str, Any],
    i18n: I18n
) -> None:
    """Run a workflow"""
    print()
    print("=" * CLI_LINE_WIDTH)
    print(Colors.BOLD + i18n.t('cli.starting_workflow') + Colors.ENDC)
    print("=" * CLI_LINE_WIDTH)

    # Load workflow
    with open(workflow_path, 'r') as f:
        workflow = yaml.safe_load(f)

    steps = workflow.get('steps', [])
    total_steps = len(steps)
    start_time = time.time()

    try:
        from core.engine.workflow.engine import WorkflowEngine
    except Exception as e:
        print()
        print(Colors.FAIL + i18n.t('cli.workflow_failed') + Colors.ENDC)
        print(f"{i18n.t('cli.error_occurred')}: {str(e)}")
        sys.exit(1)

    engine = WorkflowEngine(workflow, params)
    current_step = [0]

    async def run_workflow_async():
        current_step[0] += 1
        _print_step_progress(current_step[0], steps, total_steps, i18n)
        return await engine.execute()

    try:
        asyncio.run(run_workflow_async())
    except Exception as exec_error:
        _handle_execution_error(exec_error, engine, total_steps, i18n)
        return  # _handle_execution_error calls sys.exit, but be explicit

    # Show success for each completed step
    execution_log = engine.execution_log
    for log_entry in execution_log:
        if log_entry['status'] == 'success':
            print(f"{Colors.OKGREEN}{Colors.ENDC} {i18n.t('status.success')}")
            if current_step[0] < total_steps:
                current_step[0] += 1
                _print_step_progress(current_step[0], steps, total_steps, i18n)

    execution_time = time.time() - start_time
    _show_completion(execution_time, i18n)
    _save_results(workflow, workflow_path, params, execution_log,
                  execution_time, config, i18n)
