"""
String Uppercase Module
Convert a string to uppercase
"""

from src.core.modules.base import BaseModule
from src.core.modules.registry import register_module
from typing import Any, Dict


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
