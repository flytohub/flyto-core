"""
Salesforce Query Module

Execute SOQL query in Salesforce.
"""

import os
from typing import Any, Dict

from ....base import BaseModule
from ....registry import register_module
from ..integration import SalesforceIntegration


@register_module(
    module_id="integration.salesforce.query",
    can_connect_to=['*'],
    can_receive_from=['*'],
    version="1.0.0",
    category="integration",
    tags=["integration", "salesforce", "crm", "query", "soql"],
    label="Salesforce Query",
    label_key="modules.integration.salesforce.query.label",
    description="Execute SOQL query in Salesforce",
    description_key="modules.integration.salesforce.query.description",
    icon="Search",
    color="#00A1E0",
    input_types=["any"],
    output_types=["any"],
    timeout=60,
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
        "ok": {"type": "boolean"},
        "records": {"type": "array"},
        "total_size": {"type": "number"},
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
    author="Flyto Team",
    license="MIT",
)
class SalesforceQueryModule(BaseModule):
    """Salesforce query module."""

    module_name = "Salesforce Query"
    module_description = "Execute SOQL query in Salesforce"

    def validate_params(self):
        if not self.params.get("instance_url"):
            raise ValueError("Instance URL required")
        if not self.params.get("soql"):
            raise ValueError("SOQL query required")

        self.instance_url = self.params["instance_url"]
        self.soql = self.params["soql"]
        self.fetch_all = self.params.get("fetch_all", False)
        self.access_token = (
            self.params.get("access_token")
            or os.getenv("SALESFORCE_ACCESS_TOKEN")
        )

    async def execute(self) -> Dict[str, Any]:
        async with SalesforceIntegration(
            instance_url=self.instance_url,
            access_token=self.access_token,
        ) as sf:
            if self.fetch_all:
                records = await sf.query_all(self.soql)
                return {
                    "ok": True,
                    "records": records,
                    "total_size": len(records),
                }
            else:
                response = await sf.query(self.soql)

                if response.ok:
                    data = response.data
                    return {
                        "ok": True,
                        "records": data.get("records", []),
                        "total_size": data.get("totalSize", 0),
                        "done": data.get("done", True),
                    }
                else:
                    return {
                        "ok": False,
                        "error": response.error,
                    }
