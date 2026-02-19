# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

"""
Salesforce Modules

Atomic modules for Salesforce operations.
"""

from .create_record import SalesforceCreateRecordModule
from .query import SalesforceQueryModule
from .update_record import SalesforceUpdateRecordModule

__all__ = [
    'SalesforceCreateRecordModule',
    'SalesforceQueryModule',
    'SalesforceUpdateRecordModule',
]
