"""
Plugin CLI Commands

Manage flyto community plugins: search, install, uninstall, list.

Usage:
    flyto plugin list              # List installed plugins
    flyto plugin search <query>    # Search the plugin registry
    flyto plugin install <name>    # Install a plugin from PyPI
    flyto plugin uninstall <name>  # Uninstall a plugin
    flyto plugin info <name>       # Show plugin details
"""

import argparse
import sys
from typing import List


def add_plugin_parser(subparsers) -> None:
    """Add plugin subcommand to the CLI."""
    plugin_parser = subparsers.add_parser(
        "plugin",
        help="Manage community plugins",
        description="Search, install, and manage flyto community plugins.",
    )

    plugin_sub = plugin_parser.add_subparsers(dest="plugin_action", help="Plugin actions")

    # flyto plugin list
    plugin_sub.add_parser("list", help="List installed plugins")

    # flyto plugin search <query>
    search_p = plugin_sub.add_parser("search", help="Search the plugin registry")
    search_p.add_argument("query", help="Search query")

    # flyto plugin install <name>
    install_p = plugin_sub.add_parser("install", help="Install a plugin")
    install_p.add_argument("name", help="Plugin name (e.g. slack, database)")
    install_p.add_argument("--version", help="Specific version to install")
    install_p.add_argument("--upgrade", action="store_true", help="Upgrade if already installed")

    # flyto plugin uninstall <name>
    uninstall_p = plugin_sub.add_parser("uninstall", help="Uninstall a plugin")
    uninstall_p.add_argument("name", help="Plugin name")

    # flyto plugin info <name>
    info_p = plugin_sub.add_parser("info", help="Show plugin details")
    info_p.add_argument("name", help="Plugin name")

    # flyto plugin available
    plugin_sub.add_parser("available", help="List all available plugins from registry")


def run_plugin_command(args) -> int:
    """Execute a plugin subcommand."""
    action = getattr(args, "plugin_action", None)

    if not action:
        print("Usage: flyto plugin <list|search|install|uninstall|info|available>")
        print("Run 'flyto plugin --help' for details.")
        return 1

    if action == "list":
        return _plugin_list()
    elif action == "search":
        return _plugin_search(args.query)
    elif action == "install":
        return _plugin_install(args.name, args.version, args.upgrade)
    elif action == "uninstall":
        return _plugin_uninstall(args.name)
    elif action == "info":
        return _plugin_info(args.name)
    elif action == "available":
        return _plugin_available()
    else:
        print(f"Unknown plugin action: {action}")
        return 1


def _plugin_list() -> int:
    """List installed plugins."""
    from core.plugin.loader import get_plugin_loader

    loader = get_plugin_loader()
    plugins = loader.discover_plugins()

    if not plugins:
        print("No plugins installed.")
        print()
        print("Browse available plugins:  flyto plugin available")
        print("Install a plugin:          flyto plugin install <name>")
        return 0

    print(f"Installed plugins ({len(plugins)}):")
    print()

    for name, plugin in sorted(plugins.items()):
        status = "loaded" if plugin.loaded else "installed"
        modules = plugin.manifest.modules
        mod_count = len(modules) if modules else 0
        print(f"  {name}  v{plugin.version}  [{status}]  ({mod_count} modules)")

    return 0


def _plugin_search(query: str) -> int:
    """Search the plugin registry."""
    from core.plugin.registry import PluginRegistry

    registry = PluginRegistry()
    print(f"Searching for '{query}'...")
    print()

    results = registry.search(query)

    if not results:
        print("No plugins found.")
        return 0

    print(f"Found {len(results)} plugins:")
    print()

    for entry in results:
        installed = _is_installed(entry.name)
        marker = " [installed]" if installed else ""
        print(f"  {entry.name}  v{entry.version}{marker}")
        print(f"    {entry.description}")
        if entry.categories:
            print(f"    Categories: {', '.join(entry.categories)}")
        print()

    return 0


def _plugin_install(name: str, version: str = None, upgrade: bool = False) -> int:
    """Install a plugin."""
    from core.plugin.loader import get_plugin_loader

    loader = get_plugin_loader()

    # Normalize name
    full_name = name if name.startswith("flyto-plugin-") else f"flyto-plugin-{name}"

    print(f"Installing {full_name}...")

    success = loader.install_plugin(full_name, version=version, upgrade=upgrade)

    if success:
        print(f"Successfully installed {full_name}")

        # Try to load the plugin
        if loader.load_plugin(full_name):
            plugin = loader.get_plugin(full_name)
            if plugin and plugin.manifest.modules:
                print(f"Registered {len(plugin.manifest.modules)} modules")
        return 0
    else:
        print(f"Failed to install {full_name}", file=sys.stderr)
        return 1


def _plugin_uninstall(name: str) -> int:
    """Uninstall a plugin."""
    from core.plugin.loader import get_plugin_loader

    loader = get_plugin_loader()
    full_name = name if name.startswith("flyto-plugin-") else f"flyto-plugin-{name}"

    print(f"Uninstalling {full_name}...")

    success = loader.uninstall_plugin(full_name)

    if success:
        print(f"Successfully uninstalled {full_name}")
        return 0
    else:
        print(f"Failed to uninstall {full_name}", file=sys.stderr)
        return 1


def _plugin_info(name: str) -> int:
    """Show plugin details."""
    from core.plugin.registry import PluginRegistry
    from core.plugin.loader import get_plugin_loader

    full_name = name if name.startswith("flyto-plugin-") else f"flyto-plugin-{name}"

    # Check locally first
    loader = get_plugin_loader()
    local = loader.get_plugin(full_name)

    if local:
        print(f"Plugin: {local.name}")
        print(f"Version: {local.version}")
        print(f"Status: {'loaded' if local.loaded else 'installed'}")
        print(f"Description: {local.manifest.description}")
        if local.manifest.author:
            print(f"Author: {local.manifest.author}")
        if local.manifest.modules:
            print(f"Modules ({len(local.manifest.modules)}):")
            for mod in local.manifest.modules:
                print(f"  - {mod.module_id}: {mod.description}")
        return 0

    # Try registry
    registry = PluginRegistry()
    entry = registry.get_plugin_info(full_name) or registry.get_plugin_info(name)

    if entry:
        print(f"Plugin: {entry.name}")
        print(f"Version: {entry.version}")
        print(f"Status: not installed")
        print(f"Description: {entry.description}")
        if entry.author:
            print(f"Author: {entry.author}")
        if entry.homepage:
            print(f"Homepage: {entry.homepage}")
        if entry.repository:
            print(f"Repository: {entry.repository}")
        if entry.license:
            print(f"License: {entry.license}")
        if entry.categories:
            print(f"Categories: {', '.join(entry.categories)}")
        if entry.modules:
            print(f"Modules ({len(entry.modules)}):")
            for mod in entry.modules:
                print(f"  - {mod.get('module_id', '')}: {mod.get('description', '')}")
        print()
        print(f"Install: flyto plugin install {name}")
        return 0

    print(f"Plugin not found: {name}")
    return 1


def _plugin_available() -> int:
    """List all available plugins from registry."""
    from core.plugin.registry import PluginRegistry

    registry = PluginRegistry()
    print("Fetching plugin registry...")
    print()

    entries = registry.list_available(force_refresh=True)

    if not entries:
        print("No plugins available in the registry.")
        print("This could mean the registry is not yet set up or is unreachable.")
        return 0

    print(f"Available plugins ({len(entries)}):")
    print()

    for entry in entries:
        installed = _is_installed(entry.name)
        marker = " [installed]" if installed else ""
        print(f"  {entry.name}  v{entry.version}{marker}")
        print(f"    {entry.description}")
        print()

    return 0


def _is_installed(name: str) -> bool:
    """Check if a plugin is installed."""
    try:
        from core.plugin.loader import get_plugin_loader
        loader = get_plugin_loader()
        return loader.get_plugin(name) is not None
    except Exception:
        return False
