"""
Salesforce Integration

Provides Salesforce CRM integration:
- CRUD operations on objects (Account, Contact, Lead, Opportunity)
- SOQL queries
- Bulk operations
- Apex REST endpoints
"""

from .integration import SalesforceIntegration
from .modules import (
    SalesforceCreateRecordModule,
    SalesforceQueryModule,
    SalesforceUpdateRecordModule,
)

__all__ = [
    'SalesforceIntegration',
    'SalesforceCreateRecordModule',
    'SalesforceQueryModule',
    'SalesforceUpdateRecordModule',
]
