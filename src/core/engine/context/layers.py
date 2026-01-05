"""
Context Layers

Implements security-isolated context layers for workflow execution.
Separates public, private, and secret data to prevent accidental exposure.

Version: 1.0.0
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, Optional, Set

from ..sdk.models import ContextLayer

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Environment variables allowed in public context (never secrets)
ENV_ALLOWLIST: FrozenSet[str] = frozenset({
    "NODE_ENV",
    "DEPLOYMENT_MODE",
    "LOG_LEVEL",
    "TZ",
    "LANG",
    "LC_ALL",
})

# Keys that should never be logged
SECRET_PATTERNS: FrozenSet[str] = frozenset({
    "key",
    "token",
    "secret",
    "password",
    "credential",
    "auth",
    "bearer",
    "api_key",
    "apikey",
})

# Private key prefixes (double underscore = private)
PRIVATE_PREFIX = "__"


# =============================================================================
# Exceptions
# =============================================================================

class ContextAccessError(Exception):
    """Raised when accessing restricted context"""
    pass


class SecretExposureError(Exception):
    """Raised when attempting to expose secrets"""
    pass


# =============================================================================
# Layer Context
# =============================================================================

@dataclass
class LayeredContext:
    """
    Security-isolated context with three layers.

    - public: Exposed to VariableResolver, included in VarCatalog
    - private: Only accessible by allowlisted modules
    - secrets: Never returned to cloud/UI, never logged
    """

    public: Dict[str, Any] = field(default_factory=dict)
    private: Dict[str, Any] = field(default_factory=dict)
    secrets: Dict[str, Any] = field(default_factory=dict)

    # Modules allowed to access private layer
    _private_allowlist: Set[str] = field(default_factory=set)

    # Modules allowed to access secrets layer
    _secrets_allowlist: Set[str] = field(default_factory=set)

    def set_public(self, key: str, value: Any) -> None:
        """Set a public variable"""
        if self._is_secret_key(key):
            raise SecretExposureError(
                f"Cannot set potentially secret key '{key}' in public layer"
            )
        self.public[key] = value

    def set_private(self, key: str, value: Any) -> None:
        """Set a private variable"""
        self.private[key] = value

    def set_secret(self, key: str, value: Any) -> None:
        """Set a secret variable"""
        self.secrets[key] = value

    def get_public(self, key: str, default: Any = None) -> Any:
        """Get a public variable"""
        return self.public.get(key, default)

    def get_private(
        self,
        key: str,
        module_id: str,
        default: Any = None
    ) -> Any:
        """Get a private variable (requires module in allowlist)"""
        if module_id not in self._private_allowlist:
            logger.warning(
                f"Module '{module_id}' denied access to private key '{key}'"
            )
            return default
        return self.private.get(key, default)

    def get_secret(
        self,
        key: str,
        module_id: str,
        default: Any = None
    ) -> Any:
        """Get a secret variable (requires module in allowlist)"""
        if module_id not in self._secrets_allowlist:
            logger.warning(
                f"Module '{module_id}' denied access to secret key '{key}'"
            )
            return default
        return self.secrets.get(key, default)

    def allow_private_access(self, module_id: str) -> None:
        """Grant a module access to private layer"""
        self._private_allowlist.add(module_id)

    def allow_secrets_access(self, module_id: str) -> None:
        """Grant a module access to secrets layer"""
        self._secrets_allowlist.add(module_id)

    def get_for_resolver(self) -> Dict[str, Any]:
        """Get context for VariableResolver (public only)"""
        return self.public.copy()

    def get_for_catalog(self) -> Dict[str, Any]:
        """Get context for VarCatalog (public only, safe for UI)"""
        return self.public.copy()

    def get_for_module(
        self,
        module_id: str,
        requires_credentials: bool = False
    ) -> Dict[str, Any]:
        """
        Get context for a specific module.

        Args:
            module_id: The module requesting context
            requires_credentials: Whether module declared requires_credentials

        Returns:
            Merged context appropriate for the module
        """
        result = self.public.copy()

        # Add private if allowed
        if module_id in self._private_allowlist:
            result.update(self.private)

        # Add secrets only if module requires credentials AND is allowed
        if requires_credentials and module_id in self._secrets_allowlist:
            result.update(self.secrets)

        return result

    def get_safe_log_context(self) -> Dict[str, Any]:
        """Get context safe for logging (public + masked private)"""
        result = self.public.copy()

        for key in self.private:
            result[key] = "[PRIVATE]"

        # Never include secrets, not even masked
        return result

    def merge_public(self, data: Dict[str, Any]) -> None:
        """Merge data into public layer with validation"""
        for key, value in data.items():
            if self._is_secret_key(key):
                logger.warning(
                    f"Skipping potentially secret key '{key}' in public merge"
                )
                continue
            self.public[key] = value

    def _is_secret_key(self, key: str) -> bool:
        """Check if a key looks like a secret"""
        key_lower = key.lower()
        return any(pattern in key_lower for pattern in SECRET_PATTERNS)

    def to_dict(self, include_private: bool = False) -> Dict[str, Any]:
        """
        Convert to dictionary for serialization.

        Args:
            include_private: Whether to include private (masked)

        Returns:
            Dictionary representation (never includes secrets)
        """
        result = {"public": self.public.copy()}

        if include_private:
            result["private"] = {k: "[PRIVATE]" for k in self.private}

        # Never include secrets
        return result


# =============================================================================
# Context Builder
# =============================================================================

class ContextBuilder:
    """Builder for creating LayeredContext with proper isolation"""

    def __init__(self) -> None:
        self._public: Dict[str, Any] = {}
        self._private: Dict[str, Any] = {}
        self._secrets: Dict[str, Any] = {}
        self._private_allowlist: Set[str] = set()
        self._secrets_allowlist: Set[str] = set()

    def with_workflow_params(self, params: Dict[str, Any]) -> "ContextBuilder":
        """Add workflow parameters to public context"""
        for key, value in params.items():
            if key.startswith(PRIVATE_PREFIX):
                self._private[key] = value
            else:
                self._public[key] = value
        return self

    def with_user_context(
        self,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> "ContextBuilder":
        """Add user context to private layer"""
        if user_id:
            self._private["__user_id"] = user_id
        if tenant_id:
            self._private["__tenant_id"] = tenant_id
        if metadata:
            for key, value in metadata.items():
                self._private[f"__user_{key}"] = value
        return self

    def with_credentials(
        self,
        credentials: Dict[str, str],
        allowed_modules: Optional[Set[str]] = None
    ) -> "ContextBuilder":
        """Add credentials to secrets layer"""
        self._secrets.update(credentials)
        if allowed_modules:
            self._secrets_allowlist.update(allowed_modules)
        return self

    def with_private_access(self, module_ids: Set[str]) -> "ContextBuilder":
        """Grant modules access to private layer"""
        self._private_allowlist.update(module_ids)
        return self

    def with_secrets_access(self, module_ids: Set[str]) -> "ContextBuilder":
        """Grant modules access to secrets layer"""
        self._secrets_allowlist.update(module_ids)
        return self

    def with_environment(
        self,
        env_vars: Optional[Dict[str, str]] = None,
        allowlist: Optional[Set[str]] = None
    ) -> "ContextBuilder":
        """Add environment variables to public context (filtered)"""
        import os

        allowed = allowlist or ENV_ALLOWLIST

        if env_vars:
            source = env_vars
        else:
            source = dict(os.environ)

        for key, value in source.items():
            if key in allowed:
                self._public[f"env.{key}"] = value

        return self

    def build(self) -> LayeredContext:
        """Build the LayeredContext"""
        ctx = LayeredContext(
            public=self._public.copy(),
            private=self._private.copy(),
            secrets=self._secrets.copy(),
        )
        ctx._private_allowlist = self._private_allowlist.copy()
        ctx._secrets_allowlist = self._secrets_allowlist.copy()
        return ctx


# =============================================================================
# Factory Functions
# =============================================================================

def create_context(
    params: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    credentials: Optional[Dict[str, str]] = None,
    credential_modules: Optional[Set[str]] = None,
) -> LayeredContext:
    """
    Create a LayeredContext with common setup.

    Args:
        params: Workflow parameters
        user_id: User identifier
        tenant_id: Tenant identifier
        credentials: API keys and secrets
        credential_modules: Modules allowed to access credentials

    Returns:
        Configured LayeredContext
    """
    builder = ContextBuilder()

    if params:
        builder.with_workflow_params(params)

    if user_id or tenant_id:
        builder.with_user_context(user_id=user_id, tenant_id=tenant_id)

    if credentials:
        builder.with_credentials(
            credentials,
            allowed_modules=credential_modules
        )

    builder.with_environment()

    return builder.build()


def merge_node_output(
    context: LayeredContext,
    node_id: str,
    output: Dict[str, Any]
) -> None:
    """
    Merge node output into context public layer.

    Args:
        context: The context to update
        node_id: Node that produced the output
        output: The output data
    """
    # Store under node_id for {{node_id.field}} access
    context.set_public(node_id, output)

    # Also store as 'input' for next node's {{input}} shorthand
    context.set_public("input", output)
