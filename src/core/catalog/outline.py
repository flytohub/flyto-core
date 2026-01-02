"""
Catalog Outline API

Returns category-level summary for LLM first-round selection.
Optimized for minimal token usage (~500 tokens).
"""

from typing import Dict, List, Any


# Category metadata with descriptions and use cases
CATEGORY_METADATA = {
    'browser': {
        'label': 'Browser Automation',
        'description': 'Control browser, navigate pages, click elements, extract data',
        'common_use_cases': ['Web scraping', 'Form filling', 'Screenshots', 'Testing'],
    },
    'http': {
        'label': 'HTTP & API',
        'description': 'Make HTTP requests, handle REST/GraphQL APIs',
        'common_use_cases': ['API calls', 'Webhooks', 'Data fetching'],
    },
    'data': {
        'label': 'Data Transform',
        'description': 'JSON, CSV, text processing and transformation',
        'common_use_cases': ['Data parsing', 'Format conversion', 'Filtering'],
    },
    'flow': {
        'label': 'Flow Control',
        'description': 'Conditionals, loops, branching, error handling',
        'common_use_cases': ['Conditional logic', 'Iteration', 'Error recovery'],
    },
    'string': {
        'label': 'String Operations',
        'description': 'Text manipulation, regex, formatting',
        'common_use_cases': ['Text processing', 'Pattern matching', 'Formatting'],
    },
    'array': {
        'label': 'Array Operations',
        'description': 'List manipulation, filtering, mapping, sorting',
        'common_use_cases': ['Data processing', 'Collection operations'],
    },
    'object': {
        'label': 'Object Operations',
        'description': 'Dictionary/object manipulation, merging, extracting',
        'common_use_cases': ['Data restructuring', 'Property access'],
    },
    'math': {
        'label': 'Math Operations',
        'description': 'Calculations, statistics, number formatting',
        'common_use_cases': ['Calculations', 'Statistics', 'Aggregations'],
    },
    'datetime': {
        'label': 'Date & Time',
        'description': 'Date parsing, formatting, calculations',
        'common_use_cases': ['Date formatting', 'Time calculations', 'Scheduling'],
    },
    'file': {
        'label': 'File Operations',
        'description': 'Read, write, manipulate files',
        'common_use_cases': ['File I/O', 'Directory operations'],
    },
    'ai': {
        'label': 'AI & LLM',
        'description': 'AI model integration, text generation, embeddings',
        'common_use_cases': ['Text generation', 'Summarization', 'Classification'],
    },
    'notification': {
        'label': 'Notifications',
        'description': 'Send notifications via email, Slack, Telegram',
        'common_use_cases': ['Alerts', 'Reports', 'Messaging'],
    },
    'database': {
        'label': 'Database',
        'description': 'Query and manipulate databases',
        'common_use_cases': ['Data storage', 'Queries', 'CRUD operations'],
    },
    'trigger': {
        'label': 'Triggers',
        'description': 'Start workflows from events, schedules, webhooks',
        'common_use_cases': ['Scheduling', 'Event handling', 'Webhooks'],
    },
    'utility': {
        'label': 'Utilities',
        'description': 'Logging, debugging, delay, system operations',
        'common_use_cases': ['Debugging', 'Delays', 'Logging'],
    },
    'image': {
        'label': 'Image Processing',
        'description': 'Image manipulation, conversion, analysis',
        'common_use_cases': ['Image resize', 'Format conversion', 'OCR'],
    },
    'cloud': {
        'label': 'Cloud Services',
        'description': 'Cloud storage, computing services',
        'common_use_cases': ['File storage', 'Cloud APIs'],
    },
    'payment': {
        'label': 'Payment',
        'description': 'Payment processing, invoicing',
        'common_use_cases': ['Transactions', 'Invoices'],
    },
    'productivity': {
        'label': 'Productivity',
        'description': 'Calendar, email, document integrations',
        'common_use_cases': ['Email', 'Calendar', 'Documents'],
    },
    'agent': {
        'label': 'AI Agents',
        'description': 'Autonomous AI agent workflows',
        'common_use_cases': ['Task automation', 'Decision making'],
    },
    'api': {
        'label': 'API Tools',
        'description': 'API development and testing tools',
        'common_use_cases': ['API testing', 'Mock servers'],
    },
    'meta': {
        'label': 'Meta',
        'description': 'Workflow metadata, variables, context',
        'common_use_cases': ['Variable management', 'Context handling'],
    },
    'test': {
        'label': 'Testing',
        'description': 'Test utilities and assertions',
        'common_use_cases': ['Unit testing', 'Assertions'],
    },
    'element': {
        'label': 'Elements',
        'description': 'UI element utilities',
        'common_use_cases': ['Element handling'],
    },
}


def get_outline() -> Dict[str, Dict[str, Any]]:
    """
    Get category outline for LLM selection.

    Returns minimal info per category (~500 tokens total).
    LLM uses this to decide which categories to explore.

    Returns:
        {
            'browser': {
                'label': 'Browser Automation',
                'description': 'Control browser, navigate...',
                'count': 12,
                'common_use_cases': ['Web scraping', ...]
            },
            ...
        }
    """
    from ..modules.registry import ModuleRegistry

    all_metadata = ModuleRegistry.get_all_metadata()

    # Count modules per category
    category_counts: Dict[str, int] = {}
    for meta in all_metadata.values():
        cat = meta.get('category', 'unknown')
        category_counts[cat] = category_counts.get(cat, 0) + 1

    # Build outline
    outline = {}
    for category, count in sorted(category_counts.items()):
        cat_meta = CATEGORY_METADATA.get(category, {
            'label': category.title(),
            'description': f'{category} modules',
            'common_use_cases': [],
        })

        outline[category] = {
            'label': cat_meta['label'],
            'description': cat_meta['description'],
            'count': count,
            'common_use_cases': cat_meta['common_use_cases'],
        }

    return outline


def get_categories() -> List[str]:
    """Get list of all category names"""
    from ..modules.registry import ModuleRegistry

    all_metadata = ModuleRegistry.get_all_metadata()

    categories = set()
    for meta in all_metadata.values():
        cat = meta.get('category', 'unknown')
        categories.add(cat)

    return sorted(list(categories))
