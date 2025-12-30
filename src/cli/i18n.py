"""
CLI Internationalization

Simple i18n system for the CLI.
"""

import json
import logging
from typing import Any

from .config import I18N_DIR

logger = logging.getLogger(__name__)


class I18n:
    """Simple i18n system"""

    def __init__(self, lang: str = 'en'):
        self.lang = lang
        self.translations = {}
        self.load_language(lang)

    def load_language(self, lang: str):
        """Load language file"""
        lang_file = I18N_DIR / f'{lang}.json'
        if lang_file.exists():
            with open(lang_file, 'r', encoding='utf-8') as f:
                self.translations = json.load(f)
        else:
            logger.warning(f"Language file for '{lang}' not found")
            self.translations = {}

    def t(self, key: str, **kwargs: Any) -> str:
        """Get translated text"""
        keys = key.split('.')
        value = self.translations

        for k in keys:
            if isinstance(value, dict):
                value = value.get(k, key)
            else:
                return key

        # Replace placeholders
        if isinstance(value, str) and kwargs:
            return value.format(**kwargs)

        return value if isinstance(value, str) else key
