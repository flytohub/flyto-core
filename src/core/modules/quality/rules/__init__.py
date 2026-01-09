"""
Validation Rules Registry

All validation rules are registered here.
"""
from typing import Dict, List, Type
from .base import BaseRule, MetadataRule, ASTRule, SecurityRule
from ..types import RuleStage

# Rule registry
_RULES: Dict[str, Type[BaseRule]] = {}


def register_rule(rule_class: Type[BaseRule]) -> Type[BaseRule]:
    """Decorator to register a validation rule."""
    _RULES[rule_class.rule_id] = rule_class
    return rule_class


def get_rule(rule_id: str) -> Type[BaseRule]:
    """Get a rule by ID."""
    return _RULES.get(rule_id)


def get_all_rules() -> List[Type[BaseRule]]:
    """Get all registered rules."""
    return list(_RULES.values())


def get_rules_by_category(category: str) -> List[Type[BaseRule]]:
    """Get rules by category prefix (e.g., 'CORE-ID')."""
    return [r for r in _RULES.values() if r.rule_id.startswith(category)]


def get_rules_by_stage(stage: RuleStage) -> List[Type[BaseRule]]:
    """Get rules by execution stage."""
    return [r for r in _RULES.values() if r.stage == stage]


# Import rule modules to trigger registration
from . import identity
from . import execution
from . import schema
from . import capability
from . import security
from . import ast_rules


__all__ = [
    "register_rule",
    "get_rule",
    "get_all_rules",
    "get_rules_by_category",
    "get_rules_by_stage",
    "BaseRule",
    "MetadataRule",
    "ASTRule",
    "SecurityRule",
]
