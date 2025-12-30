"""
CLI Workflow Utilities

Workflow listing, selection, and parameter collection.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .config import CLI_LINE_WIDTH, Colors, CONFIG_FILE, WORKFLOWS_DIR
from .i18n import I18n


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

        print(f"{Colors.FAIL}"
              f"{i18n.t('cli.invalid_workflow_choice', max=len(workflows) + 1)}"
              f"{Colors.ENDC}")


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
    required_text = (i18n.t('params.required') if param.get('required', False)
                     else i18n.t('params.optional'))
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
        print(i18n.t('cli.example', placeholder=placeholder))

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
                print(f"{Colors.FAIL}{i18n.t('cli.parameter_required')}{Colors.ENDC}")
                continue

        # Convert type
        try:
            if param_type == 'number':
                value = float(user_input) if '.' in user_input else int(user_input)
                # Check min/max
                if 'min' in param and value < param['min']:
                    print(f"{Colors.FAIL}"
                          f"{i18n.t('cli.value_min', min=param['min'])}"
                          f"{Colors.ENDC}")
                    continue
                if 'max' in param and value > param['max']:
                    print(f"{Colors.FAIL}"
                          f"{i18n.t('cli.value_max', max=param['max'])}"
                          f"{Colors.ENDC}")
                    continue
                return value
            elif param_type == 'boolean':
                return user_input.lower() in ['true', 'yes', 'y', '1']
            else:
                return user_input
        except ValueError:
            print(f"{Colors.FAIL}"
                  f"{i18n.t('cli.invalid_type', type=param_type)}"
                  f"{Colors.ENDC}")


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
