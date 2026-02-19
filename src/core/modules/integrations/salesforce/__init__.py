# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

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
