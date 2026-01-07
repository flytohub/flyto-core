"""
Salesforce Update Record Module

Update an existing record in Salesforce.
"""

import os
from typing import Any, Dict

from ....base import BaseModule
from ....registry import register_module
from ..integration import SalesforceIntegration


@register_module(
    module_id="integration.salesforce.update_record",
    can_connect_to=['*'],
    can_receive_from=['*'],
    version="1.0.0",
    category="integration",
    tags=["integration", "salesforce", "crm", "update"],
    label="Update Salesforce Record",
    label_key="modules.integration.salesforce.update_record.label",
    description="Update an existing record in Salesforce",
    description_key="modules.integration.salesforce.update_record.description",
    icon="Edit",
    color="#00A1E0",
    input_types=["any"],
    output_types=["any"],
    timeout=30,
    retryable=True,
    concurrent_safe=True,
    requires_credentials=True,
    params_schema={
        "instance_url": {
            "type": "string",
            "label": "Instance URL",
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
            "required": True,
        },
        "data": {
            "type": "object",
            "label": "Update Data",
            "description": "Fields to update",
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
        "ok": {"type": "boolean"},
    },
    author="Flyto Team",
    license="MIT",
)
class SalesforceUpdateRecordModule(BaseModule):
    """Update Salesforce record module."""

    module_name = "Update Salesforce Record"
    module_description = "Update an existing record in Salesforce"

    def validate_params(self):
        required = ["instance_url", "sobject", "record_id", "data"]
        for param in required:
            if not self.params.get(param):
                raise ValueError(f"Missing required parameter: {param}")

        self.instance_url = self.params["instance_url"]
        self.sobject = self.params["sobject"]
        self.record_id = self.params["record_id"]
        self.data = self.params["data"]
        self.access_token = (
            self.params.get("access_token")
            or os.getenv("SALESFORCE_ACCESS_TOKEN")
        )

    async def execute(self) -> Dict[str, Any]:
        async with SalesforceIntegration(
            instance_url=self.instance_url,
            access_token=self.access_token,
        ) as sf:
            response = await sf.update(self.sobject, self.record_id, self.data)

            # Salesforce returns 204 No Content on successful update
            if response.ok or response.status == 204:
                return {"ok": True}
            else:
                return {
                    "ok": False,
                    "error": response.error,
                }
