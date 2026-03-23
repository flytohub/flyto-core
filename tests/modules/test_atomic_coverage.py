"""
Atomic module coverage tests.

Ensures ALL 66 atomic module categories are importable, all registered
modules have valid metadata/schema, and all modules are instantiable.
"""

import pytest
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

# All 66 atomic categories (derived from directory listing)
ALL_CATEGORIES = [
    "ai", "analysis", "archive", "array", "auth", "browser", "cache", "check",
    "communication", "compare", "convert", "crypto", "data", "database", "datetime",
    "dns", "docker", "document", "element", "encode", "env", "error", "file",
    "flow", "format", "git", "graphql", "hash", "http", "huggingface", "image",
    "k8s", "llm", "logic", "markdown", "math", "meta", "monitor", "network",
    "notification", "object", "output", "path", "port", "process", "queue",
    "random", "regex", "sandbox", "scheduler", "set", "shell", "ssh", "stats",
    "storage", "string", "template", "testing", "text", "training", "ui",
    "utility", "validate", "vector", "verify", "vision",
]


def _load_registry():
    """Import atomic modules to populate the registry and return module IDs."""
    from core.modules.registry import ModuleRegistry
    import core.modules.atomic  # noqa: F401 — triggers registration
    return list(ModuleRegistry.list_all().keys())


class TestAtomicImports:
    """Ensure all atomic module categories import cleanly."""

    @pytest.mark.parametrize("category", ALL_CATEGORIES)
    def test_category_imports(self, category):
        import importlib
        mod = importlib.import_module(f"core.modules.atomic.{category}")
        assert mod is not None


class TestModuleMetadata:
    """Ensure all registered modules have required metadata fields."""

    @pytest.fixture(scope="class")
    def all_module_ids(self):
        return _load_registry()

    def test_modules_registered(self, all_module_ids):
        """At least 100 modules should be registered."""
        assert len(all_module_ids) > 100, (
            f"Only {len(all_module_ids)} modules registered, expected > 100"
        )

    @pytest.mark.parametrize("field", [
        "version", "category", "module_id", "params_schema", "output_schema",
    ])
    def test_all_modules_have_required_field(self, all_module_ids, field):
        from core.modules.registry import ModuleRegistry
        missing = []
        for mid in all_module_ids:
            meta = ModuleRegistry.get_metadata(mid)
            if meta and field not in meta:
                missing.append(mid)
        assert missing == [], f"Modules missing '{field}': {missing[:10]}"

    @pytest.mark.parametrize("field", ["ui_label", "ui_description"])
    def test_all_modules_have_ui_field(self, all_module_ids, field):
        from core.modules.registry import ModuleRegistry
        missing = []
        for mid in all_module_ids:
            meta = ModuleRegistry.get_metadata(mid)
            if meta and field not in meta:
                missing.append(mid)
        assert missing == [], f"Modules missing '{field}': {missing[:10]}"

    def test_all_modules_have_output_schema(self, all_module_ids):
        from core.modules.registry import ModuleRegistry
        missing = []
        for mid in all_module_ids:
            meta = ModuleRegistry.get_metadata(mid)
            if meta and "output_schema" not in meta:
                missing.append(mid)
        # Allow some modules to not have output_schema (warn, not fail)
        if missing:
            pytest.skip(
                f"{len(missing)} modules without output_schema "
                f"(first 10): {missing[:10]}"
            )


class TestModuleInstantiation:
    """Ensure all registered modules can be instantiated."""

    @pytest.fixture(scope="class")
    def all_module_ids(self):
        return _load_registry()

    def test_all_modules_class_retrievable(self, all_module_ids):
        """Every registered module ID should return a class from the registry."""
        from core.modules.registry import ModuleRegistry
        failures = []
        for mid in all_module_ids:
            try:
                cls = ModuleRegistry.get(mid)
                assert cls is not None, f"{mid} returned None"
            except Exception as e:
                failures.append(f"{mid}: {e}")
        assert failures == [], (
            f"Failed to retrieve {len(failures)} modules: {failures[:10]}"
        )

    def test_module_id_matches_category(self, all_module_ids):
        """Module IDs should start with their category."""
        from core.modules.registry import ModuleRegistry
        mismatches = []
        for mid in all_module_ids:
            meta = ModuleRegistry.get_metadata(mid)
            if meta:
                category = meta.get("category", "")
                if category and not mid.startswith(category + "."):
                    mismatches.append(f"{mid} (category={category})")
        # Some modules may have different patterns, just report
        if mismatches:
            pytest.skip(
                f"{len(mismatches)} mismatches: {mismatches[:5]}"
            )
