"""Every module parameter that carries a credential says so in its contract.

A host that stores a workflow (not only one that logs a step) asks the module
contract which values are secrets: the schema marker (``secret: True`` /
``format: 'password'``), and ``sensitive_paths(params)`` for a value that is a
credential only because another value says so. The engine's name rule is a
backstop for logs, not a contract: a host that refuses to store a secret must
not have to guess from a parameter's spelling, in either direction.
"""
import pytest

from core.engine.redaction import is_sensitive_param_name, redact_step_params
from core.modules import atomic  # noqa: F401 - registers every module
from core.modules.registry import ModuleRegistry

SECRET = "not-a-real-credential-0000"


def _walk(spec, path, found):
    if not isinstance(spec, dict):
        return
    if isinstance(spec.get("items"), dict):
        _walk(spec["items"], (*path, "[]"), found)
    properties = spec.get("properties")
    if isinstance(properties, dict):
        for name, child in properties.items():
            if is_sensitive_param_name(name):
                found.append(((*path, name), child))
            _walk(child, (*path, name), found)


def _credential_named_params():
    ModuleRegistry._ensure_discovered()
    rows = []
    for module_id in sorted(ModuleRegistry._metadata):
        schema = (ModuleRegistry._metadata[module_id] or {}).get("params_schema")
        if not isinstance(schema, dict):
            continue
        found = []
        for name, spec in schema.items():
            if is_sensitive_param_name(name):
                found.append(((name,), spec))
            _walk(spec, (name,), found)
        rows.extend((module_id, ".".join(path), spec) for path, spec in found)
    return rows


class TestCatalogDeclaresItsCredentials:
    def test_every_credential_named_param_states_whether_it_is_secret(self):
        """``secret`` is True (a credential) or False (a selector, a URL, a switch).

        Left unstated, the answer is the engine's name rule, which takes
        ``password_selector`` for a password and has never heard of a value
        that is a credential because of the field it is typed into.
        """
        unstated = [
            f"{module_id}:{path}" for module_id, path, spec in _credential_named_params()
            if not isinstance(spec, dict) or not isinstance(spec.get("secret"), bool)
            and spec.get("format") != "password"
        ]
        assert unstated == []

    def test_every_top_level_secret_is_read_by_the_registry(self):
        for module_id, path, spec in _credential_named_params():
            if "." in path or spec.get("secret") is False:
                continue
            assert path in ModuleRegistry.secret_param_names(module_id), f"{module_id}:{path}"

    @pytest.mark.parametrize("module_id,param", [
        ("api.anthropic.chat", "api_key"),
        ("api.github.create_issue", "token"),
        ("notification.email.send", "password"),
        ("ssh.exec", "private_key"),
        ("cloud.aws_s3.upload", "aws_secret_access_key"),
        ("integration.slack.send_message", "token"),
        ("communication.twilio.send_sms", "auth_token"),
        ("verify.run", "figma_token"),
    ])
    def test_named_credentials_are_schema_secrets(self, module_id, param):
        assert param in ModuleRegistry.secret_param_names(module_id)

    @pytest.mark.parametrize("module_id,param,value", [
        ("browser.login", "password_selector", "#password"),
        ("auth.oauth2", "token_url", "https://auth.example.test/token"),
    ])
    def test_a_param_the_schema_clears_is_not_redacted_by_its_name(self, module_id, param, value):
        assert redact_step_params(module_id, {param: value})[param] == value


class TestFillFormDeclaresTheCredentialLeaf:
    def test_sensitive_value_carries_the_schema_marker(self):
        schema = ModuleRegistry.get_metadata("browser.fill_form")["params_schema"]
        item = schema["fields"]["items"]["properties"]["sensitive_value"]
        assert item.get("secret") is True

    def test_a_password_labelled_value_is_declared_by_its_path(self):
        params = {"fields": [
            {"label": "Email", "value": "a@example.test"},
            {"label": "Password", "value": SECRET},
            {"label": "Code", "sensitive_value": SECRET},
            {"label": "Password", "value": ""},
        ]}
        declare = ModuleRegistry.get("browser.fill_form").sensitive_paths
        assert declare(params) == frozenset({("fields", 1, "value"), ("fields", 2, "sensitive_value")})

    def test_no_credential_declares_nothing(self):
        declare = ModuleRegistry.get("browser.fill_form").sensitive_paths
        assert declare({"fields": [{"label": "Email", "value": "a@example.test"}]}) == frozenset()

    def test_the_step_record_hides_only_the_credential(self):
        params = {"fields": [
            {"label": "Email", "value": "a@example.test"},
            {"label": "Password", "value": SECRET},
        ]}
        recorded = redact_step_params("browser.fill_form", params)
        assert SECRET not in repr(recorded)
        assert recorded["fields"][0] == {"label": "Email", "value": "a@example.test"}
        assert recorded["fields"][1]["label"] == "Password"


class TestTypeDeclaresTheCredential:
    def test_sensitive_text_is_a_schema_secret(self):
        assert "sensitive_text" in ModuleRegistry.secret_param_names("browser.type")

    @pytest.mark.parametrize("params", [
        {"input_type": "password", "text": SECRET},
        {"type_method": "label", "target": "Password", "text": SECRET},
    ])
    def test_text_typed_into_a_password_field_is_declared(self, params):
        declare = ModuleRegistry.get("browser.type").sensitive_paths
        assert ("text",) in declare(params)

    def test_ordinary_text_is_not_declared(self):
        declare = ModuleRegistry.get("browser.type").sensitive_paths
        assert declare({"type_method": "label", "target": "Name", "text": "Ada"}) == frozenset()
