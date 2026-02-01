"""
Tests for multi-language runtime support.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from core.runtime.languages import (
    LanguageConfig,
    LANGUAGE_CONFIGS,
    LANGUAGE_ALIASES,
    get_language_config,
    detect_language,
    list_available_languages,
    get_install_instructions,
)
from core.runtime.exceptions import RuntimeError


class TestLanguageConfig:
    """Tests for LanguageConfig class."""

    def test_python_config(self):
        """Test Python language configuration."""
        config = LANGUAGE_CONFIGS["python"]
        assert config.language == "python"
        assert config.executable == "python3"
        assert "-u" in config.args
        assert config.entry_pattern == "main.py"
        assert config.package_manager == "pip"
        assert not config.is_compiled

    def test_node_config(self):
        """Test Node.js language configuration."""
        config = LANGUAGE_CONFIGS["node"]
        assert config.language == "node"
        assert config.executable == "node"
        assert config.entry_pattern == "index.js"
        assert config.package_manager == "npm"
        assert not config.is_compiled

    def test_go_config(self):
        """Test Go language configuration."""
        config = LANGUAGE_CONFIGS["go"]
        assert config.language == "go"
        assert config.executable is None  # Compiled
        assert config.entry_pattern == "plugin"
        assert config.package_manager == "go"
        assert config.is_compiled

    def test_rust_config(self):
        """Test Rust language configuration."""
        config = LANGUAGE_CONFIGS["rust"]
        assert config.language == "rust"
        assert config.is_compiled
        assert config.executable is None

    def test_java_config(self):
        """Test Java language configuration."""
        config = LANGUAGE_CONFIGS["java"]
        assert config.language == "java"
        assert config.executable == "java"
        assert "-jar" in config.args
        assert config.entry_pattern == "plugin.jar"

    def test_csharp_config(self):
        """Test C# language configuration."""
        config = LANGUAGE_CONFIGS["csharp"]
        assert config.language == "csharp"
        assert config.executable == "dotnet"
        assert config.entry_pattern == "Plugin.dll"

    def test_binary_config(self):
        """Test binary (compiled) configuration."""
        config = LANGUAGE_CONFIGS["binary"]
        assert config.is_compiled
        assert config.executable is None
        assert config.package_manager is None


class TestGetLanguageConfig:
    """Tests for get_language_config function."""

    def test_direct_language(self):
        """Test getting config by direct language name."""
        config = get_language_config("python")
        assert config.language == "python"

    def test_alias_py(self):
        """Test getting config by alias 'py'."""
        config = get_language_config("py")
        assert config.language == "python"

    def test_alias_js(self):
        """Test getting config by alias 'js'."""
        config = get_language_config("js")
        assert config.language == "node"

    def test_alias_golang(self):
        """Test getting config by alias 'golang'."""
        config = get_language_config("golang")
        assert config.language == "go"

    def test_case_insensitive(self):
        """Test case insensitive lookup."""
        config = get_language_config("PYTHON")
        assert config.language == "python"

        config = get_language_config("Node")
        assert config.language == "node"

    def test_unsupported_language(self):
        """Test error for unsupported language."""
        with pytest.raises(RuntimeError) as exc_info:
            get_language_config("cobol")
        assert "Unsupported language" in str(exc_info.value)
        assert exc_info.value.code == "UNSUPPORTED_LANGUAGE"


class TestBuildCommand:
    """Tests for command building."""

    def test_python_command(self):
        """Test building Python command."""
        config = LANGUAGE_CONFIGS["python"]
        entry = Path("/plugins/my-plugin/main.py")
        plugin_dir = Path("/plugins/my-plugin")

        cmd = config.build_command(entry, plugin_dir)

        assert cmd[0] == "python3"
        assert "-u" in cmd
        assert str(entry) in cmd

    def test_node_command(self):
        """Test building Node.js command."""
        config = LANGUAGE_CONFIGS["node"]
        entry = Path("/plugins/my-plugin/index.js")
        plugin_dir = Path("/plugins/my-plugin")

        cmd = config.build_command(entry, plugin_dir)

        assert cmd[0] == "node"
        assert str(entry) in cmd

    def test_java_command(self):
        """Test building Java command."""
        config = LANGUAGE_CONFIGS["java"]
        entry = Path("/plugins/my-plugin/plugin.jar")
        plugin_dir = Path("/plugins/my-plugin")

        cmd = config.build_command(entry, plugin_dir)

        assert cmd[0] == "java"
        assert "-jar" in cmd
        assert str(entry) in cmd

    def test_binary_command(self):
        """Test building binary command."""
        config = LANGUAGE_CONFIGS["binary"]
        entry = Path("/plugins/my-plugin/plugin")
        plugin_dir = Path("/plugins/my-plugin")

        cmd = config.build_command(entry, plugin_dir)

        assert len(cmd) == 1
        assert cmd[0] == str(entry)


class TestDetectLanguage:
    """Tests for auto-detecting plugin language."""

    def test_detect_python(self):
        """Test detecting Python plugin."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir)
            (plugin_dir / "main.py").touch()

            detected = detect_language(plugin_dir)
            assert detected == "python"

    def test_detect_node(self):
        """Test detecting Node.js plugin."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir)
            (plugin_dir / "index.js").touch()

            detected = detect_language(plugin_dir)
            assert detected == "node"

    def test_detect_typescript(self):
        """Test detecting TypeScript plugin."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir)
            (plugin_dir / "index.ts").touch()

            detected = detect_language(plugin_dir)
            assert detected == "typescript"

    def test_detect_by_package_json(self):
        """Test detecting Node.js by package.json."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir)
            (plugin_dir / "package.json").write_text("{}")

            detected = detect_language(plugin_dir)
            assert detected == "node"

    def test_detect_by_requirements_txt(self):
        """Test detecting Python by requirements.txt."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir)
            (plugin_dir / "requirements.txt").touch()

            detected = detect_language(plugin_dir)
            assert detected == "python"

    def test_detect_by_go_mod(self):
        """Test detecting Go by go.mod."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir)
            (plugin_dir / "go.mod").touch()

            detected = detect_language(plugin_dir)
            assert detected == "go"

    def test_detect_by_cargo_toml(self):
        """Test detecting Rust by Cargo.toml."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir)
            (plugin_dir / "Cargo.toml").touch()

            detected = detect_language(plugin_dir)
            assert detected == "rust"

    def test_detect_defaults_to_python(self):
        """Test default detection falls back to Python."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir)
            # No recognizable files

            detected = detect_language(plugin_dir)
            assert detected == "python"


class TestListAvailableLanguages:
    """Tests for listing available language runtimes."""

    def test_returns_list(self):
        """Test that function returns a list."""
        available = list_available_languages()
        assert isinstance(available, list)

    def test_includes_compiled_languages(self):
        """Test that compiled languages are always available."""
        available = list_available_languages()
        assert "go" in available or "binary" in available


class TestGetInstallInstructions:
    """Tests for installation instructions."""

    def test_python_instructions(self):
        """Test Python installation instructions."""
        instructions = get_install_instructions("python")
        assert "python" in instructions.lower()
        assert "http" in instructions.lower()

    def test_node_instructions(self):
        """Test Node.js installation instructions."""
        instructions = get_install_instructions("node")
        assert "node" in instructions.lower()

    def test_alias_works(self):
        """Test instructions work with aliases."""
        instructions = get_install_instructions("py")
        assert "python" in instructions.lower()

    def test_binary_instructions(self):
        """Test binary installation instructions."""
        instructions = get_install_instructions("binary")
        assert "don't require" in instructions.lower() or "runtime" in instructions.lower()


class TestLanguageAliases:
    """Tests for language alias coverage."""

    def test_all_aliases_resolve(self):
        """Test all aliases resolve to valid languages."""
        for alias, language in LANGUAGE_ALIASES.items():
            assert language in LANGUAGE_CONFIGS, f"Alias '{alias}' points to invalid language '{language}'"

    def test_common_aliases_exist(self):
        """Test common aliases exist."""
        expected_aliases = ["py", "js", "ts", "golang", "rs"]
        for alias in expected_aliases:
            assert alias in LANGUAGE_ALIASES, f"Missing common alias: {alias}"
