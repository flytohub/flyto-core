#!/usr/bin/env python3
"""
Module Migration Script

Auto-generates plugin manifests and entry points from existing modules.

Usage:
    python scripts/migrate_module.py llm.chat llm.embedding
    python scripts/migrate_module.py browser.goto browser.click browser.screenshot
    python scripts/migrate_module.py --category llm
    python scripts/migrate_module.py --all-heavy  # llm, browser, database, ai
"""

import argparse
import ast
import inspect
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@dataclass
class ModuleInfo:
    """Information extracted from a module."""
    module_id: str
    category: str
    action: str
    class_name: str
    file_path: str
    label: str
    description: str
    params_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    permissions: List[str]
    icon: str
    color: str
    cost_class: str
    cost_points: int


class ModuleMigrator:
    """Migrates existing modules to plugin format."""

    # Categories that should be migrated to plugins
    HEAVY_CATEGORIES = {"llm", "browser", "database", "ai"}

    # Default icons and colors by category
    CATEGORY_DEFAULTS = {
        "llm": {"icon": "MessageSquare", "color": "#8B5CF6"},
        "browser": {"icon": "Globe", "color": "#3B82F6"},
        "database": {"icon": "Database", "color": "#6366F1"},
        "ai": {"icon": "Brain", "color": "#EC4899"},
    }

    # Default cost classes by category
    CATEGORY_COSTS = {
        "llm": {"class": "premium", "points": 3},
        "browser": {"class": "standard", "points": 1},
        "database": {"class": "standard", "points": 1},
        "ai": {"class": "premium", "points": 3},
    }

    def __init__(self, src_path: Path, plugins_path: Path):
        self.src_path = src_path
        self.plugins_path = plugins_path
        self.modules_path = src_path / "core" / "modules" / "atomic"

    def discover_modules(self, category: Optional[str] = None) -> List[ModuleInfo]:
        """Discover all modules in a category."""
        modules = []

        if category:
            categories = [category]
        else:
            categories = list(self.HEAVY_CATEGORIES)

        for cat in categories:
            cat_path = self.modules_path / cat
            if not cat_path.exists():
                continue

            for py_file in cat_path.glob("*.py"):
                if py_file.name.startswith("_"):
                    continue

                try:
                    info = self._extract_module_info(py_file, cat)
                    if info:
                        modules.append(info)
                except Exception as e:
                    print(f"Warning: Failed to extract {py_file}: {e}")

        return modules

    def _extract_module_info(self, file_path: Path, category: str) -> Optional[ModuleInfo]:
        """Extract module information from a Python file."""
        with open(file_path) as f:
            source = f.read()

        try:
            tree = ast.parse(source)
        except SyntaxError:
            return None

        # Find the module class
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                # Check if it's a module class (has execute method)
                has_execute = any(
                    isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and item.name == "execute"
                    for item in node.body
                )
                if not has_execute:
                    continue

                # Extract class attributes
                module_name = None
                module_description = None

                for item in node.body:
                    if isinstance(item, ast.Assign):
                        for target in item.targets:
                            if isinstance(target, ast.Name):
                                if target.id == "module_name":
                                    if isinstance(item.value, ast.Constant):
                                        module_name = item.value.value
                                elif target.id == "module_description":
                                    if isinstance(item.value, ast.Constant):
                                        module_description = item.value.value

                if not module_name:
                    module_name = node.name

                action = file_path.stem
                module_id = f"{category}.{action}"

                defaults = self.CATEGORY_DEFAULTS.get(category, {"icon": "Box", "color": "#6B7280"})
                costs = self.CATEGORY_COSTS.get(category, {"class": "standard", "points": 1})

                return ModuleInfo(
                    module_id=module_id,
                    category=category,
                    action=action,
                    class_name=node.name,
                    file_path=str(file_path),
                    label=module_name,
                    description=module_description or f"Execute {action} operation",
                    params_schema={"type": "object", "properties": {}},
                    output_schema={"type": "object", "properties": {}},
                    permissions=self._get_permissions(category),
                    icon=defaults["icon"],
                    color=defaults["color"],
                    cost_class=costs["class"],
                    cost_points=costs["points"],
                )

        return None

    def _get_permissions(self, category: str) -> List[str]:
        """Get required permissions for a category."""
        perms = {
            "llm": ["network", "secrets.read"],
            "browser": ["network", "browser"],
            "database": ["network", "secrets.read"],
            "ai": ["network", "secrets.read"],
        }
        return perms.get(category, ["network"])

    def generate_manifest(self, category: str, modules: List[ModuleInfo]) -> Dict[str, Any]:
        """Generate a plugin manifest for a category."""
        defaults = self.CATEGORY_DEFAULTS.get(category, {"icon": "Box", "color": "#6B7280"})

        steps = []
        for mod in modules:
            steps.append({
                "id": mod.action,
                "label": mod.label,
                "description": mod.description,
                "inputSchema": mod.params_schema,
                "outputSchema": mod.output_schema,
                "cost": {
                    "points": mod.cost_points,
                    "class": mod.cost_class,
                },
                "ui": {
                    "icon": mod.icon,
                    "color": mod.color,
                    "visibility": "default",
                },
                "tags": [category, mod.action],
            })

        # Collect all permissions
        all_perms = set()
        for mod in modules:
            all_perms.update(mod.permissions)

        return {
            "id": f"flyto-official_{category}",
            "name": f"{category.upper()} Operations",
            "version": "1.0.0",
            "vendor": "flyto-official",
            "description": f"{category.upper()} operations plugin",
            "entryPoint": "main.py",
            "runtime": {
                "language": "python",
                "minVersion": "3.9",
            },
            "permissions": list(all_perms),
            "requiredSecrets": self._get_required_secrets(category),
            "meta": {
                "icon": defaults["icon"],
                "color": defaults["color"],
                "category": category,
                "tags": [category],
            },
            "steps": steps,
        }

    def _get_required_secrets(self, category: str) -> List[str]:
        """Get required secrets for a category."""
        secrets = {
            "llm": ["openai_api_key", "anthropic_api_key"],
            "browser": [],
            "database": ["database_connection"],
            "ai": ["openai_api_key", "anthropic_api_key"],
        }
        return secrets.get(category, [])

    def generate_main_py(self, category: str, modules: List[ModuleInfo]) -> str:
        """Generate main.py entry point for a plugin."""
        step_imports = "\n".join([
            f"from steps.{mod.action} import execute_{mod.action}"
            for mod in modules
        ])

        handler_mapping = ",\n            ".join([
            f'"{mod.action}": execute_{mod.action}'
            for mod in modules
        ])

        supported_steps = ", ".join([f'"{mod.action}"' for mod in modules])

        return f'''#!/usr/bin/env python3
"""
{category.upper()} Plugin Entry Point

JSON-RPC server that handles {category} operations.
Communicates with Flyto core via stdin/stdout.
"""

import asyncio
import json
import logging
import sys
from typing import Any, Dict, Optional

# Configure logging to stderr
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] [%(asctime)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

# Import step handlers
{step_imports}


# JSON-RPC version
JSONRPC_VERSION = "2.0"

# Plugin metadata
PLUGIN_ID = "flyto-official_{category}"
PLUGIN_VERSION = "1.0.0"


class {category.title()}Plugin:
    """{category.upper()} plugin JSON-RPC handler."""

    def __init__(self):
        self.protocol_version: Optional[str] = None
        self.execution_id: Optional[str] = None
        self._running = True

    async def handle_handshake(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle handshake request."""
        self.protocol_version = params.get("protocolVersion")
        self.execution_id = params.get("executionId")

        logger.info(f"Handshake: protocol={{self.protocol_version}}")

        return {{
            "ok": True,
            "pluginId": PLUGIN_ID,
            "pluginVersion": PLUGIN_VERSION,
            "supportedSteps": [{supported_steps}],
        }}

    async def handle_invoke(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle invoke request."""
        step = params.get("step")
        input_data = params.get("input", {{}})
        config = params.get("config", {{}})
        context = params.get("context", {{}})

        logger.info(f"Invoke: step={{step}}")

        # Route to appropriate handler
        handlers = {{
            {handler_mapping}
        }}

        handler = handlers.get(step)
        if not handler:
            return {{
                "ok": False,
                "error": {{
                    "code": "STEP_NOT_FOUND",
                    "message": f"Unknown step: {{step}}",
                }},
            }}

        try:
            result = await handler(input_data, config, context)
            return result
        except Exception as e:
            logger.error(f"Step {{step}} failed: {{e}}", exc_info=True)
            return {{
                "ok": False,
                "error": {{
                    "code": "EXECUTION_ERROR",
                    "message": str(e),
                    "retryable": False,
                }},
            }}

    async def handle_ping(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle ping (health check) request."""
        return {{"ok": True, "pong": True}}

    async def handle_shutdown(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle shutdown request."""
        reason = params.get("reason", "unknown")
        logger.info(f"Shutdown requested: {{reason}}")
        self._running = False
        return {{"ok": True, "cleanedUp": []}}

    async def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle a JSON-RPC request."""
        method = request.get("method")
        params = request.get("params", {{}})
        request_id = request.get("id")

        handlers = {{
            "handshake": self.handle_handshake,
            "invoke": self.handle_invoke,
            "ping": self.handle_ping,
            "shutdown": self.handle_shutdown,
        }}

        handler = handlers.get(method)
        if not handler:
            return {{
                "jsonrpc": JSONRPC_VERSION,
                "error": {{
                    "code": -32601,
                    "message": f"Method not found: {{method}}",
                }},
                "id": request_id,
            }}

        try:
            result = await handler(params)
            return {{
                "jsonrpc": JSONRPC_VERSION,
                "result": result,
                "id": request_id,
            }}
        except Exception as e:
            logger.error(f"Handler error: {{e}}", exc_info=True)
            return {{
                "jsonrpc": JSONRPC_VERSION,
                "error": {{
                    "code": -32603,
                    "message": str(e),
                }},
                "id": request_id,
            }}

    async def run(self):
        """Main loop - read from stdin, write to stdout."""
        logger.info(f"Starting {{PLUGIN_ID}} v{{PLUGIN_VERSION}}")

        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await asyncio.get_event_loop().connect_read_pipe(
            lambda: protocol, sys.stdin
        )

        while self._running:
            try:
                # Read line from stdin
                line = await reader.readline()
                if not line:
                    break

                data = line.decode("utf-8").strip()
                if not data:
                    continue

                # Parse JSON-RPC request
                try:
                    request = json.loads(data)
                except json.JSONDecodeError as e:
                    response = {{
                        "jsonrpc": JSONRPC_VERSION,
                        "error": {{
                            "code": -32700,
                            "message": f"Parse error: {{e}}",
                        }},
                        "id": None,
                    }}
                    self._write_response(response)
                    continue

                # Handle request
                response = await self.handle_request(request)
                self._write_response(response)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Main loop error: {{e}}", exc_info=True)

        logger.info("Plugin shutting down")

    def _write_response(self, response: Dict[str, Any]):
        """Write JSON-RPC response to stdout."""
        line = json.dumps(response) + "\\n"
        sys.stdout.write(line)
        sys.stdout.flush()


async def main():
    """Entry point."""
    plugin = {category.title()}Plugin()
    await plugin.run()


if __name__ == "__main__":
    asyncio.run(main())
'''

    def generate_step_file(self, module: ModuleInfo) -> str:
        """Generate a step implementation file that wraps the legacy module."""
        return f'''"""
{module.label} Step Implementation

Wraps the legacy {module.module_id} module for plugin execution.
"""

import logging
import sys
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

# Add legacy module path
_src_path = Path(__file__).parent.parent.parent.parent / "src"
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))


async def execute_{module.action}(
    input_data: Dict[str, Any],
    config: Dict[str, Any],
    context: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Execute {module.action} operation.

    Args:
        input_data: Step input parameters
        config: Step configuration
        context: Execution context with secrets

    Returns:
        Result dict with ok, output/error
    """
    try:
        # Import legacy module
        from core.modules.registry import ModuleRegistry

        module_class = ModuleRegistry.get("{module.module_id}")
        if not module_class:
            return {{
                "ok": False,
                "error": {{
                    "code": "MODULE_NOT_FOUND",
                    "message": "Legacy module {module.module_id} not found",
                }},
            }}

        # Merge input and config as params
        params = {{**input_data, **config}}

        # Resolve secrets from context
        secrets = context.get("secrets", {{}})
        for key, value in secrets.items():
            if key not in params:
                params[key] = value

        # Create and execute module instance
        module_instance = module_class(params, context)
        result = await module_instance.run()

        # Normalize result
        if isinstance(result, dict):
            if "ok" in result:
                return result
            else:
                return {{"ok": True, "output": result}}
        else:
            return {{"ok": True, "output": {{"result": result}}}}

    except Exception as e:
        logger.error(f"{module.action} execution failed: {{e}}", exc_info=True)
        return {{
            "ok": False,
            "error": {{
                "code": "EXECUTION_ERROR",
                "message": str(e),
                "retryable": False,
            }},
        }}
'''

    def generate_init_file(self, modules: List[ModuleInfo]) -> str:
        """Generate __init__.py for steps package."""
        imports = "\n".join([
            f"from .{mod.action} import execute_{mod.action}"
            for mod in modules
        ])
        exports = ", ".join([f'"execute_{mod.action}"' for mod in modules])

        return f'''"""
Step implementations for plugin.
"""

{imports}

__all__ = [
    {exports}
]
'''

    def generate_requirements(self, category: str) -> str:
        """Generate requirements.txt for a plugin."""
        reqs = {
            "llm": "# LLM Plugin Dependencies\nopenai>=1.0.0\nanthropic>=0.18.0\n",
            "browser": "# Browser Plugin Dependencies\nplaywright>=1.40.0\n",
            "database": "# Database Plugin Dependencies\nasyncpg>=0.29.0\naiomysql>=0.2.0\n",
            "ai": "# AI Plugin Dependencies\nopenai>=1.0.0\nanthropic>=0.18.0\n",
        }
        return reqs.get(category, "# Plugin Dependencies\n")

    def migrate_category(self, category: str, module_ids: Optional[List[str]] = None) -> Path:
        """Migrate a category or specific modules to plugin format."""
        print(f"\nMigrating {category} modules...")

        # Discover modules
        all_modules = self.discover_modules(category)

        # Filter if specific modules requested
        if module_ids:
            modules = [m for m in all_modules if m.module_id in module_ids]
        else:
            modules = all_modules

        if not modules:
            print(f"  No modules found for {category}")
            return None

        print(f"  Found {len(modules)} modules: {[m.action for m in modules]}")

        # Create plugin directory
        plugin_dir = self.plugins_path / f"flyto-official_{category}"
        plugin_dir.mkdir(parents=True, exist_ok=True)
        steps_dir = plugin_dir / "steps"
        steps_dir.mkdir(exist_ok=True)

        # Generate manifest
        manifest = self.generate_manifest(category, modules)
        manifest_path = plugin_dir / "plugin.manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)
        print(f"  Created {manifest_path}")

        # Generate main.py
        main_py = self.generate_main_py(category, modules)
        main_path = plugin_dir / "main.py"
        with open(main_path, "w") as f:
            f.write(main_py)
        print(f"  Created {main_path}")

        # Generate step files
        for mod in modules:
            step_file = self.generate_step_file(mod)
            step_path = steps_dir / f"{mod.action}.py"
            with open(step_path, "w") as f:
                f.write(step_file)
            print(f"  Created {step_path}")

        # Generate __init__.py
        init_file = self.generate_init_file(modules)
        init_path = steps_dir / "__init__.py"
        with open(init_path, "w") as f:
            f.write(init_file)
        print(f"  Created {init_path}")

        # Generate requirements.txt
        reqs = self.generate_requirements(category)
        reqs_path = plugin_dir / "requirements.txt"
        with open(reqs_path, "w") as f:
            f.write(reqs)
        print(f"  Created {reqs_path}")

        print(f"  Migration complete: {plugin_dir}")
        return plugin_dir


def main():
    parser = argparse.ArgumentParser(description="Migrate modules to plugins")
    parser.add_argument("modules", nargs="*", help="Module IDs to migrate (e.g., llm.chat)")
    parser.add_argument("--category", "-c", help="Migrate entire category")
    parser.add_argument("--all-heavy", action="store_true", help="Migrate all heavy categories")
    parser.add_argument("--src", default="src", help="Source directory path")
    parser.add_argument("--plugins", default="plugins", help="Plugins directory path")

    args = parser.parse_args()

    # Resolve paths
    base_path = Path(__file__).parent.parent
    src_path = base_path / args.src
    plugins_path = base_path / args.plugins

    migrator = ModuleMigrator(src_path, plugins_path)

    if args.all_heavy:
        # Migrate all heavy categories
        for category in ModuleMigrator.HEAVY_CATEGORIES:
            migrator.migrate_category(category)
    elif args.category:
        # Migrate entire category
        migrator.migrate_category(args.category)
    elif args.modules:
        # Migrate specific modules
        by_category: Dict[str, List[str]] = {}
        for mod_id in args.modules:
            parts = mod_id.split(".")
            if len(parts) >= 2:
                cat = parts[0]
                if cat not in by_category:
                    by_category[cat] = []
                by_category[cat].append(mod_id)

        for category, module_ids in by_category.items():
            migrator.migrate_category(category, module_ids)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
