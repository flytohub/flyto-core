# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Automation Modules

Provides browser automation capabilities using Playwright.
All modules use i18n keys for multi-language support.

HOW FAR THIS MODULE FOLLOWS REALITY

This module reads; it does not change anything. What it is entitled to claim is
therefore not about an effect landing but about elements having been there, and
the one line that measures that is

    elements = await browser._query_selector_all(self.selector)

which returns Playwright ``ElementHandle``s for nodes that exist in the live
DOM right now. ``len(elements)`` is not a restatement of any parameter: hand
this module the same selector against a page that has none and the number is 0.

    at least one element matched      OBSERVED -- those nodes were there
    nothing matched                   ACCEPTED

The empty case is the `database.query` empty-read, exactly: zero matches reads
identically whether the page genuinely had none, the selector was misspelt, the
content had not rendered yet, or the node lives in a frame this query never
entered. A value unchanged by whether the thing happened is not evidence of it,
so an empty match set claims only that the page answered the query.

TWO COUNTS, NOT ONE, and they are different questions. ``elements_matched`` is
how many nodes the selector resolved to; ``values_returned`` is how many usable
values came out of them. The default text mode drops elements whose text is
blank, and the multi-field mode writes ``None`` for a sub-selector that missed,
so a run with 20 matches and 0 values is an ordinary outcome. The rung rests on
the first number, because that is the one the DOM decided; the second rides in
the effect so a consumer can see the extraction came up dry without the rung
pretending the page was empty.

WHERE THE ENVELOPE LIVES, and why it is not inside ``data``. This module's
``data`` is a LIST -- of strings in the attribute and text modes, of dicts in
the field mode -- so there is no mapping inside it for an envelope to live in.
`_apply_outcome_contract` (`step_executor/executor.py`) recognises that shape
and returns without stamping, so this module carries no engine default either;
the envelope here is the only outcome the step will ever have. It survives as a
top-level sibling of ``data`` for one specific reason: this result has no ``ok``
key, so `_execute_single_mode` never calls `wrap_legacy_result` and the dict is
passed through whole, while `_outcome_payloads` appends the top-level dict as a
payload in its own right. Adding an ``ok`` key to this result would send it
through `to_legacy_dict`, which keeps ``data`` and discards every sibling, and
would silently delete this envelope. That dependency is pinned as a test.
"""
from typing import Any, Dict, List

from ....engine.outcome import ClaimBy, Outcome, envelope
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets


def _extract_outcome(
    *,
    selector: str,
    mode: str,
    elements_matched: int,
    values_returned: int,
) -> Dict[str, Any]:
    """The rung this extraction earned, and the count that earned it.

    ``elements_matched`` is the whole decision. It is ``len()`` over the handles
    the driver built from nodes in the live document, so it cannot be produced
    by a page that has none.
    """
    if elements_matched <= 0:
        return envelope(
            Outcome.ACCEPTED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'no_elements_matched',
                'mode': mode,
                'selector': selector,
                'measured_by': None,
                'detail': (
                    'The page answered the query and no node matched. That is '
                    'not an observation of the page: an empty match set reads '
                    'the same whether the content is absent, the selector is '
                    'wrong, the page had not finished rendering, or the node '
                    'is inside a frame this query never entered.'
                ),
            }],
        )

    effects: List[Dict[str, Any]] = [{
        'kind': 'elements_matched',
        'mode': mode,
        'selector': selector,
        'count': elements_matched,
        'measured_by': (
            'len() over the ElementHandles _query_selector_all returned from '
            'the live DOM'
        ),
    }, {
        'kind': 'values_returned',
        'count': values_returned,
        'measured_by': 'len() over the values read out of those elements',
        'detail': (
            'How many usable values came out, which is not how many nodes '
            'matched. Text mode drops blank elements and field mode writes '
            'null for a sub-selector that missed, so this can be lower -- '
            'including zero -- with the match itself perfectly real.'
        ),
    }]
    return envelope(Outcome.OBSERVED, claim_by=ClaimBy.NONE, effects=effects)


def _values_present(results: List[Any]) -> int:
    """How many entries carry something. Counts a dict entry with any non-null field."""
    present = 0
    for value in results:
        if isinstance(value, dict):
            if any(field_value is not None for field_value in value.values()):
                present += 1
        elif value is not None:
            present += 1
    return present


@register_module(
    module_id='browser.extract',
    version='1.0.0',
    category='browser',
    tags=['browser', 'scraping', 'data', 'extract', 'ssrf_protected'],
    label='Extract Data',
    label_key='modules.browser.extract.label',
    description='Extract structured data from the page. Run browser.snapshot first to find the correct selector from the real page DOM.',
    description_key='modules.browser.extract.description',
    icon='Database',
    color='#E74C3C',

    # Connection types
    input_types=['page'],
    output_types=['json', 'array'],


    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*', 'ai.*', 'llm.*', 'agent.*'],    params_schema=compose(
        presets.SELECTOR(required=True, placeholder='.result-item'),
        presets.EXTRACT_LIMIT(),
        presets.EXTRACT_FIELDS(),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.browser.extract.output.status.description'},
        'data': {'type': 'array', 'description': 'Output data from the operation',
                'description_key': 'modules.browser.extract.output.data.description'},
        'count': {'type': 'number', 'description': 'Number of items',
                'description_key': 'modules.browser.extract.output.count.description'},
        'outcome': {
            'type': 'object',
            'description': (
                'How far this read was followed: "observed" when the selector '
                'resolved to at least one node in the live DOM, "accepted" '
                'when it matched nothing -- an empty match set reads the same '
                'whether the page had none or the selector was wrong. Never '
                'higher than "observed": nothing here evaluates a postcondition.'
            ),
            'description_key': 'modules.browser.extract.output.outcome.description'}
    },
    examples=[
        {
            'name': 'Extract Google search results',
            'params': {
                'selector': '.g',
                'limit': 10,
                'fields': {
                    'title': {'selector': 'h3', 'type': 'text'},
                    'url': {'selector': 'a', 'type': 'attribute', 'attribute': 'href'}
                }
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=30000,
    required_permissions=["browser.automation"],
)
class BrowserExtractModule(BaseModule):
    """Extract Data Module"""

    module_name = "Extract Data"
    module_description = "Extract structured data from the page"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        if 'selector' not in self.params:
            raise ValueError("Missing required parameter: selector")

        self.selector = self.params['selector']

        # Handle limit parameter - convert string to integer
        limit_param = self.params.get('limit', None)
        if limit_param is not None:
            self.limit = int(limit_param) if isinstance(limit_param, str) else limit_param
        else:
            self.limit = None

        self.fields = self.params.get('fields', {})

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        # Use browser driver to find elements (supports CSS and XPath)
        elements = await browser._query_selector_all(self.selector)

        if self.limit:
            elements = elements[:self.limit]

        # The one measurement in this module. Taken after the limit, so it is
        # the number of nodes this run actually looked at rather than the
        # number the page happened to hold.
        elements_matched = len(elements)

        # --- Mode 1: Simple attribute extraction ---
        # When 'attribute' is set without 'fields', extract a single attribute
        # per element. Used by composite modules (e.g. {'selector': 'a', 'attribute': 'href'}).
        simple_attribute = self.params.get('attribute')
        if simple_attribute and not self.fields:
            results = []
            for element in elements:
                try:
                    if simple_attribute == 'textContent' or simple_attribute == 'text':
                        value = await element.inner_text()
                    elif simple_attribute == 'innerHTML' or simple_attribute == 'html':
                        value = await element.inner_html()
                    else:
                        value = await element.get_attribute(simple_attribute)
                    results.append(value)
                except Exception:
                    results.append(None)
            return {
                "status": "success",
                "data": results,
                "count": len(results),
                "outcome": _extract_outcome(
                    selector=self.selector,
                    mode='attribute',
                    elements_matched=elements_matched,
                    values_returned=_values_present(results),
                ),
            }

        # --- Mode 2: Default text extraction ---
        # No fields, no attribute → extract text (or html/href via extract_type).
        # Returns empty list with a hint if no content is found.
        if not self.fields:
            extract_type = self.params.get('extract_type', 'text')
            results = []
            for element in elements:
                try:
                    if extract_type == 'html' or extract_type == 'innerHTML':
                        value = await element.inner_html()
                    elif extract_type == 'href':
                        value = await element.get_attribute('href')
                    else:  # default: text
                        value = await element.inner_text()
                    if value and value.strip():
                        results.append(value.strip())
                except Exception:
                    pass
            text_outcome = _extract_outcome(
                selector=self.selector,
                mode=extract_type,
                elements_matched=elements_matched,
                values_returned=len(results),
            )
            if results:
                return {
                    "status": "success",
                    "data": results,
                    "count": len(results),
                    "outcome": text_outcome,
                }
            # If still empty, return with a hint. The rung is NOT decided by
            # this branch: matching 20 nodes that all hold blank text is an
            # observation of 20 nodes, and saying otherwise would hide the
            # difference between "the selector is wrong" and "the selector is
            # right and the content is empty" -- which is the whole reason the
            # hint below exists.
            return {
                "status": "success",
                "data": [],
                "count": 0,
                "hint": "No text content found for selector '{}'. Try browser.evaluate with JavaScript instead.".format(self.selector),
                "outcome": text_outcome,
            }

        # --- Mode 3: Multi-field structured extraction ---
        # Extract multiple named fields per element using sub-selectors.
        # Supports comma-separated selectors as fallback chain.
        results = []
        for element in elements:
            item = {}
            for field_name, field_config in self.fields.items():
                try:
                    # Support new format: {'selector': 'h3', 'type': 'text', 'attribute': 'href'}
                    # Or old format: 'h3'
                    if isinstance(field_config, dict):
                        field_selector = field_config.get('selector', '')
                        field_type = field_config.get('type', 'text')
                        attribute_name = field_config.get('attribute', 'href')
                    else:
                        field_selector = field_config
                        field_type = 'text'
                        attribute_name = 'href'

                    # Support comma-separated multiple selectors (fallback mechanism)
                    selectors = [s.strip() for s in field_selector.split(',')]
                    field_value = None

                    for selector in selectors:
                        field_element = await element.query_selector(selector)
                        if field_element:
                            if field_type == 'attribute':
                                field_value = await field_element.get_attribute(attribute_name)
                            else:  # type == 'text'
                                field_value = await field_element.inner_text()
                            break  # Stop when found

                    item[field_name] = field_value
                except Exception:
                    item[field_name] = None
            results.append(item)

        return {
            "status": "success",
            "data": results,
            "count": len(results),
            "outcome": _extract_outcome(
                selector=self.selector,
                mode='fields',
                elements_matched=elements_matched,
                values_returned=_values_present(results),
            ),
        }


