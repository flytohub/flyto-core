# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Registry-wide coverage for the gap between a declared module and a live one.

``@register_module`` only runs when something imports the file it decorates.
Nothing checked that anything did, so a module could be fully written, listed in
the generated module reference, advertised on the landing page and translated
into every locale while ``execute_module`` answered "Module not found" for it.
Sixteen modules were in that state; eight were reachable only by a host
application that imported the subpackage itself.

That gap is not merely cosmetic. Reviewing the `integration.*` family's security
posture from the generated reference — which is how GHSA-4346-4gqg-59f9 assessed
reachability — gives an answer the shipped package does not support, in either
direction: a family can look reachable while being dead, and a dead family can
come alive the moment an unrelated import is added, with no review of the sinks
inside it.

So a declared module must be one of three things, and saying which is an
explicit act:

* live in the registry;
* gated on an optional dependency, where the guard is verified to still exist;
* deliberately not shipped, with a reason — and the entry becomes an error the
  moment the module goes live, so "not shipped" cannot quietly become "shipped".
"""

import ast
import importlib.util
import re
from pathlib import Path

import pytest

import core.modules  # noqa: F401 — imports the catalog as the package ships it
from core import catalog_facts
from core.modules.registry.core import ModuleRegistry

SRC = Path(__file__).resolve().parents[2] / "src"


# Declared modules that register only when an optional package is installed.
# Each entry names that package and the file whose import guard must still be
# there; if the guard disappears the module is not optional any more, it is dead.
_TRANSFORMERS_GATE = (
    "transformers",
    "src/core/modules/atomic/huggingface/__init__.py",
    "the huggingface category registers only when transformers is installed; it "
    "is in _OPTIONAL_CATEGORIES and its package guard checks for the package "
    "before importing any task module",
)

OPTIONAL_DEPENDENCY = dict.fromkeys(
    (
        "huggingface.embedding",
        "huggingface.image-classification",
        "huggingface.speech-to-text",
        "huggingface.summarization",
        "huggingface.text-classification",
        "huggingface.text-generation",
        "huggingface.translation",
    ),
    _TRANSFORMERS_GATE,
)

# Declared modules that are deliberately not part of the shipped catalog. An
# entry here is only valid while the module really is absent from the registry:
# the moment someone imports it, `test_not_shipped_entries_are_still_dead` fails
# and the decision has to be made in the open.
NOT_SHIPPED = {
    "ai.tool_template": (
        "a sub-node that wraps a template as an agent tool, complete in source but "
        "never localized — no locale defines modules.ai.tool_template.label, so "
        "registering it would put a raw translation key in the node palette. "
        "Shipping it is an i18n decision, not an import one"
    ),
}


def _declared_modules() -> dict:
    """Every ``module_id`` a ``@register_module`` decorator names in the source."""
    declared = {}
    for path in sorted(SRC.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue  # not.py and friends: unparseable as a module name, still valid Python
        for node in ast.walk(tree):
            for decorator in getattr(node, "decorator_list", []):
                if not isinstance(decorator, ast.Call):
                    continue
                func = decorator.func
                name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
                if name != "register_module":
                    continue
                for keyword in decorator.keywords:
                    if keyword.arg == "module_id" and isinstance(keyword.value, ast.Constant):
                        declared[keyword.value.value] = path
    return declared


DECLARED = _declared_modules()
LIVE = set(ModuleRegistry.get_all_metadata(filter_by_stability=False))


def _dependency_installed(package: str) -> bool:
    return importlib.util.find_spec(package) is not None


def test_source_scan_found_the_catalog():
    """Guard against the sweep passing vacuously if the AST walk breaks."""
    assert len(DECLARED) > 400
    assert len(LIVE) > 400


def test_every_declared_module_is_live_or_explained():
    """A module that exists in the source must be reachable, or say why not."""
    dead = []

    for module_id in sorted(set(DECLARED) - LIVE):
        if module_id in NOT_SHIPPED:
            continue
        if module_id in OPTIONAL_DEPENDENCY:
            package = OPTIONAL_DEPENDENCY[module_id][0]
            if not _dependency_installed(package):
                continue
            dead.append(f"{module_id} (excused as needing {package}, which IS installed)")
            continue
        dead.append(f"{module_id}  <-  {DECLARED[module_id].relative_to(SRC.parent)}")

    assert not dead, (
        "These modules are declared with @register_module but never reach the "
        "registry, so execute_module answers 'Module not found' for them while "
        "the generated reference lists them:\n  "
        + "\n  ".join(dead)
        + "\n\nImport the module from its package __init__, or record it in "
          "NOT_SHIPPED / OPTIONAL_DEPENDENCY with a reason."
    )


@pytest.mark.parametrize("module_id", sorted(NOT_SHIPPED))
def test_not_shipped_entries_are_still_dead(module_id):
    """'Not shipped' stops being true the moment something imports it."""
    assert module_id not in LIVE, (
        f"{module_id} is recorded in NOT_SHIPPED but is now registered. If "
        f"shipping it is intended, drop the entry — and check the reason it "
        f"carried: {NOT_SHIPPED[module_id]}"
    )


@pytest.mark.parametrize("module_id", sorted(OPTIONAL_DEPENDENCY))
def test_optional_dependency_entries_still_have_their_guard(module_id):
    """An 'optional dependency' excuse is void without the guard that makes it so."""
    package, guard_file, _reason = OPTIONAL_DEPENDENCY[module_id]
    source = (SRC.parent / guard_file).read_text(encoding="utf-8")

    assert f'find_spec("{package}")' in source or f"find_spec('{package}')" in source, (
        f"{module_id} is excused as gated on {package}, but "
        f"{guard_file} no longer checks for it. Without that guard the module is "
        f"not optional, it is dead."
    )


@pytest.mark.parametrize("module_id", sorted({**OPTIONAL_DEPENDENCY, **NOT_SHIPPED}))
def test_entries_name_a_module_that_still_exists(module_id):
    """Keep the lists honest as modules are renamed or removed."""
    assert module_id in DECLARED, (
        f"{module_id} is on an allowlist here but no @register_module in the "
        f"source declares it any more. Remove the entry."
    )


def test_entries_state_a_reason():
    """A bare exemption is not reviewable; require a real sentence."""
    thin = [m for m, reason in NOT_SHIPPED.items() if len(reason.strip()) < 40]
    thin += [m for m, (_p, _f, reason) in OPTIONAL_DEPENDENCY.items() if len(reason.strip()) < 40]
    assert not thin, f"These entries need a substantive reason: {sorted(set(thin))}"


# ---------------------------------------------------------------------------
# The numbers the package says out loud
# ---------------------------------------------------------------------------
#
# core/catalog_facts.py is hand-maintained and is read by mcp_handler,
# quickstart and the API server, so it is what the product tells a user the
# catalog contains. Nothing checked it against the catalog. It said 468 while
# the registry held 476, which is the same class of drift as a module that is
# documented and unreachable — a claim with nothing behind it.
#
# The catalog itself is verified fresh against the registry by
# `scripts/generate_catalog.py --check` in CI, so comparing the constants to the
# generated header chains onto that rather than duplicating its grouping rules.

CATALOG = (Path(__file__).resolve().parents[2] / "docs" / "TOOL_CATALOG.md").read_text(
    encoding="utf-8"
)


def test_catalog_facts_match_the_generated_catalog():
    header = re.search(r"\*\*(\d+) modules\*\* across \*\*(\d+) categories\*\*", CATALOG)
    assert header, "TOOL_CATALOG.md no longer states its module/category totals"

    assert int(header.group(1)) == catalog_facts.CORE_MODULE_COUNT
    assert int(header.group(2)) == catalog_facts.CORE_CATALOG_CATEGORY_COUNT


def test_browser_module_count_matches_the_registry():
    live_browser = {module_id for module_id in LIVE if module_id.startswith("browser.")}
    assert len(live_browser) == catalog_facts.BROWSER_MODULE_COUNT


def test_built_in_recipe_count_matches_the_packaged_recipes():
    recipes = list((SRC / "recipes").glob("*.yaml"))
    assert len(recipes) == catalog_facts.BUILT_IN_RECIPE_COUNT
