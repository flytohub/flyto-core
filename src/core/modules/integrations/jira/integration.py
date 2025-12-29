"""
Jira Integration

Core Jira Cloud API integration class.
"""

import base64
import logging
import os
from typing import Any, Dict, List, Optional

from ..base import PaginatedIntegration, IntegrationConfig, APIResponse

logger = logging.getLogger(__name__)


class JiraIntegration(PaginatedIntegration):
    """
    Jira Cloud API integration.

    Usage:
        async with JiraIntegration(
            domain="your-domain.atlassian.net",
            email="user@example.com",
            api_token="your-api-token",
        ) as jira:
            await jira.create_issue(
                project_key="PROJ",
                summary="Bug fix needed",
                issue_type="Bug",
            )
    """

    service_name = "jira"
    api_version = "3"

    def __init__(
        self,
        domain: Optional[str] = None,
        email: Optional[str] = None,
        api_token: Optional[str] = None,
        access_token: Optional[str] = None,  # OAuth token
    ):
        """
        Initialize Jira integration.

        Args:
            domain: Jira Cloud domain (e.g., "your-domain.atlassian.net")
            email: User email for basic auth
            api_token: API token for basic auth
            access_token: OAuth access token (alternative)
        """
        self.domain = domain or os.getenv("JIRA_DOMAIN")
        self.email = email or os.getenv("JIRA_EMAIL")
        self.api_token = api_token or os.getenv("JIRA_API_TOKEN")

        if not self.domain:
            raise ValueError("Jira domain required")

        base_url = f"https://{self.domain}/rest/api"
        config = IntegrationConfig(
            service_name="jira",
            base_url=base_url,
            api_version="3",
            rate_limit_calls=50,
            rate_limit_period=60,
        )

        super().__init__(access_token=access_token, config=config)

    def _get_auth_header(self) -> Dict[str, str]:
        """Get Jira authorization header."""
        if self.access_token:
            return {"Authorization": f"Bearer {self.access_token}"}
        elif self.email and self.api_token:
            credentials = f"{self.email}:{self.api_token}"
            encoded = base64.b64encode(credentials.encode()).decode()
            return {"Authorization": f"Basic {encoded}"}
        return {}

    async def create_issue(
        self,
        project_key: str,
        summary: str,
        issue_type: str = "Task",
        description: Optional[str] = None,
        priority: Optional[str] = None,
        assignee: Optional[str] = None,
        labels: Optional[List[str]] = None,
        components: Optional[List[str]] = None,
        custom_fields: Optional[Dict[str, Any]] = None,
    ) -> APIResponse:
        """
        Create a new Jira issue.

        Args:
            project_key: Project key (e.g., "PROJ")
            summary: Issue summary/title
            issue_type: Issue type (Task, Bug, Story, Epic)
            description: Issue description (Atlassian Document Format or plain text)
            priority: Priority name (Highest, High, Medium, Low, Lowest)
            assignee: Account ID of assignee
            labels: List of labels
            components: List of component names
            custom_fields: Custom field values

        Returns:
            APIResponse with created issue details
        """
        fields = {
            "project": {"key": project_key},
            "summary": summary,
            "issuetype": {"name": issue_type},
        }

        if description:
            # Support both plain text and ADF
            if isinstance(description, dict):
                fields["description"] = description
            else:
                fields["description"] = {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": description}],
                        }
                    ],
                }

        if priority:
            fields["priority"] = {"name": priority}
        if assignee:
            fields["assignee"] = {"accountId": assignee}
        if labels:
            fields["labels"] = labels
        if components:
            fields["components"] = [{"name": c} for c in components]
        if custom_fields:
            fields.update(custom_fields)

        return await self.post("issue", json={"fields": fields})

    async def get_issue(
        self,
        issue_key: str,
        fields: Optional[List[str]] = None,
        expand: Optional[List[str]] = None,
    ) -> APIResponse:
        """
        Get issue details.

        Args:
            issue_key: Issue key (e.g., "PROJ-123")
            fields: Specific fields to return
            expand: Properties to expand

        Returns:
            APIResponse with issue details
        """
        params = {}
        if fields:
            params["fields"] = ",".join(fields)
        if expand:
            params["expand"] = ",".join(expand)

        return await self.get(f"issue/{issue_key}", params=params)

    async def update_issue(
        self,
        issue_key: str,
        fields: Dict[str, Any],
        notify_users: bool = True,
    ) -> APIResponse:
        """
        Update an issue.

        Args:
            issue_key: Issue key
            fields: Fields to update
            notify_users: Whether to notify watchers

        Returns:
            APIResponse with update result
        """
        params = {"notifyUsers": str(notify_users).lower()}
        return await self.put(
            f"issue/{issue_key}",
            json={"fields": fields},
            params=params,
        )

    async def transition_issue(
        self,
        issue_key: str,
        transition_id: str,
        comment: Optional[str] = None,
        fields: Optional[Dict[str, Any]] = None,
    ) -> APIResponse:
        """
        Transition an issue to a new status.

        Args:
            issue_key: Issue key
            transition_id: Transition ID (get from get_transitions)
            comment: Optional comment to add
            fields: Additional fields for transition

        Returns:
            APIResponse with transition result
        """
        payload: Dict[str, Any] = {
            "transition": {"id": transition_id}
        }

        if fields:
            payload["fields"] = fields

        if comment:
            payload["update"] = {
                "comment": [
                    {
                        "add": {
                            "body": {
                                "type": "doc",
                                "version": 1,
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [{"type": "text", "text": comment}],
                                    }
                                ],
                            }
                        }
                    }
                ]
            }

        return await self.post(f"issue/{issue_key}/transitions", json=payload)

    async def get_transitions(self, issue_key: str) -> APIResponse:
        """Get available transitions for an issue."""
        return await self.get(f"issue/{issue_key}/transitions")

    async def add_comment(
        self,
        issue_key: str,
        body: str,
        visibility: Optional[Dict[str, str]] = None,
    ) -> APIResponse:
        """
        Add a comment to an issue.

        Args:
            issue_key: Issue key
            body: Comment body (plain text or ADF)
            visibility: Restrict visibility (e.g., {"type": "group", "value": "jira-users"})

        Returns:
            APIResponse with comment details
        """
        if isinstance(body, str):
            body_adf = {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": body}],
                    }
                ],
            }
        else:
            body_adf = body

        payload: Dict[str, Any] = {"body": body_adf}
        if visibility:
            payload["visibility"] = visibility

        return await self.post(f"issue/{issue_key}/comment", json=payload)

    async def search_issues(
        self,
        jql: str,
        fields: Optional[List[str]] = None,
        max_results: int = 50,
        start_at: int = 0,
        expand: Optional[List[str]] = None,
    ) -> APIResponse:
        """
        Search issues using JQL.

        Args:
            jql: JQL query string
            fields: Fields to return
            max_results: Maximum results per request
            start_at: Starting index
            expand: Properties to expand

        Returns:
            APIResponse with search results
        """
        payload: Dict[str, Any] = {
            "jql": jql,
            "maxResults": max_results,
            "startAt": start_at,
        }

        if fields:
            payload["fields"] = fields
        if expand:
            payload["expand"] = expand

        return await self.post("search", json=payload)

    async def search_all_issues(
        self,
        jql: str,
        fields: Optional[List[str]] = None,
        max_results: int = 1000,
    ) -> List[Dict[str, Any]]:
        """
        Search all issues matching JQL (handles pagination).

        Args:
            jql: JQL query string
            fields: Fields to return
            max_results: Maximum total results

        Returns:
            List of all matching issues
        """
        all_issues = []
        start_at = 0
        page_size = 100

        while len(all_issues) < max_results:
            response = await self.search_issues(
                jql=jql,
                fields=fields,
                max_results=min(page_size, max_results - len(all_issues)),
                start_at=start_at,
            )

            if not response.ok:
                break

            issues = response.data.get("issues", [])
            if not issues:
                break

            all_issues.extend(issues)
            start_at += len(issues)

            total = response.data.get("total", 0)
            if start_at >= total:
                break

        return all_issues

    async def list_projects(self) -> APIResponse:
        """List all accessible projects."""
        return await self.get("project")

    async def get_project(self, project_key: str) -> APIResponse:
        """Get project details."""
        return await self.get(f"project/{project_key}")

    async def assign_issue(
        self,
        issue_key: str,
        account_id: Optional[str] = None,
    ) -> APIResponse:
        """
        Assign issue to a user.

        Args:
            issue_key: Issue key
            account_id: Account ID of assignee (None to unassign)
        """
        return await self.put(
            f"issue/{issue_key}/assignee",
            json={"accountId": account_id},
        )

    async def get_user(self, account_id: str) -> APIResponse:
        """Get user details by account ID."""
        return await self.get("user", params={"accountId": account_id})

    async def search_users(
        self,
        query: str,
        max_results: int = 50,
    ) -> APIResponse:
        """Search for users."""
        return await self.get("user/search", params={
            "query": query,
            "maxResults": max_results,
        })
