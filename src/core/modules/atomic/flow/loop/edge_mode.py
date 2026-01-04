"""
Edge-Based Loop Execution

Handles loop execution using output port routing (Workflow Spec v1.2).
Returns events ('iterate'/'done') for workflow engine to handle routing.

Supports two modes:
- Repeat mode: Execute N times (times parameter only)
- ForEach mode: Iterate over items array, sets loop.item and loop.index scope
"""
from typing import Any, Dict, List, Optional

ITERATION_PREFIX = '__loop_iteration_'


async def execute_edge_mode(
    target: str,
    times: int,
    context: Dict[str, Any],
    items: Optional[List[Any]] = None,
    item_var: str = 'item',
    index_var: str = 'index',
) -> Dict[str, Any]:
    """
    Edge-based loop: return event for workflow engine routing.

    Two modes:
    1. Repeat mode (items=None): Just repeat N times
    2. ForEach mode (items=[...]): Iterate over items, set loop scope

    Args:
        target: Target step ID to jump back to (deprecated in v2.0)
        times: Number of times to execute (used if items is None)
        context: Execution context for tracking iteration state
        items: Optional array to iterate over (ForEach mode)
        item_var: Variable name for current item (default: 'item')
        index_var: Variable name for current index (default: 'index')

    Returns:
        Dict with __event__ (iterate/done) and __set_context for scope:
        - iterate: Continue looping, sets loop.item and loop.index
        - done: Loop complete, clears loop scope
    """
    # Determine iteration count
    if items is not None:
        total_iterations = len(items)
    else:
        total_iterations = times

    # Use step_id or target as key to track iterations
    step_id = context.get('__current_step_id', target or 'loop')
    iteration_key = f"{ITERATION_PREFIX}{step_id}"
    current_index = context.get(iteration_key, 0)

    # Check if we've completed all iterations
    if current_index >= total_iterations:
        # Loop complete - emit 'done' event
        return {
            '__event__': 'done',
            'outputs': {
                'done': {
                    'iterations': current_index,
                    'status': 'completed'
                }
            },
            'iteration': current_index,
            'status': 'completed',
            'message': f"Loop completed after {current_index} iterations",
            '__set_context': {
                iteration_key: 0,  # Reset for next execution
                # Clear loop scope
                f'loop.{item_var}': None,
                f'loop.{index_var}': None,
                'loop.item': None,
                'loop.index': None,
            }
        }

    # Continue iterating - emit 'iterate' event
    set_context = {
        iteration_key: current_index + 1,  # Increment for next iteration
        f'loop.{index_var}': current_index,
        'loop.index': current_index,
    }

    # ForEach mode: set current item in scope
    if items is not None:
        current_item = items[current_index]
        set_context[f'loop.{item_var}'] = current_item
        set_context['loop.item'] = current_item

    response = {
        '__event__': 'iterate',
        'outputs': {
            'iterate': {
                'index': current_index,
                'remaining': total_iterations - current_index - 1,
                'total': total_iterations,
            }
        },
        'iteration': current_index,
        '__set_context': set_context,
    }

    # Add item to outputs if in ForEach mode
    if items is not None:
        response['outputs']['iterate']['item'] = items[current_index]

    # Legacy support: include next_step if target provided (deprecated)
    if target:
        response['next_step'] = target

    return response
