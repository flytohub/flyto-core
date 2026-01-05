"""
Unit Tests for Context Layers

Tests security-isolated context management with public/private/secrets layers.
"""

import pytest
import os
from typing import Any, Dict

from core.engine.context.layers import (
    LayeredContext,
    ContextBuilder,
    create_context,
    merge_node_output,
    ContextAccessError,
    SecretExposureError,
    ENV_ALLOWLIST,
    SECRET_PATTERNS,
    PRIVATE_PREFIX,
)


class TestLayeredContext:
    """Tests for LayeredContext"""

    def test_create_empty_context(self):
        ctx = LayeredContext()
        assert ctx.public == {}
        assert ctx.private == {}
        assert ctx.secrets == {}

    def test_create_with_layers(self):
        ctx = LayeredContext(
            public={"key": "value"},
            private={"_internal": "data"},
            secrets={"API_KEY": "secret123"},
        )
        assert ctx.public["key"] == "value"
        assert ctx.private["_internal"] == "data"
        assert ctx.secrets["API_KEY"] == "secret123"

    def test_set_public_value(self):
        ctx = LayeredContext()
        ctx.set_public("name", "value")
        assert ctx.public["name"] == "value"

    def test_set_private_value(self):
        ctx = LayeredContext()
        ctx.set_private("_internal", "data")
        assert ctx.private["_internal"] == "data"
        assert "_internal" not in ctx.public

    def test_set_secret_value(self):
        ctx = LayeredContext()
        ctx.set_secret("API_KEY", "secret123")
        assert ctx.secrets["API_KEY"] == "secret123"
        assert "API_KEY" not in ctx.public

    def test_get_public_value(self):
        ctx = LayeredContext(public={"name": "test"})
        assert ctx.get_public("name") == "test"

    def test_get_public_with_default(self):
        ctx = LayeredContext()
        assert ctx.get_public("missing", "default") == "default"

    def test_get_private_requires_allowlist(self):
        ctx = LayeredContext(private={"_count": 42})
        # Without allowlist, returns default
        result = ctx.get_private("_count", "unauthorized_module")
        assert result is None

    def test_get_private_with_allowlist(self):
        ctx = LayeredContext(private={"_count": 42})
        ctx.allow_private_access("authorized_module")
        result = ctx.get_private("_count", "authorized_module")
        assert result == 42

    def test_get_secret_requires_allowlist(self):
        ctx = LayeredContext(secrets={"API_KEY": "secret"})
        # Without allowlist, returns default
        result = ctx.get_secret("API_KEY", "unauthorized_module")
        assert result is None

    def test_get_secret_with_allowlist(self):
        ctx = LayeredContext(secrets={"API_KEY": "secret"})
        ctx.allow_secrets_access("authorized_module")
        result = ctx.get_secret("API_KEY", "authorized_module")
        assert result == "secret"

    def test_get_for_resolver_returns_public(self):
        ctx = LayeredContext(
            public={"name": "test"},
            secrets={"API_KEY": "secret123"},
        )
        result = ctx.get_for_resolver()
        assert "name" in result
        assert "API_KEY" not in result

    def test_get_for_catalog_excludes_secrets(self):
        ctx = LayeredContext(
            public={"name": "test"},
            private={"_internal": "data"},
            secrets={"API_KEY": "secret123"},
        )
        result = ctx.get_for_catalog()
        assert "name" in result
        assert "API_KEY" not in result
        assert "_internal" not in result

    def test_get_safe_log_context(self):
        ctx = LayeredContext(
            public={"name": "test"},
            private={"_internal": "data"},
            secrets={"API_KEY": "secret123"},
        )
        result = ctx.get_safe_log_context()
        assert result["name"] == "test"
        assert result["_internal"] == "[PRIVATE]"
        assert "API_KEY" not in result

    def test_merge_public(self):
        ctx = LayeredContext(public={"a": 1})
        ctx.merge_public({"b": 2})
        assert ctx.public == {"a": 1, "b": 2}

    def test_merge_public_skips_secrets(self):
        ctx = LayeredContext()
        ctx.merge_public({"name": "test", "api_key": "secret"})
        assert "name" in ctx.public
        # api_key should be skipped as it looks like a secret
        assert "api_key" not in ctx.public

    def test_set_public_rejects_secret_keys(self):
        ctx = LayeredContext()
        with pytest.raises(SecretExposureError):
            ctx.set_public("password", "secret123")

    def test_to_dict_excludes_secrets(self):
        ctx = LayeredContext(
            public={"name": "test"},
            private={"_internal": "data"},
            secrets={"API_KEY": "secret123"},
        )
        result = ctx.to_dict()
        assert "public" in result
        assert "secrets" not in result

    def test_to_dict_with_private(self):
        ctx = LayeredContext(
            public={"name": "test"},
            private={"_internal": "data"},
        )
        result = ctx.to_dict(include_private=True)
        assert result["private"]["_internal"] == "[PRIVATE]"


class TestContextBuilder:
    """Tests for ContextBuilder fluent API"""

    def test_builder_with_workflow_params(self):
        ctx = (
            ContextBuilder()
            .with_workflow_params({"key": "value"})
            .build()
        )
        assert ctx.get_public("key") == "value"

    def test_builder_private_params(self):
        ctx = (
            ContextBuilder()
            .with_workflow_params({"__internal": "data", "public": "value"})
            .build()
        )
        # Double underscore goes to private
        assert "__internal" in ctx.private
        assert "public" in ctx.public

    def test_builder_with_user_context(self):
        ctx = (
            ContextBuilder()
            .with_user_context(user_id="user123", tenant_id="tenant456")
            .build()
        )
        assert ctx.private["__user_id"] == "user123"
        assert ctx.private["__tenant_id"] == "tenant456"

    def test_builder_with_credentials(self):
        ctx = (
            ContextBuilder()
            .with_credentials(
                {"API_KEY": "secret123"},
                allowed_modules={"llm.agent"}
            )
            .build()
        )
        assert ctx.secrets["API_KEY"] == "secret123"
        # Should be accessible by allowed module
        result = ctx.get_secret("API_KEY", "llm.agent")
        assert result == "secret123"

    def test_builder_with_env_filter(self):
        # Set a test env var
        os.environ["NODE_ENV"] = "test"
        try:
            ctx = (
                ContextBuilder()
                .with_environment()
                .build()
            )
            # Should include filtered env vars
            assert ctx.get_public("env.NODE_ENV") == "test"
        finally:
            del os.environ["NODE_ENV"]

    def test_builder_chain(self):
        ctx = (
            ContextBuilder()
            .with_workflow_params({"name": "test"})
            .with_credentials({"KEY": "secret"})
            .with_user_context(user_id="user123")
            .build()
        )
        assert ctx.get_public("name") == "test"
        assert ctx.secrets["KEY"] == "secret"
        assert ctx.private["__user_id"] == "user123"


class TestCreateContext:
    """Tests for create_context factory"""

    def test_create_context_basic(self):
        ctx = create_context(params={"key": "value"})
        assert ctx.get_public("key") == "value"

    def test_create_context_with_credentials(self):
        ctx = create_context(
            params={},
            credentials={"API_KEY": "secret123"},
            credential_modules={"llm.agent"},
        )
        assert ctx.secrets["API_KEY"] == "secret123"
        result = ctx.get_secret("API_KEY", "llm.agent")
        assert result == "secret123"

    def test_create_context_with_user_id(self):
        ctx = create_context(
            params={},
            user_id="user123",
        )
        assert ctx.private["__user_id"] == "user123"


class TestMergeNodeOutput:
    """Tests for merge_node_output function"""

    def test_merge_simple_output(self):
        ctx = LayeredContext()
        output = {"result": "success", "data": {"key": "value"}}
        merge_node_output(ctx, "node1", output)
        assert ctx.get_public("node1") == output
        assert ctx.get_public("input") == output

    def test_merge_multiple_nodes(self):
        ctx = LayeredContext()
        merge_node_output(ctx, "node1", {"a": 1})
        merge_node_output(ctx, "node2", {"b": 2})
        assert ctx.get_public("node1") == {"a": 1}
        assert ctx.get_public("node2") == {"b": 2}
        # Input should be the last node's output
        assert ctx.get_public("input") == {"b": 2}


class TestSecretPatterns:
    """Tests for secret pattern detection"""

    def test_is_secret_key(self):
        ctx = LayeredContext()
        # These should be detected as secrets
        assert ctx._is_secret_key("api_key")
        assert ctx._is_secret_key("API_KEY")
        assert ctx._is_secret_key("password")
        assert ctx._is_secret_key("DATABASE_PASSWORD")
        assert ctx._is_secret_key("auth_token")
        assert ctx._is_secret_key("secret_value")

    def test_non_secret_key(self):
        ctx = LayeredContext()
        # These should NOT be detected as secrets
        assert not ctx._is_secret_key("username")
        assert not ctx._is_secret_key("email")
        assert not ctx._is_secret_key("name")
        assert not ctx._is_secret_key("count")


class TestEnvAllowlist:
    """Tests for environment variable allowlist"""

    def test_allowlist_contains_common_vars(self):
        assert "NODE_ENV" in ENV_ALLOWLIST
        assert "TZ" in ENV_ALLOWLIST
        assert "LOG_LEVEL" in ENV_ALLOWLIST

    def test_allowlist_excludes_secrets(self):
        # These should NOT be in the allowlist
        assert "OPENAI_API_KEY" not in ENV_ALLOWLIST
        assert "AWS_SECRET_ACCESS_KEY" not in ENV_ALLOWLIST
        assert "DATABASE_PASSWORD" not in ENV_ALLOWLIST


class TestPrivatePrefix:
    """Tests for private prefix handling"""

    def test_double_underscore_constant(self):
        assert PRIVATE_PREFIX == "__"
