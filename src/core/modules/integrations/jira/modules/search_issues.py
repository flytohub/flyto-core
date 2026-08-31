# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Jira Search Issues Module

Search issues using JQL query.

HOW FAR THE SEARCH IS FOLLOWED

ACCEPTED. Jira answered and handed back issue objects; nothing here reads
anything a second time, and for a search there is nothing to read back -- the
reply is the whole of what happened.

TWO NUMBERS, AND THEY ANSWER DIFFERENT QUESTIONS. `len(issues)` is one page:
`max_results` caps it, `startAt` is never advanced, and no cursor is followed.
`total` is Jira's own count of everything the JQL matched. Reporting the first
as if it were the second is `database.query`'s row-count trap, so both travel
in the effect with the page size that bounded them.

`total` has a second edge worth naming. It is read as `data.get("total", 0)`,
so when a Jira response omits the field the 0 that lands in the payload is a
literal written in this module, not a number that crossed the wire -- and 0
matching issues and "Jira did not say" read identically afterwards. The effect
carries `total_reported` so the two stay distinguishable.

THE ERROR PATH IS FAILED, never indeterminate: a search that Jira refused
returned no issues and altered nothing, so there is no effect left in doubt --
only data we do not have.
"""

import os
from typing import Any, Dict

from ....base import BaseModule
from ....registry import register_module
from ...base import resolve_credential
from ...outcomes import peer_answered, read_refused
from ..integration import JiraIntegration
from .....engine.outcome import ClaimBy, Outcome, envelope


@register_module(
    module_id="integration.jira.search_issues",
    can_connect_to=['*'],
    can_receive_from=['*'],
    version="1.0.0",
    category="integration",
    tags=["integration", "jira", "search", "jql", "ssrf_protected"],
    label="Search Jira Issues",
    label_key="modules.integration.jira.search_issues.label",
    description="Search issues using JQL query",
    description_key="modules.integration.jira.search_issues.description",
    icon="Search",
    color="#0052CC",
    input_types=["any"],
    output_types=["any"],
    timeout_ms=60000,
    retryable=True,
    concurrent_safe=True,
    requires_credentials=True,
    credential_keys=['JIRA_TOKEN', 'JIRA_EMAIL'],
    params_schema={
        "domain": {
            "type": "string",
            "label": "Jira Domain",
            "description": "Your Jira Cloud domain (e.g., your-domain.atlassian.net)",
            "description_key": "modules.integration.jira.search_issues.params.domain.description",
            "placeholder": "${env.JIRA_DOMAIN}",
            "required": True,
        },
        "jql": {
            "type": "string",
            "label": "JQL Query",
            "description": "JQL search query",
                "description_key": "modules.integration.jira.search_issues.params.jql.description",
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
        "ok": {"type": "boolean", "description": "Whether the operation was successful"},
        "issues": {
            "type": "array",
            "description": (
                "One page of matching issues, bounded by max_results. Not the "
                "whole result set -- no paging is done here"
            ),
        },
        "total": {
            "type": "number",
            "description": (
                "Jira's own count of matching issues, or a literal 0 when the "
                "response omitted the field -- see outcome.effects.total_reported"
            ),
        },
        "outcome": {
            "type": "object",
            "description": (
                'How far the search was followed: "accepted" when Jira answered, '
                '"failed" when it did not. Never higher -- one request, its reply, '
                'and nothing read back'
            ),
        },
    },
    author="Flyto2 Team",
    license="MIT",
)
class JiraSearchIssuesModule(BaseModule):
    """Search Jira issues module."""

    module_name = "Search Jira Issues"
    module_description = "Search issues using JQL"

    def validate_params(self) -> None:
        if not self.params.get("domain"):
            raise ValueError("Jira domain required")
        if not self.params.get("jql"):
            raise ValueError("JQL query required")

        self.domain = self.params["domain"]
        self.jql = self.params["jql"]
        self.max_results = self.params.get("max_results", 50)
        self.email, email_from_env = resolve_credential(
            self.params.get("email"), os.getenv("JIRA_EMAIL")
        )
        self.api_token, token_from_env = resolve_credential(
            self.params.get("api_token"), os.getenv("JIRA_API_TOKEN")
        )
        # `domain` is a caller parameter; the integration refuses to carry an
        # operator credential to a domain the operator never configured, and
        # can only do so if it is told the credential's origin.
        self.credentials_from_env = email_from_env or token_from_env

    async def execute(self) -> Dict[str, Any]:
        async with JiraIntegration(
            domain=self.domain,
            email=self.email,
            api_token=self.api_token,
            credentials_from_env=self.credentials_from_env,
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
                    "outcome": envelope(
                        Outcome.ACCEPTED,
                        claim_by=ClaimBy.NONE,
                        effects=[
                            peer_answered("jira", response.status),
                            {
                                "kind": "issues_returned",
                                "count": len(issues),
                                "max_results_requested": self.max_results,
                                "total": data.get("total", 0),
                                # False means the 0 beside it was written here,
                                # not sent by Jira. Newer Jira Cloud search
                                # endpoints omit `total` entirely.
                                "total_reported": "total" in data,
                                "measured_by": (
                                    "len() over the issues array Jira returned, and "
                                    "the total field of that same body"
                                ),
                                "detail": (
                                    "count is ONE PAGE -- max_results bounds it, "
                                    "startAt is never advanced, and no cursor is "
                                    "followed -- while total is Jira's own count of "
                                    "everything the JQL matched. When total_reported "
                                    "is false, the total beside it is a literal 0 "
                                    "from this module and says nothing about the "
                                    "result set."
                                ),
                            },
                        ],
                    ),
                }
            else:
                return {
                    "ok": False,
                    "error": response.error,
                    "outcome": read_refused(
                        service="jira",
                        status=response.status,
                        resource="issues",
                        error=response.error,
                    ),
                }
