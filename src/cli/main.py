#!/usr/bin/env python3
"""
Workflow Automation Engine - Standalone CLI

A powerful command-line tool for running automation workflows.
Supports interactive mode, i18n, and beautiful terminal UI.

This file has been refactored into separate modules:
- cli/config.py - Constants and configuration
- cli/i18n.py - Internationalization
- cli/ui.py - Terminal UI utilities
- cli/workflow.py - Workflow listing and parameter collection
- cli/params.py - Parameter merging
- cli/runner.py - Workflow execution
"""
import sys
import os
from pathlib import Path

# Add project root to sys.path to enable 'import src.xxx'
# Try multiple methods to ensure it works across different execution contexts
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Method 1: Add from PYTHONPATH environment variable (most reliable)
pythonpath_from_env = os.environ.get('PYTHONPATH')
if pythonpath_from_env:
    for path in pythonpath_from_env.split(os.pathsep):
        if path and path not in sys.path:
            sys.path.insert(0, path)

# Method 2: Add calculated PROJECT_ROOT
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import argparse

import yaml

from .config import Colors
from .i18n import I18n
from .ui import clear_screen, print_logo, select_language
from .workflow import collect_params, load_config, select_workflow
from .params import merge_params
from .runner import run_workflow


def main() -> None:
    """Main CLI entry point"""

    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description='Flyto2 Workflow Automation Engine',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive mode
  python -m src.cli.main

  # Non-interactive mode - basic
  python -m src.cli.main workflows/google_search.yaml
  python -m src.cli.main workflows/api_pipeline.yaml --lang zh

  # Parameter passing methods
  python -m src.cli.main workflow.yaml --params '{"keyword":"nodejs"}'
  python -m src.cli.main workflow.yaml --params-file params.json
  python -m src.cli.main workflow.yaml --env-file .env.production
  python -m src.cli.main workflow.yaml --param keyword=nodejs --param max_results=20

  # Combined (priority: param > params > params-file > YAML defaults)
  python -m src.cli.main workflow.yaml --params-file base.json --param keyword=override
        """
    )
    parser.add_argument('workflow', nargs='?', help='Path to workflow YAML file')
    parser.add_argument('--lang', '-l', default='en', choices=['en', 'zh', 'ja'],
                        help='Language (en, zh, ja)')
    parser.add_argument('--params', '-p',
                        help='Workflow parameters as JSON string')
    parser.add_argument('--params-file',
                        help='Path to JSON/YAML file containing parameters')
    parser.add_argument('--env-file',
                        help='Path to .env file for environment variables')
    parser.add_argument('--param', action='append',
                        help='Individual parameter (format: key=value), '
                             'can be used multiple times')

    args = parser.parse_args()

    # Determine mode: interactive or non-interactive
    if args.workflow:
        # Non-interactive mode
        lang = args.lang
        i18n = I18n(lang)
        config = load_config()

        workflow_path = Path(args.workflow)
        if not workflow_path.exists():
            print(f"{Colors.FAIL}Error: Workflow file not found: "
                  f"{workflow_path}{Colors.ENDC}")
            sys.exit(1)

        # Load workflow
        print(f"{i18n.t('cli.loading_workflow')}: "
              f"{Colors.OKGREEN}{workflow_path.name}{Colors.ENDC}")
        with open(workflow_path, 'r') as f:
            workflow = yaml.safe_load(f)

        # Merge parameters from all sources
        params = merge_params(workflow, args)

        # Run workflow
        run_workflow(workflow_path, params, config, i18n)

    else:
        # Interactive mode
        # Select language
        lang = select_language()
        i18n = I18n(lang)

        # Clear screen and show logo
        clear_screen()
        print_logo(i18n)

        # Load global config
        config = load_config()

        # Select workflow
        workflow_path = select_workflow(i18n)
        if not workflow_path:
            print()
            print(i18n.t('cli.goodbye'))
            sys.exit(0)

        # Load workflow to get params
        print()
        print(f"{i18n.t('cli.loading_workflow')}: "
              f"{Colors.OKGREEN}{workflow_path.name}{Colors.ENDC}")

        with open(workflow_path, 'r') as f:
            workflow = yaml.safe_load(f)

        # Collect parameters
        params = collect_params(workflow, i18n)

        # Run workflow
        run_workflow(workflow_path, params, config, i18n)

        # Goodbye
        print()
        print(i18n.t('cli.goodbye'))


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nGoodbye!")
        sys.exit(0)
