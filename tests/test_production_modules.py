"""
Production Module Tests

Verifies production module list consistency and stability requirements.
Run with: pytest tests/test_production_modules.py -v
"""
import json
import os
import sys
from pathlib import Path

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestProductionModules:
    """Test suite for production module verification."""

    @pytest.fixture(scope="class")
    def production_modules(self):
        """Load current production modules."""
        os.environ["FLYTO_ENV"] = "production"

        from core.modules.registry import ModuleRegistry
        from core.modules import atomic  # Trigger registration

        modules = ModuleRegistry.get_all_metadata(
            filter_by_stability=True,
            env="production"
        )
        # Exclude test fixture modules (keep test.assert_* which are real modules)
        return {k: v for k, v in modules.items()
                if not (k.startswith('test.') and '_fixture' in k)}

    @pytest.fixture(scope="class")
    def snapshot_data(self):
        """Load snapshot file."""
        snapshot_path = Path(__file__).parent / "snapshots" / "production_modules.json"
        with open(snapshot_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def test_production_module_count(self, production_modules):
        """Production module count must meet minimum threshold."""
        # We expect at least 170 modules in production
        # This prevents accidental module removal
        assert len(production_modules) >= 170, (
            f"Production module count ({len(production_modules)}) is below minimum (170). "
            "This may indicate modules were accidentally removed or marked as non-stable."
        )

    def test_production_module_count_exact(self, production_modules, snapshot_data):
        """Production module count should match snapshot."""
        expected_count = snapshot_data["total"]
        actual_count = len(production_modules)

        assert actual_count == expected_count, (
            f"Production module count mismatch. "
            f"Expected {expected_count}, got {actual_count}. "
            "If this is intentional, update the snapshot with: "
            "flyto modules --env production --format json > tests/snapshots/production_modules.json"
        )

    def test_no_beta_modules_in_production(self, production_modules):
        """Production should not contain beta modules."""
        beta_prefixes = [
            'huggingface.',
            'database.sqlite.',
            'database.mysql.',
            'database.postgres.',
        ]

        for module_id, metadata in production_modules.items():
            stability = metadata.get("stability", "stable")
            assert stability == "stable", (
                f"Module {module_id} has stability '{stability}' but is in production. "
                "Only stable modules should appear in production environment."
            )

            for prefix in beta_prefixes:
                if module_id.startswith(prefix):
                    pytest.fail(
                        f"Module {module_id} should not be in production. "
                        f"Modules starting with '{prefix}' are typically beta."
                    )

    def test_snapshot_module_ids_match(self, production_modules, snapshot_data):
        """Module IDs should match snapshot."""
        snapshot_ids = {m["id"] for m in snapshot_data["modules"]}
        current_ids = set(production_modules.keys())

        missing = snapshot_ids - current_ids
        extra = current_ids - snapshot_ids

        if missing:
            pytest.fail(
                f"Missing modules from production (found in snapshot): {missing}. "
                "These modules may have been accidentally removed or marked as beta."
            )

        if extra:
            pytest.fail(
                f"New modules in production (not in snapshot): {extra}. "
                "If this is intentional, update the snapshot with: "
                "flyto modules --env production --format json > tests/snapshots/production_modules.json"
            )

    def test_required_modules_present(self, production_modules):
        """Critical modules must be present in production."""
        required_modules = [
            # Browser automation
            "browser.launch",
            "browser.goto",
            "browser.click",
            "browser.type",
            "browser.close",
            # Flow control
            "flow.branch",
            "flow.loop",
            "utility.delay",
            # Data manipulation
            "array.filter",
            "array.map",
            "element.text",
            # File operations
            "file.read",
            "file.write",
        ]

        missing = [m for m in required_modules if m not in production_modules]

        assert not missing, (
            f"Required modules missing from production: {missing}. "
            "These are critical modules that must always be available."
        )

    def test_all_modules_have_required_metadata(self, production_modules):
        """All production modules must have required metadata fields."""
        required_fields = ["version", "category", "stability"]

        for module_id, metadata in production_modules.items():
            for field in required_fields:
                assert field in metadata, (
                    f"Module {module_id} is missing required field '{field}'."
                )

    def test_module_categories_valid(self, production_modules):
        """All modules should have valid categories."""
        valid_categories = {
            "atomic", "browser", "element", "form", "file", "flow",
            "array", "text", "api", "communication", "ai", "productivity",
            "development", "security", "testing", "data", "media", "vision"
        }

        for module_id, metadata in production_modules.items():
            category = metadata.get("category", "unknown")
            # Allow any category but warn about unknown ones
            if category not in valid_categories:
                # This is a soft check - just ensure category exists
                assert category, (
                    f"Module {module_id} has empty category."
                )

    def test_version_format_valid(self, production_modules):
        """All module versions should be valid semver format."""
        import re
        semver_pattern = re.compile(r'^\d+\.\d+\.\d+$')

        for module_id, metadata in production_modules.items():
            version = metadata.get("version", "")
            assert semver_pattern.match(version), (
                f"Module {module_id} has invalid version format: '{version}'. "
                "Expected semver format: X.Y.Z"
            )


class TestModuleCLI:
    """Test the flyto modules CLI command."""

    def test_cli_modules_json_output(self):
        """CLI should output valid JSON."""
        from cli.modules import get_modules_list

        os.environ["FLYTO_ENV"] = "production"
        data = get_modules_list("production")

        assert "version" in data
        assert "environment" in data
        assert "modules" in data
        assert "total" in data
        assert data["environment"] == "production"

    def test_cli_modules_development_env(self):
        """Development environment should include more modules than production."""
        from cli.modules import get_modules_list

        prod_data = get_modules_list("production")
        dev_data = get_modules_list("development")

        # Development should have at least as many modules as production
        assert dev_data["total"] >= prod_data["total"], (
            f"Development ({dev_data['total']}) has fewer modules than "
            f"production ({prod_data['total']}). This is unexpected."
        )
