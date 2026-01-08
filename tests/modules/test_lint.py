"""
Tests for module metadata lint.

Tests the registry-driven lint rules.
"""
import pytest
from src.core.modules.lint import (
    lint_module,
    lint_all_modules,
    LintResult,
    LintReport,
    Severity,
    PARAM_CANONICAL_NAMES,
    PARAM_ALIAS_TO_CANONICAL,
)


class TestLintReport:
    """Test LintReport class."""

    def test_empty_report_passes(self):
        """Test that empty report passes."""
        report = LintReport()
        assert report.passed is True
        assert report.error_count == 0

    def test_report_with_error_fails(self):
        """Test that report with error fails."""
        report = LintReport()
        report.add(LintResult(
            rule_id="TEST001",
            severity=Severity.ERROR,
            module_id="test.module",
            message="Test error"
        ))
        assert report.passed is False
        assert report.error_count == 1

    def test_report_with_warning_passes(self):
        """Test that report with only warnings passes."""
        report = LintReport()
        report.add(LintResult(
            rule_id="TEST001",
            severity=Severity.WARNING,
            module_id="test.module",
            message="Test warning"
        ))
        assert report.passed is True
        assert report.warning_count == 1

    def test_counts(self):
        """Test error/warning/info counts."""
        report = LintReport()
        report.add(LintResult("T1", Severity.ERROR, "m1", "error"))
        report.add(LintResult("T2", Severity.WARNING, "m2", "warning"))
        report.add(LintResult("T3", Severity.WARNING, "m3", "warning2"))
        report.add(LintResult("T4", Severity.INFO, "m4", "info"))

        assert report.error_count == 1
        assert report.warning_count == 2
        assert report.info_count == 1


class TestLintRequiredFields:
    """Test LINT003: Required fields."""

    def test_missing_module_id(self):
        """Test error when module_id is missing."""
        metadata = {
            "version": "1.0.0",
            "label": "Test",
            "description": "Test module"
        }
        report = lint_module("test.module", metadata)

        errors = [r for r in report.results if r.rule_id == "LINT003"]
        assert any("module_id" in r.field for r in errors)

    def test_missing_version(self):
        """Test error when version is missing."""
        metadata = {
            "module_id": "test.module",
            "label": "Test",
            "description": "Test module"
        }
        report = lint_module("test.module", metadata)

        errors = [r for r in report.results if r.rule_id == "LINT003"]
        assert any("version" in r.field for r in errors)

    def test_all_required_present(self):
        """Test no errors when all required fields present."""
        metadata = {
            "module_id": "test.module",
            "version": "1.0.0",
            "label": "Test Module",
            "description": "A test module"
        }
        report = lint_module("test.module", metadata)

        errors = [r for r in report.results if r.rule_id == "LINT003"]
        assert len(errors) == 0


class TestLintVersionFormat:
    """Test LINT004: Version format."""

    def test_valid_semver(self):
        """Test valid semver passes."""
        metadata = {
            "module_id": "test.module",
            "version": "1.2.3",
            "label": "Test",
            "description": "Test"
        }
        report = lint_module("test.module", metadata)

        errors = [r for r in report.results if r.rule_id == "LINT004"]
        assert len(errors) == 0

    def test_valid_semver_with_prerelease(self):
        """Test valid semver with prerelease passes."""
        metadata = {
            "module_id": "test.module",
            "version": "1.0.0-beta",
            "label": "Test",
            "description": "Test"
        }
        report = lint_module("test.module", metadata)

        errors = [r for r in report.results if r.rule_id == "LINT004"]
        assert len(errors) == 0

    def test_invalid_version(self):
        """Test invalid version fails."""
        metadata = {
            "module_id": "test.module",
            "version": "v1.0",
            "label": "Test",
            "description": "Test"
        }
        report = lint_module("test.module", metadata)

        errors = [r for r in report.results if r.rule_id == "LINT004"]
        assert len(errors) == 1


class TestLintParamNaming:
    """Test LINT001: Parameter naming."""

    def test_canonical_name_passes(self):
        """Test canonical param name passes."""
        metadata = {
            "module_id": "test.module",
            "version": "1.0.0",
            "label": "Test",
            "description": "Test",
            "params_schema": {
                "url": {"type": "string"}
            }
        }
        report = lint_module("test.module", metadata)

        warnings = [r for r in report.results if r.rule_id == "LINT001"]
        assert len(warnings) == 0

    def test_alias_warns(self):
        """Test alias param name warns."""
        metadata = {
            "module_id": "test.module",
            "version": "1.0.0",
            "label": "Test",
            "description": "Test",
            "params_schema": {
                "uri": {"type": "string"}  # Should use 'url'
            }
        }
        report = lint_module("test.module", metadata)

        warnings = [r for r in report.results if r.rule_id == "LINT001"]
        assert len(warnings) == 1
        assert "url" in warnings[0].hint


class TestLintI18nKeys:
    """Test LINT002: I18n keys."""

    def test_missing_label_key_info(self):
        """Test info when label_key missing."""
        metadata = {
            "module_id": "test.module",
            "version": "1.0.0",
            "label": "Test Module",
            "description": "Test"
        }
        report = lint_module("test.module", metadata)

        infos = [r for r in report.results if r.rule_id == "LINT002" and "label_key" in r.field]
        assert len(infos) == 1
        assert infos[0].severity == Severity.INFO


class TestLintTimeoutValues:
    """Test LINT009: Timeout values."""

    def test_reasonable_timeout_passes(self):
        """Test reasonable timeout passes."""
        metadata = {
            "module_id": "test.module",
            "version": "1.0.0",
            "label": "Test",
            "description": "Test",
            "timeout_ms": 30000
        }
        report = lint_module("test.module", metadata)

        warnings = [r for r in report.results if r.rule_id == "LINT009"]
        assert len(warnings) == 0

    def test_very_long_timeout_warns(self):
        """Test very long timeout warns."""
        metadata = {
            "module_id": "test.module",
            "version": "1.0.0",
            "label": "Test",
            "description": "Test",
            "timeout_ms": 600000  # 10 minutes
        }
        report = lint_module("test.module", metadata)

        warnings = [r for r in report.results if r.rule_id == "LINT009"]
        assert len(warnings) == 1

    def test_very_short_timeout_warns(self):
        """Test very short timeout warns."""
        metadata = {
            "module_id": "test.module",
            "version": "1.0.0",
            "label": "Test",
            "description": "Test",
            "timeout_ms": 500  # 0.5 seconds
        }
        report = lint_module("test.module", metadata)

        warnings = [r for r in report.results if r.rule_id == "LINT009"]
        assert len(warnings) == 1


class TestLintAllModules:
    """Test lint_all_modules function."""

    def test_lints_all_modules(self):
        """Test that all modules are linted."""
        metadata = {
            "module.a": {
                "module_id": "module.a",
                "version": "1.0.0",
                "label": "Module A",
                "description": "Test A"
            },
            "module.b": {
                "module_id": "module.b",
                "version": "invalid",
                "label": "Module B",
                "description": "Test B"
            }
        }
        report = lint_all_modules(metadata)

        # module.b should have version error
        errors = [r for r in report.results if r.module_id == "module.b" and r.rule_id == "LINT004"]
        assert len(errors) == 1
