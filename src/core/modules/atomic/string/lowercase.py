"""
String Lowercase Module
Convert a string to lowercase
"""

from src.core.modules.base import BaseModule
from src.core.modules.registry import register_module
from typing import Any, Dict


@register_module('string.lowercase')
class StringLowercase(BaseModule):
    """
    Convert a string to lowercase

    Parameters:
        text (string): The string to convert

    Returns:
        Lowercase string
    """

    module_name = "String Lowercase"
    module_description = "Convert string to lowercase"

    def validate_params(self):
        """Validate and extract parameters"""
        if "text" not in self.params:
            raise ValueError("Missing required parameter: text")
        self.text = self.params["text"]

    async def execute(self) -> Any:
        """
        Execute the module logic

        Returns:
            Lowercase string
        """
        try:
            result = str(self.text).lower()

            return {
                "result": result,
                "original": self.text,
                "status": "success"
            }

        except Exception as e:
            raise RuntimeError(f"{self.module_name} execution failed: {str(e)}")
