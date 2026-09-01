# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Salesforce Query Module

Execute SOQL query in Salesforce.

THERE IS NO SINGLE RUNG FOR THIS MODULE, and the reason is a defect rather than
a design. The two `fetch_all` branches do not have the same evidence available
to them, and one of them has almost none.

  fetch_all=False                                   ACCEPTED / FAILED
      `sf.query` hands back an `APIResponse`, so this branch can see the status
      line and the body. `records` is one page, `totalSize` is Salesforce's own
      count of the whole result set, and `done` says whether more pages exist.
      A refused query is FAILED -- a read alters nothing, so nothing is left in
      doubt, only data we do not have.

  fetch_all=True, records came back                 ACCEPTED
      At least the first page's request was answered, and the records are
      Salesforce's own report of what it holds.

  fetch_all=True, no records came back              INDETERMINATE
      This is the defect. `SalesforceIntegration.query_all` returns a bare
      `list`, and its loop does `if not response.ok: break` -- so a 401 on the
      first page, an expired token, an SSRF refusal and a query that genuinely
      matched nothing ALL arrive here as `[]`, with no status, no error and no
      way to tell them apart. The module then returns `ok: True` with
      `total_size: 0`, and the step is recorded as a success.

      `total_size` on this branch is `len(records)`, our own arithmetic over an
      empty list -- a value that is identical whether or not anything happened,
      which is exactly what `outcome.py` says may not carry a rung. So this
      path claims INDETERMINATE: the observation channel was severed inside
      `query_all` and this module cannot say what occurred.

      The honest fix is in `query_all`, not here: it should propagate the
      failed `APIResponse` instead of swallowing it. That is a change to a
      shared integration method with other callers, so it is reported rather
      than made, and the rung says plainly what the current code can support.
"""

import os
from typing import Any, Dict

from ....base import BaseModule
from ....registry import register_module
from ...base import resolve_credential
from ...outcomes import peer_answered, read_refused
from ..integration import SalesforceIntegration
from .....engine.outcome import ClaimBy, Outcome, envelope


def _fetch_all_outcome(record_count: int) -> Dict[str, Any]:
    """The rung for the `fetch_all=True` branch, where the status line is gone.

    `query_all` returns a bare list. Whatever `APIResponse` it saw -- 200, 401,
    a transport failure -- was consumed by `if not response.ok: break` and is
    not recoverable here, so the ONLY signal this branch has is how many
    records came back.

        records came back    ACCEPTED. Salesforce answered at least the first
                             page, and rows it materialised from bytes the
                             server sent cannot be produced by a failed
                             request.

        nothing came back    INDETERMINATE. `[]` reads identically for a query
                             that matched nothing, an expired token, and a
                             request that never left. `len(records) == 0` is
                             the same value whether or not the query ran, so it
                             is not evidence, and no rung may rest on it.

    INDETERMINATE and not FAILED: FAILED means a contract was evaluated and
    broken, and nothing here was evaluated. Nobody said the query would match
    anything, and an empty result set is an ordinary correct answer. What is
    wrong is that we cannot tell it from a refusal -- which is the textbook
    severed observation channel `engine/outcome.py` reserves this value for.
    """
    if record_count > 0:
        return envelope(
            Outcome.ACCEPTED,
            claim_by=ClaimBy.NONE,
            effects=[{
                "kind": "records_returned",
                "count": record_count,
                "measured_by": (
                    "len() over the list query_all accumulated from the pages "
                    "Salesforce returned"
                ),
                "detail": (
                    "Records came back, so Salesforce answered at least the first "
                    "page. query_all discards each page's status line, so the count "
                    "is all that survives: it is not known here how many pages were "
                    "fetched, nor whether the walk stopped early because a later "
                    "page was refused. A short result may be a complete answer or a "
                    "truncated one."
                ),
            }],
        )

    return envelope(
        Outcome.INDETERMINATE,
        claim_by=ClaimBy.NONE,
        effects=[{
            "kind": "records_indistinguishable_from_failure",
            "count": 0,
            "measured_by": None,
            "detail": (
                "query_all returned an empty list and no status. Its loop breaks on "
                "a failed page and returns what it has, so this reads identically "
                "for a query that matched nothing, an expired token, a refused host "
                "and a request that never left. total_size beside this is len() over "
                "that empty list -- this module's own arithmetic, unchanged whether "
                "or not the query ran. Nothing here says the query failed; what it "
                "says is that this module cannot tell."
            ),
        }],
    )


@register_module(
    module_id="integration.salesforce.query",
    can_connect_to=['*'],
    can_receive_from=['*'],
    version="1.0.0",
    category="integration",
    tags=["integration", "salesforce", "crm", "query", "soql", "ssrf_protected"],
    label="Salesforce Query",
    label_key="modules.integration.salesforce.query.label",
    description="Execute SOQL query in Salesforce",
    description_key="modules.integration.salesforce.query.description",
    icon="Search",
    color="#00A1E0",
    input_types=["any"],
    output_types=["any"],
    timeout_ms=60000,
    retryable=True,
    concurrent_safe=True,
    requires_credentials=True,
    credential_keys=['SALESFORCE_CLIENT_ID', 'SALESFORCE_CLIENT_SECRET'],
    params_schema={
        "instance_url": {
            "type": "string",
            "label": "Instance URL",
            "description": "Salesforce instance URL",
            "description_key": "modules.integration.salesforce.query.params.instance_url.description",
            "placeholder": "${env.SALESFORCE_INSTANCE_URL}",
            "required": True,
        },
        "soql": {
            "type": "text",
            "label": "SOQL Query",
            "description": "SOQL query string",
                "description_key": "modules.integration.salesforce.query.params.soql.description",
            "placeholder": "SELECT Id, Name FROM Account WHERE Industry = 'Technology' LIMIT 10",
            "required": True,
        },
        "fetch_all": {
            "type": "boolean",
            "label": "Fetch All Results",
            "description": "Automatically fetch all pages of results",
                "description_key": "modules.integration.salesforce.query.params.fetch_all.description",
            "default": False,
            "required": False,
        },
        "access_token": {
            "type": "string",
            "label": "Access Token",
            "placeholder": "${env.SALESFORCE_ACCESS_TOKEN}",
            "required": False,
            "sensitive": True,
        },
    },
    output_schema={
        "ok": {"type": "boolean", "description": "Whether the operation was successful"},
        "records": {"type": "array", "description": "Query result records"},
        "total_size": {
            "type": "number",
            "description": (
                "Salesforce's totalSize for a single-page query; len(records) when "
                "fetch_all is set, where it is this module's own arithmetic and not "
                "a number that crossed the wire"
            ),
        },
        "outcome": {
            "type": "object",
            "description": (
                'How far the query was followed, decided per return: "accepted" '
                'when Salesforce answered, "failed" when it refused a single-page '
                'query, "indeterminate" when fetch_all returned nothing -- '
                'query_all swallows a failed page, so an empty list there does not '
                'say whether the query ran'
            ),
        },
    },
    examples=[
        {
            "name": "Query Accounts",
            "params": {
                "soql": "SELECT Id, Name, Industry FROM Account LIMIT 10",
            },
        },
        {
            "name": "Query Contacts by Account",
            "params": {
                "soql": "SELECT Id, Name, Email FROM Contact WHERE AccountId = '001xx000003DGTWAA4'",
            },
        },
    ],
    author="Flyto2 Team",
    license="MIT",
)
class SalesforceQueryModule(BaseModule):
    """Salesforce query module."""

    module_name = "Salesforce Query"
    module_description = "Execute SOQL query in Salesforce"

    def validate_params(self) -> None:
        if not self.params.get("instance_url"):
            raise ValueError("Instance URL required")
        if not self.params.get("soql"):
            raise ValueError("SOQL query required")

        self.instance_url = self.params["instance_url"]
        self.soql = self.params["soql"]
        self.fetch_all = self.params.get("fetch_all", False)
        # `instance_url` is a caller parameter; the integration refuses to
        # carry an operator token to an instance the operator never configured,
        # and can only do so if it is told the token's origin.
        self.access_token, self.credentials_from_env = resolve_credential(
            self.params.get("access_token"), os.getenv("SALESFORCE_ACCESS_TOKEN")
        )

    async def execute(self) -> Dict[str, Any]:
        async with SalesforceIntegration(
            instance_url=self.instance_url,
            access_token=self.access_token,
            credentials_from_env=self.credentials_from_env,
        ) as sf:
            if self.fetch_all:
                records = await sf.query_all(self.soql)
                return {
                    "ok": True,
                    "records": records,
                    "total_size": len(records),
                    "outcome": _fetch_all_outcome(len(records)),
                }
            else:
                response = await sf.query(self.soql)

                if response.ok:
                    data = response.data
                    records = data.get("records", [])
                    return {
                        "ok": True,
                        "records": records,
                        "total_size": data.get("totalSize", 0),
                        "done": data.get("done", True),
                        "outcome": envelope(
                            Outcome.ACCEPTED,
                            claim_by=ClaimBy.NONE,
                            effects=[
                                peer_answered("salesforce", response.status),
                                {
                                    "kind": "records_returned",
                                    "count": len(records),
                                    "total_size": data.get("totalSize", 0),
                                    # False means the totalSize beside it was
                                    # written here rather than sent.
                                    "total_size_reported": "totalSize" in data,
                                    "done": data.get("done"),
                                    "done_reported": "done" in data,
                                    "measured_by": (
                                        "len() over the records array Salesforce "
                                        "returned, and totalSize in that same body"
                                    ),
                                    "detail": (
                                        "count is one page: Salesforce caps a query "
                                        "response at 2000 records and hands back a "
                                        "nextRecordsUrl this branch never follows, so "
                                        "count and total_size differ whenever done is "
                                        "false. Both are Salesforce's report of its "
                                        "own data, read once, with nothing "
                                        "corroborating them."
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
                            service="salesforce",
                            status=response.status,
                            resource="records",
                            error=response.error,
                        ),
                    }
