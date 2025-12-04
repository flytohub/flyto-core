"""
Not Module - Logical negation operation

Inverts the boolean value of the input.
"""
from typing import Any, Dict

from ...base import BaseModule
from ...registry import register_module


@register_module('utility.not')
class Not(BaseModule):
    """
    Logical negation - inverts the boolean value of the input

    Parameters:
        value (any): The value to negate (will be converted to boolean)

    Returns:
        Negated boolean result
    """

    module_name = "Not"
    module_description = "Logical negation operation"

    def validate_params(self) -> None:
        """Validate and extract parameters"""
        if "value" not in self.params:
            raise ValueError("Missing required parameter: value")
        self.value = self.params["value"]

    async def execute(self) -> Dict[str, Any]:
        """
        Execute the logical negation

        Returns:
            Dictionary containing the negated result
        """
        # Convert to boolean and negate
        result = not bool(self.value)

        return {
            "result": result,
            "original": self.value,
            "original_as_bool": bool(self.value),
            "status": "success"
        }
