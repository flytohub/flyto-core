"""
Module Connection Validation

Provides validation logic for module connections based on context requirements.
Used by UI/Planner to prevent invalid module combinations.
"""
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

from .registry import ModuleRegistry
from .composite.base import CompositeRegistry
from .types import ContextType, DEFAULT_CONTEXT_REQUIREMENTS, DEFAULT_CONTEXT_PROVISIONS


logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of a connection validation check."""
    valid: bool
    reason: Optional[str] = None
    missing_context: Optional[List[str]] = None


class ConnectionValidator:
    """
    Validates module connections based on context requirements.

    This validator checks whether modules can be connected in a workflow
    based on what context each module requires and provides.
    """

    def __init__(self):
        self._module_registry = ModuleRegistry
        self._composite_registry = CompositeRegistry

    def get_module_metadata(self, module_id: str) -> Optional[Dict[str, Any]]:
        """Get metadata for a module (atomic or composite)."""
        # Try atomic module first
        metadata = self._module_registry.get_metadata(module_id)
        if metadata:
            return metadata

        # Try composite module
        metadata = self._composite_registry.get_metadata(module_id)
        if metadata:
            return metadata

        return None

    def get_requires_context(self, module_id: str) -> List[str]:
        """Get context requirements for a module."""
        metadata = self.get_module_metadata(module_id)

        if metadata and metadata.get("requires_context"):
            return metadata["requires_context"]

        # Fallback to category-based defaults
        category = module_id.split(".")[0] if "." in module_id else module_id
        return [ctx.value for ctx in DEFAULT_CONTEXT_REQUIREMENTS.get(category, [])]

    def get_provides_context(self, module_id: str) -> List[str]:
        """Get context provided by a module."""
        metadata = self.get_module_metadata(module_id)

        if metadata and metadata.get("provides_context"):
            return metadata["provides_context"]

        # Fallback to category-based defaults
        category = module_id.split(".")[0] if "." in module_id else module_id
        return [ctx.value for ctx in DEFAULT_CONTEXT_PROVISIONS.get(category, [])]

    def can_connect(
        self,
        source_module: str,
        target_module: str,
        context_chain: Optional[List[str]] = None
    ) -> ValidationResult:
        """
        Check if target module can follow source module.

        Args:
            source_module: The module ID of the source node
            target_module: The module ID of the target node
            context_chain: List of context types accumulated from previous steps

        Returns:
            ValidationResult with valid flag and optional reason
        """
        if context_chain is None:
            context_chain = []

        # Get context provided by source and add to chain
        source_provides = self.get_provides_context(source_module)
        available_context = set(context_chain) | set(source_provides)

        # Get context required by target
        target_requires = self.get_requires_context(target_module)

        if not target_requires:
            # No requirements means any connection is valid
            return ValidationResult(valid=True)

        # Check if all required contexts are available
        missing = []
        for required in target_requires:
            if required not in available_context:
                missing.append(required)

        if missing:
            return ValidationResult(
                valid=False,
                reason=f"Module '{target_module}' requires context: {', '.join(missing)}",
                missing_context=missing
            )

        return ValidationResult(valid=True)

    def validate_workflow(
        self,
        steps: List[Dict[str, Any]]
    ) -> List[ValidationResult]:
        """
        Validate an entire workflow sequence.

        Args:
            steps: List of step definitions with 'module' key

        Returns:
            List of ValidationResult for each connection
        """
        results = []
        context_chain: Set[str] = set()

        for i, step in enumerate(steps):
            module_id = step.get("module") or step.get("composite")

            if not module_id:
                results.append(ValidationResult(
                    valid=False,
                    reason=f"Step {i} missing module or composite field"
                ))
                continue

            if i == 0:
                # First step has no source, check if it can start standalone
                requires = self.get_requires_context(module_id)
                if requires:
                    results.append(ValidationResult(
                        valid=False,
                        reason=f"First step '{module_id}' requires context: {', '.join(requires)}",
                        missing_context=requires
                    ))
                else:
                    results.append(ValidationResult(valid=True))
            else:
                # Check connection from previous step
                prev_module = steps[i - 1].get("module") or steps[i - 1].get("composite")
                result = self.can_connect(
                    source_module=prev_module,
                    target_module=module_id,
                    context_chain=list(context_chain)
                )
                results.append(result)

            # Update context chain with what this module provides
            provides = self.get_provides_context(module_id)
            context_chain.update(provides)

        return results

    def get_compatible_modules(
        self,
        after_module: str,
        context_chain: Optional[List[str]] = None,
        include_composites: bool = True
    ) -> List[str]:
        """
        Get list of modules that can follow the given module.

        Useful for UI to show only valid options when connecting nodes.

        Args:
            after_module: Module ID to find compatible successors for
            context_chain: Accumulated context from previous steps
            include_composites: Whether to include composite modules

        Returns:
            List of compatible module IDs
        """
        if context_chain is None:
            context_chain = []

        # Get available context after the source module
        source_provides = self.get_provides_context(after_module)
        available_context = set(context_chain) | set(source_provides)

        compatible = []

        # Check atomic modules
        for module_id in self._module_registry.list_all().keys():
            requires = self.get_requires_context(module_id)
            if not requires or all(r in available_context for r in requires):
                compatible.append(module_id)

        # Check composite modules
        if include_composites:
            for module_id in self._composite_registry.list_all().keys():
                requires = self.get_requires_context(module_id)
                if not requires or all(r in available_context for r in requires):
                    compatible.append(module_id)

        return sorted(compatible)

    def get_starter_modules(self, include_composites: bool = True) -> List[str]:
        """
        Get modules that can start a workflow (no context requirements).

        Returns:
            List of module IDs that can be first in a workflow
        """
        starters = []

        # Check atomic modules
        for module_id in self._module_registry.list_all().keys():
            requires = self.get_requires_context(module_id)
            if not requires:
                starters.append(module_id)

        # Check composite modules
        if include_composites:
            for module_id in self._composite_registry.list_all().keys():
                requires = self.get_requires_context(module_id)
                if not requires:
                    starters.append(module_id)

        return sorted(starters)


# Singleton instance
_validator: Optional[ConnectionValidator] = None


def get_connection_validator() -> ConnectionValidator:
    """Get singleton ConnectionValidator instance."""
    global _validator
    if _validator is None:
        _validator = ConnectionValidator()
    return _validator


def can_connect(
    source_module: str,
    target_module: str,
    context_chain: Optional[List[str]] = None
) -> ValidationResult:
    """
    Convenience function to check if two modules can be connected.

    Args:
        source_module: Source module ID
        target_module: Target module ID
        context_chain: Accumulated context from previous steps

    Returns:
        ValidationResult
    """
    return get_connection_validator().can_connect(
        source_module, target_module, context_chain
    )


def validate_workflow(steps: List[Dict[str, Any]]) -> List[ValidationResult]:
    """
    Convenience function to validate a workflow.

    Args:
        steps: List of step definitions

    Returns:
        List of ValidationResult for each connection
    """
    return get_connection_validator().validate_workflow(steps)
