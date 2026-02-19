# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

"""
Jira Integration

Provides Atlassian Jira integration:
- Create and update issues
- Search issues with JQL
- Manage projects
- Track sprints and boards
"""

from .integration import JiraIntegration
from .modules import (
    JiraCreateIssueModule,
    JiraSearchIssuesModule,
)

__all__ = [
    'JiraIntegration',
    'JiraCreateIssueModule',
    'JiraSearchIssuesModule',
]
