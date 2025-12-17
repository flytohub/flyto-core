"""
HTML Metadata Extraction Module
Extract metadata from HTML
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from core.analysis.html_analyzer import HTMLAnalyzer


@register_module('analysis.html.extract_metadata')
class HtmlExtractMetadata(BaseModule):
    """Extract metadata from HTML"""

    module_name = "HTML Metadata Extraction"
    module_description = "Extract meta information"

    def validate_params(self):
        if "html" not in self.params:
            raise ValueError("Missing required parameter: html")
        self.html = self.params["html"]

    async def execute(self) -> Any:
        analyzer = HTMLAnalyzer(self.html)
        structure = analyzer.analyze_structure()
        meta_info = structure.get("meta_info", {})
        return {
            "meta_info": meta_info
        }
