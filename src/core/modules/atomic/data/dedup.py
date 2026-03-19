# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Data Dedup Module — Deduplicate records by key fields

Single responsibility: remove duplicate records from an array.
Supports cross-run persistence via a hash file on disk.

Workflow position:
  pagination → dedup → validate → database.insert
"""
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field
from ...schema.constants import FieldGroup

logger = logging.getLogger(__name__)


def _record_hash(record: dict, keys: list) -> str:
    """Compute a stable hash for a record based on specified keys."""
    if keys:
        values = tuple(record.get(k) for k in sorted(keys))
    else:
        # Hash all fields
        values = tuple(sorted(record.items()))
    raw = json.dumps(values, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


@register_module(
    module_id='data.dedup',
    version='1.0.0',
    category='data',
    tags=['data', 'dedup', 'deduplicate', 'unique', 'filter'],
    label='Deduplicate Records',
    label_key='modules.data.dedup.label',
    description='Remove duplicate records from an array by key fields. Optionally persists seen hashes to disk or execution context for cross-run dedup. Use storage=context in cloud/stateless environments where disk is ephemeral.',
    description_key='modules.data.dedup.description',
    icon='Filter',
    color='#8B5CF6',

    input_types=['array'],
    output_types=['array'],
    can_connect_to=['*'],
    can_receive_from=['*'],

    timeout_ms=30000,
    concurrent_safe=True,

    params_schema=compose(
        field('items', type='array', label='Items',
              description='Array of records to deduplicate. Usually linked from a previous step.',
              required=True,
              group=FieldGroup.BASIC),
        field('keys', type='array', label='Key Fields',
              description='Fields to use as dedup key (e.g., ["url", "title"]). Empty = hash all fields.',
              required=False, default=[],
              items={'type': 'string'},
              group=FieldGroup.BASIC),
        field('storage', type='select', label='Hash Storage',
              description='Where to persist seen hashes for cross-run dedup. disk=local file (not for cloud workers), context=execution context (persisted by engine).',
              required=False, default='disk',
              options=[
                  {'label': 'Disk (local file)', 'value': 'disk'},
                  {'label': 'Context (execution engine)', 'value': 'context'},
              ],
              group=FieldGroup.OPTIONS),
        field('hash_file', type='string', label='Hash File (cross-run)',
              description='Path to persist seen hashes. Enables dedup across workflow runs. Leave empty for in-memory only. Not recommended for cloud/stateless workers.',
              format='path',
              required=False,
              placeholder='/tmp/flyto_dedup_hashes.json',
              showIf={"storage": "disk"},
              group=FieldGroup.OPTIONS),
        field('max_hashes', type='number', label='Max Stored Hashes',
              description='Maximum hashes to keep in the hash file (oldest evicted). 0 = unlimited.',
              default=100000, min=0, max=10000000,
              showIf={"hash_file": {"$notEmpty": True}},
              group=FieldGroup.ADVANCED),
    ),
    output_schema={
        'items':       {'type': 'array',   'description': 'Deduplicated records'},
        'total_in':    {'type': 'integer', 'description': 'Input record count'},
        'total_out':   {'type': 'integer', 'description': 'Output record count (after dedup)'},
        'duplicates':  {'type': 'integer', 'description': 'Number of duplicates removed'},
        'hash_count':  {'type': 'integer', 'description': 'Total hashes stored (for cross-run)'},
    },
    examples=[
        {'name': 'Dedup by URL', 'params': {'items': [], 'keys': ['url']}},
        {'name': 'Cross-run dedup', 'params': {'items': [], 'keys': ['url'], 'hash_file': '/tmp/seen.json'}},
    ],
    author='Flyto Team', license='MIT',
    required_permissions=[],
)
class DataDedupModule(BaseModule):
    """Deduplicate records by key fields."""

    module_name = "Deduplicate Records"
    module_description = "Remove duplicate records from an array"

    def validate_params(self) -> None:
        self.items = self.params.get('items', [])
        self.keys = self.params.get('keys', [])
        self.storage_mode = self.params.get('storage', 'disk')
        self.hash_file = self.params.get('hash_file')
        self.max_hashes = self.params.get('max_hashes', 100000)

        if not isinstance(self.items, list):
            raise ValueError("items must be an array")

    async def execute(self) -> Dict[str, Any]:
        # Load existing hashes (dict preserves insertion order for correct eviction)
        seen: Dict[str, None] = {}
        if self.storage_mode == 'context':
            for h in self.context.get('_dedup_hashes', []):
                seen[h] = None
        elif self.hash_file:
            seen = self._load_hashes()

        total_in = len(self.items)
        result = []

        for record in self.items:
            if not isinstance(record, dict):
                result.append(record)
                continue
            h = _record_hash(record, self.keys)
            if h not in seen:
                seen[h] = None
                result.append(record)

        # Save hashes
        if self.storage_mode == 'context':
            hash_list = list(seen.keys())
            if self.max_hashes > 0 and len(hash_list) > self.max_hashes:
                hash_list = hash_list[-self.max_hashes:]
            self.context['_dedup_hashes'] = hash_list
        elif self.hash_file:
            self._save_hashes(seen)

        duplicates = total_in - len(result)
        if duplicates > 0:
            logger.info(f"Dedup: {total_in} → {len(result)} ({duplicates} duplicates removed)")

        return {
            'status': 'success',
            'items': result,
            'total_in': total_in,
            'total_out': len(result),
            'duplicates': duplicates,
            'hash_count': len(seen),
        }

    def _load_hashes(self) -> Dict[str, None]:
        """Load hashes as ordered dict (preserves insertion order for eviction)."""
        path = Path(self.hash_file)
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            if isinstance(data, list):
                return {h: None for h in data}
            return {}
        except Exception:
            return {}

    def _save_hashes(self, hashes: Dict[str, None]):
        """Save hashes to disk. Evicts oldest (first-inserted) when over limit."""
        path = Path(self.hash_file)
        path.parent.mkdir(parents=True, exist_ok=True)

        hash_list = list(hashes.keys())
        if self.max_hashes > 0 and len(hash_list) > self.max_hashes:
            hash_list = hash_list[-self.max_hashes:]

        tmp = path.with_suffix('.tmp')
        tmp.write_text(json.dumps(hash_list), encoding='utf-8')
        tmp.rename(path)
