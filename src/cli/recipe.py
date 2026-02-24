"""
CLI Recipe Runner

Load and execute pre-built recipe templates from the recipes/ directory.
Recipes are YAML workflow templates with named arguments.
"""

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .config import Colors


# Recipes directory (bundled with package)
RECIPES_DIR = Path(__file__).parent.parent / 'recipes'

# Run state directory (for replay support)
RUNS_DIR = Path('.flyto-runs')

# Column width for module name alignment
_COL_MODULE = 24  # "browser.performance"


def _fmt_duration(ms: int) -> str:
    """Format milliseconds as a human-readable string with comma separators."""
    if ms < 1000:
        return f"{ms:,}ms"
    return f"{ms / 1000:,.1f}s"


def _print_step_line(
    step_num: int,
    total: int,
    module_id: str,
    status: str,
    duration_ms: int = 0,
    hint: str = '',
) -> None:
    """Print a single step line with aligned columns."""
    pad = len(str(total))
    num_str = f"{step_num:>{pad}}/{total}"

    if status == 'success':
        icon = f"{Colors.OKGREEN}\u2713{Colors.ENDC}"
    elif status in ('error', 'failed'):
        icon = f"{Colors.FAIL}\u2717{Colors.ENDC}"
    elif status == 'skipped':
        icon = f"{Colors.WARNING}\u2015{Colors.ENDC}"
    else:
        icon = f"{Colors.OKCYAN}\u2026{Colors.ENDC}"

    dur_str = _fmt_duration(duration_ms).rjust(8) if duration_ms else ''.rjust(8)
    hint_str = f"  \u2192 {hint}" if hint else ''

    print(f"  Step {num_str}  {module_id:<{_COL_MODULE}} {icon} {dur_str}{hint_str}")


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


def _step_hint(step: Dict[str, Any]) -> str:
    """Generate a short hint for notable steps based on module type."""
    module = step.get('module', '')
    params = step.get('params', {})
    if module == 'browser.performance':
        return 'Web Vitals captured'
    if module == 'browser.screenshot':
        path = params.get('path', '')
        return f'saved {path}' if path else ''
    if module == 'browser.pdf':
        path = params.get('path', '')
        return f'saved {path}' if path else ''
    if module == 'browser.viewport':
        w = params.get('width', '')
        h = params.get('height', '')
        return f'{w}\u00d7{h}' if w else ''
    if module == 'file.write':
        path = params.get('path', '')
        return f'saved {path}' if path and not path.startswith('$') else ''
    return ''


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

    try:
        from core.engine.workflow.engine import WorkflowEngine
    except ImportError as e:
        print(f"{Colors.FAIL}Error: flyto-core engine not available: {e}{Colors.ENDC}")
        return 1

    steps = workflow.get('steps', [])
    total_steps = len(steps)

    # Build step metadata lookup (index → module, hint)
    step_meta = {}
    for i, s in enumerate(steps):
        step_meta[i] = {
            'module': s.get('module', '?'),
            'hint': _step_hint(s),
        }

    # Prepare run state directory for replay support
    run_dir = RUNS_DIR / 'latest'
    run_dir.mkdir(parents=True, exist_ok=True)
    _save_json(run_dir / 'workflow.json', workflow)
    _save_json(run_dir / 'params.json', params)

    # Real-time checkpoint callback: prints each step + saves context snapshot
    completed_count = 0

    async def _on_checkpoint(step_index, step_id, checkpoint_data, status):
        nonlocal completed_count
        completed_count += 1
        meta = step_meta.get(step_index, {})
        module_id = meta.get('module', '?')
        hint = meta.get('hint', '')

        # Get duration from trace collector (available during execution)
        duration_ms = 0
        eng = engine_ref[0]
        if eng and eng._trace_collector:
            st = eng._trace_collector.trace.get_step_trace(step_id)
            if st:
                duration_ms = st.durationMs

        _print_step_line(completed_count, total_steps, module_id, status, duration_ms, hint)

        # Save context snapshot for replay (skip non-serializable objects like browser)
        _save_checkpoint_snapshot(run_dir, step_index, step_id, checkpoint_data, status)

    engine_ref = [None]  # Mutable ref for callback access

    start_time = time.time()

    async def _run():
        engine = WorkflowEngine(
            workflow, params,
            enable_trace=True,
            checkpoint_callback=_on_checkpoint,
        )
        engine_ref[0] = engine
        result = await engine.execute()
        return engine, result

    try:
        engine, result = asyncio.run(_run())

        elapsed = time.time() - start_time

        # If checkpoint callback didn't fire (e.g. old engine), fall back to trace
        if completed_count == 0:
            trace = engine.get_execution_trace()
            if trace:
                for st in trace.steps:
                    _print_step_line(
                        st.stepIndex + 1, total_steps, st.moduleId,
                        st.status, st.durationMs,
                    )

        # Summary line
        passed = completed_count or len(engine.execution_log)
        print()
        print(
            f"{Colors.OKGREEN}\u2713 Done{Colors.ENDC} in {elapsed:.1f}s"
            f" \u2014 {passed}/{total_steps} steps passed"
        )

        # Show output file sizes
        _print_output_files(args, engine)

        return 0

    except Exception as e:
        elapsed = time.time() - start_time
        # Show how far we got
        failed_at = completed_count + 1 if completed_count < total_steps else total_steps
        failed_step_id = steps[failed_at - 1].get('id', '') if failed_at <= len(steps) else ''
        print()
        print(
            f"{Colors.FAIL}\u2717 Failed{Colors.ENDC} at step {failed_at}/{total_steps}"
            f" after {elapsed:.1f}s: {e}"
        )
        if failed_step_id:
            print(
                f"  Replay from here: {Colors.BOLD}flyto replay --from-step {failed_step_id}{Colors.ENDC}"
            )
        return 1


def _print_output_files(args: Dict[str, str], engine) -> None:
    """Print sizes of any generated output files."""
    shown = set()

    # Check --output arg
    output_val = args.get('output', '')
    if output_val:
        p = Path(output_val)
        if p.exists():
            shown.add(str(p))
            print(f"  Output: {p} ({p.stat().st_size:,} bytes)")

    # Check common output files from step params
    trace = engine.get_execution_trace()
    if trace:
        for st in trace.steps:
            if st.input and st.input.params:
                for key in ('path', 'output'):
                    val = st.input.params.get(key, '')
                    if isinstance(val, str) and val and not val.startswith('$'):
                        p = Path(val)
                        if p.exists() and str(p) not in shown:
                            shown.add(str(p))
                            print(f"  Output: {p} ({p.stat().st_size:,} bytes)")


# ── Replay support helpers ─────────────────────────────────────────

def _save_json(path: Path, data: Any) -> None:
    """Save JSON, silently skip non-serializable data."""
    try:
        with open(path, 'w') as f:
            json.dump(data, f, indent=2, default=str)
    except Exception:
        pass


def _save_checkpoint_snapshot(
    run_dir: Path, step_index: int, step_id: str,
    checkpoint_data: Dict[str, Any], status: str,
) -> None:
    """Save a context snapshot after each step for replay."""
    # Filter out non-serializable objects (browser sessions, etc.)
    ctx = checkpoint_data.get('context', {})
    clean_ctx = {}
    for k, v in ctx.items():
        try:
            json.dumps(v, default=str)
            clean_ctx[k] = v
        except (TypeError, ValueError):
            clean_ctx[k] = f"<{type(v).__name__}>"

    snapshot = {
        'step_index': step_index,
        'step_id': step_id,
        'status': status,
        'context': clean_ctx,
        'params': checkpoint_data.get('params', {}),
    }
    _save_json(run_dir / f'checkpoint_{step_index:03d}_{step_id}.json', snapshot)
    # Also keep a "latest successful" pointer for easy replay
    if status == 'success':
        _save_json(run_dir / 'last_success.json', snapshot)


def run_replay(from_step: str, run_dir_path: Optional[str] = None) -> int:
    """Replay a workflow from a specific step using saved state."""
    import asyncio

    run_dir = Path(run_dir_path) if run_dir_path else RUNS_DIR / 'latest'

    # Load workflow + params
    wf_path = run_dir / 'workflow.json'
    params_path = run_dir / 'params.json'
    if not wf_path.exists():
        print(f"{Colors.FAIL}No previous run found.{Colors.ENDC} Run a recipe first.")
        return 1

    with open(wf_path) as f:
        workflow = json.load(f)
    with open(params_path) as f:
        params = json.load(f)

    steps = workflow.get('steps', [])
    total_steps = len(steps)

    # Find the target step index
    step_index = None
    for i, s in enumerate(steps):
        if s.get('id') == from_step:
            step_index = i
            break

    # Also try numeric index
    if step_index is None:
        try:
            idx = int(from_step) - 1  # user gives 1-based
            if 0 <= idx < total_steps:
                step_index = idx
                from_step = steps[idx].get('id', from_step)
        except ValueError:
            pass

    if step_index is None:
        print(f"{Colors.FAIL}Step not found: {from_step}{Colors.ENDC}")
        print(f"Available steps:")
        for i, s in enumerate(steps):
            print(f"  {i + 1}. {s.get('id', '?')} ({s.get('module', '?')})")
        return 1

    # Find the checkpoint just before the target step (context at step N-1)
    initial_context = {}
    if step_index > 0:
        # Load context from the step right before (its post-execution context)
        prev_idx = step_index - 1
        prev_id = steps[prev_idx].get('id', '')
        cp_path = run_dir / f'checkpoint_{prev_idx:03d}_{prev_id}.json'
        if cp_path.exists():
            with open(cp_path) as f:
                cp = json.load(f)
            initial_context = cp.get('context', {})
            # Remove placeholder entries for non-serializable objects
            initial_context = {
                k: v for k, v in initial_context.items()
                if not (isinstance(v, str) and v.startswith('<') and v.endswith('>'))
            }

    skipped = step_index
    replay_steps = total_steps - step_index

    print(f"{Colors.BOLD}Replay{Colors.ENDC} from step {step_index + 1}/{total_steps} ({from_step})")
    print(f"{Colors.OKCYAN}Skipping {skipped} steps, running {replay_steps}{Colors.ENDC}")
    print()

    # Show skipped steps
    for i in range(step_index):
        s = steps[i]
        _print_step_line(i + 1, total_steps, s.get('module', '?'), 'skipped')

    try:
        from core.engine.workflow.engine import WorkflowEngine
    except ImportError as e:
        print(f"{Colors.FAIL}Error: flyto-core engine not available: {e}{Colors.ENDC}")
        return 1

    # Build step metadata
    step_meta = {}
    for i, s in enumerate(steps):
        step_meta[i] = {
            'module': s.get('module', '?'),
            'hint': _step_hint(s),
        }

    completed_count = step_index  # start counting from where we pick up

    async def _on_checkpoint(si, sid, cp_data, status):
        nonlocal completed_count
        completed_count += 1
        meta = step_meta.get(si, {})
        duration_ms = 0
        eng = engine_ref[0]
        if eng and eng._trace_collector:
            st = eng._trace_collector.trace.get_step_trace(sid)
            if st:
                duration_ms = st.durationMs
        _print_step_line(completed_count, total_steps, meta.get('module', '?'),
                         status, duration_ms, meta.get('hint', ''))

    engine_ref = [None]
    start_time = time.time()

    async def _run():
        engine = WorkflowEngine(
            workflow, params,
            start_step=step_index,
            initial_context=initial_context,
            enable_trace=True,
            checkpoint_callback=_on_checkpoint,
        )
        engine_ref[0] = engine
        result = await engine.execute()
        return engine, result

    try:
        engine, result = asyncio.run(_run())
        elapsed = time.time() - start_time
        passed = completed_count - step_index
        print()
        print(
            f"{Colors.OKGREEN}\u2713 Replay done{Colors.ENDC} in {elapsed:.1f}s"
            f" \u2014 {passed}/{replay_steps} steps passed"
            f" (skipped {skipped})"
        )
        _print_output_files(params, engine)
        return 0

    except Exception as e:
        elapsed = time.time() - start_time
        print()
        print(f"{Colors.FAIL}\u2717 Replay failed{Colors.ENDC} after {elapsed:.1f}s: {e}")
        return 1
