"""
Secrets Proxy Tests

Tests for secrets proxy functionality.
Task: 1.20
"""

import time
import pytest
from unittest.mock import patch

from src.core.secrets.proxy import (
    SecretsProxy,
    SecretRef,
    SecretResolution,
    get_secrets_proxy,
)


class TestSecretsProxyWorks:
    """Test 1.20: Secrets proxy works."""

    @pytest.fixture
    def proxy(self):
        """Create a fresh secrets proxy."""
        return SecretsProxy(
            default_ttl_seconds=60,
            default_max_resolutions=1,
        )

    def test_create_ref_returns_opaque_token(self, proxy):
        """Test that create_ref returns opaque reference."""
        ref = proxy.create_ref(
            name="api_key",
            value="sk-secret-12345",
        )

        assert ref.ref.startswith("secret://")
        assert "sk-secret" not in ref.ref  # Value not exposed in ref
        assert ref.name == "api_key"

    def test_resolve_returns_value(self, proxy):
        """Test that resolve returns actual secret value."""
        ref = proxy.create_ref(
            name="api_key",
            value="sk-secret-12345",
        )

        resolution = proxy.resolve(ref.ref)

        assert resolution.success is True
        assert resolution.value == "sk-secret-12345"

    def test_ref_expires_after_ttl(self, proxy):
        """Test that ref expires after TTL."""
        ref = proxy.create_ref(
            name="api_key",
            value="sk-secret-12345",
            ttl_seconds=1,  # 1 second TTL
        )

        # Wait for expiration
        time.sleep(1.1)

        resolution = proxy.resolve(ref.ref)

        assert resolution.success is False
        assert "expired" in resolution.error.lower()

    def test_ref_exhausted_after_max_resolutions(self, proxy):
        """Test that ref is exhausted after max resolutions."""
        ref = proxy.create_ref(
            name="api_key",
            value="sk-secret-12345",
            max_resolutions=1,
        )

        # First resolution succeeds
        resolution1 = proxy.resolve(ref.ref)
        assert resolution1.success is True

        # Second resolution fails
        resolution2 = proxy.resolve(ref.ref)
        assert resolution2.success is False
        assert "already resolved" in resolution2.error.lower() or "not found" in resolution2.error.lower()

    def test_create_refs_for_context(self, proxy):
        """Test bulk ref creation for execution context."""
        secrets = {
            "database_url": "postgres://localhost/db",
            "api_key": "sk-12345",
        }

        refs = proxy.create_refs_for_context(
            secrets=secrets,
            execution_id="exec-123",
        )

        assert len(refs) == 2
        assert "database_url" in refs
        assert "api_key" in refs
        assert refs["database_url"].execution_id == "exec-123"

    def test_execution_context_mismatch(self, proxy):
        """Test that wrong execution context fails resolution."""
        ref = proxy.create_ref(
            name="api_key",
            value="sk-secret-12345",
            execution_id="exec-123",
        )

        # Try to resolve with wrong execution ID
        resolution = proxy.resolve(ref.ref, execution_id="exec-456")

        assert resolution.success is False
        assert "mismatch" in resolution.error.lower()

    def test_revoke_ref(self, proxy):
        """Test revoking a secret reference."""
        ref = proxy.create_ref(
            name="api_key",
            value="sk-secret-12345",
        )

        # Revoke
        result = proxy.revoke(ref.ref)
        assert result is True

        # Try to resolve
        resolution = proxy.resolve(ref.ref)
        assert resolution.success is False

    def test_revoke_for_execution(self, proxy):
        """Test revoking all refs for an execution."""
        refs = proxy.create_refs_for_context(
            secrets={"key1": "val1", "key2": "val2"},
            execution_id="exec-123",
        )

        count = proxy.revoke_for_execution("exec-123")

        assert count == 2

        # All refs should be invalid
        for ref in refs.values():
            resolution = proxy.resolve(ref.ref)
            assert resolution.success is False

    def test_cleanup_expired(self, proxy):
        """Test cleanup of expired references."""
        # Create a ref that expires very quickly
        # Note: ttl_seconds=0 doesn't work because `0 or default` = default
        ref = proxy.create_ref(
            name="temp_key",
            value="temp_value",
            ttl_seconds=1,  # 1 second TTL
        )

        # Wait for expiration
        time.sleep(1.1)

        # Cleanup
        count = proxy.cleanup_expired()

        assert count >= 1

    def test_get_stats(self, proxy):
        """Test getting proxy statistics."""
        proxy.create_ref(name="key1", value="val1")
        proxy.create_ref(name="key2", value="val2")

        stats = proxy.get_stats()

        assert stats["active_refs"] == 2
        assert stats["resolved_refs"] == 0


class TestSecretRef:
    """Test SecretRef dataclass."""

    def test_is_expired(self):
        """Test expiration check."""
        ref = SecretRef(
            ref="secret://abc",
            name="key",
            created_at=time.time() - 100,
            ttl_seconds=60,
        )

        assert ref.is_expired is True

    def test_is_exhausted(self):
        """Test exhaustion check."""
        ref = SecretRef(
            ref="secret://abc",
            name="key",
            max_resolutions=1,
            resolution_count=1,
        )

        assert ref.is_exhausted is True

    def test_is_valid(self):
        """Test validity check."""
        ref = SecretRef(
            ref="secret://abc",
            name="key",
            ttl_seconds=3600,
            max_resolutions=10,
            resolution_count=0,
        )

        assert ref.is_valid is True

    def test_to_dict(self):
        """Test serialization."""
        ref = SecretRef(
            ref="secret://abc",
            name="api_key",
            ttl_seconds=60,
        )

        data = ref.to_dict()

        assert data["ref"] == "secret://abc"
        assert data["name"] == "api_key"
        assert "value" not in data  # Value never exposed
