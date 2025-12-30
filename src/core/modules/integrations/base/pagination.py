"""
Paginated Integration

Base class for integrations with pagination support.
"""

import logging
from typing import Any, Dict, List, Optional

from .client import BaseIntegration

logger = logging.getLogger(__name__)


class PaginatedIntegration(BaseIntegration):
    """
    Base class for integrations with pagination support.

    Handles cursor-based and offset-based pagination.
    """

    async def paginate(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        page_key: str = "page",
        limit_key: str = "per_page",
        limit: int = 100,
        max_pages: Optional[int] = None,
        data_key: Optional[str] = None,
    ) -> List[Any]:
        """
        Fetch all pages of a paginated endpoint.

        Args:
            endpoint: API endpoint
            params: Query parameters
            page_key: Parameter name for page number
            limit_key: Parameter name for page size
            limit: Items per page
            max_pages: Maximum pages to fetch
            data_key: Key in response containing data list

        Returns:
            Combined list of all items
        """
        params = params or {}
        params[limit_key] = limit

        all_items = []
        page = 1

        while True:
            params[page_key] = page
            response = await self.get(endpoint, params=params)

            if not response.ok:
                logger.error(f"Pagination failed at page {page}: {response.error}")
                break

            # Extract items from response
            data = response.data
            if data_key and isinstance(data, dict):
                items = data.get(data_key, [])
            elif isinstance(data, list):
                items = data
            else:
                items = [data] if data else []

            if not items:
                break

            all_items.extend(items)

            # Check if more pages
            if len(items) < limit:
                break

            if max_pages and page >= max_pages:
                break

            page += 1

        return all_items

    async def cursor_paginate(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        cursor_key: str = "cursor",
        response_cursor_key: str = "next_cursor",
        data_key: str = "data",
        max_pages: Optional[int] = None,
    ) -> List[Any]:
        """
        Fetch all pages using cursor-based pagination.

        Args:
            endpoint: API endpoint
            params: Query parameters
            cursor_key: Parameter name for cursor
            response_cursor_key: Key in response containing next cursor
            data_key: Key in response containing data list
            max_pages: Maximum pages to fetch

        Returns:
            Combined list of all items
        """
        params = params or {}
        all_items = []
        cursor = None
        page = 0

        while True:
            if cursor:
                params[cursor_key] = cursor

            response = await self.get(endpoint, params=params)

            if not response.ok:
                logger.error(f"Cursor pagination failed: {response.error}")
                break

            data = response.data
            if isinstance(data, dict):
                items = data.get(data_key, [])
                cursor = data.get(response_cursor_key)
            else:
                items = data if isinstance(data, list) else []
                cursor = None

            all_items.extend(items)

            if not cursor:
                break

            page += 1
            if max_pages and page >= max_pages:
                break

        return all_items
