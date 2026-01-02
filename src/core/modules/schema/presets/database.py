"""
Database Presets / Redis Presets / MongoDB Presets
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from ..builders import field, compose
from .. import validators


def DB_TYPE(
    *,
    key: str = "database_type",
    default: str = "postgresql",
    label: str = "Database Type",
    label_key: str = "schema.field.db_type",
) -> Dict[str, Dict[str, Any]]:
    """Database type selector."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        enum=["postgresql", "mysql", "sqlite"],
    )


def DB_CONNECTION_STRING(
    *,
    key: str = "connection_string",
    label: str = "Connection String",
    label_key: str = "schema.field.db_connection_string",
) -> Dict[str, Dict[str, Any]]:
    """Database connection string."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=False,
        secret=True,
        description='Database connection string',
    )


def DB_HOST(
    *,
    key: str = "host",
    label: str = "Host",
    label_key: str = "schema.field.db_host",
) -> Dict[str, Dict[str, Any]]:
    """Database host."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=False,
        description='Database host',
    )


def DB_PORT(
    *,
    key: str = "port",
    default: int = None,
    label: str = "Port",
    label_key: str = "schema.field.db_port",
) -> Dict[str, Dict[str, Any]]:
    """Database port."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='Database port',
    )


def DB_NAME(
    *,
    key: str = "database",
    label: str = "Database Name",
    label_key: str = "schema.field.db_name",
) -> Dict[str, Dict[str, Any]]:
    """Database name."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=False,
        description='Database name',
    )


def DB_USER(
    *,
    key: str = "user",
    label: str = "Username",
    label_key: str = "schema.field.db_user",
) -> Dict[str, Dict[str, Any]]:
    """Database username."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=False,
        description='Database username',
    )


def DB_PASSWORD(
    *,
    key: str = "password",
    label: str = "Password",
    label_key: str = "schema.field.db_password",
) -> Dict[str, Dict[str, Any]]:
    """Database password."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=False,
        secret=True,
        description='Database password',
    )


def DB_TABLE(
    *,
    key: str = "table",
    required: bool = True,
    label: str = "Table Name",
    label_key: str = "schema.field.db_table",
) -> Dict[str, Dict[str, Any]]:
    """Database table name."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='Name of the table',
    )


def SQL_QUERY(
    *,
    key: str = "query",
    required: bool = True,
    label: str = "SQL Query",
    label_key: str = "schema.field.sql_query",
    placeholder: str = "SELECT * FROM users WHERE active = true",
) -> Dict[str, Dict[str, Any]]:
    """SQL query to execute."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        placeholder=placeholder,
        multiline=True,
        description='SQL query to execute',
    )


def DB_QUERY_PARAMS(
    *,
    key: str = "params",
    label: str = "Query Parameters",
    label_key: str = "schema.field.db_query_params",
) -> Dict[str, Dict[str, Any]]:
    """Parameters for parameterized SQL queries."""
    return field(
        key,
        type="array",
        label=label,
        label_key=label_key,
        required=False,
        default=[],
        description='Parameters for parameterized queries (prevents SQL injection)',
    )


def FETCH_MODE(
    *,
    key: str = "fetch",
    default: str = "all",
    label: str = "Fetch Mode",
    label_key: str = "schema.field.fetch_mode",
) -> Dict[str, Dict[str, Any]]:
    """How to fetch query results."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        enum=["all", "one", "none"],
        description='How to fetch results: all, one, or none (for INSERT/UPDATE)',
    )


def DB_DATA(
    *,
    key: str = "data",
    required: bool = True,
    label: str = "Data",
    label_key: str = "schema.field.db_data",
) -> Dict[str, Dict[str, Any]]:
    """Data for insert/update operations."""
    return field(
        key,
        type="object",
        label=label,
        label_key=label_key,
        required=required,
        description='Data to insert or update',
    )


def WHERE_CONDITIONS(
    *,
    key: str = "where",
    required: bool = True,
    label: str = "Where Conditions",
    label_key: str = "schema.field.where_conditions",
) -> Dict[str, Dict[str, Any]]:
    """WHERE conditions for update/delete."""
    return field(
        key,
        type="object",
        label=label,
        label_key=label_key,
        required=required,
        description='WHERE conditions (column: value for equality)',
    )


def RETURNING_COLUMNS(
    *,
    key: str = "returning",
    label: str = "Returning Columns",
    label_key: str = "schema.field.returning_columns",
) -> Dict[str, Dict[str, Any]]:
    """Columns to return after insert (PostgreSQL)."""
    return field(
        key,
        type="array",
        label=label,
        label_key=label_key,
        required=False,
        description='Columns to return after insert (PostgreSQL)',
    )

def REDIS_KEY(
    *,
    key: str = "key",
    required: bool = True,
    label: str = "Key",
    label_key: str = "schema.field.redis_key",
) -> Dict[str, Dict[str, Any]]:
    """Redis key."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='Redis key',
    )


def REDIS_VALUE(
    *,
    key: str = "value",
    required: bool = True,
    label: str = "Value",
    label_key: str = "schema.field.redis_value",
) -> Dict[str, Dict[str, Any]]:
    """Value to store in Redis."""
    return field(
        key,
        type="any",
        label=label,
        label_key=label_key,
        required=required,
        description='Value to store',
    )


def REDIS_TTL(
    *,
    key: str = "ttl",
    label: str = "TTL (seconds)",
    label_key: str = "schema.field.redis_ttl",
) -> Dict[str, Dict[str, Any]]:
    """Time to live in seconds."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        required=False,
        description='Time to live in seconds (optional)',
    )


def REDIS_HOST(
    *,
    key: str = "host",
    label: str = "Host",
    label_key: str = "schema.field.redis_host",
    placeholder: str = "${env.REDIS_HOST}",
) -> Dict[str, Dict[str, Any]]:
    """Redis host."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=False,
        placeholder=placeholder,
        description='Redis host (from env.REDIS_HOST or explicit)',
    )


def REDIS_PORT(
    *,
    key: str = "port",
    default: int = 6379,
    label: str = "Port",
    label_key: str = "schema.field.redis_port",
) -> Dict[str, Dict[str, Any]]:
    """Redis port."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='Redis port',
    )


def REDIS_DB(
    *,
    key: str = "db",
    default: int = 0,
    label: str = "Database",
    label_key: str = "schema.field.redis_db",
) -> Dict[str, Dict[str, Any]]:
    """Redis database number."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='Redis database number',
    )

def MONGO_CONNECTION_STRING(
    *,
    key: str = "connection_string",
    label: str = "Connection String",
    label_key: str = "schema.field.mongo_connection_string",
    placeholder: str = "${env.MONGODB_URL}",
) -> Dict[str, Dict[str, Any]]:
    """MongoDB connection string."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=False,
        placeholder=placeholder,
        secret=True,
        description='MongoDB connection string (defaults to env.MONGODB_URL)',
    )


def MONGO_DATABASE(
    *,
    key: str = "database",
    required: bool = True,
    label: str = "Database",
    label_key: str = "schema.field.mongo_database",
) -> Dict[str, Dict[str, Any]]:
    """MongoDB database name."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='Database name',
    )


def MONGO_COLLECTION(
    *,
    key: str = "collection",
    required: bool = True,
    label: str = "Collection",
    label_key: str = "schema.field.mongo_collection",
) -> Dict[str, Dict[str, Any]]:
    """MongoDB collection name."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='Collection name',
    )


def MONGO_FILTER(
    *,
    key: str = "filter",
    label: str = "Filter",
    label_key: str = "schema.field.mongo_filter",
) -> Dict[str, Dict[str, Any]]:
    """MongoDB query filter."""
    return field(
        key,
        type="object",
        label=label,
        label_key=label_key,
        required=False,
        default={},
        description='MongoDB query filter (empty object {} returns all)',
    )


def MONGO_PROJECTION(
    *,
    key: str = "projection",
    label: str = "Projection",
    label_key: str = "schema.field.mongo_projection",
) -> Dict[str, Dict[str, Any]]:
    """Fields to include/exclude in results."""
    return field(
        key,
        type="object",
        label=label,
        label_key=label_key,
        required=False,
        description='Fields to include/exclude in results',
    )


def MONGO_LIMIT(
    *,
    key: str = "limit",
    default: int = 100,
    label: str = "Limit",
    label_key: str = "schema.field.mongo_limit",
) -> Dict[str, Dict[str, Any]]:
    """Maximum number of documents to return."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        min=1,
        max=10000,
        description='Maximum number of documents to return',
    )


def MONGO_SORT(
    *,
    key: str = "sort",
    label: str = "Sort",
    label_key: str = "schema.field.mongo_sort",
) -> Dict[str, Dict[str, Any]]:
    """Sort order (1 for ascending, -1 for descending)."""
    return field(
        key,
        type="object",
        label=label,
        label_key=label_key,
        required=False,
        description='Sort order (1 for ascending, -1 for descending)',
    )


def MONGO_DOCUMENT(
    *,
    key: str = "document",
    label: str = "Document",
    label_key: str = "schema.field.mongo_document",
) -> Dict[str, Dict[str, Any]]:
    """Document to insert (for single insert)."""
    return field(
        key,
        type="object",
        label=label,
        label_key=label_key,
        required=False,
        description='Document to insert (for single insert)',
    )


def MONGO_DOCUMENTS(
    *,
    key: str = "documents",
    label: str = "Documents",
    label_key: str = "schema.field.mongo_documents",
) -> Dict[str, Dict[str, Any]]:
    """Array of documents to insert (for bulk insert)."""
    return field(
        key,
        type="array",
        label=label,
        label_key=label_key,
        required=False,
        description='Array of documents to insert (for bulk insert)',
    )

