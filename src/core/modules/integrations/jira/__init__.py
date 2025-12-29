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
