"""
Jira Search Issues Module

Search issues using JQL query.
"""

import os
from typing import Any, Dict

from ....base import BaseModule
from ....registry import register_module
from ..integration import JiraIntegration


@register_module(
    module_id="integration.jira.search_issues",
    can_connect_to=['*'],
    can_receive_from=['*'],
    version="1.0.0",
    category="integration",
    tags=["integration", "jira", "search", "jql"],
    label="Search Jira Issues",
    label_key="modules.integration.jira.search_issues.label",
    description="Search issues using JQL query",
    description_key="modules.integration.jira.search_issues.description",
    icon="Search",
    color="#0052CC",
    input_types=["any"],
    output_types=["any"],
    timeout=60,
    retryable=True,
    concurrent_safe=True,
    requires_credentials=True,
    params_schema={
        "domain": {
            "type": "string",
            "label": "Jira Domain",
            "placeholder": "${env.JIRA_DOMAIN}",
            "required": True,
        },
        "jql": {
            "type": "string",
            "label": "JQL Query",
            "description": "JQL search query",
            "placeholder": "project = PROJ AND status = Open",
            "required": True,
        },
        "max_results": {
            "type": "number",
            "label": "Max Results",
            "default": 50,
            "min": 1,
            "max": 1000,
            "required": False,
        },
        "email": {
            "type": "string",
            "placeholder": "${env.JIRA_EMAIL}",
            "required": False,
        },
        "api_token": {
            "type": "string",
            "placeholder": "${env.JIRA_API_TOKEN}",
            "required": False,
            "sensitive": True,
        },
    },
    output_schema={
        "ok": {"type": "boolean"},
        "issues": {"type": "array"},
        "total": {"type": "number"},
    },
    author="Flyto Team",
    license="MIT",
)
class JiraSearchIssuesModule(BaseModule):
    """Search Jira issues module."""

    module_name = "Search Jira Issues"
    module_description = "Search issues using JQL"

    def validate_params(self):
        if not self.params.get("domain"):
            raise ValueError("Jira domain required")
        if not self.params.get("jql"):
            raise ValueError("JQL query required")

        self.domain = self.params["domain"]
        self.jql = self.params["jql"]
        self.max_results = self.params.get("max_results", 50)
        self.email = self.params.get("email") or os.getenv("JIRA_EMAIL")
        self.api_token = self.params.get("api_token") or os.getenv("JIRA_API_TOKEN")

    async def execute(self) -> Dict[str, Any]:
        async with JiraIntegration(
            domain=self.domain,
            email=self.email,
            api_token=self.api_token,
        ) as jira:
            response = await jira.search_issues(
                jql=self.jql,
                max_results=self.max_results,
                fields=["summary", "status", "priority", "assignee", "created", "updated"],
            )

            if response.ok:
                data = response.data
                issues = [
                    {
                        "key": issue.get("key"),
                        "summary": issue.get("fields", {}).get("summary"),
                        "status": issue.get("fields", {}).get("status", {}).get("name"),
                        "priority": issue.get("fields", {}).get("priority", {}).get("name"),
                        "assignee": issue.get("fields", {}).get("assignee", {}).get("displayName"),
                        "url": f"https://{self.domain}/browse/{issue.get('key')}",
                    }
                    for issue in data.get("issues", [])
                ]
                return {
                    "ok": True,
                    "issues": issues,
                    "total": data.get("total", 0),
                }
            else:
                return {
                    "ok": False,
                    "error": response.error,
                }
