"""Tests for validate.json_schema module — type dispatch and validate_against_schema."""

import pytest

from core.modules.atomic.validate.json_schema import (
    _check_bool_excluded,
    _validate_number,
    _validate_string,
    _validate_type,
    _validate_value,
    _TYPE_CHECKERS,
    validate_against_schema,
    validate_json_schema,
)
from core.modules.errors import ValidationError


# ── _check_bool_excluded ──

class TestCheckBoolExcluded:
    def test_int_passes(self):
        assert _check_bool_excluded(42, int) is True

    def test_float_passes(self):
        assert _check_bool_excluded(3.14, (int, float)) is True

    def test_bool_excluded_from_int(self):
        assert _check_bool_excluded(True, int) is False

    def test_bool_excluded_from_int_float(self):
        assert _check_bool_excluded(False, (int, float)) is False


# ── _TYPE_CHECKERS dispatch table ──

class TestTypeCheckers:
    def test_all_types_registered(self):
        expected = {"string", "number", "integer", "boolean", "array", "object", "null"}
        assert set(_TYPE_CHECKERS.keys()) == expected

    @pytest.mark.parametrize("type_name,value,expected", [
        ("string", "hello", True),
        ("string", 42, False),
        ("number", 42, True),
        ("number", 3.14, True),
        ("number", True, False),
        ("integer", 5, True),
        ("integer", 5.0, False),
        ("integer", False, False),
        ("boolean", True, True),
        ("boolean", 0, False),
        ("array", [1, 2], True),
        ("array", "not list", False),
        ("object", {"a": 1}, True),
        ("object", [1], False),
        ("null", None, True),
        ("null", 0, False),
    ])
    def test_checker(self, type_name, value, expected):
        assert _TYPE_CHECKERS[type_name](value) is expected


# ── _validate_type ──

class TestValidateType:
    def test_valid_string(self):
        ok, err = _validate_type("hello", "string", "root")
        assert ok is True
        assert err is None

    def test_invalid_string(self):
        ok, err = _validate_type(42, "string", "root")
        assert ok is False
        assert "expected string" in err

    def test_unknown_type_passes(self):
        ok, err = _validate_type("anything", "custom_type", "root")
        assert ok is True

    def test_error_includes_path(self):
        ok, err = _validate_type(42, "string", "root.name")
        assert "root.name" in err


# ── validate_against_schema ──

class TestValidateAgainstSchema:
    def test_valid_object(self):
        data = {"name": "John", "age": 30}
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
            },
            "required": ["name"],
        }
        is_valid, errors = validate_against_schema(data, schema)
        assert is_valid is True
        assert errors == []

    def test_missing_required(self):
        data = {"age": 30}
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }
        is_valid, errors = validate_against_schema(data, schema)
        assert is_valid is False
        assert any("missing required" in e for e in errors)

    def test_wrong_type(self):
        data = {"name": 123}
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
        }
        is_valid, errors = validate_against_schema(data, schema)
        assert is_valid is False
        assert any("expected string" in e for e in errors)

    def test_array_items(self):
        data = [1, "two", 3]
        schema = {"type": "array", "items": {"type": "integer"}}
        is_valid, errors = validate_against_schema(data, schema)
        assert is_valid is False
        assert any("expected integer" in e for e in errors)

    def test_array_min_items(self):
        data = [1]
        schema = {"type": "array", "minItems": 3}
        is_valid, errors = validate_against_schema(data, schema)
        assert is_valid is False
        assert any("minimum is 3" in e for e in errors)

    def test_array_max_items(self):
        data = [1, 2, 3, 4]
        schema = {"type": "array", "maxItems": 2}
        is_valid, errors = validate_against_schema(data, schema)
        assert is_valid is False
        assert any("maximum is 2" in e for e in errors)

    def test_number_minimum(self):
        data = 3
        schema = {"type": "number", "minimum": 5}
        is_valid, errors = validate_against_schema(data, schema)
        assert is_valid is False
        assert any("less than minimum" in e for e in errors)

    def test_number_maximum(self):
        data = 100
        schema = {"type": "number", "maximum": 50}
        is_valid, errors = validate_against_schema(data, schema)
        assert is_valid is False
        assert any("greater than maximum" in e for e in errors)

    def test_string_min_length(self):
        is_valid, errors = validate_against_schema("ab", {"type": "string", "minLength": 5})
        assert is_valid is False

    def test_string_max_length(self):
        is_valid, errors = validate_against_schema("abcdef", {"type": "string", "maxLength": 3})
        assert is_valid is False

    def test_string_enum(self):
        is_valid, errors = validate_against_schema("x", {"type": "string", "enum": ["a", "b"]})
        assert is_valid is False
        assert any("not one of allowed values" in e for e in errors)

    def test_nested_object(self):
        data = {"address": {"zip": "12345"}}
        schema = {
            "type": "object",
            "properties": {
                "address": {
                    "type": "object",
                    "properties": {"zip": {"type": "string"}},
                }
            },
        }
        is_valid, errors = validate_against_schema(data, schema)
        assert is_valid is True

    def test_empty_schema(self):
        is_valid, errors = validate_against_schema({"anything": True}, {})
        assert is_valid is True

    def test_bool_not_integer(self):
        is_valid, errors = validate_against_schema(True, {"type": "integer"})
        assert is_valid is False

    def test_bool_not_number(self):
        is_valid, errors = validate_against_schema(False, {"type": "number"})
        assert is_valid is False

    def test_union_type(self):
        is_valid, errors = validate_against_schema("hello", {"type": ["string", "null"]})
        assert is_valid is True

    def test_union_type_null(self):
        # None is valid for {"type": ["string", "null"]} — "null" matches
        is_valid, errors = validate_against_schema(None, {"type": ["string", "null"]})
        assert is_valid is True
        assert errors == []


# ── _validate_value union type failure path (lines 81-82) ──

class TestValidateValueUnionTypeFail:
    def test_no_type_in_union_matches(self):
        # A list value against ["integer", "string"] — neither matches → error
        errors = []
        result = _validate_value([1, 2], {"type": ["integer", "string"]}, "root", errors)
        assert result is False
        assert len(errors) == 1
        assert "expected one of" in errors[0]

    def test_union_error_message_includes_types(self):
        errors = []
        _validate_value({"key": "val"}, {"type": ["integer", "string"]}, "field", errors)
        assert "integer" in errors[0]
        assert "string" in errors[0]

    def test_union_error_includes_actual_type(self):
        errors = []
        _validate_value(3.14, {"type": ["integer", "null"]}, "x", errors)
        assert "float" in errors[0]


# ── validate_json_schema entry point (lines 192-233) ──

class TestValidateJsonSchemaEntryPoint:
    async def _call(self, params):
        instance = validate_json_schema(params, {})
        return await instance.execute()

    async def test_valid_data_and_schema_as_dicts(self):
        params = {
            "data": {"name": "Alice", "age": 25},
            "schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "age": {"type": "integer"},
                },
                "required": ["name"],
            },
        }
        result = await self._call(params)
        assert result["ok"] is True
        assert result["data"]["valid"] is True
        assert result["data"]["errors"] == []
        assert result["data"]["error_count"] == 0

    async def test_data_as_json_string(self):
        params = {
            "data": '{"name": "Bob"}',
            "schema": {"type": "object", "properties": {"name": {"type": "string"}}},
        }
        result = await self._call(params)
        assert result["ok"] is True
        assert result["data"]["valid"] is True

    async def test_schema_as_json_string(self):
        params = {
            "data": {"name": "Carol"},
            "schema": '{"type": "object", "properties": {"name": {"type": "string"}}}',
        }
        result = await self._call(params)
        assert result["ok"] is True
        assert result["data"]["valid"] is True

    async def test_invalid_json_data_string(self):
        params = {
            "data": "{not valid json}",
            "schema": {"type": "object"},
        }
        result = await self._call(params)
        assert result["ok"] is True
        assert result["data"]["valid"] is False
        assert result["data"]["error_count"] == 1
        assert any("Invalid JSON data" in e for e in result["data"]["errors"])

    async def test_invalid_json_schema_string(self):
        params = {
            "data": {"name": "Dave"},
            "schema": "{not valid schema}",
        }
        result = await self._call(params)
        assert result["ok"] is True
        assert result["data"]["valid"] is False
        assert result["data"]["error_count"] == 1
        assert any("Invalid JSON schema" in e for e in result["data"]["errors"])

    async def test_missing_data_param_raises(self):
        params = {"schema": {"type": "object"}}
        with pytest.raises(ValidationError):
            await self._call(params)

    async def test_missing_schema_param_raises(self):
        params = {"data": {"name": "Eve"}}
        with pytest.raises(ValidationError):
            await self._call(params)

    async def test_validation_failure_returns_errors(self):
        params = {
            "data": {"age": "not-a-number"},
            "schema": {
                "type": "object",
                "properties": {"age": {"type": "integer"}},
                "required": ["age"],
            },
        }
        result = await self._call(params)
        assert result["ok"] is True
        assert result["data"]["valid"] is False
        assert result["data"]["error_count"] > 0

    async def test_both_data_and_schema_as_json_strings(self):
        """Both data AND schema supplied as JSON strings → parsed and validated."""
        params = {
            "data": '{"x": 1}',
            "schema": '{"type": "object", "properties": {"x": {"type": "integer"}}}',
        }
        result = await self._call(params)
        assert result["ok"] is True
        assert result["data"]["valid"] is True
        assert result["data"]["errors"] == []


# ── _validate_number / _validate_string no-op edge cases ──

class TestValidateNumberNoOp:
    def test_bool_true_is_noop_for_minimum(self):
        """bool is excluded from number checks — no error should be added."""
        errors: list = []
        _validate_number(True, {"minimum": 0}, "root", errors)
        assert errors == []

    def test_bool_false_is_noop_for_minimum(self):
        errors: list = []
        _validate_number(False, {"minimum": 0}, "root", errors)
        assert errors == []


class TestValidateStringNoOp:
    def test_integer_is_noop_for_min_length(self):
        """Non-string value is a no-op — no error should be added."""
        errors: list = []
        _validate_string(42, {"minLength": 1}, "root", errors)
        assert errors == []


# ── Deep nesting 4+ levels of properties ──

class TestDeepNestingValidation:
    def test_four_levels_valid(self):
        data = {"a": {"b": {"c": {"d": "leaf"}}}}
        schema = {
            "type": "object",
            "properties": {
                "a": {
                    "type": "object",
                    "properties": {
                        "b": {
                            "type": "object",
                            "properties": {
                                "c": {
                                    "type": "object",
                                    "properties": {
                                        "d": {"type": "string"},
                                    },
                                }
                            },
                        }
                    },
                }
            },
        }
        is_valid, errors = validate_against_schema(data, schema)
        assert is_valid is True
        assert errors == []

    def test_four_levels_wrong_leaf_type(self):
        data = {"a": {"b": {"c": {"d": 999}}}}
        schema = {
            "type": "object",
            "properties": {
                "a": {
                    "type": "object",
                    "properties": {
                        "b": {
                            "type": "object",
                            "properties": {
                                "c": {
                                    "type": "object",
                                    "properties": {
                                        "d": {"type": "string"},
                                    },
                                }
                            },
                        }
                    },
                }
            },
        }
        is_valid, errors = validate_against_schema(data, schema)
        assert is_valid is False
        assert any("expected string" in e for e in errors)


# ── None data with object schema → error ──

class TestNoneDataObjectSchema:
    def test_none_with_object_schema_is_invalid(self):
        is_valid, errors = validate_against_schema(None, {"type": "object"})
        assert is_valid is False
        assert len(errors) > 0


# ── Numeric boundary: minimum == maximum == value ──

class TestNumericBoundaryEqual:
    def test_value_equals_minimum_and_maximum(self):
        is_valid, errors = validate_against_schema(5, {"type": "number", "minimum": 5, "maximum": 5})
        assert is_valid is True
        assert errors == []


# ── type: "null" with non-null values → invalid ──

class TestNullTypeInvalid:
    def test_null_type_with_integer_zero(self):
        is_valid, errors = validate_against_schema(0, {"type": "null"})
        assert is_valid is False

    def test_null_type_with_empty_string(self):
        is_valid, errors = validate_against_schema("", {"type": "null"})
        assert is_valid is False

    def test_null_type_with_false(self):
        is_valid, errors = validate_against_schema(False, {"type": "null"})
        assert is_valid is False


# ── Empty required array → no error ──

class TestEmptyRequiredArray:
    def test_empty_required_produces_no_errors(self):
        data = {}
        schema = {"type": "object", "required": [], "properties": {}}
        is_valid, errors = validate_against_schema(data, schema)
        assert is_valid is True
        assert errors == []


# ── Array with items schema and minItems: 0 ──

class TestArrayMinItemsZero:
    def test_empty_array_with_min_items_zero_is_valid(self):
        is_valid, errors = validate_against_schema(
            [], {"type": "array", "items": {"type": "string"}, "minItems": 0}
        )
        assert is_valid is True
        assert errors == []
