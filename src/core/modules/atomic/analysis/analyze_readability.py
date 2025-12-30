"""
HTML Readability Analysis Module
Analyze content readability
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from core.analysis.html_analyzer import HTMLAnalyzer


@register_module(
    module_id='analysis.html.analyze_readability',
    version='1.0.0',
    category='analysis',
    tags=['analysis', 'html', 'readability', 'text'],
    label='HTML Readability',
    label_key='modules.analysis.html.readability.label',
    description='Analyze content readability',
    description_key='modules.analysis.html.readability.description',
    icon='BookOpen',
    color='#8B5CF6',
    input_types=['html', 'string'],
    output_types=['object'],
    params_schema={
        'html': {
            'type': 'string',
            'required': True,
            'label': 'HTML',
            'description': 'HTML content to analyze'
        }
    }
)
class HtmlAnalyzeReadability(BaseModule):
    """Analyze HTML readability"""

    module_name = "HTML Readability Analysis"
    module_description = "Analyze content readability"

    def validate_params(self):
        if "html" not in self.params:
            raise ValueError("Missing required parameter: html")
        self.html = self.params["html"]

    async def execute(self) -> Any:
        analyzer = HTMLAnalyzer(self.html)
        structure = analyzer.analyze_structure()
        readability = structure.get("readability", {})
        return {
            "word_count": readability.get("word_count", 0),
            "sentence_count": readability.get("sentence_count", 0),
            "readability": readability
        }
