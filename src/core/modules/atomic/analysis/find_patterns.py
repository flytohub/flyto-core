"""
HTML Pattern Detection Module
Find repeating data patterns in HTML
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets
from core.analysis.html_analyzer import HTMLAnalyzer


@register_module(
    module_id='analysis.html.find_patterns',
    version='1.0.0',
    category='analysis',
    tags=['analysis', 'html', 'patterns', 'data'],
    label='Find Patterns',
    label_key='modules.analysis.html.find_patterns.label',
    description='Find repeating data patterns in HTML',
    description_key='modules.analysis.html.find_patterns.description',
    icon='Search',
    color='#8B5CF6',
    input_types=['html', 'string'],
    output_types=['array'],

    can_receive_from=['browser.*', 'element.*', 'page.*', 'file.*', 'data.*', 'api.*', 'flow.*', 'start'],
    can_connect_to=['data.*', 'array.*', 'object.*', 'string.*', 'file.*', 'database.*', 'ai.*', 'notification.*', 'flow.*'],
    params_schema=compose(
        presets.HTML_CONTENT(),
    ),
    output_schema={
        "type": "object",
        "properties": {
            "patterns": {"type": "array", "description": "Detected data patterns"},
            "pattern_count": {"type": "number", "description": "Number of patterns found"}
        }
    },
    timeout_ms=60000,
)
class HtmlFindPatterns(BaseModule):
    """Find data patterns in HTML"""

    module_name = "HTML Pattern Detection"
    module_description = "Find repeating patterns"

    def validate_params(self) -> None:
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
