"""
Localization utilities for module metadata
"""
from typing import Any


def get_localized_value(value: Any, lang: str = 'en') -> str:
    """
    Extract localized string from value

    Supports:
    1. String: returns as-is
    2. Dict: {"en": "...", "zh": "...", "ja": "..."}

    Args:
        value: Value to process (string or dict)
        lang: Language code (en, zh, ja, es)

    Returns:
        Localized string, falls back to English if specified lang not found
    """
    if isinstance(value, str):
        return value
    elif isinstance(value, dict):
        # Try to get specified language
        if lang in value:
            return value[lang]
        # Fallback to English
        if 'en' in value:
            return value['en']
        # If no English, return first available
        return next(iter(value.values())) if value else ''
    return str(value) if value else ''
