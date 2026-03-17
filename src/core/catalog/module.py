# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Catalog Module Detail API

Returns complete module information for workflow assembly.
Only fetch when LLM has decided to use a specific module.
"""

from typing import Dict, Any, Optional, List


def get_module_detail(module_id: str) -> Optional[Dict[str, Any]]:
    """
    Get complete module information.

    Only call this after LLM has decided to use this module.
    Returns full params_schema and examples.

    Args:
        module_id: Module ID (e.g., 'browser.click')

    Returns:
        {
            'module_id': 'browser.click',
            'label': 'Click Element',
            'description': 'Click on a webpage element',

            'params_schema': {
                'selector': {
                    'type': 'string',
                    'required': True,
                    'label': 'CSS Selector',
                    'description': 'The CSS selector of the element',
                    'placeholder': '#submit-button',
                },
                'button': {
                    'type': 'string',
                    'required': False,
                    'default': 'left',
                    'options': ['left', 'right', 'middle'],
                },
                ...
            },

            'input_types': ['browser_page'],
            'output_types': ['browser_page'],
            'can_receive_from': ['browser.*'],
            'can_connect_to': ['browser.*', 'data.*'],
            'can_be_start': False,
            'start_requires_params': [],

            'examples': [
                {
                    'name': 'Click login button',
                    'params': {'selector': '#login-btn'},
                },
            ],
        }
    """
    from ..modules.registry import ModuleRegistry

    meta = ModuleRegistry.get_metadata(module_id)
    if not meta:
        return None

    return {
        'module_id': module_id,
        'label': meta.get('ui_label', module_id),
        'description': meta.get('ui_description', ''),
        'category': meta.get('category', ''),
        'subcategory': meta.get('subcategory', ''),

        # Complete params schema
        'params_schema': meta.get('params_schema', {}),
        'output_schema': meta.get('output_schema', {}),

        # Connection info
        'input_types': meta.get('input_types', []),
        'output_types': meta.get('output_types', []),
        'can_receive_from': meta.get('can_receive_from', ['*']),
        'can_connect_to': meta.get('can_connect_to', ['*']),

        # Start node info
        'can_be_start': meta.get('can_be_start', False),
        'start_requires_params': meta.get('start_requires_params', []),

        # Port configuration
        'node_type': meta.get('node_type', 'standard'),
        'input_ports': meta.get('input_ports', []),
        'output_ports': meta.get('output_ports', []),

        # Examples
        'examples': meta.get('examples', []),

        # Execution hints
        'timeout': meta.get('timeout'),
        'retryable': meta.get('retryable', False),
        'requires_credentials': meta.get('requires_credentials', False),
    }


def get_modules_batch(module_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Get complete info for multiple modules at once.

    More efficient than calling get_module_detail multiple times.

    Args:
        module_ids: List of module IDs

    Returns:
        {
            'browser.click': {...},
            'browser.screenshot': {...},
            ...
        }
    """
    result = {}
    for module_id in module_ids:
        detail = get_module_detail(module_id)
        if detail:
            result[module_id] = detail
    return result


def _score_module(
    query_words: List[str],
    query_lower: str,
    module_id: str,
    meta: Dict[str, Any],
) -> float:
    """Score a single module against query words.

    Scoring signals (per query word):
    - Exact tag match:       +4
    - In module_id:          +3
    - In label:              +2
    - In description:        +1
    - Partial text match:    +1.5
    All-words bonus:         +3
    """
    mid_lower = module_id.lower()
    label = meta.get('ui_label', '').lower()
    description = meta.get('ui_description', '').lower()
    tags = [t.lower() for t in meta.get('tags', [])]
    id_words = mid_lower.replace('.', ' ').replace('_', ' ').split()
    all_text = set(tags + id_words + label.split())

    score = 0.0
    matched_words = 0

    for word in query_words:
        word_matched = False
        if word in tags:
            score += 4
            word_matched = True
        elif word in mid_lower:
            score += 3
            word_matched = True
        elif word in label:
            score += 2
            word_matched = True
        elif word in description:
            score += 1
            word_matched = True
        elif any(word in t for t in all_text):
            score += 1.5
            word_matched = True

        if word_matched:
            matched_words += 1

    # All-words bonus (precision reward)
    if matched_words == len(query_words) and len(query_words) > 1:
        score += 3

    # Legacy: whole query substring match (backward compat)
    if score == 0:
        if query_lower in mid_lower:
            score += 3
        elif query_lower in label:
            score += 2
        elif query_lower in description:
            score += 1

    return score


def search_modules(
    query: str,
    category: Optional[str] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    Search modules by keyword with multi-signal scoring.

    Also handles fuzzy module_id lookup: if query looks like a module_id
    (contains '.'), tries to find the closest match.
    """
    from ..modules.registry import ModuleRegistry

    all_metadata = ModuleRegistry.get_all_metadata()
    query_lower = query.lower()
    query_words = [w for w in query_lower.split() if len(w) > 1]

    # If query looks like a module_id, split on dots for word matching
    if '.' in query_lower and not query_words:
        query_words = query_lower.replace('.', ' ').split()

    results = []
    for module_id, meta in all_metadata.items():
        if category and meta.get('category') != category:
            continue

        score = _score_module(query_words, query_lower, module_id, meta)
        if score > 0:
            results.append({
                'module_id': module_id,
                'label': meta.get('ui_label', module_id),
                'description': meta.get('ui_description', ''),
                'category': meta.get('category', ''),
                'can_be_start': meta.get('can_be_start', False),
                'score': score,
            })

    results.sort(key=lambda x: (-x['score'], x['module_id']))
    return results[:limit]


def get_suggested_workflow(
    task_description: str,
    max_steps: int = 5,
) -> List[Dict[str, Any]]:
    """
    Suggest a workflow based on task description.

    This is a simple heuristic-based suggestion.
    For better results, use LLM with get_outline -> get_category_detail flow.

    Args:
        task_description: What the user wants to accomplish
        max_steps: Maximum steps in suggested workflow

    Returns:
        [
            {'module_id': 'browser.launch', 'purpose': 'Start browser'},
            {'module_id': 'browser.goto', 'purpose': 'Navigate to URL'},
            ...
        ]
    """
    # Simple keyword-based suggestions
    task_lower = task_description.lower()
    suggestions = []

    # Web scraping pattern
    if any(kw in task_lower for kw in ['scrape', 'extract', 'crawl', 'webpage', 'website']):
        suggestions = [
            {'module_id': 'browser.launch', 'purpose': 'Start browser'},
            {'module_id': 'browser.goto', 'purpose': 'Navigate to target URL'},
            {'module_id': 'browser.wait', 'purpose': 'Wait for content to load'},
            {'module_id': 'browser.extract', 'purpose': 'Extract data from page'},
            {'module_id': 'browser.close', 'purpose': 'Close browser'},
        ]

    # API call pattern
    elif any(kw in task_lower for kw in ['api', 'request', 'fetch', 'endpoint']):
        suggestions = [
            {'module_id': 'http.request', 'purpose': 'Make HTTP request'},
            {'module_id': 'data.json.parse', 'purpose': 'Parse response JSON'},
        ]

    # Notification pattern
    elif any(kw in task_lower for kw in ['notify', 'alert', 'send', 'message', 'email']):
        suggestions = [
            {'module_id': 'notification.email.send', 'purpose': 'Send notification'},
        ]

    return suggestions[:max_steps]
