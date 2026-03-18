# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Extract Nested Module — Extract tree/nested data structures

Extracts hierarchical data: comment threads, nested replies,
folder trees, category hierarchies, threaded discussions.

Define parent selector + children selector → returns tree structure.
"""
import logging
from typing import Any
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field

logger = logging.getLogger(__name__)

_NESTED_JS = r"""
(options) => {
    const rootSelector = options.root_selector;
    const childrenSelector = options.children_selector || '';
    const fields = options.fields || {};
    const maxDepth = options.max_depth || 10;
    const limit = options.limit || 0;
    let count = 0;

    function extractFields(el) {
        const item = {};
        if (Object.keys(fields).length === 0) {
            // Auto-extract: first link, text content
            const link = el.querySelector('a[href]');
            if (link) {
                item.title = link.textContent.trim();
                item.url = link.href;
            }
            // Get direct text (exclude children containers)
            const clone = el.cloneNode(true);
            if (childrenSelector) {
                clone.querySelectorAll(childrenSelector).forEach(c => c.remove());
            }
            item.text = clone.textContent.trim().substring(0, 1000);
        } else {
            for (const [name, config] of Object.entries(fields)) {
                const sel = config.selector || config;
                const type = config.type || 'text';
                const attr = config.attribute || '';
                const fieldEl = typeof sel === 'string' ? el.querySelector(sel) : null;
                if (!fieldEl) { item[name] = ''; continue; }
                if (type === 'attribute' && attr) item[name] = fieldEl.getAttribute(attr) || '';
                else if (type === 'html') item[name] = fieldEl.innerHTML;
                else item[name] = fieldEl.textContent.trim();
            }
        }
        return item;
    }

    function extractNode(el, depth) {
        if (depth > maxDepth) return null;
        if (limit > 0 && count >= limit) return null;
        count++;

        const node = extractFields(el);
        node._depth = depth;

        // Find children
        if (childrenSelector) {
            // Direct children matching the selector WITHIN this element
            const childContainer = el.querySelector(childrenSelector);
            if (childContainer) {
                const childItems = childContainer.querySelectorAll(':scope > ' + rootSelector);
                if (childItems.length > 0) {
                    node.children = [];
                    for (const child of childItems) {
                        const childNode = extractNode(child, depth + 1);
                        if (childNode) node.children.push(childNode);
                    }
                }
            }
        } else {
            // Auto-detect: look for same-selector descendants at increasing depth
            const nested = el.querySelectorAll(':scope > * > ' + rootSelector + ', :scope > ' + rootSelector);
            if (nested.length > 0) {
                node.children = [];
                for (const child of nested) {
                    // Avoid extracting self
                    if (child === el) continue;
                    const childNode = extractNode(child, depth + 1);
                    if (childNode) node.children.push(childNode);
                }
            }
        }

        return node;
    }

    // Find root items (top-level, not nested inside another match)
    const allMatches = document.querySelectorAll(rootSelector);
    const roots = [];

    for (const el of allMatches) {
        // Check if this element is nested inside another match
        let isNested = false;
        let parent = el.parentElement;
        while (parent) {
            if (parent.matches && parent.matches(rootSelector)) {
                isNested = true;
                break;
            }
            parent = parent.parentElement;
        }
        if (!isNested) {
            const node = extractNode(el, 0);
            if (node) roots.push(node);
        }
        if (limit > 0 && count >= limit) break;
    }

    return {
        items: roots,
        count: roots.length,
        total_nodes: count,
    };
}
"""


@register_module(
    module_id='browser.extract_nested',
    version='1.0.0',
    category='browser',
    tags=['browser', 'extract', 'nested', 'tree', 'hierarchy', 'comments'],
    label='Extract Nested',
    label_key='modules.browser.extract_nested.label',
    description='Extract tree/nested data (comments, threads, folders). Returns hierarchical structure with children.',
    description_key='modules.browser.extract_nested.description',
    icon='GitBranch',
    color='#A855F7',
    input_types=['page'],
    output_types=['json', 'array'],
    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*'],
    params_schema=compose(
        field('root_selector', type='string', label='Item selector',
              description='CSS selector for each item (e.g., ".comment", "li.thread").',
              required=True, placeholder='.comment',
              group='basic'),
        field('children_selector', type='string', label='Children container',
              description='CSS selector for the container holding child items within each item. Leave empty for auto-detect.',
              required=False, default='', placeholder='.replies, .children',
              group='basic'),
        field('fields', type='object', label='Field mapping',
              description='Custom field extraction: {"name": {"selector": "CSS", "type": "text|html|attribute", "attribute": "href"}}. Leave empty for auto-extract.',
              required=False, default={},
              group='basic'),
        field('max_depth', type='number', label='Max depth',
              description='Maximum nesting depth to extract.',
              default=10, min=1, max=50,
              group='advanced'),
        field('limit', type='number', label='Max items',
              description='Total items to extract (all depths combined). 0 = no limit.',
              default=0, min=0, max=5000,
              group='advanced'),
    ),
    output_schema={
        'items':       {'type': 'array',  'description': 'Tree structure [{...fields, children: [{...}]}]'},
        'count':       {'type': 'number', 'description': 'Number of root items'},
        'total_nodes': {'type': 'number', 'description': 'Total nodes across all depths'},
    },
    examples=[
        {'name': 'Extract comment thread', 'params': {
            'root_selector': '.comment',
            'children_selector': '.replies',
            'fields': {'author': {'selector': '.author'}, 'text': {'selector': '.body'}, 'date': {'selector': 'time', 'type': 'attribute', 'attribute': 'datetime'}},
        }},
        {'name': 'Auto-extract nested list', 'params': {'root_selector': 'li.item'}},
    ],
    author='Flyto Team', license='MIT', timeout_ms=30000,
    required_permissions=["browser.read"],
)
class BrowserExtractNestedModule(BaseModule):
    module_name = "Extract Nested"
    required_permission = "browser.read"

    def validate_params(self) -> None:
        if not self.params.get('root_selector'):
            raise ValueError("root_selector is required")
        self.root_selector = self.params['root_selector']
        self.children_selector = self.params.get('children_selector', '')
        self.fields = self.params.get('fields', {})
        self.max_depth = self.params.get('max_depth', 10)
        self.limit = self.params.get('limit', 0)

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        result = await browser.page.evaluate(_NESTED_JS, {
            'root_selector': self.root_selector,
            'children_selector': self.children_selector,
            'fields': self.fields,
            'max_depth': self.max_depth,
            'limit': self.limit,
        })

        return {"status": "success", **result}
