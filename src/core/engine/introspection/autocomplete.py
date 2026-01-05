"""
Expression Autocomplete

Provides autocomplete suggestions for variable expressions.
Used by UI expression editors.

Version: 1.0.0
"""

import logging
from typing import Any, Dict, List, Optional

from ..sdk.models import (
    AutocompleteItem,
    AutocompleteResult,
    IntrospectionMode,
    VarCatalog,
)
from .catalog import build_catalog

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Keywords that start special paths
KEYWORDS = ["input", "inputs", "params", "global", "env"]

# Boost scores for different match types
SCORE_EXACT = 1.0
SCORE_PREFIX = 0.8
SCORE_CONTAINS = 0.5


# =============================================================================
# Autocomplete Engine
# =============================================================================

class AutocompleteEngine:
    """Provides autocomplete suggestions for expressions"""

    def __init__(self, catalog: VarCatalog):
        self._catalog = catalog
        self._all_paths: List[AutocompleteItem] = []
        self._build_paths()

    def _build_paths(self) -> None:
        """Build all available paths from catalog"""
        # Input shorthand
        self._all_paths.append(AutocompleteItem(
            path="input",
            display="input",
            var_type="any",
            description="Main input (shorthand for inputs.main)",
            insert_text="{{input}}",
        ))

        # Input ports
        for port_id, port_info in self._catalog.inputs.items():
            base = f"inputs.{port_id}" if port_id != "main" else "input"

            self._all_paths.append(AutocompleteItem(
                path=base,
                display=base,
                var_type=port_info.var_type,
                description=port_info.description or f"Input port: {port_id}",
                insert_text=f"{{{{{base}}}}}",
            ))

            # Add fields
            for field_name, field_info in port_info.fields.items():
                field_path = f"{base}.{field_name}"
                self._all_paths.append(AutocompleteItem(
                    path=field_path,
                    display=field_path,
                    var_type=field_info.var_type,
                    description=field_info.description,
                    insert_text=f"{{{{{field_path}}}}}",
                ))

        # Upstream nodes
        for node_id, node_info in self._catalog.nodes.items():
            # Node root
            self._all_paths.append(AutocompleteItem(
                path=node_id,
                display=node_id,
                var_type="object",
                description=f"Output from {node_info.node_type}",
                insert_text=f"{{{{{node_id}}}}}",
            ))

            # Node ports
            for port_id, port_info in node_info.ports.items():
                port_path = f"{node_id}.{port_id}"
                self._all_paths.append(AutocompleteItem(
                    path=port_path,
                    display=port_path,
                    var_type=port_info.var_type,
                    description=port_info.description or f"Port: {port_id}",
                    insert_text=f"{{{{{port_path}}}}}",
                ))

                # Port fields
                for field_name, field_info in port_info.fields.items():
                    field_path = f"{port_path}.{field_name}"
                    self._all_paths.append(AutocompleteItem(
                        path=field_path,
                        display=field_path,
                        var_type=field_info.var_type,
                        description=field_info.description,
                        insert_text=f"{{{{{field_path}}}}}",
                    ))

        # Params
        for key, info in self._catalog.params.items():
            path = f"params.{key}"
            self._all_paths.append(AutocompleteItem(
                path=path,
                display=path,
                var_type=info.var_type,
                description=info.description or f"Parameter: {key}",
                insert_text=f"{{{{{path}}}}}",
            ))

        # Globals
        for key, info in self._catalog.globals.items():
            path = f"global.{key}"
            self._all_paths.append(AutocompleteItem(
                path=path,
                display=path,
                var_type=info.var_type,
                description=info.description or f"Global: {key}",
                insert_text=f"{{{{{path}}}}}",
            ))

        # Env
        for key, info in self._catalog.env.items():
            path = f"env.{key}"
            self._all_paths.append(AutocompleteItem(
                path=path,
                display=path,
                var_type=info.var_type,
                description=info.description or f"Environment: {key}",
                insert_text=f"{{{{{path}}}}}",
            ))

    def suggest(
        self,
        prefix: str,
        limit: int = 20,
    ) -> AutocompleteResult:
        """
        Get autocomplete suggestions for a prefix.

        Args:
            prefix: Current input prefix
            limit: Maximum suggestions to return

        Returns:
            AutocompleteResult with suggestions
        """
        prefix = prefix.strip()

        # Remove {{ if present
        if prefix.startswith("{{"):
            prefix = prefix[2:]
        if prefix.endswith("}}"):
            prefix = prefix[:-2]

        prefix = prefix.strip()

        # Score and filter matches
        scored: List[tuple] = []

        for item in self._all_paths:
            score = self._score_match(item.path, prefix)
            if score > 0:
                scored.append((score, item))

        # Sort by score descending
        scored.sort(key=lambda x: x[0], reverse=True)

        # Take top N
        items = [item for _, item in scored[:limit]]

        return AutocompleteResult(
            prefix=prefix,
            items=items,
        )

    def _score_match(self, path: str, prefix: str) -> float:
        """Score a path against prefix"""
        if not prefix:
            # Empty prefix - show all with base score
            return 0.3

        path_lower = path.lower()
        prefix_lower = prefix.lower()

        # Exact match
        if path_lower == prefix_lower:
            return SCORE_EXACT

        # Prefix match
        if path_lower.startswith(prefix_lower):
            return SCORE_PREFIX

        # Contains match
        if prefix_lower in path_lower:
            return SCORE_CONTAINS

        # Partial match on last segment
        parts = path_lower.split(".")
        if parts and prefix_lower in parts[-1]:
            return SCORE_CONTAINS * 0.8

        return 0.0


# =============================================================================
# Expression Validator
# =============================================================================

class ExpressionValidator:
    """Validates expressions against catalog"""

    def __init__(self, catalog: VarCatalog):
        self._catalog = catalog
        self._engine = AutocompleteEngine(catalog)

    def validate(
        self,
        expression: str,
        expected_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Validate an expression.

        Args:
            expression: Expression to validate (with or without {{}})
            expected_type: Expected result type

        Returns:
            Validation result dict
        """
        # Clean expression
        expr = expression.strip()
        if expr.startswith("{{"):
            expr = expr[2:]
        if expr.endswith("}}"):
            expr = expr[:-2]
        expr = expr.strip()

        # Try to find in catalog
        suggestions = self._engine.suggest(expr, limit=1)

        if not suggestions.items:
            return {
                "valid": False,
                "error": f"Unknown variable: {expr}",
                "suggestions": [],
            }

        best_match = suggestions.items[0]

        # Check if exact match
        if best_match.path != expr:
            # Not exact, might be partial
            all_suggestions = self._engine.suggest(expr, limit=5)
            return {
                "valid": False,
                "error": f"Did you mean: {best_match.path}?",
                "suggestions": [s.path for s in all_suggestions.items],
            }

        # Check type compatibility
        if expected_type and best_match.var_type != "any":
            if not self._types_compatible(best_match.var_type, expected_type):
                return {
                    "valid": True,
                    "warning": f"Type mismatch: {best_match.var_type} vs {expected_type}",
                    "resolved_type": best_match.var_type,
                }

        return {
            "valid": True,
            "resolved_type": best_match.var_type,
        }

    def _types_compatible(self, actual: str, expected: str) -> bool:
        """Check if types are compatible"""
        if actual == expected:
            return True
        if actual == "any" or expected == "any":
            return True
        if expected == "string":
            # Everything can be stringified
            return True
        return False


# =============================================================================
# Factory Functions
# =============================================================================

def create_autocomplete(
    workflow: Dict[str, Any],
    node_id: str,
    context_snapshot: Optional[Dict[str, Any]] = None,
) -> AutocompleteEngine:
    """
    Create an autocomplete engine for a node.

    Args:
        workflow: Workflow definition
        node_id: Target node ID
        context_snapshot: Optional runtime context

    Returns:
        AutocompleteEngine instance
    """
    mode = (
        IntrospectionMode.RUNTIME
        if context_snapshot
        else IntrospectionMode.EDIT
    )

    catalog = build_catalog(
        workflow=workflow,
        node_id=node_id,
        mode=mode,
        context_snapshot=context_snapshot,
    )

    return AutocompleteEngine(catalog)


def autocomplete(
    workflow: Dict[str, Any],
    node_id: str,
    prefix: str,
    context_snapshot: Optional[Dict[str, Any]] = None,
    limit: int = 20,
) -> AutocompleteResult:
    """
    Get autocomplete suggestions for a node.

    Args:
        workflow: Workflow definition
        node_id: Target node ID
        prefix: Current input prefix
        context_snapshot: Optional runtime context
        limit: Maximum suggestions

    Returns:
        AutocompleteResult with suggestions
    """
    engine = create_autocomplete(workflow, node_id, context_snapshot)
    return engine.suggest(prefix, limit)


def validate_expression(
    workflow: Dict[str, Any],
    node_id: str,
    expression: str,
    expected_type: Optional[str] = None,
    context_snapshot: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Validate an expression for a node.

    Args:
        workflow: Workflow definition
        node_id: Target node ID
        expression: Expression to validate
        expected_type: Expected result type
        context_snapshot: Optional runtime context

    Returns:
        Validation result dict
    """
    mode = (
        IntrospectionMode.RUNTIME
        if context_snapshot
        else IntrospectionMode.EDIT
    )

    catalog = build_catalog(
        workflow=workflow,
        node_id=node_id,
        mode=mode,
        context_snapshot=context_snapshot,
    )

    validator = ExpressionValidator(catalog)
    return validator.validate(expression, expected_type)
