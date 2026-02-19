# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Storage Modules
Simple key-value storage for workflow state persistence.
"""
from .kv import storage_get, storage_set, storage_delete

__all__ = ['storage_get', 'storage_set', 'storage_delete']
