"""
Catalog Category Detail API

Returns all modules in a category for LLM second-round selection.
Medium token usage (~500-2000 tokens per category).
"""

from typing import List, Dict, Any, Optional


def get_category_detail(
    category: str,
    include_params: bool = False,
) -> List[Dict[str, Any]]:
    """
    Get all modules in a category with summary info.

    Args:
        category: Category name (e.g., 'browser', 'http')
        include_params: Include params_summary (increases token usage)

    Returns:
        [
            {
                'module_id': 'browser.launch',
                'label': 'Launch Browser',
                'description': 'Start a new browser instance',
                'can_be_start': True,
                'input_types': [],
                'output_types': ['browser_context'],
                'params_summary': ['headless', 'browser_type'],  # if include_params
            },
            ...
        ]
    """
    from ..modules.registry import ModuleRegistry

    all_metadata = ModuleRegistry.get_all_metadata()

    results = []
    for module_id, meta in sorted(all_metadata.items()):
        if meta.get('category') != category:
            continue

        item = {
            'module_id': module_id,
            'label': meta.get('ui_label', module_id),
            'description': meta.get('ui_description', ''),
            'can_be_start': meta.get('can_be_start', False),
            'input_types': meta.get('input_types', []),
            'output_types': meta.get('output_types', []),
        }

        if include_params:
            params_schema = meta.get('params_schema', {})
            item['params_summary'] = list(params_schema.keys())

        results.append(item)

    return results


def get_subcategories(category: str) -> List[str]:
    """
    Get all subcategories within a category.

    Args:
        category: Category name

    Returns:
        ['navigation', 'interaction', 'extraction', ...]
    """
    from ..modules.registry import ModuleRegistry

    all_metadata = ModuleRegistry.get_all_metadata()

    subcategories = set()
    for meta in all_metadata.values():
        if meta.get('category') != category:
            continue
        subcat = meta.get('subcategory')
        if subcat:
            subcategories.add(subcat)

    return sorted(list(subcategories))


def get_category_by_use_case(use_case: str) -> List[str]:
    """
    Find categories that match a use case description.

    Args:
        use_case: Description of what user wants to do
                  (e.g., 'scrape website', 'send notification')

    Returns:
        List of category names, ranked by relevance
    """
    from .outline import CATEGORY_METADATA

    use_case_lower = use_case.lower()
    matches = []

    for category, meta in CATEGORY_METADATA.items():
        score = 0

        # Check description
        if use_case_lower in meta['description'].lower():
            score += 2

        # Check use cases
        for uc in meta.get('common_use_cases', []):
            if use_case_lower in uc.lower() or uc.lower() in use_case_lower:
                score += 3

        # Check category name
        if use_case_lower in category:
            score += 1

        if score > 0:
            matches.append((category, score))

    # Sort by score descending
    matches.sort(key=lambda x: x[1], reverse=True)
    return [m[0] for m in matches]
