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
