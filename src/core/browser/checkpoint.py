# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Pagination Checkpoint — Save/resume pagination state

Saves metadata after each page so large scraping jobs can resume
from where they left off on crash or interruption.

Items are stored in a separate JSONL file (append-only, streaming)
to avoid holding all records in memory. The checkpoint metadata file
stays small regardless of how many items are scraped.
"""
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class PaginationCheckpoint:
    """Manages pagination checkpoint state on disk.

    Metadata file (JSON):
        {
            "version": 2,
            "item_selector": ".product-card",
            "mode": "next_button",
            "pages_processed": 5,
            "total_items": 250,
            "last_url": "https://...",
            "last_page_num": 5,
            "stopped_reason": null,
            "created_at": "2026-03-19T10:00:00",
            "updated_at": "2026-03-19T10:05:00",
            "retries_used": 2
        }

    Items file (.jsonl): one JSON object per line, append-only.
    """

    VERSION = 2

    def __init__(self, path: str, item_selector: str, mode: str):
        self.path = Path(path)
        self.item_selector = item_selector
        self.mode = mode
        self._state: Optional[Dict] = None
        self._items_path = self.path.with_suffix('.jsonl')

    def exists(self) -> bool:
        """Check if a compatible checkpoint exists."""
        if not self.path.exists():
            return False
        try:
            state = self._read()
            return (
                state.get('version') == self.VERSION
                and state.get('item_selector') == self.item_selector
                and state.get('mode') == self.mode
            )
        except Exception:
            return False

    def load(self) -> Dict[str, Any]:
        """Load checkpoint state. Returns empty state if none exists."""
        if not self.exists():
            return self._empty_state()
        state = self._read()
        self._state = state
        logger.info(
            f"Checkpoint loaded: {state['pages_processed']} pages, "
            f"{state['total_items']} items from {state.get('updated_at', '?')}"
        )
        return state

    def load_items(self) -> List[Dict]:
        """Load all items from the JSONL items file."""
        if not self._items_path.exists():
            return []
        items = []
        try:
            with open(self._items_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        items.append(json.loads(line))
        except Exception as e:
            logger.warning(f"Failed to load items file: {e}")
        return items

    def save(
        self,
        items: List[Dict],
        pages_processed: int,
        last_url: Optional[str] = None,
        last_page_num: Optional[int] = None,
        stopped_reason: Optional[str] = None,
        retries_used: int = 0,
    ):
        """Save pagination state. Appends new items to JSONL, updates metadata."""
        now = time.strftime('%Y-%m-%dT%H:%M:%S')

        # Append new items to JSONL (streaming, no full-load needed)
        prev_total = self._state.get('total_items', 0) if self._state else 0
        new_items = items[prev_total:]  # only append items not yet written
        if new_items:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._items_path, 'a', encoding='utf-8') as f:
                for item in new_items:
                    f.write(json.dumps(item, ensure_ascii=False) + '\n')

        # Update metadata (small, always full-write)
        state = {
            'version': self.VERSION,
            'item_selector': self.item_selector,
            'mode': self.mode,
            'pages_processed': pages_processed,
            'total_items': len(items),
            'last_url': last_url,
            'last_page_num': last_page_num,
            'stopped_reason': stopped_reason,
            'retries_used': retries_used,
            'created_at': (
                self._state.get('created_at', now) if self._state else now
            ),
            'updated_at': now,
        }
        self._state = state

        # Atomic write for metadata
        tmp_path = self.path.with_suffix('.tmp')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path.write_text(json.dumps(state, ensure_ascii=False), encoding='utf-8')
        tmp_path.rename(self.path)

        logger.debug(
            f"Checkpoint saved: page {pages_processed}, {len(items)} items"
        )

    def clear(self):
        """Remove checkpoint and items files."""
        try:
            self.path.unlink(missing_ok=True)
            self._items_path.unlink(missing_ok=True)
            self._state = None
            logger.info(f"Checkpoint cleared: {self.path}")
        except Exception as e:
            logger.warning(f"Failed to clear checkpoint: {e}")

    def _read(self) -> Dict:
        return json.loads(self.path.read_text(encoding='utf-8'))

    def _empty_state(self) -> Dict[str, Any]:
        return {
            'version': self.VERSION,
            'item_selector': self.item_selector,
            'mode': self.mode,
            'pages_processed': 0,
            'total_items': 0,
            'last_url': None,
            'last_page_num': None,
            'stopped_reason': None,
            'retries_used': 0,
            'created_at': None,
            'updated_at': None,
        }
