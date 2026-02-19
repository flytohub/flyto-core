# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

"""
Storage Modules
Simple key-value storage for workflow state persistence.
"""
from .kv import storage_get, storage_set, storage_delete

__all__ = ['storage_get', 'storage_set', 'storage_delete']
