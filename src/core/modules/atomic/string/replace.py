"""
String Replace Module
Replace occurrences of a substring in a string
"""
from typing import Any, Dict

from ...base import BaseModule
from ...registry import register_module


@register_module('string.replace')
class StringReplace(BaseModule):
    """
    Replace occurrences of a substring in a string

    Parameters:
        text (string): The string to process
        search (string): The substring to search for
        replace (string): The replacement string

    Returns:
        Modified string
    """

    module_name = "String Replace"
    module_description = "Replace text in a string"

    def validate_params(self):
        """Validate and extract parameters"""
        if "text" not in self.params:
            raise ValueError("Missing required parameter: text")
        if "search" not in self.params:
            raise ValueError("Missing required parameter: search")
        if "replace" not in self.params:
            raise ValueError("Missing required parameter: replace")

        self.text = self.params["text"]
        self.search = self.params["search"]
        self.replace_with = self.params["replace"]

    async def execute(self) -> Any:
        """
        Execute the module logic

        Returns:
            Modified string
        """
        try:
            result = str(self.text).replace(str(self.search), str(self.replace_with))

            return {
                "result": result,
                "original": self.text,
                "search": self.search,
                "replace": self.replace_with,
                "status": "success"
            }

        except Exception as e:
            raise RuntimeError(f"{self.module_name} execution failed: {str(e)}")
