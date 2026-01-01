"""
HTML Form Extraction Module
Extract forms from HTML
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets
from core.analysis.html_analyzer import HTMLAnalyzer


@register_module(
    module_id='analysis.html.extract_forms',
    version='1.0.0',
    category='analysis',
    tags=['analysis', 'html', 'forms', 'input'],
    label='Extract Forms',
    label_key='modules.analysis.html.forms.label',
    description='Extract form data from HTML',
    description_key='modules.analysis.html.forms.description',
    icon='FileInput',
    color='#8B5CF6',
    input_types=['html', 'string'],
    output_types=['array'],

    can_receive_from=['browser.*', 'element.*', 'page.*', 'file.*', 'data.*', 'api.*', 'flow.*', 'start'],
    can_connect_to=['data.*', 'array.*', 'object.*', 'string.*', 'file.*', 'database.*', 'ai.*', 'notification.*', 'flow.*'],    params_schema=compose(
        presets.HTML_CONTENT(),
    ),
)
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
