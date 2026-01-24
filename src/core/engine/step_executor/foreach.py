"""
Foreach Execution

Step execution for each item in an array.
"""

import logging
from typing import Any, Callable, Coroutine, Dict, List, Optional, TYPE_CHECKING

from ..exceptions import StepExecutionError

if TYPE_CHECKING:
    from ..variable_resolver import VariableResolver
    from ..trace import StepTrace

logger = logging.getLogger(__name__)


async def execute_foreach_step(
    step_config: Dict[str, Any],
    resolver: "VariableResolver",
    context: Dict[str, Any],
    foreach_array: Any,
    foreach_var: str,
    execute_single_fn: Callable[
        [Dict[str, Any], "VariableResolver", Dict[str, Any], int, int, Optional["StepTrace"]],
        Coroutine[Any, Any, Any]
    ],
    step_index: int = 0,
    step_trace: Optional["StepTrace"] = None,
) -> List[Any]:
    """
    Execute a step for each item in an array.

    Args:
        step_config: Step configuration
        resolver: Variable resolver
        context: Current workflow context
        foreach_array: Array to iterate over (may be variable reference)
        foreach_var: Variable name for current item
        execute_single_fn: Function to execute single step
        step_index: Index of the step

    Returns:
        Array of results matching input array order
    """
    step_id = step_config.get('id', f'step_{id(step_config)}')
    on_error = step_config.get('on_error', 'stop')
    timeout = step_config.get('timeout', 0)

    resolved_array = resolver.resolve(foreach_array)

    if not isinstance(resolved_array, list):
        raise StepExecutionError(
            step_id,
            f"foreach expects array, got {type(resolved_array).__name__}"
        )

    logger.info(f"Executing foreach step '{step_id}' with {len(resolved_array)} items")

    results = []
    for index, item in enumerate(resolved_array):
        context[foreach_var] = item
        context['__foreach_index__'] = index

        try:
            result = await execute_single_fn(
                step_config, resolver, context, timeout, step_index, step_trace
            )
            results.append(result)
        except Exception as e:
            if on_error == 'continue':
                logger.warning(
                    f"Foreach iteration {index} failed, continuing: {str(e)}"
                )
                results.append({'ok': False, 'error': str(e), 'index': index})
            else:
                raise StepExecutionError(
                    step_id,
                    f"Foreach iteration {index} failed: {str(e)}",
                    e
                )

    # Clean up foreach variables
    if foreach_var in context:
        del context[foreach_var]
    if '__foreach_index__' in context:
        del context['__foreach_index__']

    return results
