# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""The first-party inventory must be a property of the source, not of the machine.

`scripts/check_catalog_facts.py` counts the live `ModuleRegistry` and compares
the result to `core/catalog_facts.py`. Some module categories only register when
an optional dependency is importable (`huggingface` checks
`find_spec("transformers")` before importing anything), so a machine with the
`vector` extra installed — which pulls `transformers` in transitively — would
count 7 modules and a whole category that a default `pip install flyto-core`
does not expose.

That is a bad failure mode because it is invisible: the check passes on one
machine and fails on the next for reasons unrelated to the change under review.
So the guarantee is enforced here: the check is run in subprocesses, once with
the gating dependency visible and once with it hidden, and the two module lists
must be identical.

Installed plugins are the same failure by a second route. The registry is
deliberately open to any distribution declaring a `flyto.modules` entry point,
so the check is also run against a described plugin whose modules must not be
counted.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "check_catalog_facts.py"

# Written into a temporary PYTHONPATH entry to simulate a machine that does not
# have the gating dependency, without touching the real environment.
_HIDE_SHIM = '''\
import importlib.util

_real = importlib.util.find_spec
_HIDDEN = {names!r}


def find_spec(name, *args, **kwargs):
    if name.split(".")[0] in _HIDDEN:
        return None
    return _real(name, *args, **kwargs)


importlib.util.find_spec = find_spec
'''

# The module a described plugin registers. Its category belongs to no real one,
# so if it were ever counted it would move both the module and category totals
# — a leak cannot be mistaken for noise.
PLUGIN_MODULE_ID = "zzplugin.scan"
PLUGIN_NAME = "zzplugin"

# Installs one `flyto.modules` entry point without building a distribution.
#
# `sitecustomize` runs before anything imports the registry, so patching
# `importlib.metadata.entry_points` here reaches the name the registry binds at
# import time. That is what makes this a faithful stand-in for a real installed
# plugin rather than a monkeypatch of the checker's own internals.
_PLUGIN_SHIM = '''\
import importlib.metadata as _md

_real = _md.entry_points
_GROUP = "flyto.modules"


def _register_all():
    from core.modules.base import BaseModule
    from core.modules.registry import ModuleRegistry

    class _PluginModule(BaseModule):
        async def execute(self):
            return {{}}

    ModuleRegistry.register(
        {module_id!r},
        _PluginModule,
        {{"version": "9.9.9", "ui_description": "provided by an installed plugin"}},
    )


class _EntryPoint:
    name = {plugin!r}
    value = "zzplugin_pkg:register_all"
    group = _GROUP

    def load(self):
        return _register_all


class _Groups(dict):
    def get(self, group, default=None):
        if group == _GROUP:
            return list(dict.get(self, group, []))
        return dict.get(self, group, default)


def entry_points(**kwargs):
    group = kwargs.get("group")
    if group is not None:
        found = list(_real(**kwargs))
        return found + [_EntryPoint()] if group == _GROUP else found
    existing = _real()
    merged = _Groups()
    try:
        names = set(existing.groups)
    except AttributeError:
        names = set(existing)
    for name in names:
        merged[name] = list(
            existing.select(group=name)
            if hasattr(existing, "select")
            else existing[name]
        )
    merged.setdefault(_GROUP, [])
    merged[_GROUP] = list(merged[_GROUP]) + [_EntryPoint()]
    return merged


_md.entry_points = entry_points
'''


def _gating_dependencies() -> set[str]:
    """The optional distributions that gate a category, read from the checker."""
    # Kept in sync with scripts/check_catalog_facts.py rather than duplicated:
    # the category name maps to the distribution its __init__ checks for.
    source = CHECKER.read_text(encoding="utf-8")
    assert "_ENV_GATED_CATEGORIES" in source, (
        "check_catalog_facts.py no longer declares _ENV_GATED_CATEGORIES; the "
        "inventory may have become environment-dependent again."
    )
    return {"transformers"}


def _run_checker(extra_pythonpath: str | None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    if extra_pythonpath:
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            f"{extra_pythonpath}{os.pathsep}{existing}" if existing else extra_pythonpath
        )
    return subprocess.run(
        [sys.executable, str(CHECKER), "--list"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def _inventory(result: subprocess.CompletedProcess) -> list[str]:
    """Every counted module id followed by the checker's own totals line."""
    assert result.stdout, f"checker printed nothing: {result.stderr!r}"
    return result.stdout.splitlines()


@pytest.fixture
def hidden_dependency_path(tmp_path) -> str:
    shim_dir = tmp_path / "no_optional_deps"
    shim_dir.mkdir()
    (shim_dir / "sitecustomize.py").write_text(
        _HIDE_SHIM.format(names=_gating_dependencies()), encoding="utf-8"
    )
    return str(shim_dir)


@pytest.fixture
def installed_plugin_path(tmp_path) -> str:
    shim_dir = tmp_path / "with_plugin"
    shim_dir.mkdir()
    (shim_dir / "sitecustomize.py").write_text(
        _PLUGIN_SHIM.format(module_id=PLUGIN_MODULE_ID, plugin=PLUGIN_NAME),
        encoding="utf-8",
    )
    return str(shim_dir)


def test_the_plugin_shim_really_registers_a_module(installed_plugin_path):
    """Guard for the two tests below.

    They assert that a plugin's module is absent from the catalog, which is also
    what they would report if the shim quietly stopped installing an entry point
    — a test that passes for the wrong reason and covers nothing. This one fails
    instead, and says so."""
    probe = (
        "import sys; sys.path.insert(0, 'src')\n"
        "from core.modules.registry import ModuleRegistry\n"
        "ModuleRegistry.discover_plugins()\n"
        f"assert {PLUGIN_MODULE_ID!r} in ModuleRegistry.list_all(), 'shim registered nothing'\n"
        f"assert {PLUGIN_NAME!r} in ModuleRegistry.get_plugins(), 'shim was not discovered'\n"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        p for p in (installed_plugin_path, env.get("PYTHONPATH", "")) if p
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], cwd=ROOT, env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, (
        "The described plugin no longer reaches the registry, so the catalog "
        f"exclusion tests prove nothing.\n{result.stdout}{result.stderr}"
    )


def test_check_passes_with_an_installed_plugin(installed_plugin_path):
    """The check that made the host and the container disagree.

    A machine with any `flyto.modules` distribution installed must count the
    same inventory as a clean one; otherwise the check reports a change nobody
    made and the fix is to uninstall a package."""
    result = _run_checker(installed_plugin_path)
    assert result.returncode == 0, (
        "The first-party inventory depends on which plugin packages are "
        "installed. Plugin-owned modules must be excluded.\n"
        + result.stdout[-1500:]
        + result.stderr
    )


def test_inventory_is_unchanged_by_an_installed_plugin(installed_plugin_path):
    """Compare the full module list, so a leak names the module."""
    clean = _inventory(_run_checker(None))
    with_plugin = _inventory(_run_checker(installed_plugin_path))

    assert PLUGIN_MODULE_ID not in with_plugin
    assert clean == with_plugin, (
        "The inventory differs depending on which plugin packages are installed: "
        f"{sorted(set(clean) ^ set(with_plugin))}"
    )


def test_check_passes_in_this_environment():
    """Baseline: core/catalog_facts.py matches what this machine registers."""
    result = _run_checker(None)
    assert result.returncode == 0, (
        "core/catalog_facts.py is stale. Update it to the totals reported by "
        f"`python scripts/check_catalog_facts.py`.\n{result.stdout[-500:]}{result.stderr}"
    )


def test_check_passes_without_the_optional_dependency(hidden_dependency_path):
    """The same facts must hold on a machine without the extras.

    If this fails while the test above passes, the facts were counted on a
    machine with an optional extra installed and advertise modules the released
    package does not expose.
    """
    result = _run_checker(hidden_dependency_path)
    assert result.returncode == 0, (
        "core/catalog_facts.py is only valid on a machine that has the optional "
        "dependency installed. Environment-gated categories must be excluded.\n"
        + result.stdout[-500:]
        + result.stderr
    )


def test_inventory_agrees_across_environments(hidden_dependency_path):
    """Both runs must count exactly the same modules."""
    with_dep = _inventory(_run_checker(None))
    without_dep = _inventory(_run_checker(hidden_dependency_path))

    assert with_dep == without_dep, (
        "The inventory differs depending on which optional dependencies are "
        f"installed: {sorted(set(with_dep) ^ set(without_dep))}"
    )


def _load_checker():
    """`scripts/` is not a package, so import the checker by path."""
    import importlib.util as _iu

    spec = _iu.spec_from_file_location("_check_catalog_facts_under_test", CHECKER)
    module = _iu.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_is_plugin_owned():
    return _load_checker()._is_plugin_owned


def test_only_an_exactly_empty_owner_counts_as_first_party():
    """The one row shape the inventory may count as flyto-core's own.

    "Exactly" governs the row's type as well as its owner. `isinstance(meta,
    dict)` admitted every subclass, and a subclass decides what `.get` returns —
    so the single call this boundary makes to establish provenance was answered
    by the object whose provenance was the question. A row overriding `get` to
    reply `""` was published under Core's name while storing a plugin's, and an
    ordinary subclass got in on the strength of its base class alone. Both are
    refused before `.get` is reached, which is the only order that helps: asking
    first and validating afterwards has already taken the row's word for it.

    Built with `type()` so the hostile row is data this test installs rather
    than a shape the module declares.
    """
    is_plugin_owned = _load_is_plugin_owned()
    assert is_plugin_owned({"plugin": ""}) is False

    lying_row = type(
        "_LyingRow",
        (dict,),
        {"get": lambda self, key, default=None: "" if key == "plugin" else default},
    )
    smuggled = lying_row({"plugin": "flyto-pro"})
    # The lie is well-formed: it is a dict by every test but the exact one.
    assert isinstance(smuggled, dict)
    assert smuggled.get("plugin") == ""
    assert smuggled["plugin"] == "flyto-pro"
    assert is_plugin_owned(smuggled) is True

    # And an ordinary subclass is refused too. The rule is "the registry's own
    # exact dict", not "anything that has not been caught lying yet" — the
    # inventory cannot tell the two apart without asking the row.
    plain_subclass = type("_SubclassRow", (dict,), {})
    assert is_plugin_owned(plain_subclass({"plugin": ""})) is True


@pytest.mark.parametrize(
    "meta",
    [
        pytest.param({"plugin": "flyto-pro"}, id="named-plugin"),
        pytest.param({"plugin": None}, id="none"),
        pytest.param({"plugin": 0}, id="falsy-non-string"),
        pytest.param({"plugin": []}, id="falsy-sequence"),
        pytest.param({}, id="no-owner-key"),
        pytest.param(None, id="no-row"),
        pytest.param({"plugin": b""}, id="empty-bytes-not-empty-str"),
        pytest.param({"plugin": type("_LyingOwner", (str,), {"__eq__": lambda self, other: True})("flyto-pro")}, id="lying-str-subclass-owner"),
    ],
)
def test_a_non_empty_owner_is_never_published_as_first_party(meta):
    """Fails closed on every owner that is not exactly `""`.

    `bool(meta.get("plugin", ""))` passed four of these through as flyto-core's
    own: `None`, the falsy non-strings, and the absent key defaulting to `""`.
    `register` stamps an explicit owner on every row it stores, so none of these
    shapes describes a first-party module. Nor does a `str` subclass whose
    `__eq__` answers every comparison `True`: equality is the owner's own to
    define, so its exact type is settled before its value is ever compared.
    """
    assert _load_is_plugin_owned()(meta) is True


@pytest.mark.parametrize(
    "meta",
    [
        pytest.param("", id="empty-string-row"),
        pytest.param("flyto-pro", id="string-row"),
        pytest.param([], id="empty-list-row"),
        pytest.param([("plugin", "")], id="pair-list-row"),
        pytest.param(0, id="int-row"),
        pytest.param(object(), id="opaque-row"),
    ],
)
def test_a_row_that_is_not_a_mapping_is_plugin_owned(meta):
    """A malformed row must classify, not explode.

    `(meta or {}).get("plugin")` assumed every row was either a dict or falsy.
    Anything else — a string, a list, an arbitrary object — has no `.get`, so
    the ownership test raised `AttributeError` and took the whole check with
    it: one bad row and `python scripts/check_catalog_facts.py` produces a
    traceback instead of an inventory, and CI fails for a reason that names no
    module.

    Note that `""` and `[]` are the sharper cases. They are falsy, so the old
    expression turned them into `{}` and read the *absent* key — the same path a
    genuinely empty metadata dict takes. It happened to answer "plugin-owned"
    there, but by accident of the default rather than by deciding anything about
    the row it was actually given. Classifying on the row's shape makes both the
    crash and the coincidence into one deliberate answer: provenance that cannot
    be established is not flyto-core's.
    """
    assert _load_is_plugin_owned()(meta) is True


def test_the_inventory_survives_a_malformed_row(monkeypatch):
    """Classifying correctly is only half of it — the order has to hold too.

    The ownership test has to be the thing that excludes a malformed row, and it
    has to run before anything else reads the row. Driving the real inventory
    over a described set of rows proves both at once — the malformed row is
    skipped, the plugin rows are skipped, and the one first-party row is still
    counted.
    """
    from core.modules.registry import ModuleRegistry

    checker = _load_checker()
    rows = {
        "http.get": {"plugin": "", "ui_description": "a first-party row"},
        "broken.row": "this row is not a mapping at all",
        "unowned.row": {"ui_description": "stored without an owner stamp"},
        # A row that passes `isinstance(meta, dict)` and answers the ownership
        # probe with `""` while storing a plugin's name. If the exclusion took
        # its word, a plugin's module would be counted as Core's — the exact
        # failure the boundary exists to prevent, arriving in the one shape
        # `isinstance` waves through.
        "lying.row": type(
            "_LyingRow",
            (dict,),
            {"get": lambda self, key, default=None: "" if key == "plugin" else default},
        )({"plugin": PLUGIN_NAME, "ui_description": "claims to be first-party"}),
        PLUGIN_MODULE_ID: {"plugin": PLUGIN_NAME, "ui_description": "from a plugin"},
    }
    monkeypatch.setattr(
        ModuleRegistry, "discover_plugins", classmethod(lambda cls, **kw: {})
    )
    monkeypatch.setattr(
        ModuleRegistry, "get_all_metadata", classmethod(lambda cls, **kw: rows)
    )

    assert checker.first_party_catalog() == {"http": ["http.get"]}
