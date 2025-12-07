"""
Loop / ForEach - Iteration Module

Provides functionality to iterate over lists and execute sub-steps for each item.
Supports two modes:
- Edge-based mode: Uses 'target' and 'times' to jump back to a previous step
- Nested mode: Uses 'items' and 'steps' to execute sub-steps internally
"""
from typing import Any, List, Dict
from ...base import BaseModule
from ...registry import register_module


@register_module(
    module_id='flow.loop',
    version='1.0.0',
    category='flow',
    tags=['flow', 'loop', 'iteration', 'repeat'],
    label='Loop',
    label_key='modules.flow.loop.label',
    description='Repeat steps N times with optional jump target',
    description_key='modules.flow.loop.description',
    icon='Repeat',
    color='#8B5CF6',

    # Connection types
    input_types=['any'],
    output_types=['any'],

    # Execution settings
    retryable=False,
    concurrent_safe=True,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['flow.control'],

    params_schema={
        'times': {
            'type': 'number',
            'label': 'Times',
            'label_key': 'modules.flow.loop.params.times.label',
            'description': 'Number of times to repeat',
            'description_key': 'modules.flow.loop.params.times.description',
            'default': 10,
            'required': True
        },
        'target': {
            'type': 'string',
            'label': 'Target Step',
            'label_key': 'modules.flow.loop.params.target.label',
            'description': 'Step ID to loop back to (edge-based loop)',
            'description_key': 'modules.flow.loop.params.target.description',
            'required': False
        },
        'steps': {
            'type': 'array',
            'label': 'Steps',
            'label_key': 'modules.flow.loop.params.steps.label',
            'description': 'Steps to execute for each iteration (nested mode)',
            'description_key': 'modules.flow.loop.params.steps.description',
            'required': False
        },
        'index_var': {
            'type': 'string',
            'label': 'Index Variable',
            'label_key': 'modules.flow.loop.params.index_var.label',
            'description': 'Variable name for current index',
            'description_key': 'modules.flow.loop.params.index_var.description',
            'default': 'index'
        }
    },
    output_schema={
        'status': {'type': 'string'},
        'results': {'type': 'array', 'optional': True},
        'count': {'type': 'number', 'optional': True},
        'next_step': {'type': 'string', 'optional': True},
        'iteration': {'type': 'number', 'optional': True}
    },
    examples=[
        {
            'name': 'Edge-based loop (10 times)',
            'params': {
                'times': 10,
                'target': 'step_1'
            }
        },
        {
            'name': 'Nested loop (5 times)',
            'params': {
                'times': 5,
                'steps': [
                    {'module': 'browser.click', 'params': {'selector': '.next'}}
                ]
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
@register_module(
    module_id='flow.foreach',
    version='1.0.0',
    category='flow',
    tags=['flow', 'loop', 'iteration', 'foreach', 'list'],
    label='For Each',
    label_key='modules.flow.foreach.label',
    description='Iterate over a list and execute steps for each item',
    description_key='modules.flow.foreach.description',
    icon='List',
    color='#10B981',

    # Connection types
    input_types=['array', 'any'],
    output_types=['array', 'any'],

    # Execution settings
    retryable=False,
    concurrent_safe=True,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['flow.control'],

    params_schema={
        'items': {
            'type': 'array',
            'label': 'Items',
            'label_key': 'modules.flow.foreach.params.items.label',
            'description': 'List of items to iterate over',
            'description_key': 'modules.flow.foreach.params.items.description',
            'required': True
        },
        'steps': {
            'type': 'array',
            'label': 'Steps',
            'label_key': 'modules.flow.foreach.params.steps.label',
            'description': 'Steps to execute for each item',
            'description_key': 'modules.flow.foreach.params.steps.description',
            'required': True
        },
        'item_var': {
            'type': 'string',
            'label': 'Item Variable',
            'label_key': 'modules.flow.foreach.params.item_var.label',
            'description': 'Variable name for current item',
            'description_key': 'modules.flow.foreach.params.item_var.description',
            'default': 'item'
        },
        'index_var': {
            'type': 'string',
            'label': 'Index Variable',
            'label_key': 'modules.flow.foreach.params.index_var.label',
            'description': 'Variable name for current index',
            'description_key': 'modules.flow.foreach.params.index_var.description',
            'default': 'index'
        },
        'output_mode': {
            'type': 'string',
            'label': 'Output Mode',
            'label_key': 'modules.flow.foreach.params.output_mode.label',
            'description': 'How to collect results: collect (array), last (single), none',
            'description_key': 'modules.flow.foreach.params.output_mode.description',
            'default': 'collect',
            'enum': ['collect', 'last', 'none']
        }
    },
    output_schema={
        'status': {'type': 'string'},
        'results': {'type': 'array', 'optional': True},
        'result': {'type': 'any', 'optional': True},
        'count': {'type': 'number', 'optional': True}
    },
    examples=[
        {
            'name': 'Process each search result',
            'params': {
                'items': '${search_results}',
                'item_var': 'element',
                'steps': [
                    {
                        'module': 'element.text',
                        'params': {'element_id': '${element}'},
                        'output': 'text'
                    }
                ]
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class LoopModule(BaseModule):
    """
    Iterate over a list and execute sub-steps for each item

    Supports two modes:
    1. Edge-based mode (target + times):
       - Returns next_step to jump back to target
       - WorkflowEngine handles the actual looping

    2. Nested mode (items/times + steps):
       - Executes sub-steps internally for each iteration

    Parameters:
        times: Number of iterations (edge-based mode)
        target: Step ID to jump back to (edge-based mode)
        items: List to iterate (nested mode)
        steps: Sub-steps to execute for each item (nested mode)
        item_var: Variable name for current item (default 'item')
        index_var: Variable name for current index (default 'index')
        output_mode: Output mode for nested mode
            - 'collect': Collect all results into array (default)
            - 'last': Only return last result
            - 'none': Don't return results

    Returns:
        Edge-based mode: {next_step, iteration, __set_context} or {status: completed}
        Nested mode: {status, results/result/count}
    """

    module_name = "Loop"
    module_description = "Iterate over list and execute operations for each item"
    required_permission = "flow.control"

    ITERATION_PREFIX = '__loop_iteration_'

    def validate_params(self):
        import logging
        logger = logging.getLogger(__name__)
        logger.debug(f"LoopModule validate_params: params={self.params}")

        # Check for edge-based loop mode (target parameter)
        self.target = self.params.get('target')
        self.is_edge_mode = bool(self.target) and str(self.target).strip() != ''
        logger.debug(f"LoopModule: target={self.target!r}, is_edge_mode={self.is_edge_mode}")

        if self.is_edge_mode:
            # Edge-based loop: uses 'target' and 'times'
            self.times = self.params.get('times', 10)
            if isinstance(self.times, str) and self.times.startswith('${') and self.times.endswith('}'):
                var_name = self.times[2:-1]
                self.times = self.context.get(var_name, 10)
            self.times = int(self.times)
            self.steps = None
            self.items = None
        else:
            # Nested loop mode: uses 'steps' and either 'times' or 'items'
            has_times = 'times' in self.params
            has_items = 'items' in self.params

            if not has_times and not has_items:
                raise ValueError("Missing parameter: either 'times', 'items', or 'target' is required")
            if 'steps' not in self.params:
                raise ValueError("Missing parameter: steps (required for nested loop mode)")

            self.steps = self.params['steps']
            self.item_var = self.params.get('item_var', 'item')
            self.index_var = self.params.get('index_var', 'index')
            self.output_mode = self.params.get('output_mode', 'collect')

            # Handle 'times' parameter - generate a range list
            if has_times:
                times = self.params['times']
                if isinstance(times, str) and times.startswith('${') and times.endswith('}'):
                    var_name = times[2:-1]
                    times = self.context.get(var_name, 1)
                self.items = list(range(int(times)))
            else:
                # Handle 'items' parameter
                self.items = self.params['items']

                # items may be a variable reference, needs resolution
                if isinstance(self.items, str) and self.items.startswith('${') and self.items.endswith('}'):
                    var_name = self.items[2:-1]
                    # Support dot notation for attributes (e.g. result_elements.element_ids)
                    if '.' in var_name:
                        parts = var_name.split('.')
                        value = self.context.get(parts[0])
                        for part in parts[1:]:
                            if value is None:
                                break
                            if isinstance(value, dict):
                                value = value.get(part)
                            else:
                                value = getattr(value, part, None)
                        self.items = value if value is not None else []
                    else:
                        self.items = self.context.get(var_name, [])

                if not isinstance(self.items, list):
                    raise ValueError(f"items must be a list, got: {type(self.items)}")

    async def execute(self) -> Any:
        """
        Execute loop in one of two modes:

        Edge-based mode (target parameter):
        - Returns next_step to jump back to target
        - WorkflowEngine handles the actual looping

        Nested mode (steps parameter):
        - Executes sub-steps internally for each iteration
        """
        # Edge-based mode: return jump instruction for workflow engine
        if self.is_edge_mode:
            return await self._execute_edge_mode()

        # Nested mode: execute sub-steps internally
        return await self._execute_nested_mode()

    async def _execute_edge_mode(self) -> Dict[str, Any]:
        """
        Edge-based loop: return jump instruction to workflow engine

        The loop body (steps between target and this loop module) executes N times.
        - First execution: before any loop (iteration 0)
        - Then N-1 more jumps back to target

        So if times=2, we jump back 1 time (total 2 executions of loop body).
        """
        # Use target as key to track iterations
        iteration_key = f"{self.ITERATION_PREFIX}{self.target}"
        current_iteration = self.context.get(iteration_key, 0) + 1

        # Check if we've completed enough iterations
        # times=2 means: run 2 times total, so jump back (times-1)=1 time
        if current_iteration >= self.times:
            # Max iterations reached, continue to next step
            return {
                'status': 'completed',
                'iteration': current_iteration,
                'message': f"Loop completed after {self.times} iterations"
            }

        # Return jump instruction for next iteration
        return {
            'next_step': self.target,
            'iteration': current_iteration,
            '__set_context': {
                iteration_key: current_iteration
            }
        }

    async def _execute_nested_mode(self) -> Dict[str, Any]:
        """
        Nested loop: execute sub-steps internally
        """
        from ...registry import ModuleRegistry

        results = []

        for index, item in enumerate(self.items):
            # Set loop variables
            loop_context = self.context.copy()
            loop_context[self.item_var] = item
            loop_context[self.index_var] = index

            # Execute sub-steps
            step_result = None
            for step_config in self.steps:
                module_name = step_config['module']
                params = step_config.get('params', {})
                output_var = step_config.get('output')

                # Resolve variable references in params
                resolved_params = self._resolve_params(params, loop_context)

                # Create and execute module
                module_class = ModuleRegistry.get(module_name)
                if not module_class:
                    raise ValueError(f"Unknown module: {module_name}")

                module_instance = module_class(resolved_params, loop_context)
                step_result = await module_instance.run()

                # Save output to context
                if output_var:
                    loop_context[output_var] = step_result

            # Collect results
            if self.output_mode == 'collect':
                results.append(step_result)
            elif self.output_mode == 'last':
                results = step_result

        # Return results
        if self.output_mode == 'collect':
            return {"status": "success", "results": results, "count": len(results)}
        elif self.output_mode == 'last':
            return {"status": "success", "result": results}
        else:  # 'none'
            return {"status": "success"}

    def _resolve_params(self, params: Dict, context: Dict) -> Dict:
        """
        Resolve variable references in parameters

        Example: "${item}" -> context['item'] value
        """
        resolved = {}
        for key, value in params.items():
            if isinstance(value, str) and value.startswith('${') and value.endswith('}'):
                var_name = value[2:-1]
                resolved[key] = context.get(var_name, value)
            elif isinstance(value, dict):
                resolved[key] = self._resolve_params(value, context)
            elif isinstance(value, list):
                resolved[key] = [
                    self._resolve_params(item, context) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                resolved[key] = value
        return resolved
