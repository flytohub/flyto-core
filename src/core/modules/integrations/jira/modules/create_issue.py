# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Jira Create Issue Module

Create a new issue in Jira.

HOW FAR THE CREATE IS FOLLOWED

ACCEPTED on the path that returns a key. Jira answers the POST with an issue
object carrying a `key` and an `id` that this module could not have produced
from its own inputs -- server-assigned, so more than an echo of the summary
that was sent, which is what puts it above DISPATCHED.

It is not OBSERVED, and a created issue is where that temptation is strongest:
a 201 body is the peer reporting on its own work. To observe the issue this
module would have to GET it back and compare. It sends one request and reads
the reply to that request, exactly like `api.github.create_issue`, which
settled the identical question the identical way.

Two things in the payload are NOT evidence and are named as such in the
effects. `url` is built here out of the caller's own `domain` and whatever key
came back -- an f-string, not a measurement; it is a well-formed URL even when
`key` is None. And nothing checks that the fields Jira stored are the fields
requested: priority, labels and issue type are sent and never read back.

THE ERROR PATH now says which kind of failure it was. A 4xx is Jira refusing by
name and creating nothing (FAILED); a 5xx or no reply at all leaves an issue
that may exist (INDETERMINATE). `retryable=False` on this module is right for
exactly that reason, and it is only half the story: `BaseIntegration._request`
retries the POST itself up to `max_retries` times on a transport error, so
`status == 0` can mean up to three issues, not one.
"""

import os
from typing import Any, Dict

from ....base import BaseModule
from ....registry import register_module
from ...base import resolve_credential
from ...outcomes import mutation_unconfirmed, peer_answered
from ..integration import JiraIntegration
from .....engine.outcome import ClaimBy, Outcome, envelope


@register_module(
    module_id="integration.jira.create_issue",
    can_connect_to=['*'],
    can_receive_from=['*'],
    version="1.0.0",
    category="integration",
    tags=["integration", "jira", "issues", "project-management", "ssrf_protected"],
    label="Create Jira Issue",
    label_key="modules.integration.jira.create_issue.label",
    description="Create a new issue in Jira",
    description_key="modules.integration.jira.create_issue.description",
    icon="CheckSquare",
    color="#0052CC",
    input_types=["any"],
    output_types=["any"],
    timeout_ms=30000,
    retryable=False,
    concurrent_safe=True,
    requires_credentials=True,
    credential_keys=['JIRA_TOKEN', 'JIRA_EMAIL'],
    params_schema={
        "domain": {
            "type": "string",
            "label": "Jira Domain",
            "description": "Your Jira Cloud domain (e.g., your-domain.atlassian.net)",
                "description_key": "modules.integration.jira.create_issue.params.domain.description",
            "placeholder": "${env.JIRA_DOMAIN}",
            "required": True,
        },
        "project_key": {
            "type": "string",
            "label": "Project Key",
            "description": "Project key (e.g., PROJ)",
                "description_key": "modules.integration.jira.create_issue.params.project_key.description",
            "required": True,
        },
        "summary": {
            "type": "string",
            "label": "Summary",
            "description": "Issue summary/title",
                "description_key": "modules.integration.jira.create_issue.params.summary.description",
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
                "description_key": "modules.integration.jira.create_issue.params.description.description",
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
                "description_key": "modules.integration.jira.create_issue.params.labels.description",
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
        "ok": {"type": "boolean", "description": "Whether the operation was successful"},
        "key": {"type": "string", "description": "Issue key (e.g., PROJ-123)"},
        "id": {"type": "string", "description": "Issue ID"},
        "url": {
            "type": "string",
            "description": (
                "Issue URL, built here from the domain parameter and the returned "
                "key. Not a value Jira sent, and well-formed even when no key came "
                "back"
            ),
        },
        "outcome": {
            "type": "object",
            "description": (
                'How far the create was followed: "accepted" when Jira answered '
                'with a key it assigned, "failed" when Jira refused by name, '
                '"indeterminate" when a 5xx or no reply left an issue that may '
                'exist. Never higher -- the issue is never read back'
            ),
        },
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
    author="Flyto2 Team",
    license="MIT",
)
class JiraCreateIssueModule(BaseModule):
    """Create Jira issue module."""

    module_name = "Create Jira Issue"
    module_description = "Create a new issue in Jira"

    def validate_params(self) -> None:
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

        if not self.email or not self.api_token:
            raise ValueError("Jira credentials required (email + api_token)")

    async def execute(self) -> Dict[str, Any]:
        async with JiraIntegration(
            domain=self.domain,
            email=self.email,
            api_token=self.api_token,
            credentials_from_env=self.credentials_from_env,
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
                key = data.get("key")
                return {
                    "ok": True,
                    "key": key,
                    "id": data.get("id"),
                    "url": f"https://{self.domain}/browse/{key}",
                    "outcome": envelope(
                        Outcome.ACCEPTED,
                        claim_by=ClaimBy.NONE,
                        effects=[
                            peer_answered("jira", response.status),
                            {
                                "kind": "issue_reported_created",
                                "key": key,
                                "id": data.get("id"),
                                # Whether the two identifiers were actually
                                # there. A `key` of None is what `data.get`
                                # returns for a 2xx body that named nothing,
                                # and it reads the same as a real key to
                                # anything that only checks the rung.
                                "key_reported": "key" in data,
                                "id_reported": "id" in data,
                                "measured_by": (
                                    "key and id in the body Jira returned to this POST"
                                ),
                                "detail": (
                                    "Jira asserting that it created an issue, and "
                                    "naming it. Server-assigned, so more than an echo "
                                    "of the summary sent -- and still the peer "
                                    "reporting on its own work, so it is not an "
                                    "observation. Nothing reads the issue back, and "
                                    "nothing checks that the priority, labels and "
                                    "issue type stored are the ones requested."
                                ),
                            },
                            {
                                "kind": "issue_url_constructed",
                                "measured_by": None,
                                "detail": (
                                    "The url beside this is an f-string over the "
                                    "caller's own domain parameter and whatever key "
                                    "came back. No request was made to it and nothing "
                                    "confirms it resolves; it is well-formed even when "
                                    "key is None."
                                ),
                            },
                        ],
                    ),
                }
            else:
                return {
                    "ok": False,
                    "error": response.error,
                    "outcome": mutation_unconfirmed(
                        service="jira",
                        status=response.status,
                        operation="issue_create",
                        error=response.error,
                        retry_note=(
                            "This module sets retryable=False so the engine will not "
                            "re-run it, but BaseIntegration._request already retried "
                            "the POST itself, so more than one issue may exist."
                        ),
                    ),
                }
