"""
Loop / ForEach - Iteration Module

Workflow Spec v1.2:
- Uses output ports (iterate/done/error) instead of text params
- Returns __event__ for engine routing
- Edges determine flow, not params.target (deprecated)

Supports two modes:
- Edge-based mode: Uses output ports to route back (iterate) or forward (done)
- Nested mode: Uses 'items' and 'steps' to execute sub-steps internally
"""
from typing import Any

from ....base import BaseModule
from ....registry import register_module
from ....types import NodeType, EdgeType, DataType

from .edge_mode import execute_edge_mode, ITERATION_PREFIX
from .nested_mode import execute_nested_mode
from .resolver import resolve_params, resolve_variable


# Loop module registration (flow.loop)
LOOP_CONFIG = {
    'module_id': 'flow.loop',
    'version': '2.0.0',
    'category': 'flow',
    'tags': ['flow', 'loop', 'iteration', 'repeat'],
    'label': 'Loop',
    'label_key': 'modules.flow.loop.label',
    'description': 'Repeat steps N times using output port routing',
    'description_key': 'modules.flow.loop.description',
    'icon': 'Repeat',
    'color': '#8B5CF6',
    'node_type': NodeType.LOOP,
    'input_ports': [
        {
            'id': 'input',
            'label': 'Input',
            'label_key': 'modules.flow.loop.ports.input',
            'data_type': DataType.ANY.value,
            'edge_type': EdgeType.CONTROL.value,
            'max_connections': 1,
            'required': True
        }
    ],
    'output_ports': [
        {
            'id': 'iterate',
            'label': 'Iterate',
            'label_key': 'modules.flow.loop.ports.iterate',
            'event': 'iterate',
            'color': '#F59E0B',
            'edge_type': EdgeType.CONTROL.value
        },
        {
            'id': 'done',
            'label': 'Done',
            'label_key': 'modules.flow.loop.ports.done',
            'event': 'done',
            'color': '#10B981',
            'edge_type': EdgeType.CONTROL.value
        },
        {
            'id': 'error',
            'label': 'Error',
            'label_key': 'common.ports.error',
            'event': 'error',
            'color': '#EF4444',
            'edge_type': EdgeType.CONTROL.value
        }
    ],
    'retryable': False,
    'concurrent_safe': True,
    'requires_credentials': False,
    'handles_sensitive_data': False,
    'required_permissions': ['flow.control'],
    'params_schema': {
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
            'description': 'DEPRECATED: Use output ports and edges instead',
            'description_key': 'modules.flow.loop.params.target.description',
            'required': False,
            'deprecated': True
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
    'output_schema': {
        '__event__': {'type': 'string', 'description': 'Event for routing (iterate/done/error)'},
        'outputs': {
            'type': 'object',
            'description': 'Output values by port',
            'properties': {
                'iterate': {'type': 'object'},
                'done': {'type': 'object'}
            }
        },
        'iteration': {'type': 'number', 'description': 'Current iteration count'},
        'status': {'type': 'string', 'optional': True},
        'results': {'type': 'array', 'optional': True},
        'count': {'type': 'number', 'optional': True}
    },
    'examples': [
        {
            'name': 'Loop 10 times (v2.0 - edge-based)',
            'description': 'Connect iterate port back to the step you want to repeat',
            'params': {'times': 10},
            'note': 'Connect iterate port to loop body start, done port to next step'
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
    'author': 'Flyto2 Team',
    'license': 'MIT'
}

# ForEach module registration (flow.foreach)
FOREACH_CONFIG = {
    'module_id': 'flow.foreach',
    'version': '1.0.0',
    'category': 'flow',
    'tags': ['flow', 'loop', 'iteration', 'foreach', 'list'],
    'label': 'For Each',
    'label_key': 'modules.flow.foreach.label',
    'description': 'Iterate over a list and execute steps for each item',
    'description_key': 'modules.flow.foreach.description',
    'icon': 'List',
    'color': '#10B981',
    'input_types': ['array'],
    'output_types': ['array'],
    'retryable': False,
    'concurrent_safe': True,
    'requires_credentials': False,
    'handles_sensitive_data': False,
    'required_permissions': ['flow.control'],
    'params_schema': {
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
    'output_schema': {
        'status': {'type': 'string'},
        'results': {'type': 'array', 'optional': True},
        'result': {'type': 'any', 'optional': True},
        'count': {'type': 'number', 'optional': True}
    },
    'examples': [
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
    'author': 'Flyto2 Team',
    'license': 'MIT'
}


@register_module(**LOOP_CONFIG)
@register_module(**FOREACH_CONFIG)
class LoopModule(BaseModule):
    """
    Iterate over a list and execute sub-steps for each item.

    Supports two modes:

    1. Edge-based mode (target + times):
       - Returns next_step to jump back to target
       - WorkflowEngine handles the actual looping

    2. Nested mode (items/times + steps):
       - Executes sub-steps internally for each iteration

    Parameters:
        times: Number of iterations (edge-based mode)
        target: Step ID to jump back to (edge-based mode, deprecated)
        items: List to iterate (nested mode)
        steps: Sub-steps to execute for each item (nested mode)
        item_var: Variable name for current item (default 'item')
        index_var: Variable name for current index (default 'index')
        output_mode: Output mode for nested mode
            - 'collect': Collect all results into array (default)
            - 'last': Only return last result
            - 'none': Don't return results

    Returns:
        Edge-based mode: {__event__, outputs, iteration} or {status: completed}
        Nested mode: {status, results/result/count}
    """

    module_name = "Loop"
    module_description = "Iterate over list and execute operations for each item"
    required_permission = "flow.control"

    def validate_params(self):
        import logging
        import warnings
        logger = logging.getLogger(__name__)
        logger.debug(f"LoopModule validate_params: params={self.params}")

        # Check for edge-based loop mode (target parameter - DEPRECATED)
        self.target = self.params.get('target')
        self.is_edge_mode = bool(self.target) and str(self.target).strip() != ''
        logger.debug(f"LoopModule: target={self.target!r}, is_edge_mode={self.is_edge_mode}")

        # Deprecation warning for params.target
        if self.target:
            warnings.warn(
                "params.target is deprecated in v2.0. "
                "Use output ports and edges instead. "
                "Connect 'iterate' port to the step you want to loop back to.",
                DeprecationWarning
            )

        if self.is_edge_mode:
            self._validate_edge_mode()
        else:
            self._validate_nested_mode()

    def _validate_edge_mode(self):
        """Validate parameters for edge-based loop mode."""
        self.times = self.params.get('times', 10)
        if isinstance(self.times, str) and self.times.startswith('${') and self.times.endswith('}'):
            var_name = self.times[2:-1]
            self.times = self.context.get(var_name, 10)
        self.times = int(self.times)
        self.steps = None
        self.items = None

    def _validate_nested_mode(self):
        """Validate parameters for nested loop mode."""
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
            # Handle 'items' parameter with variable resolution
            self.items = resolve_variable(self.params['items'], self.context)

            if not isinstance(self.items, list):
                raise ValueError(f"items must be a list, got: {type(self.items)}")

    async def execute(self) -> Any:
        """
        Execute loop in one of two modes.

        Edge-based mode (target parameter):
        - Returns next_step to jump back to target
        - WorkflowEngine handles the actual looping

        Nested mode (steps parameter):
        - Executes sub-steps internally for each iteration
        """
        if self.is_edge_mode:
            return await execute_edge_mode(
                target=self.target,
                times=self.times,
                context=self.context
            )

        return await execute_nested_mode(
            items=self.items,
            steps=self.steps,
            item_var=self.item_var,
            index_var=self.index_var,
            output_mode=self.output_mode,
            context=self.context
        )

    def _resolve_params(self, params, context):
        """Backwards compatibility wrapper for resolve_params."""
        return resolve_params(params, context)
