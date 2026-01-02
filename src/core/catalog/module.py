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


def search_modules(
    query: str,
    category: Optional[str] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    Search modules by keyword.

    Args:
        query: Search query (searches in module_id, label, description)
        category: Limit to specific category
        limit: Maximum results

    Returns:
        List of module summaries matching the query
    """
    from ..modules.registry import ModuleRegistry

    all_metadata = ModuleRegistry.get_all_metadata()
    query_lower = query.lower()

    results = []
    for module_id, meta in all_metadata.items():
        if category and meta.get('category') != category:
            continue

        # Calculate relevance score
        score = 0

        if query_lower in module_id.lower():
            score += 3

        label = meta.get('ui_label', '').lower()
        if query_lower in label:
            score += 2

        description = meta.get('ui_description', '').lower()
        if query_lower in description:
            score += 1

        if score > 0:
            results.append({
                'module_id': module_id,
                'label': meta.get('ui_label', module_id),
                'description': meta.get('ui_description', ''),
                'category': meta.get('category', ''),
                'can_be_start': meta.get('can_be_start', False),
                'score': score,
            })

    # Sort by score, then by module_id
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
