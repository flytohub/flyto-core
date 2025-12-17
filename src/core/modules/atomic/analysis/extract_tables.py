"""
HTML Table Extraction Module
Extract tables from HTML
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from core.analysis.html_analyzer import HTMLAnalyzer


@register_module('analysis.html.extract_tables')
class HtmlExtractTables(BaseModule):
    """Extract tables from HTML"""

    module_name = "HTML Table Extraction"
    module_description = "Extract table data"

    def validate_params(self):
        if "html" not in self.params:
            raise ValueError("Missing required parameter: html")
        self.html = self.params["html"]

    async def execute(self) -> Any:
        analyzer = HTMLAnalyzer(self.html)
        structure = analyzer.analyze_structure()
        tables = structure.get("data_tables", [])
        return {
            "tables": tables,
            "table_count": len(tables)
        }
