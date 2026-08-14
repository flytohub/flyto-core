"""Adversarial contract tests for inert flyto.plugin.v1 adoption."""

from __future__ import annotations

import copy
import hashlib
import json
import os
from collections.abc import Mapping, Sequence

import pytest

import core.plugin.manifest as manifest_module
from core.plugin.manifest import (
    PluginManifestError,
    adopt_plugin_manifest,
    plugin_environment_names,
    validate_plugin_endpoint,
    validate_plugin_manifest,
    verify_plugin_artifact,
)


@pytest.fixture
def manifest() -> dict:
    return {
        "schema": "flyto.plugin.v1",
        "plugin": {
            "id": "com.example.vision",
            "namespace": "vision",
            "version": "1.0.0",
            "title": "Vision",
            "summary": "Observe a zone.",
            "license": "Apache-2.0",
            "support_url": "https://example.com/support",
            "publisher_key_id": "example-2026",
            "min_host": "2.28.0",
        },
        "artifact": {
            "kind": "archive",
            "name": "example-vision",
            "version": "1.0.0",
            "digest": "sha256:" + "0" * 64,
            "attestation": "sigstore",
        },
        "serve": {
            "binding": "http",
            "locality": "same_host",
            "request_timeout_ms": 5000,
            "max_response_bytes": 262144,
        },
        "capabilities": [{"id": "vision.observe"}],
        "evidence": [{"kind": "zone.overview", "produced_by": "vision.observe"}],
        "modules": [{
            "module_id": "vision.observe",
            "provides_capability": "vision.observe",
            "label": "Observe",
            "label_key": "modules.vision.observe.label",
            "description": "Observe the configured zone.",
            "category": "vision",
            "icon": "Eye",
            "actuates": False,
            "idempotent": True,
            "retryable": True,
            "timeout_ms": 30000,
            "required_permissions": [],
            "params_schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"zone": {"type": "string", "maxLength": 128}},
                "required": ["zone"],
            },
        }],
    }


def test_canonical_validation_detaches_input(manifest):
    validated = validate_plugin_manifest(manifest)
    manifest["plugin"]["namespace"] = "changed"
    assert validated["plugin"]["namespace"] == "vision"


def test_canonical_validation_recursively_sorts_equivalent_input(manifest):
    reversed_manifest = {
        key: copy.deepcopy(value) for key, value in reversed(list(manifest.items()))
    }
    reversed_manifest["plugin"] = {
        key: reversed_manifest["plugin"][key] for key in reversed(list(reversed_manifest["plugin"]))
    }
    first = validate_plugin_manifest(manifest)
    second = validate_plugin_manifest(reversed_manifest)
    assert list(first) == sorted(first)
    assert list(first["plugin"]) == sorted(first["plugin"])
    assert json.dumps(first, separators=(",", ":")) == json.dumps(second, separators=(",", ":"))


def test_canonical_serialization_ignores_deep_schema_insertion_order(manifest):
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "settings": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "filter": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "pattern": {"type": "string", "maxLength": 128},
                            "enabled": {"type": "boolean", "default": True},
                        },
                        "required": ["pattern", "enabled"],
                    },
                    "label": {"type": "string", "maxLength": 64},
                },
                "required": ["filter"],
            },
        },
        "required": ["settings"],
    }

    def reverse_mappings(value):
        if isinstance(value, dict):
            return {
                key: reverse_mappings(item)
                for key, item in reversed(list(value.items()))
            }
        if isinstance(value, list):
            return [reverse_mappings(item) for item in value]
        return value

    ordered = copy.deepcopy(manifest)
    hostile = copy.deepcopy(manifest)
    ordered["modules"][0]["params_schema"] = schema
    hostile["modules"][0]["params_schema"] = reverse_mappings(schema)

    first = validate_plugin_manifest(ordered)
    second = validate_plugin_manifest(hostile)
    first_schema = first["modules"][0]["params_schema"]
    nested_properties = first_schema["properties"]["settings"]["properties"]
    leaf_keywords = nested_properties["filter"]["properties"]["enabled"]

    assert list(first_schema) == sorted(first_schema)
    assert list(nested_properties) == sorted(nested_properties)
    assert list(leaf_keywords) == sorted(leaf_keywords)
    assert json.dumps(first, separators=(",", ":")) == json.dumps(second, separators=(",", ":"))


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda m: m.update({"surprise": True}), "UNKNOWN_KEY"),
        (lambda m: m["plugin"].update({"id": "Vision"}), "INVALID_PLUGIN_ID"),
        (lambda m: m["plugin"].update({"namespace": "shell"}), "INVALID_NAMESPACE"),
        (lambda m: m["plugin"].update({"version": "01.0.0"}), "INVALID_SEMVER"),
        (lambda m: m["modules"][0].update({"module_id": "other.observe"}), "MODULE_NAMESPACE_MISMATCH"),
        (lambda m: m["modules"][0].update({"required_permissions": ["network"]}), "INVALID_PERMISSION"),
        (lambda m: m["modules"][0]["params_schema"].update({"additionalProperties": True}), "OPEN_PARAMS_SCHEMA"),
        (lambda m: m["modules"][0]["params_schema"]["properties"].update({"token": {"type": "string"}}), "FORBIDDEN_PARAMETER"),
        (lambda m: m["capabilities"].append({"id": "vision.observe"}), "DUPLICATE_ID"),
        (lambda m: m["capabilities"].append({"id": "human.approval"}), "INVALID_CAPABILITY"),
        (lambda m: m["plugin"].update({"title": "bad\ntext"}), "INVALID_TEXT"),
        (lambda m: m["plugin"].update({"support_url": "https://example.com@evil.test/x"}), "INVALID_URL"),
    ],
)
def test_hostile_manifests_fail_closed(manifest, mutation, code):
    candidate = copy.deepcopy(manifest)
    mutation(candidate)
    with pytest.raises(PluginManifestError) as caught:
        validate_plugin_manifest(candidate)
    assert caught.value.code == code
    assert "secret-value" not in str(caught.value)


def test_wrong_schema_precedes_unknown_key(manifest):
    manifest["schema"] = "flyto.plugin.v999"
    manifest["unknown"] = True
    with pytest.raises(PluginManifestError) as caught:
        validate_plugin_manifest(manifest)
    assert caught.value.code == "UNSUPPORTED_SCHEMA"


@pytest.mark.parametrize(
    "unsafe",
    [
        "\u0085",  # C1 control
        "\u202e",  # bidi override
        "\u2066",  # bidi isolate
        "\u200b",  # zero-width format character
        "\ud800",  # surrogate
        "\ue000",  # private use
        "\ufdd0",  # noncharacter
        "\u0378",  # unassigned
        "\u2028",  # line separator
        "\u2029",  # paragraph separator
    ],
)
def test_unsafe_unicode_manifest_values_fail_stably(manifest, unsafe):
    manifest["plugin"]["title"] = f"secret-value{unsafe}hidden"
    with pytest.raises(PluginManifestError) as caught:
        validate_plugin_manifest(manifest)
    assert caught.value.code == "INVALID_TEXT"
    assert str(caught.value) == "manifest text is invalid or too long"
    assert "secret-value" not in str(caught.value)


@pytest.mark.parametrize(
    "bad_key",
    ["line\nbreak", "bad\u0085key", "bad\u202ekey", "bad\u200bkey", "bad\ud800key", "bad\ue000key", "bad\ufdd0key", "bad\u0378key", "bad\u2028key", "x" * 2049],
)
def test_unsafe_unicode_and_oversized_mapping_keys_fail_stably(manifest, bad_key):
    manifest[bad_key] = True
    with pytest.raises(PluginManifestError) as caught:
        validate_plugin_manifest(manifest)
    assert caught.value.code == "INVALID_KEY"
    assert bad_key not in str(caught.value)


def test_unknown_key_error_never_projects_the_attacker_key(manifest):
    manifest["secret-value-unknown"] = True
    with pytest.raises(PluginManifestError) as caught:
        validate_plugin_manifest(manifest)
    assert caught.value.code == "UNKNOWN_KEY"
    assert str(caught.value) == "manifest contains an unknown key"
    assert "secret-value" not in str(caught.value)


class _UnboundedMapping(Mapping):
    def __getitem__(self, key):
        raise KeyError(key)

    def __iter__(self):
        return iter(())

    def __len__(self):
        return 1

    def items(self):
        index = 0
        while True:
            yield f"key_{index}", index
            index += 1


def test_hostile_mapping_is_not_materialized_without_a_bound():
    with pytest.raises(PluginManifestError) as caught:
        validate_plugin_manifest(_UnboundedMapping())
    assert caught.value.code == "MANIFEST_TOO_COMPLEX"


class _NestedMapping(Mapping):
    def __init__(self, pairs):
        self._pairs = tuple(pairs)

    def __getitem__(self, key):
        for candidate, value in self._pairs:
            if candidate == key:
                return value
        raise KeyError(key)

    def __iter__(self):
        return (key for key, _ in self._pairs)

    def __len__(self):
        return len(self._pairs)

    def items(self):
        return iter(self._pairs)


class _NestedSequence(Sequence):
    def __init__(self, values):
        self._values = tuple(values)

    def __getitem__(self, index):
        return self._values[index]

    def __len__(self):
        return len(self._values)


def _hostile_nested_containers(value):
    if isinstance(value, dict):
        return _NestedMapping(
            (key, _hostile_nested_containers(item))
            for key, item in reversed(list(value.items()))
        )
    if isinstance(value, list):
        return _NestedSequence(_hostile_nested_containers(item) for item in value)
    return value


def test_nested_hostile_mappings_and_sequences_are_bounded_canonical_and_immutable(manifest):
    hostile = _hostile_nested_containers(manifest)
    expected = validate_plugin_manifest(manifest)
    validated = validate_plugin_manifest(hostile)
    adopted = adopt_plugin_manifest(hostile)

    assert json.dumps(validated, separators=(",", ":")) == json.dumps(
        expected, separators=(",", ":")
    )
    assert list(validated) == sorted(validated)
    assert list(validated["modules"][0]["params_schema"]) == sorted(
        validated["modules"][0]["params_schema"]
    )
    assert isinstance(adopted.manifest["modules"], tuple)
    assert isinstance(adopted.manifest["modules"][0]["params_schema"], Mapping)
    with pytest.raises(TypeError):
        adopted.manifest["modules"][0]["params_schema"]["type"] = "string"


@pytest.mark.parametrize(
    ("nested_value", "code", "message"),
    [
        (
            _NestedMapping((("type", "string"), ("secret-value\u202ekey", True))),
            "INVALID_KEY",
            "manifest key is invalid or too long",
        ),
        (
            _NestedMapping((("type", "string"), ("title", "secret-value\u202e"))),
            "INVALID_TEXT",
            "manifest text is invalid or too long",
        ),
    ],
)
def test_nested_unsafe_hostile_input_is_rejected_before_projection(
    manifest, nested_value, code, message
):
    manifest["modules"][0]["params_schema"]["properties"]["zone"] = nested_value
    hostile = _hostile_nested_containers(manifest)

    with pytest.raises(PluginManifestError) as caught:
        validate_plugin_manifest(hostile)

    assert caught.value.code == code
    assert str(caught.value) == message
    assert "secret-value" not in str(caught.value)


def test_nested_hostile_sequence_depth_is_bounded_without_reflection(manifest):
    nested = "leaf"
    for _ in range(manifest_module.MAX_JSON_DEPTH + 2):
        nested = _NestedSequence((nested,))
    manifest["modules"][0]["params_schema"]["properties"]["zone"] = nested

    with pytest.raises(PluginManifestError) as caught:
        validate_plugin_manifest(_hostile_nested_containers(manifest))

    assert caught.value.code == "MANIFEST_TOO_DEEP"
    assert str(caught.value) == "manifest exceeds the depth limit"
    assert "_NestedSequence" not in str(caught.value)


class _UnboundedNestedSequence(Sequence):
    def __init__(self):
        self.reads = 0

    def __getitem__(self, index):
        if index < 0:
            raise IndexError(index)
        self.reads += 1
        if self.reads > manifest_module.MAX_JSON_NODES:
            raise AssertionError("secret-value from _UnboundedNestedSequence")
        return "safe"

    def __len__(self):
        return manifest_module.MAX_JSON_NODES + 1


def test_nested_unbounded_sequence_stops_at_shared_node_budget(manifest):
    hostile = _UnboundedNestedSequence()
    manifest["modules"][0]["params_schema"]["properties"]["zone"]["enum"] = hostile

    with pytest.raises(PluginManifestError) as caught:
        validate_plugin_manifest(manifest)

    assert caught.value.code == "MANIFEST_TOO_COMPLEX"
    assert str(caught.value) == "manifest exceeds the node limit"
    assert "secret-value" not in str(caught.value)
    assert "_UnboundedNestedSequence" not in str(caught.value)
    assert hostile.reads <= manifest_module.MAX_JSON_NODES


@pytest.mark.parametrize("bad_type", [None, True, 1, [], {}, "strng"])
def test_parameter_schema_type_must_be_a_supported_string(manifest, bad_type):
    manifest["modules"][0]["params_schema"]["properties"]["zone"]["type"] = bad_type
    with pytest.raises(PluginManifestError) as caught:
        validate_plugin_manifest(manifest)
    assert caught.value.code == "INVALID_PARAMS_SCHEMA"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda schema: schema.update({"required": ["missing"]}),
        lambda schema: schema.update({"required": ["zone", "zone"]}),
        lambda schema: schema["properties"]["zone"].update({"additionalProperties": False}),
        lambda schema: schema["properties"]["zone"].update({"enum": "zone"}),
        lambda schema: schema["properties"]["zone"].update({"minLength": 9, "maxLength": 2}),
        lambda schema: schema["properties"]["zone"].update({"minimum": 1}),
        lambda schema: schema["properties"]["zone"].update({"default": 1}),
        lambda schema: schema["properties"]["zone"].update({"const": False}),
    ],
)
def test_parameter_schema_keywords_fail_closed(manifest, mutate):
    mutate(manifest["modules"][0]["params_schema"])
    with pytest.raises(PluginManifestError) as caught:
        validate_plugin_manifest(manifest)
    assert caught.value.code in {"INVALID_PARAMS_SCHEMA", "OPEN_PARAMS_SCHEMA"}


@pytest.mark.parametrize(
    "support_url",
    ["https://[::1", "https://[not-ipv6]/support", "https://example.com:99999/support"],
)
def test_malformed_support_urls_fail_stably(manifest, support_url):
    manifest["plugin"]["support_url"] = support_url
    with pytest.raises(PluginManifestError) as caught:
        validate_plugin_manifest(manifest)
    assert caught.value.code == "INVALID_URL"


def test_artifact_is_verified_offline_and_result_is_immutable(tmp_path, manifest):
    artifact = tmp_path / "plugin.bin"
    artifact.write_bytes(b"local artifact")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    manifest["artifact"]["digest"] = "sha256:" + digest
    result = adopt_plugin_manifest(manifest, artifact_path=artifact, endpoint="http://127.0.0.1:8080")
    assert result.artifact_sha256 == digest
    assert result.endpoint_env == "FLYTO_PLUGIN_ENDPOINT__VISION"
    with pytest.raises(TypeError):
        result.manifest["plugin"]["namespace"] = "changed"


def test_artifact_symlink_oversize_and_digest_mismatch_fail(tmp_path):
    artifact = tmp_path / "artifact"
    artifact.write_bytes(b"abc")
    link = tmp_path / "link"
    link.symlink_to(artifact)
    with pytest.raises(PluginManifestError) as caught:
        verify_plugin_artifact(link, "sha256:" + hashlib.sha256(b"abc").hexdigest())
    assert caught.value.code == "ARTIFACT_UNREADABLE"
    with pytest.raises(PluginManifestError) as caught:
        verify_plugin_artifact(artifact, "sha256:" + "0" * 64)
    assert caught.value.code == "DIGEST_MISMATCH"
    with pytest.raises(PluginManifestError) as caught:
        verify_plugin_artifact(artifact, "sha256:" + hashlib.sha256(b"abc").hexdigest(), max_bytes=2)
    assert caught.value.code == "ARTIFACT_INVALID"
    with pytest.raises(PluginManifestError) as caught:
        verify_plugin_artifact(
            artifact,
            "sha256:" + hashlib.sha256(b"abc").hexdigest(),
            max_bytes=512 * 1024 * 1024 + 1,
        )
    assert caught.value.code == "INVALID_BOUND"


def test_artifact_fallback_rejects_final_symlink(monkeypatch, tmp_path):
    artifact = tmp_path / "artifact"
    artifact.write_bytes(b"abc")
    link = tmp_path / "link"
    link.symlink_to(artifact)
    monkeypatch.setattr(manifest_module.os, "O_NOFOLLOW", 0)
    with pytest.raises(PluginManifestError) as caught:
        verify_plugin_artifact(link, "sha256:" + hashlib.sha256(b"abc").hexdigest())
    assert caught.value.code == "ARTIFACT_UNREADABLE"


def test_artifact_nofollow_rejects_final_symlink_inserted_at_open(monkeypatch, tmp_path):
    artifact = tmp_path / "artifact"
    target = tmp_path / "target"
    artifact.write_bytes(b"original")
    target.write_bytes(b"target")
    real_open = os.open

    def swap_to_symlink_then_open(path, flags):
        artifact.unlink()
        artifact.symlink_to(target)
        return real_open(path, flags)

    monkeypatch.setattr(manifest_module.os, "open", swap_to_symlink_then_open)
    with pytest.raises(PluginManifestError) as caught:
        verify_plugin_artifact(
            artifact, "sha256:" + hashlib.sha256(b"target").hexdigest()
        )
    assert caught.value.code == "ARTIFACT_UNREADABLE"


def test_artifact_fallback_rejects_final_symlink_swap_after_lstat(
    monkeypatch, tmp_path
):
    artifact = tmp_path / "artifact"
    target = tmp_path / "target"
    artifact.write_bytes(b"original")
    target.write_bytes(b"target")
    real_open = os.open

    def swap_to_symlink_then_open(path, flags):
        artifact.unlink()
        artifact.symlink_to(target)
        return real_open(path, flags)

    monkeypatch.setattr(manifest_module.os, "O_NOFOLLOW", 0)
    monkeypatch.setattr(manifest_module.os, "open", swap_to_symlink_then_open)
    with pytest.raises(PluginManifestError) as caught:
        verify_plugin_artifact(
            artifact, "sha256:" + hashlib.sha256(b"target").hexdigest()
        )
    assert caught.value.code == "ARTIFACT_CHANGED"


def test_artifact_read_stays_bound_to_open_descriptor_when_path_swaps(monkeypatch, tmp_path):
    artifact = tmp_path / "artifact"
    replacement = tmp_path / "replacement"
    artifact.write_bytes(b"original")
    replacement.write_bytes(b"replacement")
    real_open = os.open

    def open_then_swap(path, flags):
        fd = real_open(path, flags)
        os.replace(replacement, artifact)
        return fd

    monkeypatch.setattr(manifest_module.os, "open", open_then_swap)
    digest = hashlib.sha256(b"original").hexdigest()
    assert verify_plugin_artifact(artifact, "sha256:" + digest) == digest


def test_artifact_mutation_through_open_descriptor_is_detected(monkeypatch, tmp_path):
    artifact = tmp_path / "artifact"
    artifact.write_bytes(b"original")
    real_read = os.read
    mutated = False

    def read_then_mutate(fd, size):
        nonlocal mutated
        block = real_read(fd, size)
        if block and not mutated:
            mutated = True
            artifact.write_bytes(b"mutated!")
        return block

    monkeypatch.setattr(manifest_module.os, "read", read_then_mutate)
    with pytest.raises(PluginManifestError) as caught:
        verify_plugin_artifact(artifact, "sha256:" + hashlib.sha256(b"original").hexdigest())
    assert caught.value.code == "ARTIFACT_CHANGED"


@pytest.mark.parametrize("max_bytes", [0, False, -1, 512 * 1024 * 1024 + 1])
def test_artifact_byte_limit_must_be_positive_int_within_hard_cap(tmp_path, max_bytes):
    artifact = tmp_path / "artifact"
    artifact.write_bytes(b"a")
    with pytest.raises(PluginManifestError) as caught:
        verify_plugin_artifact(artifact, "sha256:" + hashlib.sha256(b"a").hexdigest(), max_bytes=max_bytes)
    assert caught.value.code == "INVALID_BOUND"


def test_endpoint_locality_never_resolves_or_accepts_url_escape():
    assert validate_plugin_endpoint("http://[::1]:9000/x", "same_host") == "http://[::1]:9000/x"
    with pytest.raises(PluginManifestError):
        validate_plugin_endpoint("https://example.com", "same_host")
    with pytest.raises(PluginManifestError):
        validate_plugin_endpoint("https://allowed.test.evil", "same_network", ["allowed.test"])
    assert validate_plugin_endpoint("https://allowed.test/v1", "same_network", ["allowed.test"]) == "https://allowed.test/v1"


@pytest.mark.parametrize("endpoint", ["http://[::1", "http://[not-ipv6]:80", "http://127.0.0.1:99999"])
def test_malformed_endpoint_fails_stably(endpoint):
    with pytest.raises(PluginManifestError) as caught:
        validate_plugin_endpoint(endpoint, "same_host")
    assert caught.value.code == "INVALID_ENDPOINT"


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://127.0.0.1/path\nnext",
        "http://127.0.0.1/path?value=bad\tvalue",
        "http://127.0.0.1/\u0085",
        "http://127.0.0.1/\u202e",
        "http://127.0.0.1/\u2066",
        "http://127.0.0.1/\u200b",
        "http://127.0.0.1/\ud800",
        "http://127.0.0.1/\ue000",
        "http://127.0.0.1/\ufdd0",
        "http://127.0.0.1/\u0378",
        "http://127.0.0.1/\u2028",
        "http://127.0.0.1/\u2029",
    ],
)
def test_endpoint_unsafe_unicode_fails_stably(endpoint):
    with pytest.raises(PluginManifestError) as caught:
        validate_plugin_endpoint(endpoint, "same_host")
    assert caught.value.code == "INVALID_ENDPOINT"


@pytest.mark.parametrize(
    "allowed",
    [["allowed.test\n"], ["bad\u0085host"], ["bad\u202ehost"], ["bad\u200bhost"], ["bad\ud800host"], ["bad\ue000host"], ["bad\ufdd0host"], ["bad\u0378host"], ["bad\u2028host"], ["x" * 2049]],
)
def test_endpoint_allowlist_text_is_bounded_and_unicode_safe(allowed):
    with pytest.raises(PluginManifestError) as caught:
        validate_plugin_endpoint("https://allowed.test", "same_network", allowed)
    assert caught.value.code == "INVALID_ENDPOINT"


def test_unsafe_manifest_text_fails_before_adoption_side_effects(monkeypatch, manifest):
    def unexpected(*args, **kwargs):
        raise AssertionError("invalid manifest must remain inert")

    monkeypatch.setattr(manifest_module, "verify_plugin_artifact", unexpected)
    monkeypatch.setattr(manifest_module, "validate_plugin_endpoint", unexpected)
    manifest["secret-value-unknown"] = True
    manifest["plugin"]["title"] = "unsafe\u202evalue"
    with pytest.raises(PluginManifestError) as caught:
        adopt_plugin_manifest(
            manifest,
            artifact_path="must-not-open",
            endpoint="https://must-not-parse.invalid",
        )
    assert caught.value.code == "INVALID_TEXT"
    assert "secret-value" not in str(caught.value)


@pytest.mark.parametrize(
    ("endpoint", "allowed_hosts"),
    [
        ("http://127.0.0.1/unsafe\u202evalue", ()),
        ("https://allowed.test", ("unsafe\u200bhost",)),
    ],
)
def test_unsafe_endpoint_inputs_fail_before_artifact_access(
    monkeypatch, manifest, endpoint, allowed_hosts
):
    def unexpected(*args, **kwargs):
        raise AssertionError("invalid endpoint input must not access an artifact")

    monkeypatch.setattr(manifest_module, "verify_plugin_artifact", unexpected)
    if allowed_hosts:
        manifest["serve"]["locality"] = "same_network"
    with pytest.raises(PluginManifestError) as caught:
        adopt_plugin_manifest(
            manifest,
            artifact_path="must-not-open",
            endpoint=endpoint,
            allowed_hosts=allowed_hosts,
        )
    assert caught.value.code == "INVALID_ENDPOINT"


@pytest.mark.parametrize(
    "allowed",
    [
        ["allowed.test"] * 2,
        ["ALLOWED.TEST", "allowed.test."],
        ["allowed.test/path"],
        ["user@allowed.test"],
        ["allowed_test"],
        ["a" * 256],
        ["allowed.test"] * 33,
    ],
)
def test_endpoint_allowlist_is_small_unique_ascii_host_authorities(allowed):
    with pytest.raises(PluginManifestError):
        validate_plugin_endpoint("https://allowed.test", "same_network", allowed)


def test_endpoint_allowlist_matches_the_exact_authority_without_dns():
    assert (
        validate_plugin_endpoint("https://allowed.test:8443/v1", "same_network", ("ALLOWED.TEST.:8443",))
        == "https://allowed.test:8443/v1"
    )
    assert validate_plugin_endpoint("http://[::1]:9000/v1", "same_network", ("[::1]:9000",))
    with pytest.raises(PluginManifestError) as caught:
        validate_plugin_endpoint("https://allowed.test:8443", "same_network", ("allowed.test",))
    assert caught.value.code == "LOCALITY_DENIED"


def test_environment_names_are_derived_only_from_namespace():
    assert plugin_environment_names("zone_camera") == (
        "FLYTO_PLUGIN_ENDPOINT__ZONE_CAMERA",
        "FLYTO_PLUGIN_TOKEN__ZONE_CAMERA",
    )


def test_existing_plugin_ids_detects_an_already_adopted_id(manifest):
    with pytest.raises(PluginManifestError) as caught:
        adopt_plugin_manifest(manifest, existing_plugin_ids=("com.example.vision",))
    assert caught.value.code == "DUPLICATE_PLUGIN_ID"


class _ExplodingExistingIds(Sequence):
    def __getitem__(self, index):
        raise AssertionError("must not index hostile collection")

    def __len__(self):
        raise AssertionError("must not size hostile collection")

    def __iter__(self):
        raise AssertionError("must not iterate hostile collection")

    def __contains__(self, item):
        raise AssertionError("must not search hostile collection")


@pytest.mark.parametrize(
    "existing_ids",
    [
        True,
        "com.example.safe",
        {"com.example.safe": True},
        (item for item in ("com.example.safe",)),
        _ExplodingExistingIds(),
        ["com.example.safe"] * 257,
        ["com.example.safe", "com.example.safe"],
        ["invalid"],
        ["com.example.bad\n"],
        ["com.example.\ud800"],
        ["com.example." + "x" * 2049],
        [False],
    ],
)
def test_existing_plugin_ids_rejects_hostile_collections_stably(manifest, existing_ids):
    with pytest.raises(PluginManifestError) as caught:
        adopt_plugin_manifest(manifest, existing_plugin_ids=existing_ids)
    assert caught.value.code == "INVALID_EXISTING_PLUGIN_IDS"
    assert str(caught.value) == (
        "existing_plugin_ids must be a bounded unique list or tuple of plugin ids"
    )
    assert "com.example.safe" not in str(caught.value)
