"""
HTML Metadata Extraction Module
Extract metadata from HTML
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets
from core.analysis.html_analyzer import HTMLAnalyzer


@register_module(
    module_id='analysis.html.extract_metadata',
    version='1.0.0',
    category='analysis',
    tags=['analysis', 'html', 'metadata', 'seo'],
    label='Extract Metadata',
    label_key='modules.analysis.html.extract_metadata.label',
    description='Extract metadata from HTML',
    description_key='modules.analysis.html.extract_metadata.description',
    icon='Tag',
    color='#8B5CF6',
    input_types=['html', 'string'],
    output_types=['object'],

    can_receive_from=['browser.*', 'element.*', 'page.*', 'file.*', 'data.*', 'api.*', 'flow.*', 'start'],
    can_connect_to=['data.*', 'array.*', 'object.*', 'string.*', 'file.*', 'database.*', 'ai.*', 'notification.*', 'flow.*'],
    params_schema=compose(
        presets.HTML_CONTENT(),
    ),
    output_schema={
        "type": "object",
        "properties": {
            "meta_info": {"type": "object", "description": "Extracted metadata information"}
        }
    },
    timeout_ms=60000,
)
class HtmlExtractMetadata(BaseModule):
    """Extract metadata from HTML"""

    module_name = "HTML Metadata Extraction"
    module_description = "Extract meta information"

    def validate_params(self) -> None:
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
