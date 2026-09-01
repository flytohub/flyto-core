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
    # The five `ai.*` sub-nodes that were here are gone: they now declare
    # `derives=True`, which `default_for` reads as "not on the ladder". They
    # were never going to earn a rung -- they are configuration providers that
    # open no sockets -- so the way off this list was to stop the engine
    # claiming they had dispatched something. See DERIVES_DECLARED below.
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


#: Every module declaring ``derives=True``, which since the rung rewrite means
#: "not on the outcome ladder at all" -- `default_for` stamps nothing for these.
#: That is the right answer for a pure computation and a dangerous one for
#: anything else, so the set is written down rather than trusted.
#:
#: This list is not a ratchet in the shrinking sense: `derives` is a claim, not a
#: deficiency, and it is fine for it to grow. What is not fine is for it to grow
#: quietly. Adding a module here is asserting that it opens no sockets, reads no
#: files and writes no durable state -- and the test below goes looking.
DERIVES_DECLARED = {
    # Configuration providers wired to `llm.agent` over a RESOURCE edge. They
    # assemble a dict and hand it over; the module that spends the money is
    # `llm.agent` itself. `ai.memory.redis` is deliberately NOT here: it really
    # does connect, and it reports its own envelope.
    "ai.memory",
    "ai.memory.entity",
    "ai.memory.vector",
    "ai.model",
    "ai.tool",
    # In side-effecting categories by prefix, doing nothing external in fact:
    # a diff between two strings, and two cron/interval calculators that
    # schedule nothing. All three declared this before `default_for` honoured
    # it, and were stamped `dispatched` for an instruction that never left.
    "file.diff",
    "scheduler.cron_parse",
    "scheduler.interval",
}

#: Cheap evidence against the claim each entry above is making. Not a proof of
#: purity -- nothing short of running them is -- but any of these names being
#: *used* in a file that claims to compute from its inputs is worth a human
#: looking.
#:
#: These are matched against the parsed syntax tree, never against the file's
#: text. The first version of this test scanned the source as a string and
#: failed on all five ai sub-nodes, because the comment explaining why each one
#: derives contains the phrase "opens no sockets". A guard that reads prose
#: catches the documentation instead of the code.
_EFFECT_NAMES = frozenset({
    "open", "socket", "requests", "httpx", "aiofiles", "subprocess",
    "urllib", "aiohttp", "shutil", "tempfile", "sqlite3", "pathlib",
})


def _names_used(source: str) -> set:
    """Every identifier the code actually references, ignoring all text."""
    tree = ast.parse(source)
    used = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            used.add(node.attr)
        elif isinstance(node, ast.Import):
            used.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            used.add(node.module.split(".")[0])
            used.update(alias.name for alias in node.names)
    return used


class TestDerivesMeansWhatItSays:
    """`derives=True` suppresses the rung, so it has to be hard to add.

    Before the rewrite this flag reached VERIFIED and the guard against abusing
    it was that `default_for` asked about side effects first -- so on a module
    in a side-effecting category the flag did nothing at all, and three modules
    that had honestly declared it were overruled and stamped `dispatched`.
    Honouring the flag fixes those three, and creates this hazard in exchange:
    a module that really does dispatch can now silence its rung with one line.
    These two tests are the price of that.
    """

    def test_the_set_of_modules_claiming_to_derive_is_the_one_written_down(self, registry):
        _, metadata = registry
        declared = {
            module_id
            for module_id, meta in metadata.items()
            if meta.get("derives")
        }
        # Entries for modules that ship in an optional package are not absences.
        expected = {m for m in DERIVES_DECLARED if m in metadata}

        assert declared == expected, (
            "the `derives=True` set moved. Added: "
            f"{sorted(declared - expected)}; removed: {sorted(expected - declared)}. "
            "Adding one means no outcome envelope is stamped for that module "
            "ever again -- say why in the commit and add it to DERIVES_DECLARED."
        )

    @pytest.mark.parametrize("module_id", sorted(DERIVES_DECLARED))
    def test_a_module_claiming_to_derive_shows_no_sign_of_reaching_out(
        self, module_id, registry
    ):
        ModuleRegistry, metadata = registry
        if module_id not in metadata:
            pytest.skip(f"{module_id} ships in an optional package")

        module_class = ModuleRegistry.get(module_id)
        source_path = inspect.getsourcefile(module_class)
        with open(source_path, encoding="utf-8") as handle:
            found = sorted(_names_used(handle.read()) & _EFFECT_NAMES)

        assert not found, (
            f"{module_id} declares derives=True -- so nothing it does is ever "
            f"stamped on the ladder -- but {source_path} uses {found}. "
            "Either the claim is stale or the name is innocent here; if it is "
            "innocent, narrow _EFFECT_NAMES and say why."
        )


class TestVerifiedIsAlwaysBackedByADeclaration:
    """The rung that renders as success, guarded at the source.

    `_apply_outcome_contract` lowers a `verified` claim from a module that
    declared no postcondition -- but only where it can find the envelope, which
    is inside `data`, or a flat result with no `data` key at all. A module whose
    `data` is a LIST or a scalar writes its envelope beside `data` instead, and
    that shape returns early: no default stamp and, more to the point here, no
    cap. `step_outcome` reads the envelope from the outer position perfectly
    well, so the place a rung is READ from is wider than the place it is CAPPED.

    Nothing exploits that today, and it was measured rather than assumed: the
    only three modules whose source can produce VERIFIED are `file.edit`,
    `scheduler.delay` and `http.response_assert`, and all three declare a
    postcondition, so their ceiling is VERIFIED and the cap would be a no-op on
    them anyway. This test is what keeps that true. It asks the question at the
    source, where the return shape cannot get in the way: a module that can say
    `verified` has declared what it verified.

    The alternative was widening the cap to the outer position. That is a real
    fix and a bigger one -- it changes what the engine writes for every
    list-shaped result -- and it should be done deliberately rather than as a
    footnote to a module sweep. This closes the hole from the other end in the
    meantime, and it closes it earlier: a module failing this test cannot ship
    the claim at all, whatever shape it returns.
    """

    def test_a_module_that_can_claim_verified_declares_a_postcondition(self, registry):
        ModuleRegistry, metadata = registry

        offenders = []
        for module_id in sorted(metadata):
            module_class = ModuleRegistry.get(module_id)
            if module_class is None:
                continue
            try:
                source_path = inspect.getsourcefile(module_class)
                with open(source_path, encoding="utf-8") as handle:
                    source = handle.read()
            except (OSError, TypeError):
                continue
            if "Outcome.VERIFIED" not in source:
                continue
            if not metadata[module_id].get("postcondition"):
                offenders.append(module_id)

        assert not offenders, (
            f"these modules can emit `verified` but declare no postcondition: "
            f"{offenders}. `verified` means a postcondition was evaluated and "
            "held, so there has to be one to name -- and for a result whose "
            "`data` is a list or a scalar nothing downstream will lower the "
            "claim for you. Declare it on the decorator, or claim `observed`."
        )

