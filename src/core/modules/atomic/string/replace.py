"""
String Replace Module
Replace occurrences of a substring in a string
"""
from typing import Any, Dict

from ...base import BaseModule
from ...registry import register_module


@register_module(
    module_id='string.replace',
    version='1.0.0',
    category='string',
    tags=['string', 'replace', 'text'],
    label='String Replace',
    label_key='modules.string.replace.label',
    description='Replace occurrences of a substring in a string',
    description_key='modules.string.replace.description',
    icon='Replace',
    color='#6366F1',
    input_types=['string'],
    output_types=['string'],
    params_schema={
        'text': {
            'type': 'string',
            'required': True,
            'label': 'Text',
            'description': 'The string to process'
        },
        'search': {
            'type': 'string',
            'required': True,
            'label': 'Search',
            'description': 'The substring to search for'
        },
        'replace': {
            'type': 'string',
            'required': True,
            'label': 'Replace With',
            'description': 'The replacement string'
        }
    }
)
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
