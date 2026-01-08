"""
HTML Table Extraction Module
Extract tables from HTML
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets
from core.analysis.html_analyzer import HTMLAnalyzer


@register_module(
    module_id='analysis.html.extract_tables',
    version='1.0.0',
    category='analysis',
    tags=['analysis', 'html', 'tables', 'data'],
    label='Extract Tables',
    label_key='modules.analysis.html.extract_tables.label',
    description='Extract table data from HTML',
    description_key='modules.analysis.html.extract_tables.description',
    icon='Table',
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
            "tables": {"type": "array", "description": "Extracted table data"},
            "table_count": {"type": "number", "description": "Number of tables found"}
        }
    },
    timeout_ms=60000,
)
class HtmlExtractTables(BaseModule):
    """Extract tables from HTML"""

    module_name = "HTML Table Extraction"
    module_description = "Extract table data"

    def validate_params(self) -> None:
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
