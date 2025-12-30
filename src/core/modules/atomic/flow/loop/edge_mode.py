"""
Edge-Based Loop Execution

Handles loop execution using output port routing (Workflow Spec v1.2).
Returns events ('iterate'/'done') for workflow engine to handle routing.
"""
from typing import Any, Dict

ITERATION_PREFIX = '__loop_iteration_'


async def execute_edge_mode(
    target: str,
    times: int,
    context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Edge-based loop: return event for workflow engine routing.

    The loop body (steps between target and this loop module) executes N times.
    - First execution: before any loop (iteration 0)
    - Then N-1 more jumps back to target

    So if times=2, we jump back 1 time (total 2 executions of loop body).

    Args:
        target: Target step ID to jump back to (deprecated in v2.0)
        times: Number of times to execute the loop
        context: Execution context for tracking iteration state

    Returns:
        Dict with __event__ (iterate/done) for engine routing:
        - iterate: Continue looping, includes iteration count
        - done: Loop complete, includes total iterations
    """
    # Use step_id or target as key to track iterations
    step_id = context.get('__current_step_id', target or 'loop')
    iteration_key = f"{ITERATION_PREFIX}{step_id}"
    current_iteration = context.get(iteration_key, 0) + 1

    # Check if we've completed enough iterations
    # times=2 means: run 2 times total, so jump back (times-1)=1 time
    if current_iteration >= times:
        # Max iterations reached - emit 'done' event
        return {
            '__event__': 'done',
            'outputs': {
                'done': {
                    'iterations': current_iteration,
                    'status': 'completed'
                }
            },
            'iteration': current_iteration,
            'status': 'completed',
            'message': f"Loop completed after {times} iterations",
            '__set_context': {
                iteration_key: 0  # Reset for next execution
            }
        }

    # Continue iterating - emit 'iterate' event
    response = {
        '__event__': 'iterate',
        'outputs': {
            'iterate': {
                'iteration': current_iteration,
                'remaining': times - current_iteration
            }
        },
        'iteration': current_iteration,
        '__set_context': {
            iteration_key: current_iteration
        }
    }

    # Legacy support: include next_step if target provided (deprecated)
    if target:
        response['next_step'] = target

    return response
