"""
Tests for catalog module - public view sanitization.

Tests the scrub_catalog_metadata and related functions.
"""
import pytest
from src.core.modules.catalog import (
    scrub_catalog_metadata,
    scrub_schema_defaults,
    scrub_examples,
    get_public_catalog_view,
    get_public_catalog,
    REDACTED_VALUE,
    FORBIDDEN_FIELDS,
    PUBLIC_FIELDS,
)


class TestScrubSchemaDefaults:
    """Test scrub_schema_defaults function."""

    def test_removes_password_field_default(self):
        """Test that password field defaults are removed."""
        schema = {
            "password": {
                "type": "string",
                "format": "password",
                "default": "secret123"
            }
        }
        result = scrub_schema_defaults(schema)

        assert "default" not in result["password"]

    def test_removes_api_key_field_default(self):
        """Test that api_key field defaults are removed."""
        schema = {
            "api_key": {
                "type": "string",
                "default": "sk-12345"
            },
            "apiKey": {
                "type": "string",
                "default": "sk-67890"
            }
        }
        result = scrub_schema_defaults(schema)

        assert "default" not in result["api_key"]
        assert "default" not in result["apiKey"]

    def test_removes_token_field_default(self):
        """Test that token field defaults are removed."""
        schema = {
            "auth_token": {
                "type": "string",
                "default": "bearer-token-123"
            }
        }
        result = scrub_schema_defaults(schema)

        assert "default" not in result["auth_token"]

    def test_keeps_safe_field_defaults(self):
        """Test that non-sensitive field defaults are preserved."""
        schema = {
            "url": {
                "type": "string",
                "default": "https://example.com"
            },
            "timeout": {
                "type": "number",
                "default": 30
            }
        }
        result = scrub_schema_defaults(schema)

        assert result["url"]["default"] == "https://example.com"
        assert result["timeout"]["default"] == 30

    def test_removes_example_from_sensitive_fields(self):
        """Test that examples are removed from sensitive fields."""
        schema = {
            "secret_key": {
                "type": "string",
                "example": "my-secret"
            }
        }
        result = scrub_schema_defaults(schema)

        assert "example" not in result["secret_key"]

    def test_handles_empty_schema(self):
        """Test handling of empty schema."""
        assert scrub_schema_defaults({}) == {}
        assert scrub_schema_defaults(None) is None


class TestScrubExamples:
    """Test scrub_examples function."""

    def test_redacts_api_key_in_params(self):
        """Test that api_key values in examples are redacted."""
        examples = [
            {
                "title": "Example 1",
                "params": {
                    "api_key": "sk-12345",
                    "url": "https://example.com"
                }
            }
        ]
        result = scrub_examples(examples)

        assert result[0]["params"]["api_key"] == REDACTED_VALUE
        assert result[0]["params"]["url"] == "https://example.com"

    def test_redacts_nested_token(self):
        """Test that nested token values are redacted."""
        examples = [
            {
                "title": "Example with auth",
                "params": {
                    "auth": {
                        "token": "bearer-123",
                        "type": "bearer"
                    }
                }
            }
        ]
        result = scrub_examples(examples)

        assert result[0]["params"]["auth"]["token"] == REDACTED_VALUE
        assert result[0]["params"]["auth"]["type"] == "bearer"

    def test_preserves_safe_values(self):
        """Test that non-sensitive values are preserved."""
        examples = [
            {
                "title": "Safe example",
                "params": {
                    "url": "https://api.example.com",
                    "method": "GET",
                    "timeout": 30
                }
            }
        ]
        result = scrub_examples(examples)

        assert result[0]["params"]["url"] == "https://api.example.com"
        assert result[0]["params"]["method"] == "GET"
        assert result[0]["params"]["timeout"] == 30

    def test_handles_empty_examples(self):
        """Test handling of empty examples list."""
        assert scrub_examples([]) == []
        assert scrub_examples(None) is None


class TestScrubCatalogMetadata:
    """Test scrub_catalog_metadata function."""

    def test_removes_forbidden_fields(self):
        """Test that forbidden fields are removed."""
        metadata = {
            "module_id": "test.module",
            "internal_config": {"secret": "value"},
            "default_credentials": {"key": "value"},
            "label": "Test Module"
        }
        result = scrub_catalog_metadata(metadata)

        assert "module_id" in result
        assert "label" in result
        assert "internal_config" not in result
        assert "default_credentials" not in result

    def test_removes_underscore_prefixed_fields(self):
        """Test that _internal fields are removed."""
        metadata = {
            "module_id": "test.module",
            "_internal_flag": True,
            "_debug_info": {"x": 1}
        }
        result = scrub_catalog_metadata(metadata)

        assert "module_id" in result
        assert "_internal_flag" not in result
        assert "_debug_info" not in result

    def test_scrubs_params_schema(self):
        """Test that params_schema is scrubbed."""
        metadata = {
            "module_id": "test.module",
            "params_schema": {
                "api_key": {
                    "type": "string",
                    "default": "sk-12345"
                }
            }
        }
        result = scrub_catalog_metadata(metadata)

        assert "default" not in result["params_schema"]["api_key"]

    def test_scrubs_examples(self):
        """Test that examples are scrubbed."""
        metadata = {
            "module_id": "test.module",
            "examples": [
                {
                    "params": {
                        "password": "secret123"
                    }
                }
            ]
        }
        result = scrub_catalog_metadata(metadata)

        assert result["examples"][0]["params"]["password"] == REDACTED_VALUE

    def test_handles_empty_metadata(self):
        """Test handling of empty metadata."""
        assert scrub_catalog_metadata({}) == {}
        assert scrub_catalog_metadata(None) is None


class TestGetPublicCatalogView:
    """Test get_public_catalog_view function."""

    def test_only_includes_public_fields(self):
        """Test that only PUBLIC_FIELDS are included."""
        metadata = {
            "module_id": "test.module",
            "version": "1.0.0",
            "label": "Test",
            "internal_config": {"x": 1},
            "private_notes": "secret"
        }
        result = get_public_catalog_view(metadata)

        assert "module_id" in result
        assert "version" in result
        assert "label" in result
        assert "internal_config" not in result
        assert "private_notes" not in result

    def test_can_exclude_schema(self):
        """Test excluding schema from public view."""
        metadata = {
            "module_id": "test.module",
            "params_schema": {"x": {"type": "string"}},
            "output_schema": {"result": {"type": "any"}}
        }
        result = get_public_catalog_view(metadata, include_schema=False)

        assert "module_id" in result
        assert "params_schema" not in result
        assert "output_schema" not in result

    def test_includes_capabilities(self):
        """Test that capabilities are included (for UI warnings)."""
        metadata = {
            "module_id": "test.module",
            "capabilities": ["network.public", "shell.exec"]
        }
        result = get_public_catalog_view(metadata)

        assert "capabilities" in result
        assert result["capabilities"] == ["network.public", "shell.exec"]


class TestGetPublicCatalog:
    """Test get_public_catalog function."""

    def test_scrubs_all_modules(self):
        """Test that all modules in catalog are scrubbed."""
        catalog = {
            "module.a": {
                "module_id": "module.a",
                "params_schema": {
                    "api_key": {"type": "string", "default": "secret"}
                }
            },
            "module.b": {
                "module_id": "module.b",
                "internal_config": {"x": 1}
            }
        }
        result = get_public_catalog(catalog)

        # module.a: api_key default removed
        assert "default" not in result["module.a"]["params_schema"]["api_key"]

        # module.b: internal_config removed
        assert "internal_config" not in result["module.b"]
