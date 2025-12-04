"""
Variable Resolver - Resolve ${...} expressions in workflow parameters
"""
import re
import os
from typing import Any, Dict, Optional
from datetime import datetime


class VariableResolver:
    """
    Resolve variable expressions in workflow parameters

    Supports:
    - ${step_id.field} - Step outputs
    - ${params.name} - Workflow parameters
    - ${env.VAR} - Environment variables
    - ${timestamp} - Built-in timestamp
    - ${workflow.id} - Workflow metadata
    """

    # Pattern to match ${...} expressions
    VAR_PATTERN = re.compile(r'\$\{([^}]+)\}')

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

        # Step outputs (e.g., step_id.field or step_id.field.subfield)
        # First part is step_id
        step_id = parts[0]
        if step_id in self.context:
            step_output = self.context[step_id]
            if len(parts) == 1:
                return step_output
            else:
                return self._get_nested_value(step_output, parts[1:])

        return None

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
