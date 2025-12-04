"""
String Uppercase Module
Convert a string to uppercase
"""
from typing import Any, Dict

from ...base import BaseModule
from ...registry import register_module


@register_module('string.uppercase')
class StringUppercase(BaseModule):
    """
    Convert a string to uppercase

    Parameters:
        text (string): The string to convert

    Returns:
        Uppercase string
    """

    module_name = "String Uppercase"
    module_description = "Convert string to uppercase"

    def validate_params(self):
        """Validate and extract parameters"""
        if "text" not in self.params:
            raise ValueError("Missing required parameter: text")
        self.text = self.params["text"]

    async def execute(self) -> Any:
        """
        Execute the module logic

        Returns:
            Uppercase string
        """
        try:
            result = str(self.text).upper()

            return {
                "result": result,
                "original": self.text,
                "status": "success"
            }

        except Exception as e:
            raise RuntimeError(f"{self.module_name} execution failed: {str(e)}")
