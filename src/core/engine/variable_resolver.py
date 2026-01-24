"""
Variable Resolver - Resolve ${...} expressions in workflow parameters

Supports item-based execution variables per ITEM_PIPELINE_SPEC.md Section 4.3
"""
import re
import os
from typing import Any, Dict, List, Optional
from datetime import datetime


class VariableResolver:
    """
    Resolve variable expressions in workflow parameters

    Supports:
    - ${step_id.field} - Step outputs (first item's json field for backward compat)
    - ${step_id.data.field} - Same as above (explicit data access)
    - ${step_id.items} - All items from step (new: item-based)
    - ${step_id.items[0].field} - Specific item field (new: item-based)
    - ${step_id.items.length} - Item count (new: item-based)
    - ${$item.field} - Current item (new: items mode execution)
    - ${$index} - Current item index (new: items mode execution)
    - ${params.name} - Workflow parameters
    - ${env.VAR} - Environment variables
    - ${timestamp} - Built-in timestamp
    - ${workflow.id} - Workflow metadata
    """

    # Pattern to match ${...} expressions
    VAR_PATTERN = re.compile(r'\$\{([^}]+)\}')

    # Pattern to match array index access like items[0]
    INDEX_PATTERN = re.compile(r'^(\w+)\[(\d+)\]$')

    def __init__(self,
                 params: Dict[str, Any],
                 context: Dict[str, Any],
                 workflow_metadata: Optional[Dict[str, Any]] = None):
        """
        Initialize resolver

        Args:
            params: Workflow input parameters
            context: Execution context (step outputs)
            workflow_metadata: Workflow metadata (id, name, etc.)
        """
        self.params = params or {}
        self.context = context or {}
        self.workflow_metadata = workflow_metadata or {}

        # Built-in variables
        self.builtins = {
            'timestamp': datetime.now().isoformat(),
            'workflow': self.workflow_metadata
        }

    def resolve(self, value: Any) -> Any:
        """
        Resolve variables in a value

        Args:
            value: Value to resolve (can be string, dict, list, or primitive)

        Returns:
            Resolved value
        """
        if isinstance(value, str):
            return self._resolve_string(value)
        elif isinstance(value, dict):
            return self._resolve_dict(value)
        elif isinstance(value, list):
            return self._resolve_list(value)
        else:
            return value

    def _resolve_string(self, text: str) -> Any:
        """Resolve variables in a string"""
        # Check if entire string is a single variable reference
        match = self.VAR_PATTERN.fullmatch(text)
        if match:
            # Return the actual value (might not be a string)
            return self._get_variable_value(match.group(1))

        # Otherwise, replace all variable references with their string representations
        def replacer(match):
            value = self._get_variable_value(match.group(1))
            return str(value) if value is not None else match.group(0)

        return self.VAR_PATTERN.sub(replacer, text)

    def _resolve_dict(self, d: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve variables in a dictionary"""
        return {k: self.resolve(v) for k, v in d.items()}

    def _resolve_list(self, lst: list) -> list:
        """Resolve variables in a list"""
        return [self.resolve(item) for item in lst]

    def _get_variable_value(self, var_path: str) -> Any:
        """
        Get value for a variable path

        Args:
            var_path: Variable path (e.g., "step1.data", "params.keyword", "env.API_KEY")

        Returns:
            Variable value or None if not found

        Item-based syntax (ITEM_PIPELINE_SPEC.md Section 4.3):
            ${step.items} - All items array
            ${step.items[0].field} - Specific item field
            ${step.items.length} - Item count
            ${$item.field} - Current item (in items mode)
            ${$index} - Current item index
        """
        parts = var_path.split('.')

        if not parts:
            return None

        # Determine variable type from first part
        var_type = parts[0]

        # Built-in variables
        if var_type == 'timestamp':
            return self.builtins['timestamp']

        if var_type == 'workflow':
            if len(parts) == 1:
                return self.builtins['workflow']
            else:
                return self._get_nested_value(self.builtins['workflow'], parts[1:])

        # Environment variables
        if var_type == 'env':
            if len(parts) < 2:
                return None
            env_var = parts[1]
            return os.getenv(env_var)

        # Workflow parameters
        if var_type == 'params':
            if len(parts) < 2:
                return None
            param_name = parts[1]
            value = self.params.get(param_name)
            if len(parts) > 2:
                return self._get_nested_value(value, parts[2:])
            return value

        # Item-based execution variables (ITEM_PIPELINE_SPEC.md)
        # ${$item.field} - Current item being processed
        if var_type == '$item':
            current_item = self.params.get('$item', {})
            if len(parts) == 1:
                return current_item
            return self._get_nested_value(current_item, parts[1:])

        # ${$index} - Current item index
        if var_type == '$index':
            return self.params.get('$index', 0)

        # Step outputs (e.g., step_id.field or step_id.field.subfield)
        # First part is step_id
        step_id = parts[0]
        if step_id in self.context:
            step_output = self.context[step_id]
            if len(parts) == 1:
                return step_output
            else:
                # Handle items access
                return self._get_step_value(step_output, parts[1:])

        return None

    def _get_step_value(self, step_output: Any, path: List[str]) -> Any:
        """
        Get value from step output with items support.

        Handles:
            - data.field (backward compat: from first item)
            - items (all items array)
            - items[0].field (specific item)
            - items.length (item count)
        """
        if not path:
            return step_output

        first_key = path[0]

        # Check if it's items access
        if first_key == 'items':
            items = self._get_items_from_output(step_output)

            if len(path) == 1:
                return items

            second_key = path[1]

            # items.length
            if second_key == 'length':
                return len(items)

            # items[0] or items[0].field
            index_match = self.INDEX_PATTERN.match(second_key)
            if index_match:
                idx = int(index_match.group(2))
                if 0 <= idx < len(items):
                    item = items[idx]
                    if len(path) > 2:
                        return self._get_nested_value(item, path[2:])
                    return item
                return None

            # If second_key is a number string
            if second_key.isdigit():
                idx = int(second_key)
                if 0 <= idx < len(items):
                    item = items[idx]
                    if len(path) > 2:
                        return self._get_nested_value(item, path[2:])
                    return item
                return None

            return None

        # Check for items[0] in first key
        index_match = self.INDEX_PATTERN.match(first_key)
        if index_match:
            key_name = index_match.group(1)
            idx = int(index_match.group(2))

            if key_name == 'items':
                items = self._get_items_from_output(step_output)
                if 0 <= idx < len(items):
                    item = items[idx]
                    if len(path) > 1:
                        return self._get_nested_value(item, path[1:])
                    return item
                return None

        # Backward compat: data.field or direct field access
        return self._get_nested_value(step_output, path)

    def _get_items_from_output(self, step_output: Any) -> List[Any]:
        """
        Extract items array from step output.

        Handles both:
        - New format: {"ok": true, "data": {...}, "items": [...]}
        - Legacy format: {"ok": true, "data": {...}} -> wrap as single item
        """
        if not isinstance(step_output, dict):
            return [step_output] if step_output is not None else []

        # Check for explicit items array
        items = step_output.get('items')
        if items is not None:
            return items if isinstance(items, list) else [items]

        # Legacy format: wrap data as single item
        data = step_output.get('data')
        if data is not None:
            return [data] if not isinstance(data, list) else data

        # Just the output itself as single item
        return [step_output]

    def _get_nested_value(self, obj: Any, path: list) -> Any:
        """
        Get nested value from object using path

        Args:
            obj: Object to traverse
            path: List of keys/indices

        Returns:
            Nested value or None
        """
        current = obj

        for key in path:
            if current is None:
                return None

            # Handle dict access
            if isinstance(current, dict):
                current = current.get(key)
            # Handle list/array access by index
            elif isinstance(current, (list, tuple)):
                try:
                    # Try to parse key as integer index
                    index = int(key) if key.isdigit() else None
                    if index is not None and 0 <= index < len(current):
                        current = current[index]
                    else:
                        return None
                except (ValueError, IndexError):
                    return None
            # Handle object attribute access
            elif hasattr(current, key):
                current = getattr(current, key)
            else:
                return None

        return current

    def evaluate_condition(self, condition: str) -> bool:
        """
        Evaluate a condition expression

        Supports operators: ==, !=, >, <, >=, <=, contains, !contains

        Args:
            condition: Condition string (e.g., "${step1.count} > 0")

        Returns:
            Boolean result
        """
        # Resolve variables in condition first
        resolved = self._resolve_string(condition)

        # Simple operators
        operators = [
            ('==', lambda a, b: a == b),
            ('!=', lambda a, b: a != b),
            ('>=', lambda a, b: float(a) >= float(b)),
            ('<=', lambda a, b: float(a) <= float(b)),
            ('>', lambda a, b: float(a) > float(b)),
            ('<', lambda a, b: float(a) < float(b)),
            ('!contains', lambda a, b: str(b) not in str(a)),
            ('contains', lambda a, b: str(b) in str(a)),
        ]

        for op_str, op_func in operators:
            if op_str in resolved:
                parts = resolved.split(op_str, 1)
                if len(parts) == 2:
                    left = parts[0].strip()
                    right = parts[1].strip()
                    try:
                        return op_func(left, right)
                    except (ValueError, TypeError):
                        return False

        # If no operator found, treat as boolean
        if isinstance(resolved, bool):
            return resolved
        if isinstance(resolved, str):
            return resolved.lower() in ['true', 'yes', '1']

        return bool(resolved)
