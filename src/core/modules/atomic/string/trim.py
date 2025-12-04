"""
String Trim Module
Remove whitespace from both ends of a string
"""
from typing import Any, Dict

from ...base import BaseModule
from ...registry import register_module


@register_module('string.trim')
class StringTrim(BaseModule):
    """
    Remove whitespace from both ends of a string

    Parameters:
        text (string): The string to trim

    Returns:
        Trimmed string
    """

    module_name = "String Trim"
    module_description = "Remove whitespace from string ends"

    def validate_params(self):
        """Validate and extract parameters"""
        if "text" not in self.params:
            raise ValueError("Missing required parameter: text")
        self.text = self.params["text"]

    async def execute(self) -> Any:
        """
        Execute the module logic

        Returns:
            Trimmed string
        """
        try:
            result = str(self.text).strip()

            return {
                "result": result,
                "original": self.text,
                "status": "success"
            }

        except Exception as e:
            raise RuntimeError(f"{self.module_name} execution failed: {str(e)}")
