# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Capability and plugin ownership as the catalog reports them.

A module declares ``provides_capability``; ``ModuleRegistry.register`` stamps
the owning ``plugin``. The catalog used to drop both, so a host that installed
an optional package had no way to learn from the catalog what that package made
available, and naming a capability fell back to someone typing it by hand.

What is pinned here: both catalog entry points forward the registry's values
and agree with one another, the public ``core.mcp_handler`` bridge hands them
on untouched, the values are never reconstructed from anything but registry
metadata, "declares nothing" has exactly one spelling, and scoring, ordering,
limit, and category filtering are untouched.
"""

from types import MappingProxyType

import pytest

from core.catalog.module import get_module_detail, search_modules
from core.mcp_handler import search_modules as bridge_search_modules
from core.modules.registry import ModuleRegistry

_ABSENT = object()


def _meta(label, description="", category="scan", **extra):
    """Registry-shaped metadata; callers supply only the keys under test."""
    base = {
        "ui_label": label,
        "ui_description": description,
        "category": category,
        "tags": [],
        "can_be_start": False,
    }
    base.update(extra)
    return base


@pytest.fixture
def catalog(monkeypatch):
    """Back every catalog reader with one fixed table.

    Search reads ``get_all_metadata`` and detail reads ``get_metadata``; feeding
    both from the same snapshot is what makes a parity assertion meaningful,
    since any disagreement then belongs to the catalog and not the fixture. The
    real registry is never mutated and no module is ever executed.
    """
    def _install(table):
        snapshot = dict(table)
        monkeypatch.setattr(
            ModuleRegistry,
            "get_all_metadata",
            classmethod(lambda cls, *a, **kw: dict(snapshot)),
        )
        monkeypatch.setattr(
            ModuleRegistry,
            "get_metadata",
            classmethod(lambda cls, module_id, *a, **kw: snapshot.get(module_id)),
        )
    return _install


def _by_id(results):
    return {r["module_id"]: r for r in results}


def _identity(entry):
    return entry["provides_capability"], entry["plugin"]


# -- the discovery this exists to enable -----------------------------------


def test_a_plugins_capability_and_owner_reach_both_entry_points(catalog):
    catalog({
        "vision.observe": _meta(
            "Observe Scene",
            provides_capability="vision.observe",
            plugin="vision",
        ),
    })

    hit = _by_id(search_modules("observe"))["vision.observe"]

    assert _identity(hit) == ("vision.observe", "vision")
    assert _identity(get_module_detail("vision.observe")) == ("vision.observe", "vision")


def test_read_only_registry_metadata_still_reports_both_fields(catalog):
    """A registry may hand out its metadata as a read-only view rather than a
    fresh ``dict``. The projection only reads keys, so a ``MappingProxyType``
    entry must reach both entry points with the same pair as a plain dict."""
    catalog({
        "vision.observe": MappingProxyType(_meta(
            "Observe Scene",
            provides_capability="vision.observe",
            plugin="vision",
        )),
    })

    hit = _by_id(search_modules("observe"))["vision.observe"]

    assert _identity(hit) == ("vision.observe", "vision")
    assert _identity(get_module_detail("vision.observe")) == ("vision.observe", "vision")


def test_two_providers_of_one_capability_are_both_reported(catalog):
    """Binding one of several providers is the host's call, and the catalog
    must not pre-empt it by dropping one. Note the owner is not the
    capability's prefix: neither field is derived from the other."""
    catalog({
        "vision.observe": _meta("Observe", provides_capability="scan.read", plugin="vision"),
        "thermal.observe": _meta("Observe", provides_capability="scan.read", plugin="thermal"),
    })

    found = _by_id(search_modules("observe"))

    assert _identity(found["vision.observe"]) == ("scan.read", "vision")
    assert _identity(found["thermal.observe"]) == ("scan.read", "thermal")
    # Still distinguishable one level down, where the call is actually built.
    assert _identity(get_module_detail("thermal.observe")) == ("scan.read", "thermal")


# -- the public bridge flyto-ai calls --------------------------------------


def test_the_mcp_bridge_passes_both_fields_through_unchanged(catalog):
    """``core.mcp_handler.search_modules`` is the boundary flyto-ai actually
    calls. It wraps the catalog in an envelope, and the envelope must not
    rewrite, drop, or re-key what the catalog put in each result — otherwise the
    fields exist and no caller can see them."""
    catalog({
        "vision.observe": _meta(
            "Observe Scene", "scan the scene",
            provides_capability="vision.observe", plugin="vision",
        ),
        "string.uppercase": _meta("Uppercase", "scan text", category="string"),
    })

    envelope = bridge_search_modules("scan")

    assert "error" not in envelope
    assert envelope["total"] == len(envelope["results"])
    bridged = _by_id(envelope["results"])
    # Byte-identical to the catalog's own answer, entry for entry.
    assert bridged == _by_id(search_modules("scan"))
    assert _identity(bridged["vision.observe"]) == ("vision.observe", "vision")
    # A Core module keeps the empty pair through the envelope too.
    assert _identity(bridged["string.uppercase"]) == ("", "")


# -- search and detail must not tell different stories ---------------------


def test_search_and_detail_agree_on_capability_and_owner(catalog):
    """Guards the split brain: a host searches, picks a module, fetches its
    detail to assemble a call, and is handed a different owner than the one it
    chose on."""
    catalog({
        "vision.observe": _meta(
            "Observe Scene", "scan the scene",
            provides_capability="vision.observe", plugin="vision",
        ),
        "string.uppercase": _meta("Uppercase", "scan text", category="string"),
    })

    for hit in search_modules("scan"):
        assert _identity(get_module_detail(hit["module_id"])) == _identity(hit)


def test_detail_is_unchanged_for_a_module_that_does_not_exist(catalog):
    catalog({})

    assert get_module_detail("nope.missing") is None


# -- modules that declare nothing, which is nearly all of them -------------


@pytest.mark.parametrize(
    "declared",
    [
        # Metadata written before the fields existed carries neither key.
        _ABSENT,
        None,
        "",
        "   ",
        "\n",
        "\t ",
        # ``ModuleRegistry.register`` takes a metadata dict as given, so a
        # legacy registration can leave a non-string behind. That is not a
        # capability name, and the catalog must say so instead of raising in
        # the middle of a search.
        123,
        ["vision.observe"],
        {"name": "vision"},
        True,
    ],
    ids=[
        "absent", "none", "empty", "spaces", "newline", "tab",
        "int", "list", "dict", "bool",
    ],
)
def test_a_missing_blank_or_non_string_declaration_reads_as_empty(catalog, declared):
    """Every one of these collapses to the empty string, the single spelling of
    "declares nothing", so no caller has to test for a missing key, ``None``,
    and a junk value separately."""
    extra = (
        {}
        if declared is _ABSENT
        else {"provides_capability": declared, "plugin": declared}
    )
    catalog({"string.uppercase": _meta("Uppercase", "Convert text", "string", **extra)})

    hit = _by_id(search_modules("uppercase"))["string.uppercase"]

    assert _identity(hit) == ("", "")
    assert _identity(get_module_detail("string.uppercase")) == ("", "")


def test_whitespace_is_stripped_at_the_edges_of_a_real_name_only(catalog):
    """The registry stores ``(value or "").strip()``. A padded name arriving
    unstripped would not compare equal to the same capability read anywhere
    else. Stripping stays at the edges: an interior space in a declared name is
    the module's business, not the catalog's."""
    catalog({
        "vision.observe": _meta(
            "Observe Scene",
            provides_capability="  vision observe\n",
            plugin="\t vision  ",
        ),
    })

    hit = _by_id(search_modules("observe"))["vision.observe"]

    assert _identity(hit) == ("vision observe", "vision")
    assert _identity(get_module_detail("vision.observe")) == ("vision observe", "vision")


def test_one_junk_field_does_not_blank_the_other(catalog):
    """The two fields are normalized independently. A legacy registration that
    left a non-string ``plugin`` behind must not cost the module its declared
    capability — that would silently hide a real capability from every caller,
    and search and detail must make the same call on each field separately."""
    catalog({
        "vision.observe": _meta(
            "Observe Scene",
            provides_capability="  vision.observe \n",
            plugin=123,
        ),
    })

    hit = _by_id(search_modules("observe"))["vision.observe"]

    assert _identity(hit) == ("vision.observe", "")
    assert _identity(get_module_detail("vision.observe")) == ("vision.observe", "")


def test_first_party_modules_have_no_plugin_owner(catalog):
    """Core's own modules belong to no plugin, and the empty owner is how the
    registry states that — a value no plugin can ever be assigned."""
    catalog({
        "http.get": _meta("HTTP Get", "Make an HTTP request", category="http", plugin=""),
    })

    assert _by_id(search_modules("http"))["http.get"]["plugin"] == ""
    assert get_module_detail("http.get")["plugin"] == ""


# -- the values are the registry's, not something reconstructed ------------


def test_identity_is_never_inferred_from_the_query_id_or_category(catalog):
    """``vision.observe`` in category ``vision``, retrieved by a query naming
    that very capability, is precisely the shape a hard-coded mapping or a
    query echo would guess right. The registry says this module declares
    nothing and ships with Core, and that is the reported answer."""
    catalog({
        "vision.observe": _meta("Observe Scene", "scan the scene", category="vision"),
    })

    hit = _by_id(search_modules("vision.observe"))["vision.observe"]

    assert _identity(hit) == ("", "")
    assert _identity(get_module_detail("vision.observe")) == ("", "")


# -- what must not change --------------------------------------------------


def test_scores_and_ordering_are_unchanged(catalog):
    catalog({
        "scan.read": _meta("Read Code", "Read a code", tags=["scan"]),
        "vision.observe": _meta(
            "Observe Scene", "Scan the scene",
            provides_capability="vision.observe", plugin="vision",
        ),
    })

    results = search_modules("scan")

    # An exact tag match (+4) still outranks a description match (+1).
    assert [r["module_id"] for r in results] == ["scan.read", "vision.observe"]
    assert results[0]["score"] == 4
    assert results[1]["score"] == 1


@pytest.mark.parametrize("field, query", [
    ("provides_capability", "thermography"),
    ("plugin", "acme-optics"),
])
def test_neither_field_is_a_search_signal(catalog, field, query):
    """Carrying the fields must not make them matchable. If it did, which
    modules match and in what order would change, and installing a package
    would quietly make every module it ships match its own name."""
    catalog({
        "vision.observe": _meta("Observe Scene", "Look at a scene", **{field: query}),
    })

    assert search_modules(query) == []


def test_the_limit_still_bounds_results(catalog):
    catalog({
        f"scan.read{i}": _meta(
            f"Read {i}", "scan input",
            provides_capability="scan.read", plugin="vision",
        )
        for i in range(10)
    })

    results = search_modules("scan", limit=3)

    assert len(results) == 3
    assert all(r["provides_capability"] == "scan.read" for r in results)


def test_the_category_filter_still_applies(catalog):
    catalog({
        "vision.observe": _meta(
            "Observe", "scan the scene", category="vision",
            provides_capability="vision.observe", plugin="vision",
        ),
        "string.scan": _meta("Scan Text", "scan a string", category="string"),
    })

    results = search_modules("scan", category="vision")

    assert [r["module_id"] for r in results] == ["vision.observe"]


def test_existing_search_keys_are_all_still_present(catalog):
    catalog({"string.uppercase": _meta("Uppercase", "Convert text", category="string")})

    hit = _by_id(search_modules("uppercase"))["string.uppercase"]

    assert {"module_id", "label", "description", "category", "can_be_start", "score"} <= set(hit)
    assert hit["label"] == "Uppercase"
    assert hit["category"] == "string"
    assert hit["can_be_start"] is False


def test_existing_detail_keys_are_all_still_present(catalog):
    """The two fields are additions to the detail payload, not a reshaping of
    it."""
    catalog({
        "string.uppercase": _meta(
            "Uppercase", "Convert text", category="string",
            params_schema={"text": {"type": "string"}},
            output_types=["string"],
        ),
    })

    detail = get_module_detail("string.uppercase")

    assert {
        "module_id", "label", "description", "category", "subcategory",
        "params_schema", "output_schema", "input_types", "output_types",
        "can_receive_from", "can_connect_to", "can_be_start",
        "start_requires_params", "node_type", "input_ports", "output_ports",
        "examples", "timeout", "retryable", "requires_credentials",
    } <= set(detail)
    assert detail["label"] == "Uppercase"
    assert detail["params_schema"] == {"text": {"type": "string"}}
    assert detail["output_types"] == ["string"]
