"""
HTML Pattern Detection Module
Find repeating data patterns in HTML
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from core.analysis.html_analyzer import HTMLAnalyzer


@register_module(
    module_id='analysis.html.find_patterns',
    version='1.0.0',
    category='analysis',
    tags=['analysis', 'html', 'patterns', 'data'],
    label='Find Patterns',
    label_key='modules.analysis.html.patterns.label',
    description='Find repeating data patterns in HTML',
    description_key='modules.analysis.html.patterns.description',
    icon='Search',
    color='#8B5CF6',
    input_types=['html', 'string'],
    output_types=['array'],
    params_schema={
        'html': {
            'type': 'string',
            'required': True,
            'label': 'HTML',
            'description': 'HTML content to find patterns in'
        }
    }
)
class HtmlFindPatterns(BaseModule):
    """Find data patterns in HTML"""

    module_name = "HTML Pattern Detection"
    module_description = "Find repeating patterns"

    def validate_params(self):
        if "html" not in self.params:
            raise ValueError("Missing required parameter: html")
        self.html = self.params["html"]

    async def execute(self) -> Any:
        analyzer = HTMLAnalyzer(self.html)
        patterns = analyzer.find_data_patterns()
        return {
            "patterns": patterns,
            "pattern_count": len(patterns)
        }
