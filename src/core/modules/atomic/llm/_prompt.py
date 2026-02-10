"""
Prompt resolution helpers for LLM Agent module.

Handles:
- Manual vs auto prompt source
- Variable substitution ({{...}} templates)
- Array join strategies
- Value stringification with size limits
"""

import json
import logging
import re
from typing import Any, Dict, List, Union

logger = logging.getLogger(__name__)


def resolve_task_prompt(
    context: Dict[str, Any],
    params: Dict[str, Any],
    prompt_source: str,
    prompt_path: str,
    join_strategy: str,
    join_separator: str,
    max_input_size: int,
) -> str:
    """
    Resolve the task prompt based on source configuration.

    Args:
        context: Execution context with inputs
        params: Module parameters
        prompt_source: 'manual' or 'auto'
        prompt_path: Path expression for auto mode (e.g., {{input.message}})
        join_strategy: How to handle arrays ('first', 'newline', 'separator', 'json')
        join_separator: Custom separator for 'separator' strategy
        max_input_size: Maximum characters for prompt

    Returns:
        Resolved task string
    """
    if prompt_source == 'manual':
        task = params.get('task', '')
        if task and '{{' in task:
            task = substitute_variables(task, context, max_input_size)
        return task

    return _resolve_from_input(
        context=context,
        prompt_path=prompt_path,
        join_strategy=join_strategy,
        join_separator=join_separator,
        max_input_size=max_input_size,
    )


def _resolve_from_input(
    context: Dict[str, Any],
    prompt_path: str,
    join_strategy: str,
    join_separator: str,
    max_input_size: int,
) -> str:
    """Resolve prompt from input using path expression."""
    try:
        from core.engine.sdk.resolver import VariableResolver, ResolutionMode
        resolver = VariableResolver(context=context)
        raw_value = resolver.resolve(prompt_path, mode=ResolutionMode.RAW)
    except ImportError:
        raw_value = simple_resolve(context, prompt_path)

    if raw_value is None:
        return ''

    if isinstance(raw_value, (list, tuple)):
        return _join_array(raw_value, join_strategy, join_separator, max_input_size)

    return stringify_value(raw_value, max_input_size)


def simple_resolve(context: Dict[str, Any], path: str) -> Any:
    """
    Simple variable resolution fallback.
    Supports basic paths: {{input}}, {{input.field}}
    """
    match = re.match(r'\{\{(.+?)\}\}', path.strip())
    if not match:
        return None

    path_str = match.group(1).strip()
    parts = path_str.split('.')

    if parts[0] == 'input':
        current = context.get('inputs', {}).get('input')
        if current is None:
            current = context.get('inputs', {}).get('main')
        parts = parts[1:]
    elif parts[0] == 'inputs':
        current = context.get('inputs', {})
        parts = parts[1:]
    else:
        current = context.get(parts[0])
        parts = parts[1:]

    for part in parts:
        if current is None:
            return None
        if isinstance(current, dict):
            current = current.get(part)
        elif hasattr(current, part):
            current = getattr(current, part)
        else:
            return None

    return current


def substitute_variables(
    template: str,
    context: Dict[str, Any],
    max_input_size: int,
) -> str:
    """Substitute {{...}} variables in a template string."""
    def replacer(match: re.Match) -> str:
        path = '{{' + match.group(1) + '}}'
        value = simple_resolve(context, path)
        if value is None:
            return match.group(0)
        return stringify_value(value, max_input_size)

    return re.sub(r'\{\{(.+?)\}\}', replacer, template)


def _join_array(
    arr: Union[List, tuple],
    strategy: str,
    separator: str,
    max_size: int,
) -> str:
    """Join array elements based on strategy."""
    if not arr:
        return ''

    if strategy == 'first':
        return stringify_value(arr[0], max_size)
    elif strategy == 'newline':
        items = [stringify_value(item, max_size // len(arr)) for item in arr]
        return '\n'.join(items)[:max_size]
    elif strategy == 'separator':
        items = [stringify_value(item, max_size // len(arr)) for item in arr]
        return separator.join(items)[:max_size]
    elif strategy == 'json':
        result = json.dumps(arr, ensure_ascii=False, indent=2)
        if len(result) > max_size:
            result = result[:max_size] + '\n... [truncated]'
        return result

    return stringify_value(arr[0], max_size)


def stringify_value(value: Any, max_size: int) -> str:
    """Convert value to string with size limit."""
    if value is None:
        return ''

    if isinstance(value, str):
        result = value
    elif isinstance(value, bool):
        result = 'true' if value else 'false'
    elif isinstance(value, (dict, list)):
        result = json.dumps(value, ensure_ascii=False, indent=2)
    else:
        result = str(value)

    if len(result) > max_size:
        truncated = len(result) - max_size
        result = result[:max_size] + f'\n... [truncated, {truncated} chars omitted]'
        logger.warning(f'Value truncated to {max_size} chars')

    return result
