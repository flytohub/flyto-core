"""
Tests for plugin process management with multi-language support.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.runtime.process import ProcessConfig, ProcessStatus, PluginProcess, RestartPolicy
from core.runtime.protocol import PROTOCOL_VERSION


class TestProcessConfig:
    """Tests for ProcessConfig with multi-language support."""

    def test_default_language(self):
        """Test default language is Python."""
        config = ProcessConfig(
            plugin_id="test-plugin",
            plugin_dir=Path("/plugins/test"),
        )
        assert config.language == "python"

    def test_custom_language(self):
        """Test setting custom language."""
        config = ProcessConfig(
            plugin_id="test-plugin",
            plugin_dir=Path("/plugins/test"),
            language="node",
            entry_point="index.js",
        )
        assert config.language == "node"

    def test_get_language_config(self):
        """Test getting language config from ProcessConfig."""
        config = ProcessConfig(
            plugin_id="test-plugin",
            plugin_dir=Path("/plugins/test"),
            language="node",
        )
        lang_config = config.get_language_config()
        assert lang_config.language == "node"
        assert lang_config.executable == "node"

    def test_build_command_python(self):
        """Test building Python command."""
        config = ProcessConfig(
            plugin_id="test-plugin",
            plugin_dir=Path("/plugins/test"),
            entry_point="main.py",
            language="python",
        )
        cmd = config.build_command()

        assert cmd[0] == "python3"
        assert "-u" in cmd
        assert "/plugins/test/main.py" in cmd[-1]

    def test_build_command_node(self):
        """Test building Node.js command."""
        config = ProcessConfig(
            plugin_id="test-plugin",
            plugin_dir=Path("/plugins/test"),
            entry_point="index.js",
            language="node",
        )
        cmd = config.build_command()

        assert cmd[0] == "node"
        assert "/plugins/test/index.js" in cmd[-1]

    def test_build_command_java(self):
        """Test building Java command."""
        config = ProcessConfig(
            plugin_id="test-plugin",
            plugin_dir=Path("/plugins/test"),
            entry_point="plugin.jar",
            language="java",
        )
        cmd = config.build_command()

        assert cmd[0] == "java"
        assert "-jar" in cmd
        assert "/plugins/test/plugin.jar" in cmd[-1]

    def test_build_command_binary(self):
        """Test building binary command."""
        config = ProcessConfig(
            plugin_id="test-plugin",
            plugin_dir=Path("/plugins/test"),
            entry_point="plugin",
            language="binary",
        )
        cmd = config.build_command()

        assert len(cmd) == 1
        assert cmd[0] == "/plugins/test/plugin"

    def test_get_process_env(self):
        """Test getting process environment."""
        config = ProcessConfig(
            plugin_id="test-plugin",
            plugin_dir=Path("/plugins/test"),
            language="python",
            env={"CUSTOM_VAR": "custom_value"},
        )
        env = config.get_process_env()

        # Check Flyto vars
        assert env["FLYTO_PLUGIN_ID"] == "test-plugin"
        assert env["FLYTO_PROTOCOL_VERSION"] == PROTOCOL_VERSION
        assert env["FLYTO_LANGUAGE"] == "python"

        # Check language-specific vars
        assert env["PYTHONUNBUFFERED"] == "1"

        # Check custom vars
        assert env["CUSTOM_VAR"] == "custom_value"

    def test_get_process_env_node(self):
        """Test Node.js environment vars."""
        config = ProcessConfig(
            plugin_id="test-plugin",
            plugin_dir=Path("/plugins/test"),
            language="node",
        )
        env = config.get_process_env()

        assert env["NODE_ENV"] == "production"
        assert env["FLYTO_LANGUAGE"] == "node"


class TestPluginProcess:
    """Tests for PluginProcess class."""

    def test_init(self):
        """Test PluginProcess initialization."""
        config = ProcessConfig(
            plugin_id="test-plugin",
            plugin_dir=Path("/plugins/test"),
        )
        process = PluginProcess(config)

        assert process.config == config
        assert process.status == ProcessStatus.STOPPED
        assert not process.is_ready
        assert not process.is_unhealthy

    def test_custom_restart_policy(self):
        """Test custom restart policy."""
        config = ProcessConfig(
            plugin_id="test-plugin",
            plugin_dir=Path("/plugins/test"),
        )
        policy = RestartPolicy(
            max_restarts=5,
            restart_window_seconds=120,
        )
        process = PluginProcess(config, restart_policy=policy)

        assert process.restart_policy.max_restarts == 5
        assert process.restart_policy.restart_window_seconds == 120


class TestProcessConfigWithLanguageAlias:
    """Tests for ProcessConfig with language aliases."""

    def test_language_alias_py(self):
        """Test 'py' alias for Python."""
        config = ProcessConfig(
            plugin_id="test-plugin",
            plugin_dir=Path("/plugins/test"),
            language="py",
        )
        lang_config = config.get_language_config()
        assert lang_config.language == "python"

    def test_language_alias_js(self):
        """Test 'js' alias for Node.js."""
        config = ProcessConfig(
            plugin_id="test-plugin",
            plugin_dir=Path("/plugins/test"),
            language="js",
            entry_point="index.js",
        )
        lang_config = config.get_language_config()
        assert lang_config.language == "node"

    def test_language_alias_golang(self):
        """Test 'golang' alias for Go."""
        config = ProcessConfig(
            plugin_id="test-plugin",
            plugin_dir=Path("/plugins/test"),
            language="golang",
            entry_point="plugin",
        )
        lang_config = config.get_language_config()
        assert lang_config.language == "go"
        assert lang_config.is_compiled
