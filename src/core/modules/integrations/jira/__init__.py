# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

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
