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
- cli/modules.py - Module listing command
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
from .modules import add_modules_parser, run_modules_command
from .plugin import add_plugin_parser, run_plugin_command
from .recipe import run_recipe, run_recipes_list, run_replay
from .template import add_template_parser, run_template_command


def add_serve_parser(subparsers) -> None:
    """Add serve subcommand for HTTP Execution API server."""
    serve_parser = subparsers.add_parser(
        "serve",
        help="Start HTTP Execution API server",
        description="Start the flyto-core HTTP Execution API server."
    )
    serve_parser.add_argument('--host', default='127.0.0.1',
                              help='Host to bind (default: 127.0.0.1)')
    serve_parser.add_argument('--port', '-p', type=int, default=8333,
                              help='Port to listen on (default: 8333)')


def run_serve_command(host: str = '127.0.0.1', port: int = 8333) -> int:
    """Start the HTTP Execution API server."""
    try:
        from core.api.server import main as serve_main
        serve_main(host=host, port=port)
        return 0
    except ImportError as e:
        print(f"{Colors.FAIL}Error: Missing dependencies for serve command.{Colors.ENDC}")
        print(f"Install with: pip install flyto-core[api]")
        print(f"Details: {e}")
        return 1


def add_run_parser(subparsers) -> None:
    """Add run subcommand for workflow execution."""
    run_parser = subparsers.add_parser(
        "run",
        help="Run a workflow",
        description="Execute a workflow YAML file with parameters."
    )
    run_parser.add_argument('workflow', nargs='?', help='Path to workflow YAML file')
    run_parser.add_argument('--lang', '-l', default='en', choices=['en', 'zh', 'ja'],
                            help='Language (en, zh, ja)')
    run_parser.add_argument('--params', '-p',
                            help='Workflow parameters as JSON string')
    run_parser.add_argument('--params-file',
                            help='Path to JSON/YAML file containing parameters')
    run_parser.add_argument('--env-file',
                            help='Path to .env file for environment variables')
    run_parser.add_argument('--param', action='append',
                            help='Individual parameter (format: key=value), '
                                 'can be used multiple times')


def main() -> None:
    """Main CLI entry point"""

    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description='Flyto2 Workflow Automation Engine',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run a pre-built recipe
  flyto recipe screenshot --url https://example.com
  flyto recipe scrape-page --url https://example.com --selector h1
  flyto recipe csv-to-json --input data.csv
  flyto recipe monitor-site --url https://myapp.com

  # List all recipes
  flyto recipes

  # Run a custom workflow
  flyto run workflow.yaml
  flyto run workflow.yaml --params '{"keyword":"nodejs"}'

  # List modules
  flyto modules

  # Manage plugins
  flyto plugin available
  flyto plugin install slack
  flyto plugin list

  # Template management
  flyto template list
  flyto template export <template-id> -o template.yaml
  flyto template import template.yaml
  flyto template push <template-id> template.yaml -m "Fix extraction"
  flyto template push <template-id> template.yaml --pr -m "Add new step"
  flyto template pull <template-id> -o template.yaml
  flyto template diff <template-id> template.yaml
  flyto template search "browser extract"
  flyto template info <template-id>
  flyto template history <template-id>

  # Start HTTP API server
  flyto serve
        """
    )

    # Add subcommands
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    add_run_parser(subparsers)
    add_modules_parser(subparsers)
    add_plugin_parser(subparsers)
    add_serve_parser(subparsers)
    add_template_parser(subparsers)

    # Recipe commands
    subparsers.add_parser(
        "recipes",
        help="List all available recipes",
        description="Show all pre-built recipes with usage examples."
    )
    recipe_parser = subparsers.add_parser(
        "recipe",
        help="Run a pre-built recipe",
        description="Execute a pre-built recipe template with arguments."
    )
    recipe_parser.add_argument('recipe_name', nargs='?', help='Recipe name')
    recipe_parser.add_argument('recipe_args', nargs=argparse.REMAINDER, help='Recipe arguments (--key value)')

    # Replay command
    replay_parser = subparsers.add_parser(
        "replay",
        help="Replay a workflow from a specific step",
        description="Re-execute a previous workflow run from a specific step, skipping earlier steps."
    )
    replay_parser.add_argument('--from-step', required=True,
                               help='Step ID or number (1-based) to replay from')
    replay_parser.add_argument('--run-dir',
                               help='Path to run state directory (default: .flyto-runs/latest)')

    # Legacy mode: rewrite `flyto workflow.yaml` → `flyto run workflow.yaml`
    # so argparse routes it through the run subparser correctly.
    if len(sys.argv) > 1 and sys.argv[1] not in (
        'run', 'modules', 'plugin', 'serve', 'template',
        'recipes', 'recipe', 'replay', '-h', '--help'
    ) and (sys.argv[1].endswith('.yaml') or sys.argv[1].endswith('.yml')):
        sys.argv.insert(1, 'run')

    args = parser.parse_args()

    # Handle 'serve' command
    if args.command == 'serve':
        sys.exit(run_serve_command(
            host=args.host,
            port=args.port,
        ))

    # Handle 'modules' command
    if args.command == 'modules':
        sys.exit(run_modules_command(
            env=args.env,
            format=args.format,
            output_file=args.output
        ))

    # Handle 'plugin' command
    if args.command == 'plugin':
        sys.exit(run_plugin_command(args))

    # Handle 'recipes' command (list all)
    if args.command == 'recipes':
        sys.exit(run_recipes_list())

    # Handle 'recipe' command (run one)
    if args.command == 'recipe':
        if not args.recipe_name:
            sys.exit(run_recipes_list())
        sys.exit(run_recipe(args.recipe_name, args.recipe_args or []))

    # Handle 'template' command
    if args.command == 'template':
        sys.exit(run_template_command(args))

    # Handle 'replay' command
    if args.command == 'replay':
        sys.exit(run_replay(
            from_step=args.from_step,
            run_dir_path=getattr(args, 'run_dir', None),
        ))

    # Handle 'run' command (legacy .yaml paths are rewritten to 'run' above)
    if args.command == 'run':
        workflow_arg = args.workflow
    else:
        workflow_arg = None

    # Determine mode: interactive or non-interactive
    if workflow_arg:
        # Non-interactive mode
        lang = args.lang
        i18n = I18n(lang)
        config = load_config()

        workflow_path = Path(workflow_arg)
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
