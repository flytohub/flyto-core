# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Display keys on an evidence spec (2.40.0).

An evidence spec may say what the reading it judges *is*, so a host can show
it without provider-specific code: a localized ``label`` (``{lang: text}``), a
``unit`` and the telemetry ``channel`` the observed field belongs to. They are
optional, validated by type and bound, kept verbatim in the normalized spec,
and never take part in :func:`judge`. Any other unknown key is still refused.

The vocabulary below is deliberately neutral: a thermostat, a queue depth or a
lift floor reads the same.
"""

import copy

import pytest

from core import capability_manifest
from core.capability_contract import (
    EVIDENCE_DISPLAY_FIELDS,
    EVIDENCE_LABEL_LANGS_MAX,
    EVIDENCE_LABEL_MAX,
    EVIDENCE_LABEL_PATTERN,
    EVIDENCE_UNIT_MAX,
    TELEMETRY_CHANNEL_PATTERN,
    judge,
    validate_contract,
    validate_evidence,
)
from core.capability_manifest import build_capability_manifest, compute_manifest_hash
from core.catalog.module import get_module_detail
from core.modules.base import BaseModule
from core.modules.registry import ModuleRegistry
from core.modules.registry import core as registry_core

SPEC = {
    "kind": "temperature-set",
    "observe": "climate",
    "phases": ["before", "after"],
    "measure": {"op": "delta", "fields": ["temp_c"]},
    "expect": {"argument": "delta_c"},
    "tolerance": {"absolute": 0.5},
}
DISPLAY = {
    "label": {"zh-TW": "車內溫度", "en": "Cabin temperature"},
    "unit": "°C",
    "channel": "climate.cabin",
}
PARAMS = {"delta_c": {"type": "number", "min": -10, "max": 10}}


def spec(**display):
    return {**copy.deepcopy(SPEC), **copy.deepcopy(display)}


def contract(*evidence):
    return {
        "actuates": True,
        "safety_class": "controlled",
        "requires_safe_stop": False,
        "cancellable": False,
        "idempotent": True,
        "evidence": [copy.deepcopy(item) for item in evidence],
    }


def test_the_vocabulary_is_published_for_providers_and_hosts():
    assert frozenset(("label", "unit", "channel")) == EVIDENCE_DISPLAY_FIELDS
    assert EVIDENCE_LABEL_LANGS_MAX == 8
    assert EVIDENCE_LABEL_MAX == 64
    assert EVIDENCE_UNIT_MAX == 16
    for tag in ("en", "und", "zh-TW", "pt-BR", "yue-Hant"):
        assert EVIDENCE_LABEL_PATTERN.fullmatch(tag)
    for channel in ("climate.cabin", "motion.speed", "Line-3/bay:2@east"):
        assert TELEMETRY_CHANNEL_PATTERN.fullmatch(channel)


def test_all_three_keys_are_kept_verbatim():
    normalized = validate_evidence(spec(**DISPLAY), PARAMS)
    for key, value in DISPLAY.items():
        assert normalized[key] == value
    # Label order is the provider's, not sorted.
    assert list(normalized["label"]) == ["zh-TW", "en"]


@pytest.mark.parametrize("key", sorted(DISPLAY))
def test_each_key_is_admitted_alone(key):
    normalized = validate_evidence(spec(**{key: DISPLAY[key]}))
    assert normalized[key] == DISPLAY[key]
    assert not (EVIDENCE_DISPLAY_FIELDS - {key}) & set(normalized)


def test_an_empty_unit_is_a_dimensionless_reading():
    assert validate_evidence(spec(unit=""))["unit"] == ""


def test_the_bounds_are_inclusive():
    label = {f"a{chr(97 + index)}": "x" * EVIDENCE_LABEL_MAX for index in range(EVIDENCE_LABEL_LANGS_MAX)}
    normalized = validate_evidence(spec(label=label, unit="u" * EVIDENCE_UNIT_MAX, channel="c" * 128))
    assert normalized["label"] == label


def test_a_spec_without_display_keys_normalizes_and_hashes_as_before():
    plain = validate_contract(contract(SPEC), PARAMS)
    assert set(plain["evidence"][0]) == {"kind", "observe", "phases", "measure", "expect", "tolerance"}


def test_the_normalized_keys_do_not_alias_the_input():
    given = spec(**DISPLAY)
    normalized = validate_evidence(given)
    normalized["label"]["en"] = "changed"
    assert given["label"]["en"] == "Cabin temperature"


def test_judge_ignores_display_keys():
    observations = {"before": {"temp_c": 20.0}, "after": {"temp_c": 22.0}}
    assert judge(spec(**DISPLAY), {"delta_c": 2}, observations) == judge(spec(), {"delta_c": 2}, observations)


REFUSED = [
    ("label not a mapping", {"label": "Cabin temperature"}, "label must be a mapping"),
    ("label empty", {"label": {}}, "label must hold 1..8"),
    ("label too many", {"label": {f"a{chr(97 + i)}": "x" for i in range(9)}}, "label must hold 1..8"),
    ("label bad tag", {"label": {"EN": "x"}}, "language tag"),
    ("label underscore tag", {"label": {"zh_TW": "x"}}, "language tag"),
    ("label non-string text", {"label": {"en": 3}}, "label['en'] must be"),
    ("label empty text", {"label": {"en": ""}}, "label['en'] must be"),
    ("label long text", {"label": {"en": "x" * 65}}, "label['en'] must be"),
    ("label control text", {"label": {"en": "a\nb"}}, "label['en'] must be"),
    ("unit not a string", {"unit": 1}, "unit must be a string"),
    ("unit none", {"unit": None}, "unit must be a string"),
    ("unit too long", {"unit": "u" * 17}, "unit must be a string"),
    ("unit control", {"unit": "m\t"}, "unit must be a string"),
    ("channel not a string", {"channel": ["climate.cabin"]}, "channel must be a telemetry channel id"),
    ("channel empty", {"channel": ""}, "channel must be a telemetry channel id"),
    ("channel bad start", {"channel": ".cabin"}, "channel must be a telemetry channel id"),
    ("channel space", {"channel": "climate cabin"}, "channel must be a telemetry channel id"),
    ("channel too long", {"channel": "c" * 129}, "channel must be a telemetry channel id"),
    ("still unknown", {"display_name": "Cabin"}, "unknown keys: display_name"),
    ("precision still unknown", {"precision": 1}, "unknown keys: precision"),
]


@pytest.mark.parametrize("name, extra, message", REFUSED, ids=[row[0] for row in REFUSED])
def test_invalid_display_keys_are_refused(name, extra, message):
    with pytest.raises(ValueError, match=r"contract\.evidence\[0\]") as raised:
        validate_contract(contract(spec(**extra)), PARAMS)
    assert message in str(raised.value)


# ---------------------------------------------------------------------------
# End to end: a plugin registers it, the registry, catalog and manifest keep it
# ---------------------------------------------------------------------------

_REGISTRY_STATE = (
    "_modules", "_metadata", "_plugins", "_plugin_contributions", "_core_baseline",
    "_pass_registered", "_pass_touched", "_pass_displaced", "_loading_plugin",
    "_cleared", "_started_empty", "_initialized",
)


class _Module(BaseModule):
    async def execute(self):  # pragma: no cover - never executed here
        return {}


class _Groups(list):
    def get(self, group, default=None):
        return list(self)


class _EntryPoint:
    name = "thermostat"
    value = "thermostat_pkg:register_all"

    def load(self):
        def register_all():
            ModuleRegistry.register("climate.adjust", _Module, {
                "module_id": "climate.adjust",
                "category": "climate",
                "stability": "stable",
                "ui_label": "Adjust temperature",
                "ui_description": "Adjust the cabin temperature",
                "provides_capability": "climate.adjust",
                "params_schema": copy.deepcopy(PARAMS),
                "contract": contract(spec(**DISPLAY)),
            })

        return register_all


@pytest.fixture
def registered(monkeypatch):
    saved = {}
    for name in _REGISTRY_STATE:
        value = getattr(ModuleRegistry, name)
        saved[name] = value.copy() if hasattr(value, "copy") else value
    monkeypatch.setattr(registry_core, "entry_points", lambda **kw: _Groups([_EntryPoint()]), raising=False)
    ModuleRegistry._modules = {}
    ModuleRegistry._metadata = {}
    ModuleRegistry._plugins = {}
    ModuleRegistry._plugin_contributions = {}
    ModuleRegistry._core_baseline = {}
    ModuleRegistry._pass_registered = None
    ModuleRegistry._pass_touched = None
    ModuleRegistry._pass_displaced = {}
    ModuleRegistry._loading_plugin = ""
    ModuleRegistry._cleared = False
    ModuleRegistry._started_empty = True
    ModuleRegistry._initialized = False
    ModuleRegistry.discover_plugins(force=True)
    capability_manifest._cached = None
    capability_manifest._cached_generation = -1
    try:
        yield
    finally:
        for name, value in saved.items():
            setattr(ModuleRegistry, name, value)
        capability_manifest._cached = None
        capability_manifest._cached_generation = -1


def test_the_registry_keeps_the_display_keys(registered):
    stored = ModuleRegistry.get_metadata("climate.adjust")["contract"]["evidence"][0]
    for key, value in DISPLAY.items():
        assert stored[key] == value


def test_the_manifest_a_host_reads_carries_the_display_keys(registered):
    manifest = build_capability_manifest()
    evidence = manifest["contracts"]["climate.adjust"]["contract"]["evidence"][0]
    for key, value in DISPLAY.items():
        assert evidence[key] == value
    assert manifest["hash"] == compute_manifest_hash(manifest)


def test_the_catalog_detail_carries_the_display_keys(registered):
    detail = get_module_detail("climate.adjust")
    evidence = detail["contract"]["evidence"][0]
    for key, value in DISPLAY.items():
        assert evidence[key] == value
