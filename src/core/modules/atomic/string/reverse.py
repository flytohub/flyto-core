"""
Reverse Module - Reverses the input text string
"""

from core.modules.base import BaseModule
from core.modules.registry import register_module
from typing import Any, Dict


@register_module('text.reverse')
class Reverse(BaseModule):
    """
    Reverses the input text string

    Parameters:
        text (str): The input text string to reverse

    Returns:
        Dict[str, Any] with keys: result (reversed string)
    """

    module_name = "Reverse"
    module_description = "Reverses the input text string"

    def validate_params(self):
        """Validate and extract parameters"""
        if "text" not in self.params:
            raise ValueError("Missing required parameter: text")
        self.text = self.params["text"]

    async def execute(self) -> Any:
        """
        Execute the module logic to reverse a text string.

        Returns:
            Dict with reversed text string
        """
        try:
            if not isinstance(self.text, str):
                raise ValueError("Invalid input: text must be a string")

            reversed_text = self.text[::-1]

            return {
                "result": reversed_text,
                "original": self.text,
                "length": len(self.text)
            }

        except Exception as e:
            raise RuntimeError(f"text.reverse execution failed: {str(e)}")
