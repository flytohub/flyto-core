# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""The generated catalog must be a property of the source, not of the machine.

`docs/TOOL_CATALOG.md` is generated from the live `ModuleRegistry`, and some
module categories only register when an optional dependency is importable
(`huggingface` checks `find_spec("transformers")` before importing anything).
That made the output depend on which extras the developer happened to have:
running the generator on a machine with the `vector` extra installed — which
pulls `transformers` in transitively — silently rewrote the catalog to advertise
7 modules and a whole category that a default `pip install flyto-core` does not
expose, and every cross-referencing count in README/STATE/ARCHITECTURE with it.

That is a bad failure mode because it is invisible: the generator succeeds, the
diff looks intentional, and the next person to regenerate on a clean machine
reverts it. So the guarantee is enforced here rather than documented and hoped
for: the generator is run twice in subprocesses, once with the gating dependency
visible and once with it hidden, and the two outputs must be byte-identical.

Installed plugins are the same failure by a second route. The catalog is built
from the live `ModuleRegistry`, which is deliberately open to any distribution
declaring a `flyto.modules` entry point — so a checkout with a module pack
installed generated a catalog carrying that pack's modules. `--check` then
passed inside the clean release container and failed on the developer's host,
for reasons that had nothing to do with the change under review. The same
technique covers it: the generator is run against a described plugin whose
modules must not reach the file.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GENERATOR = ROOT / "scripts" / "generate_catalog.py"
CATALOG = ROOT / "docs" / "TOOL_CATALOG.md"

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

# The module a described plugin registers. Its category sorts last and belongs
# to no real one, so if it ever reached the file it would move the module count,
# the category count, the table of contents and a whole section — a leak cannot
# be mistaken for noise.
PLUGIN_MODULE_ID = "zzplugin.scan"
PLUGIN_NAME = "zzplugin"

# Installs one `flyto.modules` entry point without building a distribution.
#
# `sitecustomize` runs before anything imports the registry, so patching
# `importlib.metadata.entry_points` here reaches the name the registry binds at
# import time. That is what makes this a faithful stand-in for a real installed
# plugin rather than a monkeypatch of the generator's own internals.
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
    """The optional distributions that gate a category, read from the generator."""
    # Kept in sync with scripts/generate_catalog.py rather than duplicated: the
    # category name maps to the distribution its __init__ checks for.
    source = GENERATOR.read_text(encoding="utf-8")
    assert "_ENV_GATED_CATEGORIES" in source, (
        "generate_catalog.py no longer declares _ENV_GATED_CATEGORIES; the "
        "catalog may have become environment-dependent again."
    )
    return {"transformers"}


def _run_generator(extra_pythonpath: str | None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    if extra_pythonpath:
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            f"{extra_pythonpath}{os.pathsep}{existing}" if existing else extra_pythonpath
        )
    return subprocess.run(
        [sys.executable, str(GENERATOR), "--check"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def _counts(result: subprocess.CompletedProcess) -> str:
    """The generator's own reported totals, so a mismatch names the numbers."""
    for line in result.stdout.splitlines():
        if "modules across" in line:
            return line.strip()
    return f"<no count line: {result.stdout!r} {result.stderr!r}>"


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


def test_committed_catalog_ignores_an_installed_plugin(installed_plugin_path):
    """The check that made the host and the container disagree.

    A machine with any `flyto.modules` distribution installed must generate the
    same catalog as a clean one; otherwise `--check` reports a change nobody
    made and the fix is to uninstall a package."""
    result = _run_generator(installed_plugin_path)
    assert result.returncode == 0, (
        "docs/TOOL_CATALOG.md depends on which plugin packages are installed. "
        "The generator must exclude plugin-owned modules so the catalog stays a "
        "property of this source tree.\n" + result.stdout + result.stderr
    )


def test_catalog_counts_are_unchanged_by_an_installed_plugin(installed_plugin_path):
    """Compare the reported totals, so a mismatch names the numbers."""
    clean = _run_generator(None)
    with_plugin = _run_generator(installed_plugin_path)

    assert _counts(clean) == _counts(with_plugin), (
        "The catalog generator reports different totals depending on which "
        "plugin packages are installed:\n"
        f"  without plugin: {_counts(clean)}\n"
        f"  with plugin:    {_counts(with_plugin)}"
    )


def test_committed_catalog_lists_no_plugin_module():
    """The counts could agree while a plugin module still appeared somewhere.

    Read the committed file. Together with the check above — which proves a
    with-plugin render equals this file byte for byte — that closes it."""
    catalog = CATALOG.read_text(encoding="utf-8")
    assert PLUGIN_MODULE_ID not in catalog
    assert f"## {PLUGIN_NAME}" not in catalog
    assert "plugin packages are excluded" in catalog, (
        "The catalog no longer says its counts exclude installed plugins, so a "
        "reader cannot tell whether the number is core-only."
    )


def test_the_catalog_documents_how_ownership_is_decided():
    """The rule itself has to be readable, not only its consequence.

    "Plugin modules are excluded" does not tell a reader what happens to a row
    whose owner is `null`, or missing, or not a mapping at all — and those are
    exactly the shapes the exclusion fails closed on. Someone auditing whether a
    module belongs to Core must be able to learn the rule from the file rather
    than from the generator's source."""
    catalog = CATALOG.read_text(encoding="utf-8")
    assert "exactly the empty string" in catalog, (
        "The catalog no longer states that first-party means an owner of "
        "exactly `\"\"`, so a reader cannot tell how a malformed or unowned row "
        "was classified."
    )
    assert "not a metadata mapping" in catalog, (
        "The catalog no longer says a row that is not a mapping counts as "
        "plugin-owned, which is the conservative half of the rule."
    )


def test_committed_catalog_is_current_in_this_environment():
    """Baseline: the catalog matches what this machine generates."""
    result = _run_generator(None)
    assert result.returncode == 0, (
        "docs/TOOL_CATALOG.md is stale. Run "
        f"`python scripts/generate_catalog.py`.\n{result.stdout}{result.stderr}"
    )


def test_committed_catalog_is_current_without_the_optional_dependency(
    hidden_dependency_path,
):
    """The same catalog must be correct on a machine without the extras.

    This is the check that matters. If it fails while the test above passes,
    the committed catalog was generated on a machine with an optional extra
    installed and advertises modules the released package does not expose.
    """
    result = _run_generator(hidden_dependency_path)
    assert result.returncode == 0, (
        "docs/TOOL_CATALOG.md is only valid on a machine that has the optional "
        "dependency installed. Regenerate it — the generator must exclude "
        "environment-gated categories.\n" + result.stdout + result.stderr
    )


def test_catalog_counts_agree_across_environments(hidden_dependency_path):
    """Both runs must report the same module and category totals.

    Compares the generator's own reported counts rather than only its exit
    status, so a mismatch names the numbers instead of just failing."""
    with_dep = _run_generator(None)
    without_dep = _run_generator(hidden_dependency_path)

    assert _counts(with_dep) == _counts(without_dep), (
        "The catalog generator reports different totals depending on which "
        f"optional dependencies are installed:\n"
        f"  with:    {_counts(with_dep)}\n"
        f"  without: {_counts(without_dep)}"
    )


def test_catalog_documents_the_exclusion():
    """A reader must be able to tell the counts exclude optional categories,
    otherwise the number looks like the whole story."""
    catalog = CATALOG.read_text(encoding="utf-8")
    assert "default `pip install flyto-core`" in catalog
    assert "huggingface" in catalog, (
        "The catalog no longer names the excluded optional category, so its "
        "module count silently under-reports what the package can offer."
    )


def _load_generator():
    """`scripts/` is not a package, so import the generator by path."""
    import importlib.util as _iu

    spec = _iu.spec_from_file_location("_generate_catalog_under_test", GENERATOR)
    module = _iu.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_is_plugin_owned():
    return _load_generator()._is_plugin_owned


def test_only_an_exactly_empty_owner_counts_as_first_party():
    """The one row shape the catalog may publish as flyto-core's own.

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
    # catalog cannot tell the two apart without asking the row.
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
    the ownership test raised `AttributeError` and took the whole generator with
    it: one bad row and `python scripts/generate_catalog.py` produces a
    traceback instead of a catalog, and `--check` fails in CI for a reason that
    names no module.

    Note that `""` and `[]` are the sharper cases. They are falsy, so the old
    expression turned them into `{}` and read the *absent* key — the same path a
    genuinely empty metadata dict takes. It happened to answer "plugin-owned"
    there, but by accident of the default rather than by deciding anything about
    the row it was actually given. Classifying on the row's shape makes both the
    crash and the coincidence into one deliberate answer: provenance that cannot
    be established is not flyto-core's.
    """
    assert _load_is_plugin_owned()(meta) is True


def test_the_generator_renders_past_a_malformed_row(monkeypatch):
    """Classifying correctly is only half of it — the order has to hold too.

    `render_catalog` reads `ui_description`, `params_schema` and `output_schema`
    off each row. If a row that is not a mapping reached any of those, the run
    would still die on `.get`; the ownership test has to be the thing that
    excludes it, and it has to run first. Driving the real renderer over a
    described set of rows proves both at once — the malformed row is skipped,
    the plugin row is skipped, and the one first-party row is still published
    with its counts intact.
    """
    from core.modules.registry import ModuleRegistry

    generator = _load_generator()
    rows = {
        "http.get": {
            "plugin": "",
            "ui_description": "a first-party row",
            "params_schema": {"url": {"type": "string", "required": True}},
            "output_schema": {"body": {"type": "string"}},
        },
        "broken.row": "this row is not a mapping at all",
        "unowned.row": {"ui_description": "stored without an owner stamp"},
        # A row that passes `isinstance(meta, dict)` and answers the ownership
        # probe with `""` while storing a plugin's name. Everything the renderer
        # reads off it afterwards comes from the same overridden `get`, so if
        # the exclusion took its word the catalog would publish a plugin's
        # module under Core's name — the exact failure the boundary exists to
        # prevent, arriving in the one shape `isinstance` waves through.
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

    content, total, cat_count = generator.render_catalog()

    assert (total, cat_count) == (1, 1)
    assert "`http.get`" in content
    assert "broken.row" not in content
    assert "unowned.row" not in content
    assert "lying.row" not in content
    assert "claims to be first-party" not in content
    assert PLUGIN_MODULE_ID not in content
