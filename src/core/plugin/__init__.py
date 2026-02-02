"""
Flyto Plugin System

Provides infrastructure for third-party plugin development and distribution.

Features:
- Plugin manifest schema for package metadata
- Plugin loader for discovering and loading plugins
- Security sandbox for plugin execution
- Version compatibility checking

Usage:
    from core.plugin import PluginManifest, PluginLoader

    # Load and validate a manifest
    manifest = PluginManifest.from_dict(manifest_data)
    errors = manifest.validate()

    # Discover installed plugins
    loader = PluginLoader()
    plugins = loader.discover_plugins()
"""

from .manifest import (
    PluginManifest,
    PluginModule,
    PluginCredentialType,
    PluginStatus,
    PluginPermission,
    load_manifest_from_file,
    create_manifest_template,
)

__all__ = [
    # Manifest
    "PluginManifest",
    "PluginModule",
    "PluginCredentialType",
    "PluginStatus",
    "PluginPermission",
    # Functions
    "load_manifest_from_file",
    "create_manifest_template",
]
