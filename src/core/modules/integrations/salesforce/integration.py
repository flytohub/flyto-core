"""
Salesforce Integration

Core Salesforce REST API integration class.
"""

import logging
import os
from typing import Any, Dict, List, Optional

from ..base import PaginatedIntegration, IntegrationConfig, APIResponse

logger = logging.getLogger(__name__)


class SalesforceIntegration(PaginatedIntegration):
    """
    Salesforce REST API integration.

    Usage:
        async with SalesforceIntegration(
            instance_url="https://yourorg.salesforce.com",
            access_token="your_access_token",
        ) as sf:
            # Create a lead
            await sf.create("Lead", {
                "FirstName": "John",
                "LastName": "Doe",
                "Company": "Acme Corp",
            })

            # Query records
            await sf.query("SELECT Id, Name FROM Account LIMIT 10")
    """

    service_name = "salesforce"
    api_version = "v59.0"

    def __init__(
        self,
        instance_url: Optional[str] = None,
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
    ):
        """
        Initialize Salesforce integration.

        Args:
            instance_url: Salesforce instance URL (e.g., https://yourorg.salesforce.com)
            access_token: OAuth access token
            refresh_token: OAuth refresh token for auto-refresh
            client_id: Connected App client ID (for refresh)
            client_secret: Connected App client secret (for refresh)
        """
        self.instance_url = (
            instance_url
            or os.getenv("SALESFORCE_INSTANCE_URL")
            or "https://login.salesforce.com"
        )
        self.refresh_token = refresh_token
        self.client_id = client_id or os.getenv("SALESFORCE_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("SALESFORCE_CLIENT_SECRET")

        token = access_token or os.getenv("SALESFORCE_ACCESS_TOKEN")

        base_url = f"{self.instance_url.rstrip('/')}/services/data"
        config = IntegrationConfig(
            service_name="salesforce",
            base_url=base_url,
            api_version=self.api_version,
            rate_limit_calls=100,
            rate_limit_period=60,
        )

        super().__init__(access_token=token, config=config)

    def _get_auth_header(self) -> Dict[str, str]:
        """Get Salesforce authorization header."""
        if self.access_token:
            return {"Authorization": f"Bearer {self.access_token}"}
        return {}

    # CRUD Operations

    async def create(
        self,
        sobject: str,
        data: Dict[str, Any],
    ) -> APIResponse:
        """
        Create a new record.

        Args:
            sobject: Object type (Account, Contact, Lead, etc.)
            data: Field values

        Returns:
            APIResponse with created record ID
        """
        return await self.post(f"sobjects/{sobject}", json=data)

    async def get(
        self,
        sobject: str,
        record_id: str,
        fields: Optional[List[str]] = None,
    ) -> APIResponse:
        """
        Get a record by ID.

        Args:
            sobject: Object type
            record_id: Record ID
            fields: Specific fields to retrieve

        Returns:
            APIResponse with record data
        """
        endpoint = f"sobjects/{sobject}/{record_id}"
        params = {}
        if fields:
            params["fields"] = ",".join(fields)
        return await super().get(endpoint, params=params)

    async def update(
        self,
        sobject: str,
        record_id: str,
        data: Dict[str, Any],
    ) -> APIResponse:
        """
        Update a record.

        Args:
            sobject: Object type
            record_id: Record ID
            data: Fields to update

        Returns:
            APIResponse with result
        """
        return await self.patch(f"sobjects/{sobject}/{record_id}", json=data)

    async def upsert(
        self,
        sobject: str,
        external_id_field: str,
        external_id: str,
        data: Dict[str, Any],
    ) -> APIResponse:
        """
        Upsert a record using external ID.

        Args:
            sobject: Object type
            external_id_field: External ID field name
            external_id: External ID value
            data: Field values

        Returns:
            APIResponse with result
        """
        return await self.patch(
            f"sobjects/{sobject}/{external_id_field}/{external_id}",
            json=data,
        )

    async def delete_record(
        self,
        sobject: str,
        record_id: str,
    ) -> APIResponse:
        """
        Delete a record.

        Args:
            sobject: Object type
            record_id: Record ID

        Returns:
            APIResponse with result
        """
        return await self.delete(f"sobjects/{sobject}/{record_id}")

    # Query Operations

    async def query(self, soql: str) -> APIResponse:
        """
        Execute SOQL query.

        Args:
            soql: SOQL query string

        Returns:
            APIResponse with query results
        """
        from urllib.parse import quote
        return await super().get(f"query?q={quote(soql)}")

    async def query_all(
        self,
        soql: str,
        include_deleted: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Execute SOQL query and fetch all results (handles pagination).

        Args:
            soql: SOQL query string
            include_deleted: Include deleted/archived records

        Returns:
            List of all matching records
        """
        from urllib.parse import quote

        endpoint = "queryAll" if include_deleted else "query"
        all_records = []
        next_url = f"{endpoint}?q={quote(soql)}"

        while next_url:
            response = await super().get(next_url)
            if not response.ok:
                break

            data = response.data
            records = data.get("records", [])
            all_records.extend(records)

            # Check for more records
            if data.get("done", True):
                break

            next_records_url = data.get("nextRecordsUrl")
            if next_records_url:
                # Extract path after /services/data/vXX.X/
                next_url = next_records_url.split(f"/{self.api_version}/")[-1]
            else:
                break

        return all_records

    async def search(self, sosl: str) -> APIResponse:
        """
        Execute SOSL search.

        Args:
            sosl: SOSL search string

        Returns:
            APIResponse with search results
        """
        from urllib.parse import quote
        return await super().get(f"search?q={quote(sosl)}")

    # Describe Operations

    async def describe(self, sobject: str) -> APIResponse:
        """
        Describe an object's metadata.

        Args:
            sobject: Object type

        Returns:
            APIResponse with object metadata
        """
        return await super().get(f"sobjects/{sobject}/describe")

    async def describe_global(self) -> APIResponse:
        """Get list of all available objects."""
        return await super().get("sobjects")

    # Composite Operations

    async def composite(
        self,
        requests: List[Dict[str, Any]],
        all_or_none: bool = False,
    ) -> APIResponse:
        """
        Execute composite request (multiple operations in one call).

        Args:
            requests: List of subrequests
            all_or_none: Rollback all if any fails

        Returns:
            APIResponse with results
        """
        return await self.post("composite", json={
            "allOrNone": all_or_none,
            "compositeRequest": requests,
        })

    async def composite_batch(
        self,
        requests: List[Dict[str, Any]],
        halt_on_error: bool = False,
    ) -> APIResponse:
        """
        Execute batch request (up to 25 subrequests).

        Args:
            requests: List of subrequests
            halt_on_error: Stop on first error

        Returns:
            APIResponse with results
        """
        return await self.post("composite/batch", json={
            "haltOnError": halt_on_error,
            "batchRequests": requests,
        })

    # Bulk Operations

    async def bulk_create(
        self,
        sobject: str,
        records: List[Dict[str, Any]],
    ) -> APIResponse:
        """
        Create multiple records using Composite API.

        Args:
            sobject: Object type
            records: List of records to create

        Returns:
            APIResponse with results
        """
        return await self.post(f"composite/sobjects/{sobject}", json={
            "allOrNone": False,
            "records": [{"attributes": {"type": sobject}, **r} for r in records],
        })

    async def bulk_update(
        self,
        sobject: str,
        records: List[Dict[str, Any]],
    ) -> APIResponse:
        """
        Update multiple records (each must have 'Id' field).

        Args:
            sobject: Object type
            records: List of records with Id and fields to update

        Returns:
            APIResponse with results
        """
        return await self.patch(f"composite/sobjects/{sobject}", json={
            "allOrNone": False,
            "records": [{"attributes": {"type": sobject}, **r} for r in records],
        })

    async def bulk_delete(
        self,
        record_ids: List[str],
        all_or_none: bool = False,
    ) -> APIResponse:
        """
        Delete multiple records.

        Args:
            record_ids: List of record IDs
            all_or_none: Rollback all if any fails

        Returns:
            APIResponse with results
        """
        ids_param = ",".join(record_ids)
        return await self.delete(
            "composite/sobjects",
            params={"ids": ids_param, "allOrNone": str(all_or_none).lower()},
        )

    # Convenience Methods

    async def get_account(self, account_id: str) -> APIResponse:
        """Get Account record."""
        return await self.get("Account", account_id)

    async def get_contact(self, contact_id: str) -> APIResponse:
        """Get Contact record."""
        return await self.get("Contact", contact_id)

    async def get_lead(self, lead_id: str) -> APIResponse:
        """Get Lead record."""
        return await self.get("Lead", lead_id)

    async def get_opportunity(self, opp_id: str) -> APIResponse:
        """Get Opportunity record."""
        return await self.get("Opportunity", opp_id)
