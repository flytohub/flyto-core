from core.modules import atomic  # noqa: F401 - register built-in modules
from core.modules.registry import ModuleRegistry


def test_optional_response_assertions_are_not_required_by_catalog_metadata():
    schema = ModuleRegistry.get_metadata("http.response_assert")["params_schema"]

    assert schema["response"]["required"] is True
    assert schema["body_matches"].get("required", False) is False
