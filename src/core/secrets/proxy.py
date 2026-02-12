"""
Secrets Proxy

Provides secure secret handling for plugins.
Plugins receive opaque reference tokens instead of raw secret values.
Core resolves references when making actual service calls.

Security Model:
- Plugins NEVER see raw secret values
- References are short-lived (60s TTL by default)
- References can only be resolved once (single-use)
- Resolution requires matching execution context
"""

import hashlib
import logging
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class SecretRef:
    """
    Opaque reference to a secret.

    Plugins receive this instead of the raw secret value.
    """
    ref: str  # Opaque reference token (e.g., "secret://abc123")
    name: str  # Secret name/key
    created_at: float = field(default_factory=time.time)
    ttl_seconds: int = 60
    max_resolutions: int = 1
    resolution_count: int = 0
    execution_id: Optional[str] = None  # Tied to specific execution

    @property
    def is_expired(self) -> bool:
        """Check if reference has expired."""
        return time.time() > (self.created_at + self.ttl_seconds)

    @property
    def is_exhausted(self) -> bool:
        """Check if resolution limit reached."""
        return self.resolution_count >= self.max_resolutions

    @property
    def is_valid(self) -> bool:
        """Check if reference can still be resolved."""
        return not self.is_expired and not self.is_exhausted

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "ref": self.ref,
            "name": self.name,
            "ttl_seconds": self.ttl_seconds,
        }


@dataclass
class SecretResolution:
    """Result of resolving a secret reference."""
    success: bool
    value: Optional[str] = None
    error: Optional[str] = None


class SecretsProxy:
    """
    Proxy for secure secret handling.

    Creates opaque references for plugins and resolves them
    when the core needs the actual values.
    """

    def __init__(
        self,
        default_ttl_seconds: int = 60,
        default_max_resolutions: int = 1,
    ):
        self.default_ttl_seconds = default_ttl_seconds
        self.default_max_resolutions = default_max_resolutions

        # Maps ref token -> SecretRef
        self._refs: Dict[str, SecretRef] = {}

        # Maps ref token -> actual secret value
        self._values: Dict[str, str] = {}

        # Track resolved refs for cleanup
        self._resolved_refs: Set[str] = set()

    def create_ref(
        self,
        name: str,
        value: str,
        execution_id: Optional[str] = None,
        ttl_seconds: Optional[int] = None,
        max_resolutions: Optional[int] = None,
    ) -> SecretRef:
        """
        Create an opaque reference for a secret.

        Args:
            name: Secret name/key
            value: Actual secret value (stored securely)
            execution_id: Optional execution context ID
            ttl_seconds: Reference TTL (default: 60)
            max_resolutions: Max times ref can be resolved (default: 1)

        Returns:
            SecretRef with opaque token
        """
        # Generate unique reference token
        token = self._generate_token()
        ref_uri = f"secret://{token}"

        ref = SecretRef(
            ref=ref_uri,
            name=name,
            ttl_seconds=ttl_seconds or self.default_ttl_seconds,
            max_resolutions=max_resolutions or self.default_max_resolutions,
            execution_id=execution_id,
        )

        # Store reference and value
        self._refs[ref_uri] = ref
        self._values[ref_uri] = value

        logger.debug("Created secret ref")

        return ref

    def create_refs_for_context(
        self,
        secrets: Dict[str, str],
        execution_id: Optional[str] = None,
    ) -> Dict[str, SecretRef]:
        """
        Create references for all secrets in a context.

        Args:
            secrets: Dict of secret_name -> secret_value
            execution_id: Optional execution context ID

        Returns:
            Dict of secret_name -> SecretRef
        """
        refs = {}
        for name, value in secrets.items():
            refs[name] = self.create_ref(
                name=name,
                value=value,
                execution_id=execution_id,
            )
        return refs

    def resolve(
        self,
        ref_uri: str,
        execution_id: Optional[str] = None,
    ) -> SecretResolution:
        """
        Resolve a secret reference to its actual value.

        Args:
            ref_uri: The opaque reference (e.g., "secret://abc123")
            execution_id: Execution context (must match if ref was tied)

        Returns:
            SecretResolution with value or error
        """
        # Check if ref exists
        ref = self._refs.get(ref_uri)
        if not ref:
            logger.warning(f"Secret ref not found: {ref_uri}")
            return SecretResolution(
                success=False,
                error="Secret reference not found",
            )

        # Check expiration
        if ref.is_expired:
            logger.warning(f"Secret ref expired: {ref_uri}")
            self._cleanup_ref(ref_uri)
            return SecretResolution(
                success=False,
                error="Secret reference expired",
            )

        # Check resolution limit
        if ref.is_exhausted:
            logger.warning(f"Secret ref exhausted: {ref_uri}")
            return SecretResolution(
                success=False,
                error="Secret reference already resolved",
            )

        # Check execution context
        if ref.execution_id and ref.execution_id != execution_id:
            logger.warning(f"Secret ref execution mismatch: {ref_uri}")
            return SecretResolution(
                success=False,
                error="Execution context mismatch",
            )

        # Get value and increment counter
        value = self._values.get(ref_uri)
        if value is None:
            logger.error(f"Secret value missing for ref: {ref_uri}")
            return SecretResolution(
                success=False,
                error="Secret value not found",
            )

        ref.resolution_count += 1
        self._resolved_refs.add(ref_uri)

        logger.debug(f"Resolved secret ref: {ref_uri} ({ref.resolution_count}/{ref.max_resolutions})")

        # Cleanup if exhausted
        if ref.is_exhausted:
            self._cleanup_ref(ref_uri)

        return SecretResolution(
            success=True,
            value=value,
        )

    def revoke(self, ref_uri: str) -> bool:
        """
        Revoke a secret reference immediately.

        Args:
            ref_uri: The reference to revoke

        Returns:
            True if revoked, False if not found
        """
        if ref_uri in self._refs:
            self._cleanup_ref(ref_uri)
            logger.info(f"Revoked secret ref: {ref_uri}")
            return True
        return False

    def revoke_for_execution(self, execution_id: str) -> int:
        """
        Revoke all references for an execution context.

        Args:
            execution_id: Execution context ID

        Returns:
            Number of references revoked
        """
        to_revoke = [
            ref_uri
            for ref_uri, ref in self._refs.items()
            if ref.execution_id == execution_id
        ]

        for ref_uri in to_revoke:
            self._cleanup_ref(ref_uri)

        if to_revoke:
            logger.info(f"Revoked {len(to_revoke)} refs for execution: {execution_id}")

        return len(to_revoke)

    def cleanup_expired(self) -> int:
        """
        Clean up all expired references.

        Returns:
            Number of references cleaned up
        """
        expired = [
            ref_uri
            for ref_uri, ref in self._refs.items()
            if ref.is_expired
        ]

        for ref_uri in expired:
            self._cleanup_ref(ref_uri)

        if expired:
            logger.debug(f"Cleaned up {len(expired)} expired secret refs")

        return len(expired)

    def get_stats(self) -> Dict[str, Any]:
        """Get proxy statistics."""
        return {
            "active_refs": len(self._refs),
            "resolved_refs": len(self._resolved_refs),
            "expired_count": sum(1 for ref in self._refs.values() if ref.is_expired),
        }

    def _generate_token(self) -> str:
        """Generate a secure random token."""
        return secrets.token_urlsafe(24)

    def _cleanup_ref(self, ref_uri: str):
        """Remove a reference and its value."""
        self._refs.pop(ref_uri, None)
        self._values.pop(ref_uri, None)


# Global singleton
_proxy: Optional[SecretsProxy] = None


def get_secrets_proxy() -> SecretsProxy:
    """Get global secrets proxy instance."""
    global _proxy
    if _proxy is None:
        _proxy = SecretsProxy()
    return _proxy
