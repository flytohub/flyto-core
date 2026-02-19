# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

"""
Introspection Module

Provides variable catalog and autocomplete for workflow nodes.

Usage:
    from core.engine.introspection import build_catalog, autocomplete

    catalog = build_catalog(workflow, node_id, mode="edit")
    suggestions = autocomplete(workflow, node_id, prefix="input.")
"""

from .catalog import (
    CatalogBuilder,
    GraphAnalyzer,
    SchemaIntrospector,
    build_catalog,
)

from .autocomplete import (
    AutocompleteEngine,
    ExpressionValidator,
    autocomplete,
    create_autocomplete,
    validate_expression,
)

__all__ = [
    # Catalog
    "CatalogBuilder",
    "GraphAnalyzer",
    "SchemaIntrospector",
    "build_catalog",
    # Autocomplete
    "AutocompleteEngine",
    "ExpressionValidator",
    "autocomplete",
    "create_autocomplete",
    "validate_expression",
]
