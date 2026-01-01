"""
Salesforce Create Record Module

Create a new record in Salesforce.
"""

import os
from typing import Any, Dict

from ....base import BaseModule
from ....registry import register_module
from ..integration import SalesforceIntegration


@register_module(
    module_id="integration.salesforce.create_record",
    can_connect_to=['*'],
    can_receive_from=['*'],
    version="1.0.0",
    category="integration",
    tags=["integration", "salesforce", "crm", "create"],
    label="Create Salesforce Record",
    description="Create a new record in Salesforce",
    icon="Database",
    color="#00A1E0",
    input_types=["any"],
    output_types=["any"],
    timeout=30,
    retryable=False,
    concurrent_safe=True,
    requires_credentials=True,
    params_schema={
        "instance_url": {
            "type": "string",
            "label": "Instance URL",
            "description": "Salesforce instance URL",
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
        "ok": {"type": "boolean"},
        "id": {"type": "string"},
        "success": {"type": "boolean"},
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
                    "Email": "john.doe@acme.com",
                },
            },
        },
    ],
    author="Flyto Team",
    license="MIT",
)
class SalesforceCreateRecordModule(BaseModule):
    """Create Salesforce record module."""

    module_name = "Create Salesforce Record"
    module_description = "Create a new record in Salesforce"

    def validate_params(self):
        if not self.params.get("instance_url"):
            raise ValueError("Instance URL required")
        if not self.params.get("sobject"):
            raise ValueError("Object type required")
        if not self.params.get("data"):
            raise ValueError("Record data required")

        self.instance_url = self.params["instance_url"]
        self.sobject = self.params["sobject"]
        self.data = self.params["data"]
        self.access_token = (
            self.params.get("access_token")
            or os.getenv("SALESFORCE_ACCESS_TOKEN")
        )

        if not self.access_token:
            raise ValueError("Salesforce access token required")

    async def execute(self) -> Dict[str, Any]:
        async with SalesforceIntegration(
            instance_url=self.instance_url,
            access_token=self.access_token,
        ) as sf:
            response = await sf.create(self.sobject, self.data)

            if response.ok:
                data = response.data
                return {
                    "ok": True,
                    "id": data.get("id"),
                    "success": data.get("success", True),
                }
            else:
                return {
                    "ok": False,
                    "error": response.error,
                }
