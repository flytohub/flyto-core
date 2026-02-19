# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

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
