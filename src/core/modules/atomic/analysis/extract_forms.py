"""
HTML Form Extraction Module
Extract forms from HTML
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from core.analysis.html_analyzer import HTMLAnalyzer


@register_module('analysis.html.extract_forms')
class HtmlExtractForms(BaseModule):
    """Extract forms from HTML"""

    module_name = "HTML Form Extraction"
    module_description = "Extract form data"

    def validate_params(self):
        if "html" not in self.params:
            raise ValueError("Missing required parameter: html")
        self.html = self.params["html"]

    async def execute(self) -> Any:
        analyzer = HTMLAnalyzer(self.html)
        structure = analyzer.analyze_structure()
        forms = structure.get("forms", [])
        return {
            "forms": forms,
            "form_count": len(forms)
        }
