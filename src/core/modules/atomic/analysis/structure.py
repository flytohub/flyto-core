"""
HTML Structure Analysis Module
Analyze HTML DOM structure
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from core.analysis.html_analyzer import HTMLAnalyzer


@register_module(
    module_id='analysis.html.structure',
    version='1.0.0',
    category='analysis',
    tags=['analysis', 'html', 'dom', 'structure'],
    label='HTML Structure',
    label_key='modules.analysis.html.structure.label',
    description='Analyze HTML DOM structure',
    description_key='modules.analysis.html.structure.description',
    icon='FileCode',
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
class HtmlStructureAnalysis(BaseModule):
    """Analyze HTML structure"""

    module_name = "HTML Structure"
    module_description = "Analyze HTML DOM structure"

    def validate_params(self):
        if "html" not in self.params:
            raise ValueError("Missing required parameter: html")
        self.html = self.params["html"]

    async def execute(self) -> Any:
        analyzer = HTMLAnalyzer(self.html)
        result = analyzer.analyze_structure()
        return result
