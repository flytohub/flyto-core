"""
Nested Loop Execution

Handles loop execution with internal sub-step execution.
Executes sub-steps for each item in the iteration.
"""
from typing import Any, Dict, List

from .resolver import resolve_params


async def execute_nested_mode(
    items: List[Any],
    steps: List[Dict[str, Any]],
    item_var: str,
    index_var: str,
    output_mode: str,
    context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Nested loop: execute sub-steps internally for each item.

    Args:
        items: List of items to iterate over
        steps: List of step configurations to execute
        item_var: Variable name for current item (e.g., 'item')
        index_var: Variable name for current index (e.g., 'index')
        output_mode: How to collect results ('collect', 'last', 'none')
        context: Base execution context

    Returns:
        Dict with status and results based on output_mode:
        - collect: {'status': 'success', 'results': [...], 'count': N}
        - last: {'status': 'success', 'result': last_value}
        - none: {'status': 'success'}
    """
    from ....registry import ModuleRegistry

    results = []

    for index, item in enumerate(items):
        # Set loop variables in context
        loop_context = context.copy()
        loop_context[item_var] = item
        loop_context[index_var] = index

        # Execute sub-steps sequentially
        step_result = None
        for step_config in steps:
            module_name = step_config['module']
            params = step_config.get('params', {})
            output_var = step_config.get('output')

            # Resolve variable references in params
            resolved_params = resolve_params(params, loop_context)

            # Create and execute module
            module_class = ModuleRegistry.get(module_name)
            if not module_class:
                raise ValueError(f"Unknown module: {module_name}")

            module_instance = module_class(resolved_params, loop_context)
            step_result = await module_instance.run()

            # Save output to context for next step
            if output_var:
                loop_context[output_var] = step_result

        # Collect results based on output_mode
        if output_mode == 'collect':
            results.append(step_result)
        elif output_mode == 'last':
            results = step_result

    # Return results based on output_mode
    if output_mode == 'collect':
        return {"status": "success", "results": results, "count": len(results)}
    elif output_mode == 'last':
        return {"status": "success", "result": results}
    else:  # 'none'
        return {"status": "success"}
