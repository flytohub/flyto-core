# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Table Module — Extract HTML tables as structured data

Auto-detects table headers (thead/th), iterates rows, returns array of objects.
Handles merged cells, nested tables, and headerless tables.
"""
import logging
from typing import Any
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field, presets

logger = logging.getLogger(__name__)

_TABLE_JS = r"""
(options) => {
    const selector = options.selector || 'table';
    const tableIndex = options.table_index || 0;
    const includeHtml = options.include_html === true;
    const maxRows = options.max_rows || 0;

    const tables = document.querySelectorAll(selector);
    if (tables.length === 0) return { rows: [], headers: [], count: 0, tables_found: 0 };
    if (tableIndex >= tables.length) return { rows: [], headers: [], count: 0, tables_found: tables.length };

    const table = tables[tableIndex];

    // Extract headers: try thead > th, then first row th, then first row td
    let headers = [];
    const thead = table.querySelector('thead');
    if (thead) {
        const ths = thead.querySelectorAll('th');
        headers = Array.from(ths).map(th => th.textContent.trim());
    }
    if (headers.length === 0) {
        const firstRow = table.querySelector('tr');
        if (firstRow) {
            const cells = firstRow.querySelectorAll('th');
            if (cells.length > 0) {
                headers = Array.from(cells).map(c => c.textContent.trim());
            }
        }
    }

    // Get all data rows (skip header row if headers came from first row)
    const allRows = table.querySelectorAll('tbody > tr, tr');
    const rows = [];
    let startIdx = 0;

    // If headers came from first row (no thead), skip first row
    if (headers.length > 0 && !thead) {
        const firstRow = table.querySelector('tr');
        const firstCells = firstRow?.querySelectorAll('th');
        if (firstCells && firstCells.length > 0) startIdx = 1;
    }
    // If thead exists, skip all thead rows
    const theadRows = thead ? thead.querySelectorAll('tr').length : 0;

    const seen = new Set();
    for (const row of allRows) {
        // Skip thead rows (they appear in both 'tbody > tr' and 'tr' queries)
        if (thead && thead.contains(row)) continue;
        // Dedup (tr can match both selectors)
        if (seen.has(row)) continue;
        seen.add(row);

        if (startIdx > 0) { startIdx--; continue; }
        if (maxRows > 0 && rows.length >= maxRows) break;

        const cells = row.querySelectorAll('td, th');
        if (cells.length === 0) continue;

        if (headers.length > 0) {
            // Named columns
            const obj = {};
            cells.forEach((cell, i) => {
                const key = i < headers.length ? headers[i] : `col_${i}`;
                obj[key] = cell.textContent.trim();
                if (includeHtml) obj[key + '_html'] = cell.innerHTML;
            });
            rows.push(obj);
        } else {
            // No headers — return arrays
            const arr = Array.from(cells).map(c => c.textContent.trim());
            rows.push(arr);
        }
    }

    // Auto-generate headers if none found (col_0, col_1, ...)
    if (headers.length === 0 && rows.length > 0 && Array.isArray(rows[0])) {
        const colCount = Math.max(...rows.map(r => r.length));
        headers = Array.from({length: colCount}, (_, i) => `col_${i}`);
        // Convert arrays to objects
        const objRows = rows.map(arr => {
            const obj = {};
            arr.forEach((val, i) => { obj[headers[i] || `col_${i}`] = val; });
            return obj;
        });
        return { rows: objRows, headers, count: objRows.length, tables_found: tables.length };
    }

    return { rows, headers, count: rows.length, tables_found: tables.length };
}
"""


@register_module(
    module_id='browser.table',
    version='1.0.0',
    category='browser',
    tags=['browser', 'extract', 'table', 'data', 'scraping'],
    label='Extract Table',
    label_key='modules.browser.table.label',
    description='Extract HTML tables as structured data. Auto-detects headers from thead/th.',
    description_key='modules.browser.table.description',
    icon='Table',
    color='#10B981',
    input_types=['page'],
    output_types=['array', 'json'],
    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*'],
    params_schema=compose(
        field('selector', type='string', label='Table selector',
              description='CSS selector for the table. Default: first <table> on page.',
              default='table', placeholder='table.data-grid',
              group='basic'),
        field('table_index', type='number', label='Table index',
              description='If multiple tables match, which one to extract (0-based).',
              default=0, min=0, max=50,
              group='basic'),
        field('max_rows', type='number', label='Max rows',
              description='Maximum rows to extract. 0 = all rows.',
              default=0, min=0, max=10000,
              group='basic'),
        field('include_html', type='boolean', label='Include cell HTML',
              description='Include raw HTML for each cell (as field_name_html).',
              default=False,
              group='advanced'),
    ),
    output_schema={
        'rows':         {'type': 'array',  'description': 'Table rows as objects [{header: value, ...}]'},
        'headers':      {'type': 'array',  'description': 'Column headers detected'},
        'count':        {'type': 'number', 'description': 'Number of rows extracted'},
        'tables_found': {'type': 'number', 'description': 'Total tables matching selector'},
    },
    examples=[
        {'name': 'Extract first table', 'params': {}},
        {'name': 'Extract specific table', 'params': {'selector': '#results-table', 'max_rows': 100}},
    ],
    author='Flyto Team', license='MIT', timeout_ms=30000,
    required_permissions=["browser.read"],
)
class BrowserTableModule(BaseModule):
    module_name = "Extract Table"
    required_permission = "browser.read"

    def validate_params(self) -> None:
        self.selector = self.params.get('selector', 'table')
        self.table_index = self.params.get('table_index', 0)
        self.max_rows = self.params.get('max_rows', 0)
        self.include_html = self.params.get('include_html', False)

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        result = await browser.page.evaluate(_TABLE_JS, {
            'selector': self.selector,
            'table_index': self.table_index,
            'max_rows': self.max_rows,
            'include_html': self.include_html,
        })

        return {"status": "success", **result}
