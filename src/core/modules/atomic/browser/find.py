# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
browser.find - Find elements in page

This is an atomic operation. Only responsible for finding and returning element ID list

HOW FAR THIS MODULE FOLLOWS REALITY

``count`` here is the honest kind of number and it is worth saying why, because
the shape that is NOT honest is one line away. The ids in ``element_ids`` are
UUIDs this process minted -- ``registry.register_many`` hands out one per handle
-- so counting the ids would be counting our own bookkeeping. It happens to
equal the number of handles today, but a count of things we generated is
`file.write`'s ``bytes_written`` in a new costume, and it would keep reporting
happily if the registry ever deduplicated, capped or dropped an entry.

So the rung rests on ``len(elements)``, the handles ``_query_selector_all``
built from nodes in the live document, measured before anything is registered:

    at least one element matched      OBSERVED -- those nodes were there
    nothing matched                   ACCEPTED

The empty case is the `database.query` empty-read. Zero matches reads
identically whether the page had none, the selector was wrong, or the content
had not rendered, so it claims only that the page answered the query. The two
counts are both carried, so a divergence between handles found and ids issued
is visible in the effect rather than hidden inside a single number.
"""
from typing import Any, Dict

from ....engine.outcome import ClaimBy, Outcome, envelope
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets
from ..element_registry import get_element_registry


def _find_outcome(*, selector: str, elements_matched: int, ids_issued: int) -> Dict[str, Any]:
    """The rung this query earned, from the handles rather than from the ids."""
    if elements_matched <= 0:
        return envelope(
            Outcome.ACCEPTED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'no_elements_matched',
                'selector': selector,
                'measured_by': None,
                'detail': (
                    'The page answered the query and no node matched. An empty '
                    'match set reads the same whether the content is absent, '
                    'the selector is wrong, or the page had not rendered yet, '
                    'so it is not an observation of the page.'
                ),
            }],
        )
    return envelope(
        Outcome.OBSERVED,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'elements_matched',
            'selector': selector,
            'count': elements_matched,
            'measured_by': (
                'len() over the ElementHandles _query_selector_all returned '
                'from the live DOM, before registration'
            ),
        }, {
            'kind': 'element_ids_issued',
            'count': ids_issued,
            'measured_by': 'len() over the UUIDs the element registry minted',
            'detail': (
                'Bookkeeping of this process, not a measurement of the page. '
                'Carried beside the match count so that the two diverging is '
                'visible rather than folded into one number.'
            ),
        }],
    )


@register_module(
    module_id='browser.find',
    version='1.0.0',
    category='browser',
    subcategory='browser',
    tags=['browser', 'find', 'element', 'selector', 'ssrf_protected'],
    label='Find Elements',
    label_key='modules.browser.find.label',
    description='Find elements in page and return element ID list. Run browser.snapshot first to find the correct selector from the real page DOM.',
    description_key='modules.browser.find.description',
    icon='Search',
    color='#8B5CF6',

    # Connection types
    input_types=['page'],
    output_types=['element', 'array'],


    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*', 'ai.*', 'llm.*', 'agent.*'],    # Phase 2: Execution settings
    timeout_ms=10000,  # Finding elements should complete within 10s
    retryable=True,  # Can retry if elements not ready
    max_retries=2,
    concurrent_safe=True,  # Stateless find operation

    # Phase 2: Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['browser.read', 'browser.write'],

    params_schema=compose(
        presets.SELECTOR(required=True, placeholder='div.result-item'),
        presets.EXTRACT_LIMIT(),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.browser.find.output.status.description'},
        'count': {'type': 'number', 'description': 'Number of items',
                'description_key': 'modules.browser.find.output.count.description'},
        'element_ids': {'type': 'array', 'description': 'The element ids',
                'description_key': 'modules.browser.find.output.element_ids.description'},
        'outcome': {
            'type': 'object',
            'description': (
                'How far this query was followed: "observed" when the selector '
                'resolved to at least one node in the live DOM, "accepted" '
                'when it matched nothing. Decided from the element handles, '
                'never from the ids this process minted.'
            ),
            'description_key': 'modules.browser.find.output.outcome.description'}
    },
    examples=[{
        'title': 'Find search results',
        'params': {
            'selector': 'div.tF2Cxc',
            'limit': 10
        }
    }],
    author='Flyto2 Team',
    license='MIT'
)
class BrowserFindModule(BaseModule):
    """
    Find elements in page

    Parameters:
        selector: CSS Selector
        limit: Limit count (optional)

    Return:
        element_ids: element ID list (list of UUID strings)

    Example:
        {
            "module": "core.browser.find",
            "params": {
                "selector": "div.tF2Cxc",
                "limit": 10
            },
            "output": "search_results"
        }
        # search_results = ['uuid-1', 'uuid-2', ...]
    """

    module_name = "Find Elements"
    module_description = "Find elements in page and return element ID list"
    required_permission = "browser.read"

    def validate_params(self) -> None:
        if 'selector' not in self.params:
            raise ValueError("Missing parameter: selector")

        self.selector = self.params['selector']
        self.limit = self.params.get('limit', None)

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser or not browser.page:
            raise RuntimeError("Browser not started")

        # Use browser driver to find elements (supports CSS and XPath)
        elements = await browser._query_selector_all(self.selector)

        # Limit count
        if self.limit is not None:
            elements = elements[:self.limit]

        # Measured here, from the handles, and before registration: the rung
        # must not rest on a count of ids this process generated.
        elements_matched = len(elements)

        # Get element registry from context (context-aware, not global singleton)
        registry = get_element_registry(self.context)

        # Register elements and return ID list
        element_ids = registry.register_many(elements)

        return {
            "status": "success",
            "count": len(element_ids),
            "element_ids": element_ids,
            "outcome": _find_outcome(
                selector=self.selector,
                elements_matched=elements_matched,
                ids_issued=len(element_ids),
            ),
        }
