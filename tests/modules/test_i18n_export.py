"""
Tests for i18n export module.

Tests the registry-driven i18n key extraction and coverage reporting.
"""
import pytest
from src.core.modules.i18n_export import (
    get_module_i18n_keys,
    extract_all_i18n_keys,
    export_en_baseline,
    keys_to_nested,
    nested_to_flat,
    get_i18n_coverage,
    validate_locale_structure,
    I18nCoverageReport,
)


class TestGetModuleI18nKeys:
    """Test get_module_i18n_keys function."""

    def test_extracts_label_key(self):
        """Test extraction of label_key."""
        metadata = {
            "label_key": "modules.test.module.label",
            "label": "Test Module"
        }
        keys = get_module_i18n_keys("test.module", metadata)

        assert "modules.test.module.label" in keys
        assert keys["modules.test.module.label"] == "Test Module"

    def test_generates_label_key_from_label(self):
        """Test generation of key when label_key not present."""
        metadata = {
            "label": "Test Module"
        }
        keys = get_module_i18n_keys("test.module", metadata)

        assert "modules.test.module.label" in keys
        assert keys["modules.test.module.label"] == "Test Module"

    def test_extracts_params_schema_keys(self):
        """Test extraction of params_schema i18n keys."""
        metadata = {
            "params_schema": {
                "url": {
                    "label_key": "modules.test.module.params.url.label",
                    "label": "URL",
                    "description_key": "modules.test.module.params.url.description",
                    "description": "Target URL"
                }
            }
        }
        keys = get_module_i18n_keys("test.module", metadata)

        assert "modules.test.module.params.url.label" in keys
        assert keys["modules.test.module.params.url.label"] == "URL"
        assert "modules.test.module.params.url.description" in keys
        assert keys["modules.test.module.params.url.description"] == "Target URL"

    def test_extracts_output_schema_keys(self):
        """Test extraction of output_schema i18n keys."""
        metadata = {
            "output_schema": {
                "result": {
                    "description_key": "modules.test.module.output.result.description",
                    "description": "Operation result"
                }
            }
        }
        keys = get_module_i18n_keys("test.module", metadata)

        assert "modules.test.module.output.result.description" in keys

    def test_extracts_example_keys(self):
        """Test extraction of example i18n keys."""
        metadata = {
            "examples": [
                {
                    "title_key": "modules.test.module.examples.0.title",
                    "title": "Basic Example"
                }
            ]
        }
        keys = get_module_i18n_keys("test.module", metadata)

        assert "modules.test.module.examples.0.title" in keys


class TestKeysConversion:
    """Test keys conversion functions."""

    def test_keys_to_nested(self):
        """Test converting flat keys to nested structure."""
        flat = {
            "modules.browser.goto.label": "Go to URL",
            "modules.browser.goto.description": "Navigate to URL"
        }
        nested = keys_to_nested(flat)

        assert nested["modules"]["browser"]["goto"]["label"] == "Go to URL"
        assert nested["modules"]["browser"]["goto"]["description"] == "Navigate to URL"

    def test_nested_to_flat(self):
        """Test converting nested structure to flat keys."""
        nested = {
            "modules": {
                "browser": {
                    "goto": {
                        "label": "Go to URL"
                    }
                }
            }
        }
        flat = nested_to_flat(nested)

        assert "modules.browser.goto.label" in flat
        assert flat["modules.browser.goto.label"] == "Go to URL"

    def test_round_trip(self):
        """Test that flat -> nested -> flat preserves data."""
        original = {
            "a.b.c": "value1",
            "a.b.d": "value2",
            "x.y": "value3"
        }
        nested = keys_to_nested(original)
        flat = nested_to_flat(nested)

        assert flat == original


class TestExportEnBaseline:
    """Test export_en_baseline function."""

    def test_exports_all_modules(self):
        """Test that all modules are exported."""
        metadata = {
            "module.a": {
                "label": "Module A",
                "description": "Description A"
            },
            "module.b": {
                "label": "Module B"
            }
        }
        baseline = export_en_baseline(metadata)

        assert "modules" in baseline
        assert "module" in baseline["modules"]


class TestI18nCoverage:
    """Test get_i18n_coverage function."""

    def test_full_coverage(self):
        """Test 100% coverage report."""
        baseline = {"modules": {"test": {"label": "Test"}}}
        translations = {"modules": {"test": {"label": "測試"}}}

        report = get_i18n_coverage(baseline, translations)

        assert report.total_keys == 1
        assert report.translated_keys == 1
        assert report.coverage_percent == 100.0
        assert report.is_complete is True

    def test_missing_keys(self):
        """Test detection of missing keys."""
        baseline = {
            "modules": {
                "test": {
                    "label": "Test",
                    "description": "Description"
                }
            }
        }
        translations = {
            "modules": {
                "test": {
                    "label": "測試"
                }
            }
        }

        report = get_i18n_coverage(baseline, translations)

        assert report.total_keys == 2
        assert report.translated_keys == 1
        assert len(report.missing_keys) == 1
        assert "modules.test.description" in report.missing_keys
        assert report.is_complete is False

    def test_extra_keys(self):
        """Test detection of extra keys in translations."""
        baseline = {"modules": {"test": {"label": "Test"}}}
        translations = {
            "modules": {
                "test": {
                    "label": "測試",
                    "extra": "額外"
                }
            }
        }

        report = get_i18n_coverage(baseline, translations)

        assert len(report.extra_keys) == 1
        assert "modules.test.extra" in report.extra_keys

    def test_todo_keys(self):
        """Test detection of __TODO__ placeholders."""
        baseline = {"modules": {"test": {"label": "Test"}}}
        translations = {"modules": {"test": {"label": "__TODO__"}}}

        report = get_i18n_coverage(baseline, translations)

        assert len(report.todo_keys) == 1
        assert report.is_complete is False


class TestValidateLocaleStructure:
    """Test validate_locale_structure function."""

    def test_valid_structure(self):
        """Test valid structure passes."""
        locale = {
            "modules": {
                "test": {
                    "label": "Test Module",
                    "description": "A test module"
                }
            }
        }
        errors = validate_locale_structure(locale)

        assert len(errors) == 0

    def test_empty_value_error(self):
        """Test empty value is detected."""
        locale = {"modules": {"test": {"label": ""}}}
        errors = validate_locale_structure(locale)

        assert any("empty value" in e for e in errors)

    def test_todo_placeholder_error(self):
        """Test __TODO__ placeholder is detected."""
        locale = {"modules": {"test": {"label": "__TODO__"}}}
        errors = validate_locale_structure(locale)

        assert any("__TODO__" in e for e in errors)

    def test_valid_placeholder(self):
        """Test valid placeholder passes."""
        locale = {"modules": {"test": {"message": "Hello {name}!"}}}
        errors = validate_locale_structure(locale)

        assert len(errors) == 0
