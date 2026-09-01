# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Salesforce Update Record Module

Update an existing record in Salesforce.

HOW FAR THE UPDATE IS FOLLOWED

ACCEPTED, and this is the thinnest evidence in the group -- worth saying out
loud rather than hiding behind a rung that looks like the others. A successful
Salesforce PATCH answers **204 No Content**. There is no body. Nothing names the
record, nothing echoes a field, nothing reports a count. The entire measurement
is a status line, which is the definition of "the other side acknowledged taking
it": ACCEPTED, exactly, and not one step further.

What is NOT known on this path: whether the values now stored are the values
sent, whether any field was silently dropped by a validation rule or field-level
security, and whether the record was already in that state. Reaching OBSERVED
would take a GET of the record and a comparison, and this module makes one
request.

THE PAYLOAD IS `{"ok": True}` -- literally nothing else, so before this change a
consumer had no field at all that distinguished a real 204 from a step that ran.
The envelope is now that field.

THE ERROR PATH splits on whether the record may have changed. A 4xx is
Salesforce refusing by name and writing nothing: FAILED. A 5xx, or no reply,
leaves an update that may have landed: INDETERMINATE. That matters more here
than for a create, because `retryable=True` on this module means the engine will
re-run the PATCH -- which is safe only because the same PATCH twice is the same
end state, not because anything confirmed the first one.
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
    module_id="integration.salesforce.update_record",
    can_connect_to=['*'],
    can_receive_from=['*'],
    version="1.0.0",
    category="integration",
    tags=["integration", "salesforce", "crm", "update", "ssrf_protected"],
    label="Update Salesforce Record",
    label_key="modules.integration.salesforce.update_record.label",
    description="Update an existing record in Salesforce",
    description_key="modules.integration.salesforce.update_record.description",
    icon="Edit",
    color="#00A1E0",
    input_types=["any"],
    output_types=["any"],
    timeout_ms=30000,
    retryable=True,
    concurrent_safe=True,
    requires_credentials=True,
    credential_keys=['SALESFORCE_CLIENT_ID', 'SALESFORCE_CLIENT_SECRET'],
    params_schema={
        "instance_url": {
            "type": "string",
            "label": "Instance URL",
            "description": "Salesforce instance URL",
            "description_key": "modules.integration.salesforce.update_record.params.instance_url.description",
            "placeholder": "${env.SALESFORCE_INSTANCE_URL}",
            "required": True,
        },
        "sobject": {
            "type": "select",
            "label": "Object Type",
            "options": ["Account", "Contact", "Lead", "Opportunity", "Case", "Task", "Event"],
            "required": True,
        },
        "record_id": {
            "type": "string",
            "label": "Record ID",
            "description": "Salesforce record ID (18 characters)",
                "description_key": "modules.integration.salesforce.update_record.params.record_id.description",
            "required": True,
        },
        "data": {
            "type": "object",
            "label": "Update Data",
            "description": "Fields to update",
                "description_key": "modules.integration.salesforce.update_record.params.data.description",
            "required": True,
        },
        "access_token": {
            "type": "string",
            "placeholder": "${env.SALESFORCE_ACCESS_TOKEN}",
            "required": False,
            "sensitive": True,
        },
    },
    output_schema={
        "ok": {"type": "boolean", "description": "Whether the operation was successful"},
        "outcome": {
            "type": "object",
            "description": (
                'How far the update was followed: "accepted" when Salesforce '
                'answered 204, "failed" when it refused by name, "indeterminate" '
                'when a 5xx or no reply left an update that may have landed. Never '
                'higher -- a 204 carries no body and the record is never read back'
            ),
        },
    },
    author="Flyto2 Team",
    license="MIT",
)
class SalesforceUpdateRecordModule(BaseModule):
    """Update Salesforce record module."""

    module_name = "Update Salesforce Record"
    module_description = "Update an existing record in Salesforce"

    def validate_params(self) -> None:
        required = ["instance_url", "sobject", "record_id", "data"]
        for param in required:
            if not self.params.get(param):
                raise ValueError(f"Missing required parameter: {param}")

        self.instance_url = self.params["instance_url"]
        self.sobject = self.params["sobject"]
        self.record_id = self.params["record_id"]
        self.data = self.params["data"]
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
            response = await sf.update(self.sobject, self.record_id, self.data)

            # Salesforce returns 204 No Content on successful update
            if response.ok or response.status == 204:
                return {
                    "ok": True,
                    "outcome": envelope(
                        Outcome.ACCEPTED,
                        claim_by=ClaimBy.NONE,
                        effects=[
                            peer_answered("salesforce", response.status),
                            {
                                "kind": "record_update_accepted",
                                "sobject": self.sobject,
                                "record_id": self.record_id,
                                "fields_sent": sorted(self.data)
                                if isinstance(self.data, dict) else None,
                                "measured_by": (
                                    "APIResponse.status alone -- a successful "
                                    "Salesforce PATCH is 204 No Content and carries "
                                    "no body"
                                ),
                                "detail": (
                                    "Salesforce accepted the patch. That is the whole "
                                    "of the evidence: no body came back, so nothing "
                                    "names the record, echoes a field or reports a "
                                    "count. The record_id and fields_sent here are "
                                    "this module's own inputs, listed so a reader can "
                                    "see what was asked for -- they are not a "
                                    "measurement and they read identically whether "
                                    "the values landed, were dropped by a validation "
                                    "rule, or were already set."
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
                        operation="record_update",
                        error=response.error,
                        retry_note=(
                            "This module sets retryable=True, so the engine may re-run "
                            "the PATCH. That is safe only because the same PATCH twice "
                            "is the same end state, not because the first one was "
                            "confirmed."
                        ),
                    ),
                }
