"""
Not Module - Logical negation operation

Inverts the boolean value of the input.
"""
from typing import Any, Dict

from ...base import BaseModule
from ...registry import register_module


@register_module(
    module_id='utility.not',
    version='1.0.0',
    category='utility',
    tags=['utility', 'logic', 'not', 'boolean'],
    label='Not',
    description='Logical negation operation',
    icon='CircleSlash',
    color='#EF4444',

    # Connection types
    input_types=['boolean'],
    output_types=['boolean'],

    can_receive_from=['*'],
    can_connect_to=['data.*', 'string.*', 'file.*', 'api.*', 'notification.*', 'flow.*', 'utility.*'],)
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
