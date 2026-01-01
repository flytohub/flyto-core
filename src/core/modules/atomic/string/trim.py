"""
String Trim Module
Remove whitespace from both ends of a string
"""
from typing import Any, Dict

from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets


@register_module(
    module_id='string.trim',
    version='1.0.0',
    category='string',
    tags=['string', 'trim', 'whitespace', 'text'],
    label='String Trim',
    label_key='modules.string.trim.label',
    description='Remove whitespace from both ends of a string',
    description_key='modules.string.trim.description',
    icon='Scissors',
    color='#6366F1',
    input_types=['string'],
    output_types=['string'],

    can_receive_from=['*'],
    can_connect_to=['data.*', 'array.*', 'object.*', 'string.*', 'file.*', 'database.*', 'api.*', 'ai.*', 'notification.*', 'flow.*'],    # Schema-driven params
    params_schema=compose(
        presets.INPUT_TEXT(required=True),
    )
)
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
