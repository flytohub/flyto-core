"""
Security Tests for Plugin Runtime

Tests for security fixes in the subprocess runtime:
- Environment variable whitelist (prevent credential leakage)
- Entry point path traversal validation
- Browser session authentication
- Manifest security validation
- JSON-RPC input validation and secret filtering
"""

import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from core.runtime.process import ProcessConfig, SAFE_ENV_VARS
from core.runtime.languages import validate_entry_point, LanguageConfig, get_language_config
from core.runtime.browser_session import BrowserSession, BrowserSessionManager
from core.runtime.manager import (
    validate_plugin_id,
    validate_version,
    validate_permissions,
    PluginManifest,
)
from core.runtime.protocol import (
    filter_sensitive_data,
    validate_message_size,
    JsonRpcRequest,
    JsonRpcResponse,
    ValidatedJsonRpcRequest,
    InvokeParams,
    MAX_MESSAGE_SIZE,
)
from core.runtime.exceptions import (
    SecurityError,
    PathTraversalError,
    ValidationError,
    InvalidSessionTokenError,
    UnauthorizedAccessError,
)


class TestEnvironmentVariableWhitelist:
    """Tests for CRITICAL: Environment variable leak prevention."""

    def test_secrets_not_leaked(self):
        """Verify secrets in parent process are not passed to plugins."""
        # Set some "secrets" in the environment
        secrets = {
            "SECRET_API_KEY": "super_secret_key_12345",
            "DATABASE_PASSWORD": "db_password_67890",
            "AWS_SECRET_ACCESS_KEY": "aws_secret_abcdef",
            "OPENAI_API_KEY": "sk-test123456789",
            "GITHUB_TOKEN": "ghp_xxxxxxxxxxxx",
            "ANTHROPIC_API_KEY": "sk-ant-api123",
        }

        for key, value in secrets.items():
            os.environ[key] = value

        try:
            config = ProcessConfig(
                plugin_id="test-plugin",
                plugin_dir=Path("/tmp/test"),
            )
            env = config.get_process_env()

            # None of the secrets should be in the environment
            for secret_key in secrets:
                assert secret_key not in env, f"Secret {secret_key} was leaked!"
        finally:
            # Clean up
            for key in secrets:
                os.environ.pop(key, None)

    def test_safe_vars_are_present(self):
        """Verify safe/required environment variables are present."""
        config = ProcessConfig(
            plugin_id="test-plugin",
            plugin_dir=Path("/tmp/test"),
        )
        env = config.get_process_env()

        # PATH is essential for subprocess execution
        assert "PATH" in env

        # Flyto-specific vars should be set
        assert env["FLYTO_PLUGIN_ID"] == "test-plugin"
        assert "FLYTO_PROTOCOL_VERSION" in env
        assert "FLYTO_LANGUAGE" in env

    def test_language_specific_vars_added(self):
        """Verify language-specific env vars are added."""
        config = ProcessConfig(
            plugin_id="test-plugin",
            plugin_dir=Path("/tmp/test"),
            language="python",
        )
        env = config.get_process_env()

        # Python should have PYTHONUNBUFFERED
        assert env.get("PYTHONUNBUFFERED") == "1"

    def test_user_env_vars_override(self):
        """Verify user-specified env vars are added."""
        config = ProcessConfig(
            plugin_id="test-plugin",
            plugin_dir=Path("/tmp/test"),
            env={"CUSTOM_VAR": "custom_value"},
        )
        env = config.get_process_env()

        assert env["CUSTOM_VAR"] == "custom_value"


class TestPathTraversalValidation:
    """Tests for CRITICAL: Entry point path traversal prevention."""

    def test_double_dot_blocked(self):
        """Verify .. path traversal is blocked."""
        with pytest.raises(PathTraversalError):
            validate_entry_point("../../../etc/passwd", Path("/plugins/test"))

    def test_absolute_path_blocked(self):
        """Verify absolute paths are blocked."""
        with pytest.raises(PathTraversalError):
            validate_entry_point("/etc/passwd", Path("/plugins/test"))

    def test_null_byte_blocked(self):
        """Verify null byte injection is blocked."""
        with pytest.raises(PathTraversalError):
            validate_entry_point("main.py\x00../../etc/passwd", Path("/plugins/test"))

    def test_valid_entry_point_accepted(self, tmp_path):
        """Verify valid entry points are accepted."""
        # Create a valid entry point
        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()
        entry_file = plugin_dir / "main.py"
        entry_file.touch()

        result = validate_entry_point("main.py", plugin_dir)
        assert result == entry_file.resolve()

    def test_nested_valid_path_accepted(self, tmp_path):
        """Verify nested paths within plugin dir are accepted."""
        plugin_dir = tmp_path / "test-plugin"
        src_dir = plugin_dir / "src"
        src_dir.mkdir(parents=True)
        entry_file = src_dir / "main.py"
        entry_file.touch()

        result = validate_entry_point("src/main.py", plugin_dir)
        assert result == entry_file.resolve()

    def test_symlink_escape_blocked(self, tmp_path):
        """Verify symlinks that escape plugin dir are blocked."""
        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()

        # Create a symlink that points outside plugin dir
        outside_file = tmp_path / "outside.py"
        outside_file.touch()
        symlink = plugin_dir / "evil.py"
        symlink.symlink_to(outside_file)

        with pytest.raises(PathTraversalError):
            validate_entry_point("evil.py", plugin_dir)


class TestBrowserSessionAuthentication:
    """Tests for CRITICAL: CDP WebSocket authentication."""

    def test_session_token_generated(self):
        """Verify session token is automatically generated."""
        session = BrowserSession(
            session_id="test",
            ws_endpoint="ws://localhost:9222/test",
        )

        assert session.session_token
        assert len(session.session_token) >= 32

    def test_owner_authorized_with_token(self):
        """Verify owner is authorized with correct token."""
        session = BrowserSession(
            session_id="test",
            ws_endpoint="ws://localhost:9222/test",
            owner_plugin="my-plugin",
        )
        session.authorize_plugin("my-plugin")

        assert session.is_authorized("my-plugin", session.session_token)

    def test_wrong_token_rejected(self):
        """Verify wrong token is rejected."""
        session = BrowserSession(
            session_id="test",
            ws_endpoint="ws://localhost:9222/test",
            owner_plugin="my-plugin",
        )
        session.authorize_plugin("my-plugin")

        assert not session.is_authorized("my-plugin", "wrong-token")

    def test_unauthorized_plugin_rejected(self):
        """Verify unauthorized plugins are rejected."""
        session = BrowserSession(
            session_id="test",
            ws_endpoint="ws://localhost:9222/test",
            owner_plugin="my-plugin",
        )
        session.authorize_plugin("my-plugin")

        assert not session.is_authorized("other-plugin", session.session_token)

    def test_authorized_plugin_accepted(self):
        """Verify explicitly authorized plugins are accepted."""
        session = BrowserSession(
            session_id="test",
            ws_endpoint="ws://localhost:9222/test",
            owner_plugin="my-plugin",
        )
        session.authorize_plugin("my-plugin")
        session.authorize_plugin("allowed-plugin")

        assert session.is_authorized("allowed-plugin", session.session_token)

    def test_revoke_access(self):
        """Verify access can be revoked."""
        session = BrowserSession(
            session_id="test",
            ws_endpoint="ws://localhost:9222/test",
            owner_plugin="my-plugin",
        )
        session.authorize_plugin("guest-plugin")

        assert session.is_authorized("guest-plugin", session.session_token)

        session.revoke_plugin("guest-plugin")

        assert not session.is_authorized("guest-plugin", session.session_token)


class TestManifestValidation:
    """Tests for manifest security validation."""

    def test_valid_plugin_id(self):
        """Verify valid plugin IDs are accepted."""
        validate_plugin_id("my-plugin")
        validate_plugin_id("vendor/plugin")
        validate_plugin_id("a")
        validate_plugin_id("plugin_v2")

    def test_path_traversal_in_id_blocked(self):
        """Verify path traversal in plugin ID is blocked."""
        with pytest.raises(SecurityError):
            validate_plugin_id("../etc/passwd")

    def test_too_long_id_blocked(self):
        """Verify too long plugin IDs are blocked."""
        with pytest.raises(ValidationError):
            validate_plugin_id("a" * 200)

    def test_empty_id_blocked(self):
        """Verify empty plugin ID is blocked."""
        with pytest.raises(ValidationError):
            validate_plugin_id("")

    def test_valid_version(self):
        """Verify valid versions are accepted."""
        validate_version("1.0.0")
        validate_version("1.0.0-beta")
        validate_version("1.0.0-beta.1")
        validate_version("1.0.0+build123")

    def test_dangerous_permissions_flagged(self):
        """Verify dangerous permissions are flagged."""
        dangerous = validate_permissions(["read", "write", "filesystem:*"])
        assert "filesystem:*" in dangerous

    def test_wildcard_permissions_flagged(self):
        """Verify wildcard permissions are flagged."""
        dangerous = validate_permissions(["*"])
        assert "*" in dangerous

    def test_manifest_validation_on_create(self):
        """Verify manifest validation happens on creation."""
        # Valid manifest
        manifest = PluginManifest.from_dict({
            "id": "test-plugin",
            "version": "1.0.0",
            "steps": [],
        })
        assert manifest.id == "test-plugin"

        # Invalid ID should raise
        with pytest.raises(SecurityError):
            PluginManifest.from_dict({
                "id": "../evil",
                "version": "1.0.0",
                "steps": [],
            })


class TestJsonRpcValidation:
    """Tests for JSON-RPC input validation and secret filtering."""

    def test_filter_password(self):
        """Verify passwords are filtered from error messages."""
        msg = 'Connection failed: password="secret123"'
        filtered = filter_sensitive_data(msg)
        assert "secret123" not in filtered
        assert "[REDACTED]" in filtered

    def test_filter_api_key(self):
        """Verify API keys are filtered."""
        msg = "Error: API_KEY=abc123xyz"
        filtered = filter_sensitive_data(msg)
        assert "abc123" not in filtered
        assert "[REDACTED]" in filtered

    def test_filter_bearer_token(self):
        """Verify Bearer tokens are filtered."""
        msg = "Auth failed: Bearer eyJhbGciOiJIUzI1NiJ9.xyz"
        filtered = filter_sensitive_data(msg)
        assert "eyJhbG" not in filtered
        assert "[REDACTED]" in filtered

    def test_filter_openai_key(self):
        """Verify OpenAI API keys are filtered."""
        msg = "OpenAI error: sk-abcdefghij123456"
        filtered = filter_sensitive_data(msg)
        assert "sk-abcd" not in filtered
        assert "[REDACTED]" in filtered

    def test_filter_aws_key(self):
        """Verify AWS access keys are filtered."""
        msg = "AWS error: AKIAIOSFODNN7EXAMPLE"
        filtered = filter_sensitive_data(msg)
        assert "AKIAIOS" not in filtered
        assert "[REDACTED]" in filtered

    def test_filter_github_token(self):
        """Verify GitHub tokens are filtered."""
        msg = "GitHub error: ghp_xxxxxxxxxxxxxxxxxxxx"
        filtered = filter_sensitive_data(msg)
        assert "ghp_xxx" not in filtered
        assert "[REDACTED]" in filtered

    def test_filter_private_key(self):
        """Verify private keys are filtered."""
        msg = "Error loading -----BEGIN PRIVATE KEY-----"
        filtered = filter_sensitive_data(msg)
        assert "BEGIN PRIVATE KEY" not in filtered
        assert "[REDACTED]" in filtered

    def test_normal_message_unchanged(self):
        """Verify normal messages are not filtered."""
        msg = "Connection failed: timeout after 30 seconds"
        filtered = filter_sensitive_data(msg)
        assert filtered == msg

    def test_message_size_limit(self):
        """Verify oversized messages are rejected."""
        large_msg = "x" * (MAX_MESSAGE_SIZE + 1)
        with pytest.raises(ValueError) as exc_info:
            validate_message_size(large_msg)
        assert "too large" in str(exc_info.value)

    def test_validated_request_rejects_path_traversal(self):
        """Verify path traversal in step ID is rejected."""
        from pydantic import ValidationError as PydanticValidationError

        with pytest.raises(PydanticValidationError):
            InvokeParams(step="../../../etc/passwd")

    def test_validated_request_accepts_valid_step(self):
        """Verify valid step IDs are accepted."""
        params = InvokeParams(step="my-step")
        assert params.step == "my-step"

    def test_request_from_json_validates(self):
        """Verify JSON parsing includes validation."""
        # Valid request
        req = JsonRpcRequest.from_json(
            '{"jsonrpc": "2.0", "method": "invoke", "params": {"step": "test"}, "id": 1}'
        )
        assert req.method == "invoke"

        # Oversized request should fail
        large_json = '{"method": "test", "params": {}, "id": 1, "data": "' + "x" * MAX_MESSAGE_SIZE + '"}'
        with pytest.raises(ValueError):
            JsonRpcRequest.from_json(large_json)


class TestExceptionClasses:
    """Tests for security exception classes."""

    def test_security_error(self):
        """Verify SecurityError contains correct info."""
        err = SecurityError("Test error", "TEST_TYPE", {"key": "value"})
        assert err.violation_type == "TEST_TYPE"
        assert "TEST_TYPE" in str(err.to_dict())

    def test_path_traversal_error(self):
        """Verify PathTraversalError contains correct info."""
        err = PathTraversalError("../etc/passwd", "/plugins/test")
        assert "PATH_TRAVERSAL" in str(err.to_dict())

    def test_unauthorized_access_error(self):
        """Verify UnauthorizedAccessError contains correct info."""
        err = UnauthorizedAccessError("browser_session:123", "evil-plugin")
        assert "UNAUTHORIZED_ACCESS" in str(err.to_dict())

    def test_invalid_session_token_error(self):
        """Verify InvalidSessionTokenError contains correct info."""
        err = InvalidSessionTokenError("test-session")
        assert "INVALID_SESSION_TOKEN" in str(err.to_dict())


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
