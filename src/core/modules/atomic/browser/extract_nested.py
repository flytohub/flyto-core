# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Extract Nested Module — Extract tree/nested data structures

Extracts hierarchical data: comment threads, nested replies,
folder trees, category hierarchies, threaded discussions.

Define parent selector + children selector → returns tree structure.

HOW FAR THIS MODULE FOLLOWS REALITY

Two numbers come back from the page and they answer different questions.
``count`` is how many ROOT items survived the "is this nested inside another
match" filter; ``total_nodes`` is the JS ``count`` variable, incremented once
per node ``extractNode`` actually walked, at every depth.

The rung rests on ``total_nodes``, not on ``count``. A tree whose roots were all
filtered out is not the same page as a tree with nothing in it, and a limit that
stops the walk part-way leaves ``count`` describing a subset of what was seen.
``total_nodes`` is the count of nodes this run touched in the live DOM, so it is
the number that changes when the page does:

    at least one node was walked      OBSERVED -- those nodes were there
    nothing was walked                ACCEPTED

The empty case is the `database.query` empty-read: zero nodes reads identically
whether the page has no such structure, ``root_selector`` is wrong, or the
content had not rendered. Both counts ride in the effect, because a run with 40
nodes and 1 root and a run with 40 nodes and 40 roots are different results and
one integer cannot say which happened.

WHAT IS NOT CLAIMED: that the tree's SHAPE is right. ``children`` is assembled
by two different strategies -- an explicit ``children_selector`` container, or a
``:scope > * > root`` guess when none is given -- and neither is checked against
anything. The nodes were seen; that they were assembled into the correct
hierarchy is an inference of the page script's, and OBSERVED is defined as "we
saw the world change. Not that the right thing changed".
"""
import logging
from typing import Any, Dict

from ....engine.outcome import ClaimBy, Outcome, envelope
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field

logger = logging.getLogger(__name__)


def _nested_outcome(*, root_selector: str, roots: int, total_nodes: int) -> Dict[str, Any]:
    """The rung this walk earned, decided by nodes visited rather than by roots."""
    if total_nodes <= 0:
        return envelope(
            Outcome.ACCEPTED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'no_nodes_walked',
                'root_selector': root_selector,
                'measured_by': None,
                'detail': (
                    'The page answered and no node matched the root selector. '
                    'An empty walk reads the same whether the structure is '
                    'absent, the selector is wrong, or the content had not '
                    'rendered, so it is not an observation of the page.'
                ),
            }],
        )
    return envelope(
        Outcome.OBSERVED,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'nodes_walked',
            'root_selector': root_selector,
            'count': total_nodes,
            'measured_by': (
                'the in-page counter incremented once per node extractNode '
                'walked over document.querySelectorAll(root_selector)'
            ),
        }, {
            'kind': 'root_items_returned',
            'count': roots,
            'measured_by': 'len() over the nodes that were not inside another match',
            'detail': (
                'A subset of the nodes walked. The hierarchy they were '
                'assembled into is this page script\'s inference and is not '
                'checked against anything, so the shape of the tree is not '
                'part of what was observed.'
            ),
        }],
    )

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
    can_connect_to=['browser.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*', 'ai.*', 'llm.*', 'agent.*'],
    params_schema=compose(
        field('root_selector', type='string', label='Item selector',
              description='CSS selector for each item (e.g., ".comment", "li.thread").',
              required=True, placeholder='.comment',
              ui={"widget": "element_picker", "element_types": ["button", "link", "input"], "value_key": "selector"},
              group='basic'),
        field('children_selector', type='string', label='Children container',
              description='CSS selector for the container holding child items within each item. Leave empty for auto-detect.',
              required=False, default='', placeholder='.replies, .children',
              ui={"widget": "element_picker", "element_types": ["button", "link", "input"], "value_key": "selector"},
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
        'outcome':     {'type': 'object',
                        'description': (
                            'How far this read was followed: "observed" when at '
                            'least one node was walked in the live DOM, '
                            '"accepted" when none was. The shape of the tree is '
                            'not part of the claim.'
                        )},
    },
    examples=[
        {'name': 'Extract comment thread', 'params': {
            'root_selector': '.comment',
            'children_selector': '.replies',
            'fields': {'author': {'selector': '.author'}, 'text': {'selector': '.body'}, 'date': {'selector': 'time', 'type': 'attribute', 'attribute': 'datetime'}},
        }},
        {'name': 'Auto-extract nested list', 'params': {'root_selector': 'li.item'}},
    ],
    author='Flyto2 Team', license='MIT', timeout_ms=30000,
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

        return {
            "status": "success",
            **result,
            "outcome": _nested_outcome(
                root_selector=self.root_selector,
                roots=result.get('count') or 0,
                total_nodes=result.get('total_nodes') or 0,
            ),
        }
