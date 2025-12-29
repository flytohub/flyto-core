"""
Jira Create Issue Module

Create a new issue in Jira.
"""

import os
from typing import Any, Dict

from ....base import BaseModule
from ....registry import register_module
from ..integration import JiraIntegration


@register_module(
    module_id="integration.jira.create_issue",
    version="1.0.0",
    category="integration",
    tags=["integration", "jira", "issues", "project-management"],
    label="Create Jira Issue",
    description="Create a new issue in Jira",
    icon="CheckSquare",
    color="#0052CC",
    input_types=["any"],
    output_types=["any"],
    timeout=30,
    retryable=False,
    concurrent_safe=True,
    requires_credentials=True,
    params_schema={
        "domain": {
            "type": "string",
            "label": "Jira Domain",
            "description": "Your Jira Cloud domain (e.g., your-domain.atlassian.net)",
            "placeholder": "${env.JIRA_DOMAIN}",
            "required": True,
        },
        "project_key": {
            "type": "string",
            "label": "Project Key",
            "description": "Project key (e.g., PROJ)",
            "required": True,
        },
        "summary": {
            "type": "string",
            "label": "Summary",
            "description": "Issue summary/title",
            "required": True,
        },
        "issue_type": {
            "type": "select",
            "label": "Issue Type",
            "options": ["Task", "Bug", "Story", "Epic", "Subtask"],
            "default": "Task",
            "required": False,
        },
        "description": {
            "type": "text",
            "label": "Description",
            "description": "Issue description",
            "required": False,
        },
        "priority": {
            "type": "select",
            "label": "Priority",
            "options": ["Highest", "High", "Medium", "Low", "Lowest"],
            "required": False,
        },
        "labels": {
            "type": "array",
            "label": "Labels",
            "description": "Issue labels",
            "required": False,
        },
        "email": {
            "type": "string",
            "label": "Email",
            "placeholder": "${env.JIRA_EMAIL}",
            "required": False,
        },
        "api_token": {
            "type": "string",
            "label": "API Token",
            "placeholder": "${env.JIRA_API_TOKEN}",
            "required": False,
            "sensitive": True,
        },
    },
    output_schema={
        "ok": {"type": "boolean"},
        "key": {"type": "string"},
        "id": {"type": "string"},
        "url": {"type": "string"},
    },
    examples=[
        {
            "name": "Create bug report",
            "params": {
                "project_key": "PROJ",
                "summary": "Login button not working",
                "issue_type": "Bug",
                "priority": "High",
                "description": "Users cannot login after clicking the login button.",
            },
        },
    ],
    author="Flyto Team",
    license="MIT",
)
class JiraCreateIssueModule(BaseModule):
    """Create Jira issue module."""

    module_name = "Create Jira Issue"
    module_description = "Create a new issue in Jira"

    def validate_params(self):
        required = ["domain", "project_key", "summary"]
        for param in required:
            if not self.params.get(param):
                raise ValueError(f"Missing required parameter: {param}")

        self.domain = self.params["domain"]
        self.project_key = self.params["project_key"]
        self.summary = self.params["summary"]
        self.issue_type = self.params.get("issue_type", "Task")
        self.description = self.params.get("description")
        self.priority = self.params.get("priority")
        self.labels = self.params.get("labels")
        self.email = self.params.get("email") or os.getenv("JIRA_EMAIL")
        self.api_token = self.params.get("api_token") or os.getenv("JIRA_API_TOKEN")

        if not self.email or not self.api_token:
            raise ValueError("Jira credentials required (email + api_token)")

    async def execute(self) -> Dict[str, Any]:
        async with JiraIntegration(
            domain=self.domain,
            email=self.email,
            api_token=self.api_token,
        ) as jira:
            response = await jira.create_issue(
                project_key=self.project_key,
                summary=self.summary,
                issue_type=self.issue_type,
                description=self.description,
                priority=self.priority,
                labels=self.labels,
            )

            if response.ok:
                data = response.data
                return {
                    "ok": True,
                    "key": data.get("key"),
                    "id": data.get("id"),
                    "url": f"https://{self.domain}/browse/{data.get('key')}",
                }
            else:
                return {
                    "ok": False,
                    "error": response.error,
                }
