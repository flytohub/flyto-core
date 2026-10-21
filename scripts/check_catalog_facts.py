#!/usr/bin/env python3
"""
Check core/catalog_facts.py against the first-party module registry.

``catalog_facts`` is hand-maintained and is what the MCP handler, quickstart and
the API server tell a user the catalog contains. This counts the modules a
default ``pip install flyto-core`` registers and fails when the constants
disagree.

Usage:
    python scripts/check_catalog_facts.py          # check counts
    python scripts/check_catalog_facts.py --list   # also print every module id
"""

import argparse
import os
import sys
from pathlib import Path

# Setup path
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root / "src"))

os.environ["FLYTO_VALIDATION_MODE"] = "dev"


# Categories whose *registration* is gated on an optional dependency being
# importable, so whether they appear depends on which extras the machine
# running this script happens to have installed.
#
# `core.modules.atomic._OPTIONAL_CATEGORIES` lists categories imported inside a
# try/except, but most of those still register unconditionally because their
# third-party imports are lazy (ssh defers asyncssh into the call). Only these
# gate registration itself — huggingface/__init__.py checks
# `find_spec("transformers")` before importing any module.
#
# They are excluded so the inventory is a property of the source tree rather
# than of the developer's virtualenv. Without this, a machine with the `vector`
# extra installed (which pulls transformers in transitively) counts 7 modules
# and a category that a default `pip install flyto-core` does not expose.
#
# tests/core/test_catalog_determinism.py enforces that the inventory is
# identical with and without the gating dependency present.
_ENV_GATED_CATEGORIES = {"huggingface"}


def _is_plugin_owned(meta: object) -> bool:
    """Whether a registry row arrived from an installed plugin package.

    ``ModuleRegistry.register`` stamps every row with the entry point that was
    loading when it was registered, and with ``""`` for flyto-core's own. The
    owner is assigned rather than accepted, so this is the registry's answer
    about how a module arrived, not the module's claim about itself.

    The facts describe flyto-core, so a plugin's modules are not part of them.
    That is the second way the inventory used to depend on the machine: a
    checkout with any ``flyto.modules`` distribution installed — a pro module
    pack, a locally `pip install -e`'d plugin — counted that plugin's modules,
    so the check passed inside the release container and failed on the
    developer's host for reasons that had nothing to do with the change under
    review. Excluded here rather than by name, because the set of
    installed plugins is exactly the thing that is not knowable from the source.

    Fails closed: first-party means the owner is exactly ``""``, and every other
    value is treated as plugin-owned and excluded. A truthiness test let three
    non-first-party rows through as flyto-core's own — ``None``, a falsy
    non-string, and a row carrying no ``plugin`` key at all. ``register`` stamps
    an explicit owner on every row it stores, so a stored row missing the key is
    not a first-party module; it is a row that reached ``_metadata`` by some
    route that did not stamp it, and the catalog is the wrong place to guess.
    Being wrong in this direction drops a module from the count, which is
    visible; being wrong in the other publishes a plugin's module as Core's.

    A row that is not an exact ``dict`` is plugin-owned by the same rule, and
    that case is the reason this takes ``object``. A subclass decides what
    ``.get`` returns, so a row overriding it answers the very question asked
    about it. And ``(meta or {}).get`` raised ``AttributeError`` on anything —
    a string, a list, a dataclass — so a single malformed row aborted the whole
    check with a traceback instead of producing an inventory. Worse, the crash
    is the *safe* half of the behaviour: `--check` failing loudly is survivable,
    but it happens at the exact boundary that decides whose module this is, and
    the answer to "I cannot read this row's owner" must be the conservative one.
    A row whose provenance cannot be established is not flyto-core's.
    """
    if type(meta) is not dict:
        return True
    owner = meta.get("plugin")
    # Exactly the built-in empty string. `isinstance` admitted `str` subclasses,
    # and a subclass defines `==`, so the type is settled before the value is asked.
    return not (type(owner) is str and owner == "")


def first_party_catalog() -> dict[str, list[str]]:
    """Module ids a default install registers, grouped by category.

    The category is the module id's first segment, so ``file.read`` and
    ``file.copy`` share ``file``.
    """
    from core.modules.registry import ModuleRegistry

    registry = ModuleRegistry()
    registry.discover_plugins()

    all_metadata = registry.get_all_metadata(lang="en", filter_by_stability=False)

    categories: dict[str, list[str]] = {}
    for module_id, meta in sorted(all_metadata.items()):
        category = module_id.split(".")[0]
        # Skip categories whose registration depends on an optional dependency
        # being installed locally — see _ENV_GATED_CATEGORIES.
        if category in _ENV_GATED_CATEGORIES:
            continue
        # Skip modules an installed plugin contributed — see _is_plugin_owned.
        # This runs before anything else reads the row, so a malformed row is
        # classified rather than crashing the check.
        if _is_plugin_owned(meta):
            continue
        categories.setdefault(category, []).append(module_id)
    return categories


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="print every counted module id")
    args = parser.parse_args()

    from core import catalog_facts

    categories = first_party_catalog()
    total = sum(len(modules) for modules in categories.values())
    category_count = len(categories)
    if args.list:
        for modules in categories.values():
            for module_id in modules:
                print(module_id)
    print(f"{total} modules across {category_count} categories")

    expected = (catalog_facts.CORE_MODULE_COUNT, catalog_facts.CORE_CATALOG_CATEGORY_COUNT)
    if (total, category_count) != expected:
        print(
            "core/catalog_facts.py is stale: it states "
            f"{expected[0]} modules across {expected[1]} categories",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
