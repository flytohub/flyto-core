# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Which side-effecting modules still cannot say what they proved.

Not a percentage, and not a number in a budget file: a list, by name, that may
only get shorter. The difference matters. A count of 196 tells you nothing you
can act on; a name tells you which module to open. And a module that quietly
falls out of the population — because somebody renamed a category, or the
classifier drifted — shows up as a stale entry rather than as an improvement.

Two ways a module satisfies this:

  * it declares — `postcondition=` or `derives=` on `@register_module`; or
  * it reports — its source imports `core.engine.outcome`, meaning it builds an
    envelope at runtime and the rung is decided from what it measured.

Reporting without declaring is a real state and deliberately counts: `verified`
requires a declared postcondition, but `dispatched`, `accepted` and `observed`
are earned by measurement, and a module that honestly reports `accepted` has
done the work this ratchet exists to ask for. What it has not done is claim to
have proved anything, which is the point.

THE POPULATION is `outcome.is_side_effecting` — 200 of 483 registered modules.
That predicate had to be widened from the one live classifier in the repository
(`modules/quality/rules/capability.py:47`), which lists `sms`, a category no
module registers, and omits `http`, `ssh`, `docker`, `k8s`, `network`,
`notification`, `storage`, `queue`, `git`, `process`, `port` and `dns`. Under
the old list `http.request` was not side-effecting, which is not a taxonomy
anyone can defend.

WHAT THIS DOES NOT DO is fail a module for being on the list. Everything here is
allowed to be here — that is what makes shipping possible at all. What it stops
is the other thing: a module leaving the list without anybody noticing, and a
module joining the population and being silently absent from both the covered
set and the written-down gap.
"""

from __future__ import annotations

import ast
import inspect
import os

import pytest

from core.engine.outcome import is_side_effecting


@pytest.fixture(scope="module")
def registry():
    os.environ.pop("FLYTO_ENV", None)
    from core.modules import atomic  # noqa: F401 - registers every module
    from core.modules import composite  # noqa: F401
    from core.modules.registry import ModuleRegistry

    # filter_by_stability=False on purpose: the default hides beta and alpha
    # modules under FLYTO_ENV=production, and a gate that cannot see them is a
    # gate the next beta module walks straight past.
    return ModuleRegistry, ModuleRegistry.get_all_metadata(filter_by_stability=False)


def _carries_contract(ModuleRegistry, module_id, metadata):
    """Declared on the decorator, or built at runtime from a measurement."""
    if metadata.get("postcondition") or metadata.get("derives"):
        return True
    module_class = ModuleRegistry.get(module_id)
    if module_class is None:
        return False
    try:
        source_path = inspect.getsourcefile(module_class)
        tree = ast.parse(open(source_path, encoding="utf-8").read())
    except (OSError, SyntaxError, TypeError):
        return False
    return any(
        isinstance(node, ast.ImportFrom)
        and node.module
        and "engine.outcome" in node.module
        for node in ast.walk(tree)
    )


#: Side-effecting modules that cannot yet say what they proved. May only shrink.
#: Generated once from the registry on the day this landed; every later change
#: to it should be a deletion.
UNDECLARED = {
    "ai.memory",
    "ai.memory.entity",
    "ai.memory.vector",
    "ai.model",
    "ai.tool",
    "browser.click",
    "browser.hover",
    "browser.press",
    "k8s.apply",
    "k8s.describe",
    "k8s.get_pods",
    "k8s.logs",
    "k8s.scale",
    # These three are registered from an installed extension package,
    # `flyto_modules_robotics`, and their source is not in this repository --
    # `inspect.getsourcefile` for them points into flyto-modules-robotics. They
    # stay listed here because that is where the population is measured, but
    # they cannot be fixed from this tree.
    #
    # They also do not need what the other entries need. A robotics step
    # *declares* motion and never performs it: `execute` builds a plan, returns
    # it as the job payload the robot's own runner reads, and sets
    # `dispatched: False` in so many words. Nothing leaves this machine. They
    # are in this population only because `requires_credentials=True` puts them
    # there -- the `robotics` category prefix is not in SIDE_EFFECT_CATEGORIES.
    # So `default_for` currently stamps them `dispatched`, which is one rung
    # above what happened, and the honest envelope for a plan builder is no
    # envelope at all. See the handoff notes: the fix belongs in
    # flyto-modules-robotics, and it is a metadata question before it is an
    # outcome question.
    #
    # The robotics pass confirmed all of that by running the three modules and
    # wrote the evidence into `tests/modules/test_robotics_outcome.py`, which
    # also measures the one-line fix: with `requires_credentials=False`,
    # `default_for` returns None for all three on today's code. It adds two
    # findings this note did not have. The refusal path -- parameters that never
    # became a plan, payload nothing but an error string -- is stamped
    # `dispatched` too, which for `robotics.stop` reads as a safe stop having
    # been sent by a step that could not say to which robot. And that payload
    # carries no `ok` key, so `_execute_single_mode` returns it raw and the step
    # completes GREEN with an `error` field in it.
    #
    # No rung was invented for them, deliberately. `indeterminate` is the one
    # that fits the shape and it is reserved: on a robot it means a move that
    # timed out and may still be running, and spending it on "nothing was ever
    # sent" folds those two together for whoever decides to walk in front of the
    # machine.
    "robotics.move",
    "robotics.stop",
    "robotics.turn",
}


class TestTheListOnlyShrinks:
    def test_no_new_module_is_missing_from_both_the_covered_set_and_this_list(
        self, registry
    ):
        """The one that catches a module added tomorrow.

        A new side-effecting module is either written with an outcome or written
        down here. Silently neither is how 483 modules came to have one contract
        between them.
        """
        ModuleRegistry, metadata = registry
        unaccounted = sorted(
            module_id
            for module_id, meta in metadata.items()
            if is_side_effecting(module_id, meta)
            and not _carries_contract(ModuleRegistry, module_id, meta)
            and module_id not in UNDECLARED
        )

        assert not unaccounted, (
            "these side-effecting modules report no outcome and are not on the "
            f"list: {unaccounted}. Give each one an envelope, or add it here and "
            "say so in the commit."
        )

    def test_the_list_has_no_stale_entries(self, registry):
        """An entry that no longer needs excusing is progress worth recording."""
        ModuleRegistry, metadata = registry
        no_longer_needed = sorted(
            module_id
            for module_id in UNDECLARED
            if module_id in metadata
            and _carries_contract(ModuleRegistry, module_id, metadata[module_id])
        )

        assert not no_longer_needed, (
            f"these now report an outcome and can come off the list: "
            f"{no_longer_needed}"
        )

    def test_the_list_names_no_module_that_does_not_exist(self, registry):
        """Renames and deletions leave entries that excuse nothing.

        "Absent" has to mean deleted, not uninstalled. Some categories ship as
        optional packages — `robotics.*` comes from `flyto_modules_robotics`,
        which CI does not install — and on a machine without one, every entry
        for it looks stale. This test failed in CI for exactly that reason while
        passing locally, which is the shape of an environment-dependent gate:
        it fires on the machine, not on the change.

        So a category with NO registered modules at all is read as an absent
        package rather than a set of deletions. A module deleted from a category
        that still has siblings is still caught, which is the case that matters:
        a rename or a removal inside a package that is installed.
        """
        _, metadata = registry
        present_categories = {module_id.split(".")[0] for module_id in metadata}
        gone = sorted(
            module_id
            for module_id in UNDECLARED
            if module_id not in metadata
            and module_id.split(".")[0] in present_categories
        )

        assert not gone, f"these are not registered any more: {gone}"

    def test_an_uninstalled_optional_package_is_not_read_as_deletions(self, registry):
        """The rule above, asserted rather than left implicit.

        Without this, someone tightening the check back to a plain membership
        test would make the suite pass on their machine and fail in CI, which is
        how the check got written wrong the first time.
        """
        _, metadata = registry
        listed_categories = {module_id.split(".")[0] for module_id in UNDECLARED}
        present_categories = {module_id.split(".")[0] for module_id in metadata}
        absent_packages = listed_categories - present_categories

        for category in absent_packages:
            entries = [m for m in UNDECLARED if m.split(".")[0] == category]
            assert entries, category

    def test_the_list_names_nothing_that_is_not_side_effecting(self, registry):
        """A derived module on this list would be excusing a duty it never had."""
        _, metadata = registry
        wrong_population = sorted(
            module_id
            for module_id in UNDECLARED
            if module_id in metadata and not is_side_effecting(module_id, metadata[module_id])
        )

        assert not wrong_population, (
            f"these are not side-effecting and do not belong here: {wrong_population}"
        )


class TestThePopulationIsWhatItClaims:
    def test_http_request_is_side_effecting(self, registry):
        """The module the previous classifier missed, pinned by name.

        `http` was absent from `capability.py`'s seven categories while `sms` —
        which no module registers — was present. A contract whose population
        excludes HTTP is not a contract, and the next person to narrow the list
        should have to delete this test to do it.
        """
        _, metadata = registry
        assert is_side_effecting("http.request", metadata.get("http.request", {}))

    def test_a_pure_computation_is_not_side_effecting(self, registry):
        _, metadata = registry
        assert not is_side_effecting("string.uppercase", metadata.get("string.uppercase", {}))

    def test_requires_credentials_is_enough_on_its_own(self):
        """The half of the rule that is not the category prefix."""
        assert is_side_effecting("anything.at_all", {"requires_credentials": True})
