"""
HTML Structure Analysis Module
Analyze HTML DOM structure
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from core.analysis.html_analyzer import HTMLAnalyzer


@register_module('analysis.html.structure')
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
