"""
CLI Parameter Utilities

Parameter parsing and merging for CLI.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

import yaml

from .config import Colors


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


def merge_params(workflow: Dict[str, Any], args: Any) -> Dict[str, Any]:
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
            print(f"{Colors.FAIL}Error: Parameter file not found: "
                  f"{params_file_path}{Colors.ENDC}")
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
            print(f"{Colors.FAIL}Error: Environment file not found: "
                  f"{env_file_path}{Colors.ENDC}")
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
                print(f"{Colors.FAIL}Error: Invalid --param format: "
                      f"{param_str}{Colors.ENDC}")
                print("Expected format: --param key=value")
                sys.exit(1)

            key, value = param_str.split('=', 1)
            params[key.strip()] = auto_convert_type(value.strip())

    return params
