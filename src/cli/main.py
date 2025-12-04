#!/usr/bin/env python3
"""
Workflow Automation Engine - Standalone CLI

A powerful command-line tool for running automation workflows.
Supports interactive mode, i18n, and beautiful terminal UI.
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
import json
import logging
import yaml
import time
from datetime import datetime
from typing import Dict, Any, List, Optional


logger = logging.getLogger(__name__)

# CLI Constants
CLI_VERSION = "1.1.0"
CLI_LINE_WIDTH = 70
SUPPORTED_LANGUAGES = {
    '1': ('en', 'English'),
    '2': ('zh', 'Chinese'),
    '3': ('ja', 'Japanese'),
}
I18N_DIR = Path(__file__).parent.parent.parent / 'i18n'
CONFIG_FILE = Path(__file__).parent.parent.parent / 'engine.yaml'
WORKFLOWS_DIR = Path(__file__).parent.parent.parent / 'workflows'
DEFAULT_OUTPUT_DIR = Path('./output')

# ASCII Logo
LOGO = r"""
                    
              
                  
              
         
                
"""

# Color codes for terminal output
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


class I18n:
    """Simple i18n system"""
    
    def __init__(self, lang: str = 'en'):
        self.lang = lang
        self.translations = {}
        self.load_language(lang)
    
    def load_language(self, lang: str):
        """Load language file"""
        lang_file = I18N_DIR / f'{lang}.json'
        if lang_file.exists():
            with open(lang_file, 'r', encoding='utf-8') as f:
                self.translations = json.load(f)
        else:
            logger.warning(f"Language file for '{lang}' not found")
            self.translations = {}
    
    def t(self, key: str, **kwargs) -> str:
        """Get translated text"""
        keys = key.split('.')
        value = self.translations
        
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k, key)
            else:
                return key
        
        # Replace placeholders
        if isinstance(value, str) and kwargs:
            return value.format(**kwargs)
        
        return value if isinstance(value, str) else key


def _clear_screen() -> None:
    """Clear terminal screen using ANSI escape codes"""
    # Use ANSI escape sequence for cross-platform compatibility
    print('\033[2J\033[H', end='')


def print_logo(i18n: I18n) -> None:
    """Print ASCII logo"""
    print(Colors.OKCYAN + LOGO + Colors.ENDC)
    print(Colors.BOLD + i18n.t('cli.welcome') + Colors.ENDC)
    print(i18n.t('cli.version'))
    print(i18n.t('cli.description'))
    print()


def select_language() -> str:
    """Interactive language selection"""
    print("=" * CLI_LINE_WIDTH)
    print("Select language / Select Language / LanguageSelect:")
    for key, (code, name) in SUPPORTED_LANGUAGES.items():
        print(f"  {key}. {name}")
    print("=" * CLI_LINE_WIDTH)

    while True:
        choice = input("> ").strip()
        if choice in SUPPORTED_LANGUAGES:
            return SUPPORTED_LANGUAGES[choice][0]
        else:
            print(f"Invalid choice. Please enter 1-{len(SUPPORTED_LANGUAGES)}.")


def load_config() -> Dict[str, Any]:
    """Load global configuration"""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'r') as f:
            return yaml.safe_load(f)
    return {}


def list_workflows() -> List[Path]:
    """List available workflows"""
    if not WORKFLOWS_DIR.exists():
        return []

    return list(WORKFLOWS_DIR.glob('*.yaml'))


def select_workflow(i18n: I18n) -> Optional[Path]:
    """Interactive workflow selection"""
    workflows = list_workflows()
    
    if not workflows:
        print(Colors.WARNING + i18n.t('cli.no_workflows_found') + Colors.ENDC)
        return None
    
    print()
    print("=" * CLI_LINE_WIDTH)
    print(Colors.BOLD + i18n.t('cli.available_workflows') + Colors.ENDC)
    print("=" * CLI_LINE_WIDTH)
    
    for idx, workflow_path in enumerate(workflows, 1):
        # Load workflow to get name and description
        with open(workflow_path, 'r') as f:
            workflow = yaml.safe_load(f)
        
        name = workflow.get('name', workflow_path.stem)
        desc = workflow.get('description', {})
        
        # Get localized description
        if isinstance(desc, dict):
            desc_text = desc.get(i18n.lang, desc.get('en', ''))
        else:
            desc_text = desc
        
        print(f"  {idx}. {Colors.OKGREEN}{name}{Colors.ENDC}")
        if desc_text:
            print(f"     {desc_text}")
    
    print(f"  {len(workflows) + 1}. {i18n.t('cli.enter_custom_path')}")
    print("=" * CLI_LINE_WIDTH)
    
    while True:
        choice = input("> ").strip()
        try:
            choice_num = int(choice)
            if 1 <= choice_num <= len(workflows):
                return workflows[choice_num - 1]
            elif choice_num == len(workflows) + 1:
                custom_path = input(f"{i18n.t('cli.enter_custom_path')}: ").strip()
                return Path(custom_path)
        except ValueError:
            pass
        
        print(f"{Colors.FAIL}Invalid choice.{Colors.ENDC} Please enter a number between 1 and {len(workflows) + 1}")


def get_param_input(param: Dict[str, Any], i18n: I18n) -> Any:
    """Get user input for a parameter"""
    param_name = param['name']
    param_type = param.get('type', 'string')
    
    # Get localized label
    label = param.get('label', {})
    if isinstance(label, dict):
        label_text = label.get(i18n.lang, label.get('en', param_name))
    else:
        label_text = label or param_name
    
    # Get description
    desc = param.get('description', {})
    if isinstance(desc, dict):
        desc_text = desc.get(i18n.lang, desc.get('en', ''))
    else:
        desc_text = desc or ''
    
    # Show parameter info
    print()
    required_text = i18n.t('params.required') if param.get('required', False) else i18n.t('params.optional')
    print(f"{Colors.BOLD}{label_text}{Colors.ENDC} ({required_text})")
    if desc_text:
        print(f"{Colors.OKCYAN}{desc_text}{Colors.ENDC}")
    
    # Show default value
    default_value = param.get('default')
    if default_value is not None:
        print(f"[{i18n.t('params.default')}: {default_value}]")
    
    # Show placeholder
    placeholder = param.get('placeholder', '')
    if placeholder:
        print(f"Example: {placeholder}")
    
    # Get input
    while True:
        user_input = input("> ").strip()
        
        # Use default if empty and not required
        if not user_input:
            if default_value is not None:
                return default_value
            elif not param.get('required', False):
                return None
            else:
                print(f"{Colors.FAIL}This parameter is required.{Colors.ENDC}")
                continue
        
        # Convert type
        try:
            if param_type == 'number':
                value = float(user_input) if '.' in user_input else int(user_input)
                # Check min/max
                if 'min' in param and value < param['min']:
                    print(f"{Colors.FAIL}Value must be >= {param['min']}{Colors.ENDC}")
                    continue
                if 'max' in param and value > param['max']:
                    print(f"{Colors.FAIL}Value must be <= {param['max']}{Colors.ENDC}")
                    continue
                return value
            elif param_type == 'boolean':
                return user_input.lower() in ['true', 'yes', 'y', '1']
            else:
                return user_input
        except ValueError:
            print(f"{Colors.FAIL}Invalid input for type {param_type}{Colors.ENDC}")


def collect_params(workflow: Dict[str, Any], i18n: I18n) -> Dict[str, Any]:
    """Collect parameters from user"""
    params_schema = workflow.get('params', [])
    
    if not params_schema:
        return {}
    
    print()
    print("=" * CLI_LINE_WIDTH)
    print(Colors.BOLD + i18n.t('cli.required_parameters') + Colors.ENDC)
    print("=" * CLI_LINE_WIDTH)
    
    params = {}
    for param in params_schema:
        value = get_param_input(param, i18n)
        if value is not None:
            params[param['name']] = value
    
    return params


def run_workflow(workflow_path: Path, params: Dict[str, Any], config: Dict[str, Any], i18n: I18n):
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
        import asyncio

        # Create workflow engine
        engine = WorkflowEngine(workflow, params)

        # Track progress during execution
        current_step = [0]

        def show_step_progress():
            current_step[0] += 1
            if current_step[0] <= total_steps:
                progress = i18n.t('cli.step_progress', current=current_step[0], total=total_steps)
                step = steps[current_step[0] - 1] if current_step[0] <= len(steps) else {}
                module_id = step.get('module', 'unknown')
                description = step.get('description', '')
                print(f"\n{Colors.OKCYAN}[{progress}]{Colors.ENDC} {description or module_id}")

        # Execute workflow
        async def run_workflow():
            # Show first step
            show_step_progress()

            # Execute and track completion
            result = await engine.execute()
            return result

        # Run async workflow
        try:
            output = asyncio.run(run_workflow())

            # Get execution log
            execution_log = engine.execution_log

            # Show success for each completed step
            for log_entry in execution_log:
                if log_entry['status'] == 'success':
                    print(f"{Colors.OKGREEN}{Colors.ENDC} {i18n.t('status.success')}")
                    if current_step[0] < total_steps:
                        show_step_progress()

        except Exception as exec_error:
            print(f"\n{Colors.FAIL}{Colors.BOLD}{i18n.t('status.error')}{Colors.ENDC}")
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
        print(Colors.OKGREEN + Colors.BOLD + i18n.t('cli.workflow_completed') + Colors.ENDC)
        print("=" * CLI_LINE_WIDTH)
        print(f"{i18n.t('cli.execution_time')}: {execution_time:.2f}s")
        
        # Save results
        output_dir = Path(config.get('storage', {}).get('output_dir', str(DEFAULT_OUTPUT_DIR)))
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


def auto_convert_type(value: str) -> Any:
    """
    Automatically convert string to appropriate type

    Args:
        value: String value to convert

    Returns:
        Converted value (bool, int, float, or str)
    """
    # Boolean: true/false
    if value.lower() in ['true', 'false']:
        return value.lower() == 'true'

    # Number: try int first, then float
    try:
        if '.' in value:
            return float(value)
        return int(value)
    except ValueError:
        pass

    # Default: string
    return value


def merge_params(workflow: Dict[str, Any], args) -> Dict[str, Any]:
    """
    Merge parameters from multiple sources with priority order:
    1. YAML defaults (lowest priority)
    2. --params-file
    3. --env-file (loads into environment)
    4. --params JSON string
    5. --param individual parameters (highest priority)

    Args:
        workflow: Loaded workflow YAML
        args: Parsed command-line arguments

    Returns:
        Merged parameters dictionary
    """
    params = {}

    # 1. Extract defaults from YAML params schema
    if 'params' in workflow:
        for param_def in workflow['params']:
            if 'default' in param_def:
                params[param_def['name']] = param_def['default']

    # 2. Load from --params-file (JSON or YAML)
    if hasattr(args, 'params_file') and args.params_file:
        params_file_path = Path(args.params_file)
        if not params_file_path.exists():
            print(f"{Colors.FAIL}Error: Parameter file not found: {params_file_path}{Colors.ENDC}")
            sys.exit(1)

        try:
            with open(params_file_path, 'r') as f:
                if params_file_path.suffix == '.json':
                    file_params = json.load(f)
                else:  # .yaml or .yml
                    file_params = yaml.safe_load(f)
                params.update(file_params)
        except Exception as e:
            print(f"{Colors.FAIL}Error loading parameter file: {e}{Colors.ENDC}")
            sys.exit(1)

    # 3. Load from --env-file (into environment variables)
    if hasattr(args, 'env_file') and args.env_file:
        env_file_path = Path(args.env_file)
        if not env_file_path.exists():
            print(f"{Colors.FAIL}Error: Environment file not found: {env_file_path}{Colors.ENDC}")
            sys.exit(1)

        try:
            with open(env_file_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        os.environ[key.strip()] = value.strip()
        except Exception as e:
            print(f"{Colors.FAIL}Error loading environment file: {e}{Colors.ENDC}")
            sys.exit(1)

    # 4. Load from --params JSON string
    if hasattr(args, 'params') and args.params:
        try:
            json_params = json.loads(args.params)
            params.update(json_params)
        except json.JSONDecodeError as e:
            print(f"{Colors.FAIL}Error parsing --params JSON: {e}{Colors.ENDC}")
            sys.exit(1)

    # 5. Load from --param individual parameters (highest priority)
    if hasattr(args, 'param') and args.param:
        for param_str in args.param:
            if '=' not in param_str:
                print(f"{Colors.FAIL}Error: Invalid --param format: {param_str}{Colors.ENDC}")
                print(f"Expected format: --param key=value")
                sys.exit(1)

            key, value = param_str.split('=', 1)
            params[key.strip()] = auto_convert_type(value.strip())

    return params


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
                       help='Individual parameter (format: key=value), can be used multiple times')

    args = parser.parse_args()

    # Determine mode: interactive or non-interactive
    if args.workflow:
        # Non-interactive mode
        lang = args.lang
        i18n = I18n(lang)
        config = load_config()

        workflow_path = Path(args.workflow)
        if not workflow_path.exists():
            print(f"{Colors.FAIL}Error: Workflow file not found: {workflow_path}{Colors.ENDC}")
            sys.exit(1)

        # Load workflow
        print(f"{i18n.t('cli.loading_workflow')}: {Colors.OKGREEN}{workflow_path.name}{Colors.ENDC}")
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
        _clear_screen()
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
        print(f"{i18n.t('cli.loading_workflow')}: {Colors.OKGREEN}{workflow_path.name}{Colors.ENDC}")

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
