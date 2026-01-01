"""
String Split Module
Split a string into an array using a delimiter
"""
from typing import Any, Dict

from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets


@register_module(
    module_id='string.split',
    version='1.0.0',
    category='string',
    tags=['string', 'split', 'array'],
    label='Split String',
    description='Split a string into an array using a delimiter',
    icon='Scissors',
    color='#3B82F6',

    # Connection types
    input_types=['string'],
    output_types=['array'],


    can_receive_from=['*'],
    can_connect_to=['data.*', 'array.*', 'object.*', 'string.*', 'file.*', 'database.*', 'api.*', 'ai.*', 'notification.*', 'flow.*'],    # Schema-driven params
    params_schema=compose(
        presets.INPUT_TEXT(required=True),
        presets.STRING_DELIMITER(default=' '),
    ),
)
class StringSplit(BaseModule):
    """
    Split a string into an array using a delimiter

    Parameters:
        text (string): The string to split
        delimiter (string): The delimiter to split on (default: space)

    Returns:
        Array of string parts
    """

    module_name = "String Split"
    module_description = "Split a string into an array"

    def validate_params(self):
        """Validate and extract parameters"""
        if "text" not in self.params:
            raise ValueError("Missing required parameter: text")
        self.text = self.params["text"]
        self.delimiter = self.params.get("delimiter", " ")

    async def execute(self) -> Any:
        """
        Execute the module logic

        Returns:
            Array of string parts
        """
        try:
            parts = str(self.text).split(self.delimiter)

            return {
                "parts": parts,
                "result": parts,
                "length": len(parts),
                "original": self.text,
                "delimiter": self.delimiter,
                "status": "success"
            }

        except Exception as e:
            raise RuntimeError(f"{self.module_name} execution failed: {str(e)}")
