"""
Variable Resolver v2

Implements the variable resolution specification with full syntax support.
Supports {{path}}, array indexing, quoted keys, and resolution modes.

Version: 1.0.0
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Match, Optional, Tuple, Union

from .models import (
    ExpressionToken,
    ParsedExpression,
    ResolutionMode,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Main expression pattern: {{...}}
EXPRESSION_PATTERN = re.compile(r"\{\{(.+?)\}\}")

# Token patterns for path parsing
TOKEN_IDENTIFIER = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_]*)")
TOKEN_DOT = re.compile(r"^\.")
TOKEN_BRACKET_INT = re.compile(r"^\[(\d+)\]")
TOKEN_BRACKET_QUOTED = re.compile(r'^\["([^"]+)"\]|^\[\'([^\']+)\'\]')

# Default filter pattern: | default('value')
DEFAULT_FILTER_PATTERN = re.compile(
    r"^(.+?)\s*\|\s*default\s*\(\s*['\"](.+?)['\"]\s*\)\s*$"
)


# =============================================================================
# Exceptions
# =============================================================================

class VariableNotFoundError(Exception):
    """Raised when a variable path cannot be resolved"""

    def __init__(self, path: str, message: Optional[str] = None):
        self.path = path
        super().__init__(message or f"Variable not found: {path}")


class ExpressionSyntaxError(Exception):
    """Raised when expression syntax is invalid"""

    def __init__(self, expression: str, position: int, message: str):
        self.expression = expression
        self.position = position
        super().__init__(f"Syntax error at position {position}: {message}")


# =============================================================================
# Expression Parser
# =============================================================================

class ExpressionParser:
    """Parses variable expressions into tokens"""

    def parse(self, expression: str) -> ParsedExpression:
        """
        Parse a variable expression.

        Args:
            expression: Raw expression (without {{ }})

        Returns:
            ParsedExpression with tokens or error
        """
        # Check for default filter
        default_match = DEFAULT_FILTER_PATTERN.match(expression)
        if default_match:
            path = default_match.group(1).strip()
            # Parse the path part only
            result = self._parse_path(path)
            # Mark that default filter is present
            result.raw = expression
            return result

        return self._parse_path(expression.strip())

    def _parse_path(self, path: str) -> ParsedExpression:
        """Parse a path into tokens"""
        tokens: List[ExpressionToken] = []
        pos = 0
        original = path

        while pos < len(path):
            remaining = path[pos:]

            # Try identifier
            match = TOKEN_IDENTIFIER.match(remaining)
            if match:
                tokens.append(ExpressionToken(
                    token_type="identifier",
                    value=match.group(1),
                    start=pos,
                    end=pos + len(match.group(0)),
                ))
                pos += len(match.group(0))
                continue

            # Try dot
            if remaining.startswith("."):
                pos += 1
                continue

            # Try bracket with integer
            match = TOKEN_BRACKET_INT.match(remaining)
            if match:
                tokens.append(ExpressionToken(
                    token_type="index",
                    value=match.group(1),
                    start=pos,
                    end=pos + len(match.group(0)),
                ))
                pos += len(match.group(0))
                continue

            # Try bracket with quoted string
            match = TOKEN_BRACKET_QUOTED.match(remaining)
            if match:
                value = match.group(1) or match.group(2)
                tokens.append(ExpressionToken(
                    token_type="quoted_key",
                    value=value,
                    start=pos,
                    end=pos + len(match.group(0)),
                ))
                pos += len(match.group(0))
                continue

            # Invalid character
            return ParsedExpression(
                raw=original,
                is_valid=False,
                error=f"Unexpected character at position {pos}: '{remaining[0]}'"
            )

        return ParsedExpression(
            raw=original,
            is_valid=True,
            tokens=tokens,
        )

    def extract_expressions(self, text: str) -> List[Tuple[str, int, int]]:
        """
        Extract all {{...}} expressions from text.

        Returns:
            List of (expression, start, end) tuples
        """
        results = []
        for match in EXPRESSION_PATTERN.finditer(text):
            results.append((
                match.group(1),
                match.start(),
                match.end(),
            ))
        return results


# =============================================================================
# Variable Resolver
# =============================================================================

class VariableResolver:
    """
    Resolves variable expressions in workflow parameters.

    Supports:
    - {{input}} - Main input port (alias for {{inputs.main}})
    - {{input.field}} - Field from main input
    - {{inputs.<port>}} - Specific input port
    - {{node_id}} - Full output of a node
    - {{node_id.port.field}} - Nested field from node
    - {{node_id.arr[0]}} - Array index
    - {{node_id.obj["key"]}} - Quoted key for special chars
    - {{params.name}} - Workflow parameter
    - {{global.var}} - Global variable
    - {{env.VAR}} - Environment variable
    - {{path | default('value')}} - Default value filter
    """

    def __init__(
        self,
        context: Dict[str, Any],
        params: Optional[Dict[str, Any]] = None,
        globals: Optional[Dict[str, Any]] = None,
        env: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize resolver.

        Args:
            context: Execution context with node outputs
            params: Workflow parameters
            globals: Global variables
            env: Environment variables (filtered)
        """
        self._context = context or {}
        self._params = params or {}
        self._globals = globals or {}
        self._env = env or {}
        self._parser = ExpressionParser()

    def resolve(
        self,
        value: Any,
        mode: ResolutionMode = ResolutionMode.RAW,
        strict: bool = False,
    ) -> Any:
        """
        Resolve variables in a value.

        Args:
            value: Value to resolve (string, dict, list, or primitive)
            mode: Resolution mode (raw or string)
            strict: Raise error on missing variables

        Returns:
            Resolved value

        Raises:
            VariableNotFoundError: If strict=True and variable not found
        """
        if isinstance(value, str):
            return self._resolve_string(value, mode, strict)
        elif isinstance(value, dict):
            return {k: self.resolve(v, mode, strict) for k, v in value.items()}
        elif isinstance(value, list):
            return [self.resolve(v, mode, strict) for v in value]
        else:
            return value

    def _resolve_string(
        self,
        text: str,
        mode: ResolutionMode,
        strict: bool,
    ) -> Any:
        """Resolve variables in a string"""
        # Check if entire string is a single expression
        match = EXPRESSION_PATTERN.fullmatch(text)
        if match:
            return self._resolve_expression(
                match.group(1),
                mode,
                strict,
                return_original_on_miss=not strict,
            )

        # Otherwise, substitute all expressions
        def replacer(m: Match[str]) -> str:
            result = self._resolve_expression(
                m.group(1),
                ResolutionMode.STRING,  # Force string mode for substitution
                strict,
                return_original_on_miss=True,
            )
            return self._stringify(result)

        return EXPRESSION_PATTERN.sub(replacer, text)

    def _resolve_expression(
        self,
        expression: str,
        mode: ResolutionMode,
        strict: bool,
        return_original_on_miss: bool = False,
    ) -> Any:
        """Resolve a single expression"""
        expression = expression.strip()

        # Check for default filter
        default_value: Optional[str] = None
        default_match = DEFAULT_FILTER_PATTERN.match(expression)
        if default_match:
            expression = default_match.group(1).strip()
            default_value = default_match.group(2)

        # Parse expression
        parsed = self._parser.parse(expression)
        if not parsed.is_valid:
            if strict:
                raise ExpressionSyntaxError(expression, 0, parsed.error or "Invalid")
            return f"{{{{{expression}}}}}" if return_original_on_miss else None

        if not parsed.tokens:
            return None

        # Resolve the path
        result = self._resolve_path(parsed.tokens)

        # Handle missing value
        if result is None:
            if default_value is not None:
                return default_value
            if strict:
                raise VariableNotFoundError(expression)
            return f"{{{{{expression}}}}}" if return_original_on_miss else None

        # Apply mode
        if mode == ResolutionMode.STRING:
            return self._stringify(result)

        return result

    def _resolve_path(self, tokens: List[ExpressionToken]) -> Any:
        """Resolve a parsed path to a value"""
        if not tokens:
            return None

        first = tokens[0]
        root_key = first.value

        # Determine root value based on first identifier
        if root_key == "input":
            # Shorthand for inputs.main
            root = self._context.get("inputs", {}).get("main")
            if root is None:
                # Fallback to direct input key
                root = self._context.get("input")
            tokens = tokens[1:]

        elif root_key == "inputs":
            root = self._context.get("inputs", {})
            tokens = tokens[1:]

        elif root_key == "params":
            root = self._params
            tokens = tokens[1:]

        elif root_key == "global":
            root = self._globals
            tokens = tokens[1:]

        elif root_key == "env":
            root = self._env
            tokens = tokens[1:]

        else:
            # Node ID or other context key
            root = self._context.get(root_key)
            tokens = tokens[1:]

        # Navigate remaining path
        return self._navigate_path(root, tokens)

    def _navigate_path(
        self,
        current: Any,
        tokens: List[ExpressionToken],
    ) -> Any:
        """Navigate a path starting from a value"""
        for token in tokens:
            if current is None:
                return None

            if token.token_type == "identifier":
                if isinstance(current, dict):
                    current = current.get(token.value)
                elif hasattr(current, token.value):
                    current = getattr(current, token.value)
                else:
                    return None

            elif token.token_type == "index":
                try:
                    index = int(token.value)
                    if isinstance(current, (list, tuple)):
                        if 0 <= index < len(current):
                            current = current[index]
                        else:
                            return None
                    else:
                        return None
                except (ValueError, TypeError):
                    return None

            elif token.token_type == "quoted_key":
                if isinstance(current, dict):
                    current = current.get(token.value)
                else:
                    return None

        return current

    def _stringify(self, value: Any) -> str:
        """Convert value to string for template substitution"""
        if value is None:
            return ""
        elif isinstance(value, str):
            return value
        elif isinstance(value, bool):
            return "true" if value else "false"
        elif isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        else:
            return str(value)

    def evaluate_condition(self, condition: str) -> bool:
        """
        Evaluate a condition expression.

        Supports: ==, !=, >, <, >=, <=, contains, !contains

        Args:
            condition: Condition string

        Returns:
            Boolean result
        """
        # Resolve variables first
        resolved = self._resolve_string(
            condition,
            ResolutionMode.STRING,
            strict=False,
        )

        if not isinstance(resolved, str):
            return bool(resolved)

        # Operators in order of precedence
        operators = [
            ("==", lambda a, b: str(a).strip() == str(b).strip()),
            ("!=", lambda a, b: str(a).strip() != str(b).strip()),
            (">=", lambda a, b: float(a) >= float(b)),
            ("<=", lambda a, b: float(a) <= float(b)),
            (">", lambda a, b: float(a) > float(b)),
            ("<", lambda a, b: float(a) < float(b)),
            ("!contains", lambda a, b: str(b) not in str(a)),
            ("contains", lambda a, b: str(b) in str(a)),
        ]

        for op_str, op_func in operators:
            if op_str in resolved:
                parts = resolved.split(op_str, 1)
                if len(parts) == 2:
                    left = parts[0].strip()
                    right = parts[1].strip()
                    try:
                        return op_func(left, right)
                    except (ValueError, TypeError):
                        return False

        # No operator - treat as boolean
        resolved_lower = resolved.lower().strip()
        return resolved_lower in ("true", "yes", "1")


# =============================================================================
# Factory Functions
# =============================================================================

def create_resolver(
    context: Dict[str, Any],
    params: Optional[Dict[str, Any]] = None,
    workflow_metadata: Optional[Dict[str, Any]] = None,
) -> VariableResolver:
    """
    Create a VariableResolver with standard setup.

    Args:
        context: Execution context (node outputs)
        params: Workflow parameters
        workflow_metadata: Workflow info (id, name, version)

    Returns:
        Configured VariableResolver
    """
    import os

    # Build globals
    globals_dict: Dict[str, Any] = {}
    if workflow_metadata:
        globals_dict["workflow"] = workflow_metadata

    # Build env (filtered)
    from ..context.layers import ENV_ALLOWLIST
    env_dict = {
        k: v for k, v in os.environ.items()
        if k in ENV_ALLOWLIST
    }

    return VariableResolver(
        context=context,
        params=params,
        globals=globals_dict,
        env=env_dict,
    )
