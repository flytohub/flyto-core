"""
loop / foreach - Loop/ForEach Module

Provides functionality to iterate through list and execute sub-steps for each item
"""
from typing import Any, List, Dict
from ..base import BaseModule
from ..registry import register_module


@register_module(
    module_id='core.flow.loop',
    version='1.0.0',
    category='flow',
    tags=['flow', 'loop', 'iteration', 'control'],
    label='Loop',
    label_key='modules.flow.loop.label',
    description='Iterate through list and execute sub-steps for each item',
    description_key='modules.flow.loop.description',
    icon='Repeat',
    color='#3498DB',

    # Connection types
    input_types=['any'],
    output_types=['any'],

    # Phase 2: Execution settings
    # No timeout - let sub-steps handle their own timeouts
    retryable=False,  # Logic errors won't fix themselves
    concurrent_safe=True,  # Stateless flow control

    # Phase 2: Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['flow.control'],

    params_schema={
        'items': {
            'type': 'array',
            'label': 'Items',
            'label_key': 'modules.flow.loop.params.items.label',
            'description': 'List to iterate (can be element ID list or any list)',
            'description_key': 'modules.flow.loop.params.items.description',
            'required': True
        },
        'steps': {
            'type': 'array',
            'label': 'Steps',
            'label_key': 'modules.flow.loop.params.steps.label',
            'description': 'Sub-steps to execute for each item',
            'description_key': 'modules.flow.loop.params.steps.description',
            'required': True
        },
        'item_var': {
            'type': 'string',
            'label': 'Item Variable',
            'label_key': 'modules.flow.loop.params.item_var.label',
            'description': 'Variable name for current item (default: item)',
            'description_key': 'modules.flow.loop.params.item_var.description',
            'default': 'item',
            'required': False
        },
        'index_var': {
            'type': 'string',
            'label': 'Index Variable',
            'label_key': 'modules.flow.loop.params.index_var.label',
            'description': 'Variable name for current index (default: index)',
            'description_key': 'modules.flow.loop.params.index_var.description',
            'default': 'index',
            'required': False
        },
        'output_mode': {
            'type': 'select',
            'label': 'Output Mode',
            'label_key': 'modules.flow.loop.params.output_mode.label',
            'description': 'How to collect results',
            'description_key': 'modules.flow.loop.params.output_mode.description',
            'options': [
                {
                    'value': 'collect',
                    'label': 'Collect All',
                    'label_key': 'modules.flow.loop.params.output_mode.options.collect'
                },
                {
                    'value': 'last',
                    'label': 'Last Only',
                    'label_key': 'modules.flow.loop.params.output_mode.options.last'
                },
                {
                    'value': 'none',
                    'label': 'None',
                    'label_key': 'modules.flow.loop.params.output_mode.options.none'
                }
            ],
            'default': 'collect',
            'required': False
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
            'name': 'Extract data from search results',
            'params': {
                'items': '${search_results}',
                'item_var': 'result_element',
                'steps': [
                    {
                        'module': 'core.element.query',
                        'params': {
                            'element_id': '${result_element}',
                            'selector': 'h3'
                        },
                        'output': 'title_elem'
                    },
                    {
                        'module': 'core.element.text',
                        'params': {
                            'element_id': '${title_elem}'
                        },
                        'output': 'title'
                    }
                ],
                'output_mode': 'collect'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class LoopModule(BaseModule):
    """
    Iterate through list and execute sub-steps for each item

    Parameters:
        items: List to iterate (can be element ID list or any list)
        steps: Sub-steps to execute for each item
        item_var: Variable name for current item (Default 'item')
        index_var: Variable name for current index (Default 'index')
        output_mode: Output mode
            - 'collect': Collect all results into array (Default)
            - 'last': Only return last result
            - 'none': Don't return result

    Return:
        results: Result list (depends on output_mode)

    Example:
        {
            "module": "core.flow.loop",
            "params": {
                "items": "${search_results}",
                "item_var": "result_element",
                "steps": [
                    {
                        "module": "core.element.query",
                        "params": {
                            "element_id": "${result_element}",
                            "selector": "h3"
                        },
                        "output": "title_elem"
                    },
                    {
                        "module": "core.element.text",
                        "params": {
                            "element_id": "${title_elem}"
                        },
                        "output": "title"
                    }
                ],
                "output_mode": "collect"
            },
            "output": "all_titles"
        }
    """

    module_name = "Loop"
    module_description = "Iterate list and execute operations for each item"
    required_permission = "flow.control"

    def validate_params(self):
        if 'items' not in self.params:
            raise ValueError("Missing parameter: items")
        if 'steps' not in self.params:
            raise ValueError("Missing parameter: steps")

        self.items = self.params['items']
        self.steps = self.params['steps']
        self.item_var = self.params.get('item_var', 'item')
        self.index_var = self.params.get('index_var', 'index')
        self.output_mode = self.params.get('output_mode', 'collect')

        # items may be variable reference, need to resolve
        if isinstance(self.items, str) and self.items.startswith('${') and self.items.endswith('}'):
            var_name = self.items[2:-1]
            # Support dot syntax to get property (e.g. result_elements.element_ids)
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
            raise ValueError(f"items must be list, got: {type(self.items)}")

    async def execute(self) -> Any:
        """
        Execute loop

        For each item:
        1. Set item_var and index_var to context
        2. Execute all sub-steps
        3. Collect result (depends on output_mode)
        """
        from ..registry import ModuleRegistry

        results = []

        for index, item in enumerate(self.items):
            # Set loop variable
            loop_context = self.context.copy()
            loop_context[self.item_var] = item
            loop_context[self.index_var] = index

            # Execute sub-steps
            step_result = None
            for step_config in self.steps:
                module_name = step_config['module']
                params = step_config.get('params', {})
                output_var = step_config.get('output')

                # Resolve variable references in parameters
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

            # Collect result
            if self.output_mode == 'collect':
                results.append(step_result)
            elif self.output_mode == 'last':
                results = step_result

        # Return result
        if self.output_mode == 'collect':
            return {"status": "success", "results": results, "count": len(results)}
        elif self.output_mode == 'last':
            return {"status": "success", "result": results}
        else:  # 'none'
            return {"status": "success"}

    def _resolve_params(self, params: Dict, context: Dict) -> Dict:
        """
        Resolve variable references in parameters

        e.g.: "${item}" -> value of context['item']
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
