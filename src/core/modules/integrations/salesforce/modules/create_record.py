# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Salesforce Create Record Module

Create a new record in Salesforce.

HOW FAR THE CREATE IS FOLLOWED

ACCEPTED. Salesforce answers the POST with `{"id": "003...", "success": true}`,
and that id is server-assigned -- this module could not have produced it from
the field values it sent, which is what puts the claim above DISPATCHED. It is
not OBSERVED: the record is never read back, and nothing checks that the fields
Salesforce stored are the fields requested.

THE `success` FIELD IS THE TRAP HERE, and it is a live one. The payload reads
`data.get("success", True)`, so a 2xx body that never mentioned success arrives
downstream as `success: true` -- a value invented in this module that reads
identically to Salesforce's own. The rung does not rest on it. `success_reported`
in the effect says whether the flag crossed the wire, and `success_flag` says
what it was.

THE ERROR PATH splits on whether the record may exist. A 4xx (a validation
rule, a required field, a bad sobject) is Salesforce refusing by name and
creating nothing: FAILED. A 5xx, or no reply at all, leaves a record that may
exist: INDETERMINATE. `retryable=False` on this module is right for that
reason; note that `BaseIntegration._request` still retries the POST itself on a
transport error, so `status == 0` can mean more than one record.
"""

import os
from typing import Any, Dict

from ....base import BaseModule
from ....registry import register_module
from ...base import resolve_credential
from ...outcomes import mutation_unconfirmed, peer_answered
from ..integration import SalesforceIntegration
from .....engine.outcome import ClaimBy, Outcome, envelope


@register_module(
    module_id="integration.salesforce.create_record",
    can_connect_to=['*'],
    can_receive_from=['*'],
    version="1.0.0",
    category="integration",
    tags=["integration", "salesforce", "crm", "create", "ssrf_protected"],
    label="Create Salesforce Record",
    label_key="modules.integration.salesforce.create_record.label",
    description="Create a new record in Salesforce",
    description_key="modules.integration.salesforce.create_record.description",
    icon="Database",
    color="#00A1E0",
    input_types=["any"],
    output_types=["any"],
    timeout_ms=30000,
    retryable=False,
    concurrent_safe=True,
    requires_credentials=True,
    credential_keys=['SALESFORCE_CLIENT_ID', 'SALESFORCE_CLIENT_SECRET'],
    params_schema={
        "instance_url": {
            "type": "string",
            "label": "Instance URL",
            "description": "Salesforce instance URL",
                "description_key": "modules.integration.salesforce.create_record.params.instance_url.description",
            "placeholder": "${env.SALESFORCE_INSTANCE_URL}",
            "required": True,
        },
        "sobject": {
            "type": "select",
            "label": "Object Type",
            "options": ["Account", "Contact", "Lead", "Opportunity", "Case", "Task", "Event"],
            "default": "Lead",
            "required": True,
        },
        "data": {
            "type": "object",
            "label": "Record Data",
            "description": "Field values for the record",
                "description_key": "modules.integration.salesforce.create_record.params.data.description",
            "required": True,
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
        "id": {"type": "string", "description": "Created record ID, assigned by Salesforce"},
        "success": {
            "type": "boolean",
            "description": (
                "Salesforce success status, or a literal true when the body omitted "
                "it -- see outcome.effects.success_reported"
            ),
        },
        "outcome": {
            "type": "object",
            "description": (
                'How far the create was followed: "accepted" when Salesforce '
                'answered with an id it assigned, "failed" when it refused by '
                'name, "indeterminate" when a 5xx or no reply left a record that '
                'may exist. Never higher -- the record is never read back'
            ),
        },
    },
    examples=[
        {
            "name": "Create Lead",
            "params": {
                "sobject": "Lead",
                "data": {
                    "FirstName": "John",
                    "LastName": "Doe",
                    "Company": "Acme Corp",
                    "Email": "sales@flyto2.com",
                },
            },
        },
    ],
    author="Flyto2 Team",
    license="MIT",
)
class SalesforceCreateRecordModule(BaseModule):
    """Create Salesforce record module."""

    module_name = "Create Salesforce Record"
    module_description = "Create a new record in Salesforce"

    def validate_params(self) -> None:
        if not self.params.get("instance_url"):
            raise ValueError("Instance URL required")
        if not self.params.get("sobject"):
            raise ValueError("Object type required")
        if not self.params.get("data"):
            raise ValueError("Record data required")

        self.instance_url = self.params["instance_url"]
        self.sobject = self.params["sobject"]
        self.data = self.params["data"]
        # `instance_url` is a caller parameter; the integration refuses to
        # carry an operator token to an instance the operator never configured,
        # and can only do so if it is told the token's origin.
        self.access_token, self.credentials_from_env = resolve_credential(
            self.params.get("access_token"), os.getenv("SALESFORCE_ACCESS_TOKEN")
        )

        if not self.access_token:
            raise ValueError("Salesforce access token required")

    async def execute(self) -> Dict[str, Any]:
        async with SalesforceIntegration(
            instance_url=self.instance_url,
            access_token=self.access_token,
            credentials_from_env=self.credentials_from_env,
        ) as sf:
            response = await sf.create(self.sobject, self.data)

            if response.ok:
                data = response.data
                return {
                    "ok": True,
                    "id": data.get("id"),
                    "success": data.get("success", True),
                    "outcome": envelope(
                        Outcome.ACCEPTED,
                        claim_by=ClaimBy.NONE,
                        effects=[
                            peer_answered("salesforce", response.status),
                            {
                                "kind": "record_reported_created",
                                "sobject": self.sobject,
                                "record_id": data.get("id"),
                                "id_reported": "id" in data,
                                # The `success` in the payload defaults to True.
                                # These two keep "Salesforce said so" and "this
                                # module filled it in" apart.
                                "success_reported": "success" in data,
                                "success_flag": data.get("success"),
                                "measured_by": (
                                    "id and success in the body Salesforce returned "
                                    "to this POST"
                                ),
                                "detail": (
                                    "Salesforce asserting that it created a record, "
                                    "and naming it. The id is server-assigned, so it "
                                    "is more than an echo of the field values sent -- "
                                    "and still the peer reporting on its own work, so "
                                    "it is not an observation. The record is not read "
                                    "back and no field is compared with what was "
                                    "requested. When success_reported is false, the "
                                    "success beside this is a default written in this "
                                    "module."
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
                        service="salesforce",
                        status=response.status,
                        operation="record_create",
                        error=response.error,
                        retry_note=(
                            "This module sets retryable=False so the engine will not "
                            "re-run it, but BaseIntegration._request already retried "
                            "the POST itself, so more than one record may exist."
                        ),
                    ),
                }
