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

from .config import CLI_LINE_WIDTH, Colors, DEFAULT_OUTPUT_DIR
from .i18n import I18n


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

    # Import execution engine
    try:
        from ..core.engine.workflow_engine import WorkflowEngine

        # Create workflow engine
        engine = WorkflowEngine(workflow, params)

        # Track progress during execution
        current_step = [0]

        def show_step_progress():
            current_step[0] += 1
            if current_step[0] <= total_steps:
                progress = i18n.t('cli.step_progress',
                                  current=current_step[0],
                                  total=total_steps)
                step = steps[current_step[0] - 1] if current_step[0] <= len(steps) else {}
                module_id = step.get('module', 'unknown')
                description = step.get('description', '')
                print(f"\n{Colors.OKCYAN}[{progress}]{Colors.ENDC} "
                      f"{description or module_id}")

        # Execute workflow
        async def run_workflow_async():
            # Show first step
            show_step_progress()

            # Execute and track completion
            result = await engine.execute()
            return result

        # Run async workflow
        try:
            output = asyncio.run(run_workflow_async())

            # Get execution log
            execution_log = engine.execution_log

            # Show success for each completed step
            for log_entry in execution_log:
                if log_entry['status'] == 'success':
                    print(f"{Colors.OKGREEN}{Colors.ENDC} {i18n.t('status.success')}")
                    if current_step[0] < total_steps:
                        show_step_progress()

        except Exception as exec_error:
            print(f"\n{Colors.FAIL}{Colors.BOLD}"
                  f"{i18n.t('status.error')}{Colors.ENDC}")
            print(f"{Colors.FAIL}Error: {str(exec_error)}{Colors.ENDC}")

            # Show execution summary
            summary = engine.get_execution_summary()
            print(f"\n{Colors.WARNING}Execution Summary:{Colors.ENDC}")
            print(f"  Steps executed: {summary['steps_executed']}/{total_steps}")
            print(f"  Status: {summary['status']}")

            sys.exit(1)

        results = execution_log

        # Calculate execution time
        execution_time = time.time() - start_time

        # Show completion
        print()
        print("=" * CLI_LINE_WIDTH)
        print(Colors.OKGREEN + Colors.BOLD +
              i18n.t('cli.workflow_completed') + Colors.ENDC)
        print("=" * CLI_LINE_WIDTH)
        print(f"{i18n.t('cli.execution_time')}: {execution_time:.2f}s")

        # Save results
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

    except Exception as e:
        print()
        print(Colors.FAIL + i18n.t('cli.workflow_failed') + Colors.ENDC)
        print(f"{i18n.t('cli.error_occurred')}: {str(e)}")
        sys.exit(1)
