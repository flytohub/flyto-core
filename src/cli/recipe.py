"""
CLI Recipe Runner

Load and execute pre-built recipe templates from the recipes/ directory.
Recipes are YAML workflow templates with named arguments.
"""

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .config import Colors


# Recipes directory (bundled with package)
RECIPES_DIR = Path(__file__).parent.parent / 'recipes'


def load_recipe(recipe_name: str) -> Optional[Dict[str, Any]]:
    """Load a recipe YAML file by name."""
    recipe_path = RECIPES_DIR / f"{recipe_name}.yaml"
    if not recipe_path.exists():
        return None
    with open(recipe_path, 'r') as f:
        return yaml.safe_load(f)


def list_all_recipes() -> List[Dict[str, Any]]:
    """List all available recipes with metadata."""
    if not RECIPES_DIR.exists():
        return []
    recipes = []
    for path in sorted(RECIPES_DIR.glob('*.yaml')):
        try:
            with open(path, 'r') as f:
                data = yaml.safe_load(f)
            recipes.append({
                'id': path.stem,
                'name': data.get('name', path.stem),
                'description': data.get('description', ''),
                'args': data.get('args', {}),
            })
        except Exception:
            continue
    return recipes


def substitute_args(workflow: Dict[str, Any], args: Dict[str, str]) -> Dict[str, Any]:
    """Replace {{arg}} placeholders in workflow with actual values."""
    return _substitute_deep(workflow, args)


def _substitute_deep(obj: Any, args: Dict[str, str]) -> Any:
    """Recursively substitute {{arg}} placeholders."""
    if isinstance(obj, str):
        for key, value in args.items():
            placeholder = f"{{{{{key}}}}}"
            if obj == placeholder:
                # Exact match: return typed value (int, float, bool)
                return _auto_type(str(value))
            obj = obj.replace(placeholder, str(value))
        return obj
    elif isinstance(obj, dict):
        return {k: _substitute_deep(v, args) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_substitute_deep(item, args) for item in obj]
    return obj


def _auto_type(value: str) -> Any:
    """Convert string to int/float/bool/json if possible."""
    import json as _json

    if value.lower() in ('true', 'false'):
        return value.lower() == 'true'
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    # Try JSON for objects/arrays (e.g. '{"email":"test@example.com"}')
    if value.startswith(('{', '[')):
        try:
            return _json.loads(value)
        except (ValueError, _json.JSONDecodeError):
            pass
    return value


def parse_recipe_args(raw_args: List[str], recipe: Dict[str, Any]) -> Dict[str, str]:
    """Parse CLI args like --symbol AAPL --range 1mo into a dict."""
    args_schema = recipe.get('args', {})
    parsed = {}

    # Apply defaults first
    for arg_name, arg_def in args_schema.items():
        if isinstance(arg_def, dict) and 'default' in arg_def:
            parsed[arg_name] = arg_def['default']

    # Parse --key value pairs
    i = 0
    while i < len(raw_args):
        token = raw_args[i]
        if token.startswith('--'):
            key = token[2:]
            if i + 1 < len(raw_args) and not raw_args[i + 1].startswith('--'):
                parsed[key] = raw_args[i + 1]
                i += 2
            else:
                parsed[key] = 'true'
                i += 1
        else:
            i += 1

    # Validate required args
    missing = []
    for arg_name, arg_def in args_schema.items():
        if isinstance(arg_def, dict) and arg_def.get('required', False):
            if arg_name not in parsed:
                missing.append(arg_name)

    if missing:
        print(f"{Colors.FAIL}Missing required arguments: {', '.join(missing)}{Colors.ENDC}")
        print()
        print_recipe_usage(recipe)
        sys.exit(1)

    return parsed


def print_recipe_usage(recipe: Dict[str, Any]) -> None:
    """Print usage for a single recipe."""
    recipe_id = recipe.get('_id', recipe.get('name', 'unknown'))
    args_schema = recipe.get('args', {})

    print(f"Usage: flyto recipe {recipe_id}", end='')
    for arg_name, arg_def in args_schema.items():
        if isinstance(arg_def, dict):
            required = arg_def.get('required', False)
            if required:
                print(f" --{arg_name} <value>", end='')
            else:
                default = arg_def.get('default', '')
                print(f" [--{arg_name} {default}]", end='')
    print()
    print()

    if args_schema:
        print("Arguments:")
        for arg_name, arg_def in args_schema.items():
            if isinstance(arg_def, dict):
                desc = arg_def.get('description', '')
                required = arg_def.get('required', False)
                default = arg_def.get('default', '')
                req_tag = " (required)" if required else f" (default: {default})" if default else ""
                print(f"  --{arg_name:<20} {desc}{req_tag}")


def run_recipes_list() -> int:
    """List all available recipes."""
    recipes = list_all_recipes()

    if not recipes:
        print(f"{Colors.WARNING}No recipes found.{Colors.ENDC}")
        return 1

    print(f"{Colors.BOLD}Available recipes:{Colors.ENDC}")
    print()

    for r in recipes:
        args_schema = r.get('args', {})
        arg_names = list(args_schema.keys())
        args_preview = ' '.join(f"--{a} ..." for a in arg_names[:3])
        if len(arg_names) > 3:
            args_preview += ' ...'

        print(f"  {Colors.OKCYAN}{r['id']:<24}{Colors.ENDC} {r['description']}")
        if args_preview:
            print(f"  {'':24} {Colors.WARNING}flyto recipe {r['id']} {args_preview}{Colors.ENDC}")
        print()

    print(f"{len(recipes)} recipes available. Run {Colors.BOLD}flyto recipe <name> --help{Colors.ENDC} for details.")
    return 0


def run_recipe(recipe_name: str, raw_args: List[str]) -> int:
    """Load, substitute, and execute a recipe."""
    recipe = load_recipe(recipe_name)

    if recipe is None:
        print(f"{Colors.FAIL}Recipe not found: {recipe_name}{Colors.ENDC}")
        print()
        print(f"Run {Colors.BOLD}flyto recipes{Colors.ENDC} to see available recipes.")
        return 1

    recipe['_id'] = recipe_name

    # Handle --help
    if '--help' in raw_args or '-h' in raw_args:
        print(f"{Colors.BOLD}{recipe.get('name', recipe_name)}{Colors.ENDC}")
        print(f"{recipe.get('description', '')}")
        print()
        print_recipe_usage(recipe)
        return 0

    # Parse args
    args = parse_recipe_args(raw_args, recipe)

    # Substitute {{placeholders}} with actual values
    workflow = substitute_args(recipe, args)

    # Also pass args as params for ${params.x} resolution
    params = dict(args)

    # Print recipe info
    print(f"{Colors.BOLD}{recipe.get('name', recipe_name)}{Colors.ENDC}")
    if args:
        args_display = ', '.join(f"{k}={v}" for k, v in args.items())
        print(f"{Colors.OKCYAN}{args_display}{Colors.ENDC}")
    print()

    # Execute workflow directly via WorkflowEngine
    import asyncio
    import json
    import time

    try:
        from core.engine.workflow.engine import WorkflowEngine
    except ImportError as e:
        print(f"{Colors.FAIL}Error: flyto-core engine not available: {e}{Colors.ENDC}")
        return 1

    steps = workflow.get('steps', [])
    total_steps = len(steps)

    print(f"Running {total_steps} steps...")
    print()

    start_time = time.time()

    async def _run():
        engine = WorkflowEngine(workflow, params, enable_trace=True)
        result = await engine.execute()
        return engine, result

    try:
        engine, result = asyncio.run(_run())

        elapsed = time.time() - start_time

        # Show step results
        for entry in engine.execution_log:
            step_id = entry.get('step_id', '?')
            status = entry.get('status', 'unknown')
            module = entry.get('module', '')
            if status == 'success':
                print(f"  {Colors.OKGREEN}✓{Colors.ENDC} {step_id} ({module})")
            else:
                error = entry.get('error', '')
                print(f"  {Colors.FAIL}✗{Colors.ENDC} {step_id} ({module}) — {error}")

        print()
        print(f"{Colors.OKGREEN}Done{Colors.ENDC} in {elapsed:.1f}s")

        # Show output hints
        for a_name, a_val in args.items():
            if a_name == 'output' and a_val:
                output_path = Path(a_val)
                if output_path.exists():
                    size = output_path.stat().st_size
                    print(f"Output: {a_val} ({size:,} bytes)")

        return 0

    except Exception as e:
        elapsed = time.time() - start_time
        print(f"{Colors.FAIL}Failed{Colors.ENDC} after {elapsed:.1f}s: {e}")
        return 1
