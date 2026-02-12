"""
Data Pipeline Module - Chain multiple data transformations

Provides a single module that can apply multiple transformations
to data in sequence, similar to a Unix pipe or functional programming
pipeline.

Supported operations:
- filter: Filter items by condition
- map: Transform items using expression
- sort: Sort items by field
- limit: Take first N items
- skip: Skip first N items
- unique: Remove duplicates
- flatten: Flatten nested arrays
- pick: Select specific fields from objects
- omit: Remove specific fields from objects

This reduces the need for chaining multiple nodes and
improves workflow readability.
"""
from typing import Any, Dict, List, Optional
import operator

from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field
from ...types import NodeType, EdgeType, DataType


def _evaluate_condition(item: Any, condition: str, value: Any) -> bool:
    """Evaluate a filter condition against an item."""
    ops = {
        'eq': operator.eq,
        '==': operator.eq,
        'ne': operator.ne,
        '!=': operator.ne,
        'gt': operator.gt,
        '>': operator.gt,
        'gte': operator.ge,
        '>=': operator.ge,
        'lt': operator.lt,
        '<': operator.lt,
        'lte': operator.le,
        '<=': operator.le,
    }

    if condition in ops:
        try:
            return ops[condition](item, value)
        except TypeError:
            return False

    if condition == 'contains':
        if isinstance(item, str):
            return str(value) in item
        if isinstance(item, (list, dict)):
            return value in item
        return False

    if condition == 'startswith':
        return isinstance(item, str) and item.startswith(str(value))

    if condition == 'endswith':
        return isinstance(item, str) and item.endswith(str(value))

    if condition == 'matches':
        import re
        return isinstance(item, str) and bool(re.match(str(value), item))

    if condition == 'exists':
        return item is not None

    if condition == 'truthy':
        return bool(item)

    return False


def _get_nested_value(obj: Any, path: str) -> Any:
    """Get a nested value from an object using dot notation."""
    if not path:
        return obj

    parts = path.split('.')
    current = obj

    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            idx = int(part)
            current = current[idx] if 0 <= idx < len(current) else None
        elif hasattr(current, part):
            current = getattr(current, part)
        else:
            return None

    return current


@register_module(
    module_id='data.pipeline',
    version='1.0.0',
    category='data',
    tags=['data', 'pipeline', 'transform', 'filter', 'map', 'sort'],
    label='Data Pipeline',
    label_key='modules.data.pipeline.label',
    description='Chain multiple data transformations in a single step',
    description_key='modules.data.pipeline.description',
    icon='GitBranch',
    color='#EC4899',

    # Type definitions for connection validation
    input_types=['any'],
    output_types=['any'],

    can_receive_from=['*'],
    can_connect_to=['*'],

    node_type=NodeType.STANDARD,

    input_ports=[
        {
            'id': 'input',
            'label': 'Input',
            'label_key': 'modules.data.pipeline.ports.input',
            'data_type': DataType.ANY.value,
            'edge_type': EdgeType.CONTROL.value,
            'max_connections': 1,
            'required': True
        }
    ],

    output_ports=[
        {
            'id': 'output',
            'label': 'Output',
            'label_key': 'modules.data.pipeline.ports.output',
            'event': 'success',
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

    retryable=False,
    concurrent_safe=True,
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema=compose(
        field(
            'input',
            type='any',
            label='Input Data',
            label_key='modules.data.pipeline.params.input.label',
            description='Input data to transform (array or object)',
            description_key='modules.data.pipeline.params.input.description',
            required=True,
        ),
        field(
            'steps',
            type='array',
            label='Pipeline Steps',
            label_key='modules.data.pipeline.params.steps.label',
            description='Array of transformation steps to apply in order',
            description_key='modules.data.pipeline.params.steps.description',
            required=True,
        ),
    ),

    output_schema={
        'result': {
            'type': 'any',
            'description': 'Transformed data',
            'description_key': 'modules.data.pipeline.output.result.description'
        },
        'original_count': {
            'type': 'integer',
            'description': 'Count of items before transformation',
            'description_key': 'modules.data.pipeline.output.original_count.description'
        },
        'result_count': {
            'type': 'integer',
            'description': 'Count of items after transformation',
            'description_key': 'modules.data.pipeline.output.result_count.description'
        },
        'steps_applied': {
            'type': 'integer',
            'description': 'Number of transformation steps applied',
            'description_key': 'modules.data.pipeline.output.steps_applied.description'
        }
    },

    examples=[
        {
            'name': 'Filter and sort',
            'description': 'Filter active users and sort by name',
            'params': {
                'input': '${input.users}',
                'steps': [
                    {'filter': {'field': 'active', 'condition': 'eq', 'value': True}},
                    {'sort': {'field': 'name', 'order': 'asc'}}
                ]
            }
        },
        {
            'name': 'Transform and limit',
            'description': 'Extract IDs and take first 10',
            'params': {
                'input': '${input.records}',
                'steps': [
                    {'map': {'extract': 'id'}},
                    {'limit': 10}
                ]
            }
        },
        {
            'name': 'Complex pipeline',
            'description': 'Full data transformation pipeline',
            'params': {
                'input': '${input.data}',
                'steps': [
                    {'filter': {'field': 'status', 'condition': 'eq', 'value': 'completed'}},
                    {'pick': ['id', 'name', 'timestamp']},
                    {'sort': {'field': 'timestamp', 'order': 'desc'}},
                    {'skip': 5},
                    {'limit': 20}
                ]
            }
        }
    ],
    author='Flyto Team',
    license='MIT',
    timeout_ms=30000,
)
class DataPipelineModule(BaseModule):
    """
    Data Pipeline module.

    Applies a series of transformation steps to input data.
    Each step is processed in order, with the output of one
    step becoming the input of the next.

    Step Types:
    - filter: Filter items (field, condition, value)
    - map: Transform items (extract field or apply function)
    - sort: Sort items (field, order: asc/desc)
    - limit: Take first N items
    - skip: Skip first N items
    - unique: Remove duplicates (optional field)
    - flatten: Flatten nested arrays (optional depth)
    - pick: Select specific fields from objects
    - omit: Remove specific fields from objects
    """

    module_name = "Data Pipeline"
    module_description = "Chain multiple data transformations"

    def validate_params(self) -> None:
        self.input_data = self.params.get('input', [])
        self.steps = self.params.get('steps', [])

        if not isinstance(self.steps, list):
            raise ValueError("steps must be an array")

        # Validate step structure
        valid_operations = {'filter', 'map', 'sort', 'limit', 'skip', 'unique', 'flatten', 'pick', 'omit'}
        for i, step in enumerate(self.steps):
            if not isinstance(step, dict):
                raise ValueError(f"Step {i} must be an object")

            step_ops = set(step.keys())
            if not step_ops.intersection(valid_operations):
                raise ValueError(
                    f"Step {i} must contain one of: {', '.join(valid_operations)}. "
                    f"Got: {', '.join(step_ops)}"
                )

    async def execute(self) -> Dict[str, Any]:
        """Apply all transformation steps to input data."""
        try:
            data = self.input_data
            original_count = len(data) if isinstance(data, list) else 1
            steps_applied = 0

            for i, step in enumerate(self.steps):
                try:
                    data = self._apply_step(data, step)
                    steps_applied += 1
                except Exception as e:
                    return {
                        '__event__': 'error',
                        'outputs': {
                            'error': {
                                'message': f'Step {i} failed: {str(e)}',
                                'step_index': i,
                                'step': step
                            }
                        },
                        '__error__': {
                            'code': 'PIPELINE_STEP_ERROR',
                            'message': f'Step {i} failed: {str(e)}'
                        }
                    }

            result_count = len(data) if isinstance(data, list) else 1

            return {
                'ok': True,
                'data': {
                    'result': data,
                    'original_count': original_count,
                    'result_count': result_count,
                    'steps_applied': steps_applied
                }
            }

        except Exception as e:
            return {
                '__event__': 'error',
                'outputs': {
                    'error': {'message': str(e)}
                },
                '__error__': {
                    'code': 'PIPELINE_ERROR',
                    'message': str(e)
                }
            }

    def _apply_step(self, data: Any, step: Dict[str, Any]) -> Any:
        """Apply a single transformation step."""

        # Filter
        if 'filter' in step:
            return self._apply_filter(data, step['filter'])

        # Map
        if 'map' in step:
            return self._apply_map(data, step['map'])

        # Sort
        if 'sort' in step:
            return self._apply_sort(data, step['sort'])

        # Limit
        if 'limit' in step:
            limit = step['limit']
            if isinstance(limit, dict):
                limit = limit.get('count', limit.get('n', 10))
            return data[:int(limit)] if isinstance(data, list) else data

        # Skip
        if 'skip' in step:
            skip = step['skip']
            if isinstance(skip, dict):
                skip = skip.get('count', skip.get('n', 0))
            return data[int(skip):] if isinstance(data, list) else data

        # Unique
        if 'unique' in step:
            return self._apply_unique(data, step['unique'])

        # Flatten
        if 'flatten' in step:
            return self._apply_flatten(data, step['flatten'])

        # Pick
        if 'pick' in step:
            fields = step['pick']
            if isinstance(fields, str):
                fields = [fields]
            return self._apply_pick(data, fields)

        # Omit
        if 'omit' in step:
            fields = step['omit']
            if isinstance(fields, str):
                fields = [fields]
            return self._apply_omit(data, fields)

        return data

    def _apply_filter(self, data: Any, filter_config: Any) -> List[Any]:
        """Apply filter operation."""
        if not isinstance(data, list):
            data = [data]

        # Simple string filter (expression)
        if isinstance(filter_config, str):
            # For now, treat as field exists check
            return [item for item in data if _get_nested_value(item, filter_config) is not None]

        # Dict filter config
        if isinstance(filter_config, dict):
            field_path = filter_config.get('field', '')
            condition = filter_config.get('condition', 'eq')
            value = filter_config.get('value')

            result = []
            for item in data:
                item_value = _get_nested_value(item, field_path) if field_path else item
                if _evaluate_condition(item_value, condition, value):
                    result.append(item)
            return result

        return data

    def _apply_map(self, data: Any, map_config: Any) -> List[Any]:
        """Apply map operation."""
        if not isinstance(data, list):
            data = [data]

        # Simple string - extract field
        if isinstance(map_config, str):
            return [_get_nested_value(item, map_config) for item in data]

        # Dict config
        if isinstance(map_config, dict):
            # Extract field
            if 'extract' in map_config:
                field_path = map_config['extract']
                return [_get_nested_value(item, field_path) for item in data]

            # Template
            if 'template' in map_config:
                template = map_config['template']
                result = []
                for item in data:
                    if isinstance(item, dict):
                        try:
                            result.append(template.format(**item))
                        except (KeyError, IndexError):
                            result.append(template)
                    else:
                        result.append(template)
                return result

        return data

    def _apply_sort(self, data: Any, sort_config: Any) -> List[Any]:
        """Apply sort operation."""
        if not isinstance(data, list):
            return data

        # Simple string - field name
        if isinstance(sort_config, str):
            return sorted(data, key=lambda x: _get_nested_value(x, sort_config) or '')

        # Dict config
        if isinstance(sort_config, dict):
            field_path = sort_config.get('field', '')
            order = sort_config.get('order', 'asc')
            reverse = order.lower() == 'desc'

            def sort_key(x):
                val = _get_nested_value(x, field_path) if field_path else x
                # Handle None values
                if val is None:
                    return (1, '')  # Put None at end
                return (0, val)

            return sorted(data, key=sort_key, reverse=reverse)

        return data

    def _apply_unique(self, data: Any, unique_config: Any) -> List[Any]:
        """Apply unique operation."""
        if not isinstance(data, list):
            return data

        # Simple field-based unique
        if isinstance(unique_config, str):
            seen = set()
            result = []
            for item in data:
                key = _get_nested_value(item, unique_config)
                if key not in seen:
                    seen.add(key)
                    result.append(item)
            return result

        # True or dict - remove exact duplicates
        seen = []
        result = []
        for item in data:
            # Use repr for hashability
            key = repr(item)
            if key not in seen:
                seen.append(key)
                result.append(item)
        return result

    def _apply_flatten(self, data: Any, flatten_config: Any) -> List[Any]:
        """Apply flatten operation."""
        if not isinstance(data, list):
            return data

        depth = 1
        if isinstance(flatten_config, int):
            depth = flatten_config
        elif isinstance(flatten_config, dict):
            depth = flatten_config.get('depth', 1)

        def _flatten(lst: List, d: int) -> List:
            result = []
            for item in lst:
                if isinstance(item, list) and d > 0:
                    result.extend(_flatten(item, d - 1))
                else:
                    result.append(item)
            return result

        return _flatten(data, depth if depth >= 0 else 999)

    def _apply_pick(self, data: Any, fields: List[str]) -> Any:
        """Apply pick operation - select specific fields."""
        def pick_from_item(item: Any) -> Dict[str, Any]:
            if not isinstance(item, dict):
                return item
            return {f: _get_nested_value(item, f) for f in fields if _get_nested_value(item, f) is not None}

        if isinstance(data, list):
            return [pick_from_item(item) for item in data]
        return pick_from_item(data)

    def _apply_omit(self, data: Any, fields: List[str]) -> Any:
        """Apply omit operation - remove specific fields."""
        def omit_from_item(item: Any) -> Dict[str, Any]:
            if not isinstance(item, dict):
                return item
            return {k: v for k, v in item.items() if k not in fields}

        if isinstance(data, list):
            return [omit_from_item(item) for item in data]
        return omit_from_item(data)
