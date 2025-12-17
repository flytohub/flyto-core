"""
HTML Pattern Detection Module
Find repeating data patterns in HTML
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from core.analysis.html_analyzer import HTMLAnalyzer


@register_module('analysis.html.find_patterns')
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
