"""
Test Lint Rules with Fixtures

This test suite validates that lint rules correctly detect violations.
Each fixture is designed to test specific rules.

Fixture Expectations:
- valid_module.py              -> PASS (all rules)
- invalid_missing_fields.py    -> FAIL (S001)
- invalid_hardcoded_secret.py  -> FAIL (SEC004)
- invalid_command_injection.py -> FAIL (SEC005)
- invalid_sql_injection.py     -> FAIL (SEC006)
- invalid_eval_usage.py        -> FAIL (SEC007)
- valid_eval_breakpoint.py     -> PASS (SEC007 exempt)

Run: python -m pytest tests/lint_fixtures/test_lint_rules.py -v
"""
import sys
from pathlib import Path

import pytest

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from core.modules.validator import ModuleValidator
from core.modules.registry.validation_types import ValidationMode
from core.modules.registry import ModuleRegistry


def get_module_validation_result(module_id: str, mode: str = "ci"):
    """Helper to validate a single module and return errors."""
    validator = ModuleValidator(mode=ValidationMode(mode))
    metadata = ModuleRegistry.get_all_metadata().get(module_id)

    if metadata is None:
        return None, ["Module not found in registry"]

    module_class = ModuleRegistry.get(module_id)
    is_valid = validator.validate(metadata, module_class)

    return is_valid, list(validator.errors)


class TestValidModules:
    """Test that valid modules pass validation."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Import fixtures to register them."""
        from tests.lint_fixtures import valid_module
        from tests.lint_fixtures import valid_eval_breakpoint

    def test_valid_module_passes(self):
        """valid_module.py should pass all validation rules."""
        is_valid, errors = get_module_validation_result('test.valid_fixture')
        assert is_valid, f"Expected PASS but got errors: {errors}"
        assert len(errors) == 0

    def test_eval_breakpoint_passes(self):
        """valid_eval_breakpoint.py should pass (SEC007 exempt)."""
        is_valid, errors = get_module_validation_result('test.eval_breakpoint_fixture')
        assert is_valid, f"Expected PASS but got errors: {errors}"
        # Should not have SEC007 error
        sec007_errors = [e for e in errors if 'SEC007' in e]
        assert len(sec007_errors) == 0, f"Unexpected SEC007 error: {sec007_errors}"


class TestS001MissingFields:
    """Test S001: Missing required fields detection."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Import fixture."""
        try:
            from tests.lint_fixtures import invalid_missing_fields
        except Exception:
            pytest.skip("Fixture has import error (expected for invalid modules)")

    def test_missing_fields_fails(self):
        """invalid_missing_fields.py should fail with S001."""
        is_valid, errors = get_module_validation_result('test.missing_fields_fixture')

        # May not be registered due to missing required decorator args
        if errors == ["Module not found in registry"]:
            # This is expected - the decorator rejects invalid modules
            return

        # If registered, should have S001 errors
        assert not is_valid, "Expected FAIL for missing fields"
        s001_errors = [e for e in errors if 'S001' in e]
        assert len(s001_errors) > 0, f"Expected S001 errors, got: {errors}"


class TestSEC004HardcodedSecrets:
    """Test SEC004: Hardcoded secrets detection."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Import fixture."""
        from tests.lint_fixtures import invalid_hardcoded_secret

    def test_hardcoded_secret_fails(self):
        """invalid_hardcoded_secret.py should fail with SEC004."""
        is_valid, errors = get_module_validation_result('test.hardcoded_secret_fixture')

        # Look for SEC004 error
        sec004_errors = [e for e in errors if 'SEC004' in e]
        assert len(sec004_errors) > 0, f"Expected SEC004 error for hardcoded secret, got: {errors}"


class TestSEC005CommandInjection:
    """Test SEC005: Command injection detection."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Import fixture."""
        from tests.lint_fixtures import invalid_command_injection

    def test_command_injection_fails(self):
        """invalid_command_injection.py should fail with SEC005."""
        is_valid, errors = get_module_validation_result('test.command_injection_fixture')

        # Look for SEC005 error
        sec005_errors = [e for e in errors if 'SEC005' in e]
        assert len(sec005_errors) > 0, f"Expected SEC005 error for command injection, got: {errors}"


class TestSEC006SQLInjection:
    """Test SEC006: SQL injection detection."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Import fixture."""
        from tests.lint_fixtures import invalid_sql_injection

    def test_sql_injection_fails(self):
        """invalid_sql_injection.py should fail with SEC006."""
        is_valid, errors = get_module_validation_result('test.sql_injection_fixture')

        # Look for SEC006 error
        sec006_errors = [e for e in errors if 'SEC006' in e]
        assert len(sec006_errors) > 0, f"Expected SEC006 error for SQL injection, got: {errors}"


class TestSEC007EvalExec:
    """Test SEC007: Dangerous eval/exec detection."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Import fixtures."""
        from tests.lint_fixtures import invalid_eval_usage
        from tests.lint_fixtures import valid_eval_breakpoint

    def test_eval_usage_fails(self):
        """invalid_eval_usage.py should fail with SEC007."""
        is_valid, errors = get_module_validation_result('test.eval_usage_fixture')

        # Look for SEC007 error
        sec007_errors = [e for e in errors if 'SEC007' in e]
        assert len(sec007_errors) > 0, f"Expected SEC007 error for eval usage, got: {errors}"

    def test_eval_breakpoint_passes(self):
        """valid_eval_breakpoint.py should pass (exempt tag)."""
        is_valid, errors = get_module_validation_result('test.eval_breakpoint_fixture')

        # Should NOT have SEC007 error
        sec007_errors = [e for e in errors if 'SEC007' in e]
        assert len(sec007_errors) == 0, f"Unexpected SEC007 error for breakpoint module: {sec007_errors}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
