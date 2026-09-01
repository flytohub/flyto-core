"""What the engine can see of a step's outcome, and what it does about it.

Two separate things, and conflating them is the trap:

  * WHAT IS SEEN. The old walk read the result dict and, if `data` happened to
    be a dict, that too. A module in `execution_mode` 'items' or 'all' returns
    `{ok, data, items, items_full}` where `data` is a *list*, so every per-item
    outcome underneath was invisible. A module could report all ten of its
    items unobserved and the step recorded a clean success.

  * WHAT IS DONE ABOUT IT. Only off-ladder answers degrade the step's status,
    exactly as before. `dispatched` / `accepted` / `observed` are carried, not
    acted on, because they are the ordinary state of almost every step today
    and marking them `partial` before any consumer can render the difference
    would empty the word out — for the second time, `TraceStatus.PARTIAL`
    already meaning "some items failed".

The second half is the one worth guarding hardest. A contract that makes every
run amber gets turned off, and then it protects nothing.
"""

import pytest

from core.engine.outcome import ClaimBy, Outcome, envelope
from core.engine.step_executor.executor import (
    _unconfirmed_outcome,
    step_outcome,
)


def _rung(result):
    found = step_outcome(result)
    return None if found is None else found[0]


class TestWhatTheEngineCanSee:
    def test_a_plain_result_with_an_envelope(self):
        assert _rung({"outcome": envelope(Outcome.OBSERVED)}) is Outcome.OBSERVED

    def test_an_envelope_nested_under_data(self):
        """Where it has to live: `to_legacy_dict` discards data's siblings."""
        result = {"ok": True, "data": {"outcome": envelope(Outcome.ACCEPTED)}}

        assert _rung(result) is Outcome.ACCEPTED

    def test_a_foreach_result_is_a_list_of_results(self):
        results = [
            {"data": {"outcome": envelope(Outcome.VERIFIED)}},
            {"data": {"outcome": envelope(Outcome.DISPATCHED)}},
        ]

        assert _rung(results) is Outcome.DISPATCHED

    def test_an_items_mode_aggregate_hides_its_outcomes_in_items(self):
        """The hole. `data` is a list here, so the old walk skipped it."""
        aggregate = {
            "ok": True,
            "data": [[{"written": True}]],
            "items": [{"written": True, "outcome": envelope(Outcome.DISPATCHED)}],
            "items_full": [
                {"json": {"written": True, "outcome": envelope(Outcome.DISPATCHED)}}
            ],
        }

        assert _rung(aggregate) is Outcome.DISPATCHED

    def test_one_unobserved_item_among_many_decides_the_step(self):
        """A step is only as confirmed as its least confirmed part."""
        aggregate = {
            "ok": True,
            "items": [
                {"outcome": envelope(Outcome.VERIFIED)},
                {"outcome": envelope(Outcome.VERIFIED)},
                {"outcome": envelope(Outcome.ACCEPTED)},
            ],
        }

        assert _rung(aggregate) is Outcome.ACCEPTED

    def test_a_step_that_reported_nothing_stays_distinguishable_from_dispatched(self):
        """None is not a rung. Most steps say nothing and must keep saying it."""
        assert step_outcome({"ok": True, "data": {"rows": 3}}) is None
        assert step_outcome("a bare string") is None
        assert step_outcome(None) is None


class TestOffLadderAnswersWinOutright:
    def test_failed_beats_any_rung(self):
        results = [
            {"outcome": envelope(Outcome.VERIFIED)},
            {"outcome": envelope(Outcome.FAILED)},
        ]

        assert _rung(results) is Outcome.FAILED

    def test_failed_beats_indeterminate(self):
        """A broken contract is the one somebody has to act on."""
        results = [
            {"outcome": envelope(Outcome.INDETERMINATE)},
            {"outcome": envelope(Outcome.FAILED)},
        ]

        assert _rung(results) is Outcome.FAILED

    def test_indeterminate_is_not_averaged_away_by_a_verified_sibling(self):
        results = [
            {"outcome": envelope(Outcome.VERIFIED)},
            {"outcome": envelope(Outcome.INDETERMINATE)},
        ]

        assert _rung(results) is Outcome.INDETERMINATE


class TestTheLegacyModuleStillWorks:
    """browser.click is the only module of 483 that reports an outcome."""

    @pytest.mark.parametrize(
        "legacy,expected",
        [
            ("not_requested", Outcome.DISPATCHED),
            ("dispatched", Outcome.DISPATCHED),
            ("inferred", Outcome.OBSERVED),
            ("unverified", Outcome.INDETERMINATE),
            ("verified", Outcome.VERIFIED),
        ],
    )
    def test_each_of_its_five_words_maps_onto_a_rung(self, legacy, expected):
        result = {"status": "success", "verification_status": legacy}

        assert _rung(result) is expected

    def test_its_guessed_expectation_that_did_not_hold_is_indeterminate_not_failed(self):
        """The second axis, on the one case that exists today.

        `unverified` means the module inferred an expectation from markup and
        did not see it. The click may well have been fine and the guess wrong,
        so it is not a broken contract. A caller who asks explicitly and does
        not get it never reaches here — click.py raises.
        """
        result = {"verification_status": "unverified", "expected_outcome": "new_tab"}

        rung, claim_by, expected = step_outcome(result)

        assert rung is Outcome.INDETERMINATE
        assert claim_by == ClaimBy.INFERRED.value
        assert expected == "new_tab"

    def test_an_envelope_wins_over_a_legacy_field_on_the_same_payload(self):
        """During migration a module may carry both; the new one is the truth."""
        result = {
            "verification_status": "verified",
            "outcome": envelope(Outcome.DISPATCHED),
        }

        assert _rung(result) is Outcome.DISPATCHED


class TestWhatDegradesAStep:
    """The half that must not over-fire."""

    @pytest.mark.parametrize(
        "rung", [Outcome.DISPATCHED, Outcome.ACCEPTED, Outcome.OBSERVED]
    )
    def test_a_rung_below_verified_does_not_degrade_the_step(self, rung):
        """Carried, not acted on. See the module docstring for why."""
        assert _unconfirmed_outcome({"outcome": envelope(rung)}) is None

    def test_verified_does_not_degrade_the_step(self):
        assert _unconfirmed_outcome({"outcome": envelope(Outcome.VERIFIED)}) is None

    def test_a_step_that_said_nothing_does_not_degrade(self):
        assert _unconfirmed_outcome({"ok": True, "data": {"rows": 3}}) is None

    @pytest.mark.parametrize("rung", [Outcome.FAILED, Outcome.INDETERMINATE])
    def test_off_ladder_answers_degrade_the_step(self, rung):
        reason = _unconfirmed_outcome({"outcome": envelope(rung)})

        assert reason is not None
        assert rung.value in reason

    def test_the_legacy_unverified_still_degrades_exactly_as_it_did(self):
        """The one behaviour that existed before this change, unchanged."""
        result = {"verification_status": "unverified", "expected_outcome": "new_tab"}

        assert _unconfirmed_outcome(result) is not None

    @pytest.mark.parametrize("legacy", ["not_requested", "dispatched", "inferred", "verified"])
    def test_the_other_four_legacy_words_still_do_not_degrade(self, legacy):
        """They were inert before. They stay inert until a consumer exists."""
        assert _unconfirmed_outcome({"verification_status": legacy}) is None

    def test_a_per_item_off_ladder_outcome_now_degrades_the_step(self):
        """The hole, from the acting side.

        Before this change a module could report every item unobserved inside
        an items-mode aggregate and the step recorded a clean success.
        """
        aggregate = {
            "ok": True,
            "data": [[{"clicked": True}]],
            "items": [{"outcome": envelope(Outcome.INDETERMINATE)}],
        }

        assert _unconfirmed_outcome(aggregate) is not None


class TestTheDefaultRule:
    """The rule the whole contract stands on.

    "A side-effecting module with no declared postcondition must never default
    above dispatched/accepted." Get this wrong in the generous direction and 149
    modules become compliant overnight while verifying nothing — which would be
    the largest deliberate false green in the project, built on purpose, by the
    thing meant to prevent it.
    """

    @pytest.fixture
    def stamp(self, monkeypatch):
        """Run _apply_outcome_contract for a module id with given metadata."""
        from core.engine.step_executor import executor as executor_module
        from core.modules.registry import ModuleRegistry

        def run(module_id, result, **metadata):
            monkeypatch.setattr(
                ModuleRegistry,
                "get_metadata",
                staticmethod(lambda mid: metadata if mid == module_id else None),
            )
            instance = type("_M", (), {"module_id": module_id})()
            return executor_module._apply_outcome_contract(instance, result)

        return run

    def test_a_side_effecting_module_that_said_nothing_is_stamped_dispatched(self, stamp):
        result = stamp("file.write", {"ok": True, "data": {"path": "/tmp/x"}})

        assert result["data"]["outcome"]["rung"] == "dispatched"

    def test_the_stamp_lands_inside_data_where_it_survives_the_step(self, stamp):
        """`to_legacy_dict` keeps only `data`; a sibling key is discarded."""
        from core.modules.items import wrap_legacy_result

        result = stamp("shell.exec", {"ok": True, "data": {"exit_code": 0}})
        surviving = wrap_legacy_result(result).to_legacy_dict()

        assert surviving["data"]["outcome"]["rung"] == "dispatched"

    def test_a_derived_module_is_not_stamped_at_all(self, stamp):
        """334 modules. An envelope on every string concatenation is noise."""
        result = stamp("string.uppercase", {"ok": True, "data": {"value": "X"}})

        assert "outcome" not in result["data"]

    def test_requires_credentials_makes_a_module_side_effecting(self, stamp):
        """The classifier's second half, not just the category prefix."""
        result = stamp(
            "notification.send",
            {"ok": True, "data": {}},
            requires_credentials=True,
        )

        assert result["data"]["outcome"]["rung"] == "dispatched"

    def test_a_declared_derives_module_is_not_stamped_at_all(self, stamp):
        """Its return value IS its effect, so there is no distance to report.

        This asserted `verified` while `derives` was the one thing a default
        could reach it by. The ladder measures how far an effect was followed
        into the world; a pure computation has no such distance, and saying
        "verified" about it claims a postcondition was evaluated when the
        module declared none. No envelope is the honest answer, and it is the
        same one every other non-side-effecting module already gets.
        """
        result = stamp("array.sort", {"ok": True, "data": {}}, derives=True)

        assert "outcome" not in result["data"]


class TestTheCeiling:
    @pytest.fixture
    def stamp(self, monkeypatch):
        from core.engine.step_executor import executor as executor_module
        from core.modules.registry import ModuleRegistry

        def run(module_id, result, **metadata):
            monkeypatch.setattr(
                ModuleRegistry,
                "get_metadata",
                staticmethod(lambda mid: metadata if mid == module_id else None),
            )
            instance = type("_M", (), {"module_id": module_id})()
            return executor_module._apply_outcome_contract(instance, result)

        return run

    def test_verified_without_a_declared_postcondition_is_lowered(self, stamp):
        """Not policy: `verified` means a postcondition held, and there is none."""
        claimed = {"ok": True, "data": {"outcome": envelope(Outcome.VERIFIED)}}

        result = stamp("http.request", claimed)

        assert result["data"]["outcome"]["rung"] == "observed"

    def test_verified_with_a_declared_postcondition_stands(self, stamp):
        claimed = {"ok": True, "data": {"outcome": envelope(Outcome.VERIFIED)}}

        result = stamp("file.write", claimed, postcondition="st_size equals the offered length")

        assert result["data"]["outcome"]["rung"] == "verified"
        assert result["data"]["outcome"]["postcondition"] == "st_size equals the offered length"

    def test_observed_is_available_without_a_declaration(self, stamp):
        """Observing is not asserting. An honest measurement may say so."""
        claimed = {"ok": True, "data": {"outcome": envelope(Outcome.OBSERVED)}}

        result = stamp("http.request", claimed)

        assert result["data"]["outcome"]["rung"] == "observed"

    @pytest.mark.parametrize("rung", [Outcome.FAILED, Outcome.INDETERMINATE])
    def test_an_off_ladder_answer_is_never_capped(self, stamp, rung):
        claimed = {"ok": True, "data": {"outcome": envelope(rung)}}

        result = stamp("shell.exec", claimed)

        assert result["data"]["outcome"]["rung"] == rung.value

    def test_a_low_claim_is_never_raised(self, stamp):
        """Nothing here may promote. Only the module can see its own effect."""
        claimed = {"ok": True, "data": {"outcome": envelope(Outcome.DISPATCHED)}}

        result = stamp("file.write", claimed, postcondition="the file exists")

        assert result["data"]["outcome"]["rung"] == "dispatched"

    def test_a_module_that_reported_the_legacy_way_is_not_overwritten(self, stamp):
        """The regression this cost: the one module with a contract lost it.

        browser.click reports through `verification_status` and carries no
        envelope. A default check that asked only `read_envelope` found none and
        stamped `dispatched` beside the legacy field; `_payload_outcome` prefers
        an envelope, so it then returned the stamp and the module's own
        `indeterminate` was never seen. Six existing tests caught it.
        """
        claimed = {"status": "success", "verification_status": "unverified"}

        result = stamp("browser.click", claimed)

        assert "outcome" not in result
        assert step_outcome(result)[0] is Outcome.INDETERMINATE


class TestTheDefaultCannotManufactureAGreenTick:
    """The self-contradiction an adversarial pass found in this very file.

    `default_for`'s docstring said "Never VERIFIED, under any circumstance" and
    the first line of its body returned VERIFIED for anything declaring
    `derives`. Three modules in a side-effect category declared it — file.diff,
    scheduler.interval, scheduler.cron_parse — and were stamped `verified` with
    `postcondition: None` and `effects: []`: a green tick with nothing behind
    it, produced by the default whose job is to prevent exactly that.
    """

    def test_declaring_derives_reaches_no_rung_at_all(self):
        """The hazard is gone rather than unreachable.

        Ordering alone made VERIFIED unreachable, which fixed the symptom and
        left the mechanism in the building. It also contradicted `ceiling_for`,
        where VERIFIED is *defined* as "a postcondition was evaluated and it
        held" -- so handing it to a module whose `postcondition` is None was
        never a policy overreach, it was a category error. A boolean flag is
        not a predicate.
        """
        from core.engine.outcome import default_for

        assert default_for("file.diff", {"derives": True}) is None
        assert default_for("scheduler.interval", {"derives": True}) is None
        assert default_for("array.sort", {"derives": True}) is None

    def test_a_module_that_derives_is_not_reported_as_having_dispatched(self):
        """The other half, and the reason the ordering changed.

        `derives` now outranks the category, because the two are different kinds
        of statement: `is_side_effecting` reads the text before the first dot
        and is guessing, while `derives` is a declaration about the module in
        front of the author. Eight modules were in that disagreement and all
        eight were being told on: `dispatched` says an instruction left us, and
        for a diff between two strings none did.
        """
        from core.engine.outcome import Outcome, default_for, is_side_effecting

        assert is_side_effecting("file.diff", {})
        assert default_for("file.diff", {}) is Outcome.DISPATCHED
        assert default_for("file.diff", {"derives": True}) is None

    def test_no_shipped_module_is_stamped_verified_by_default(self):
        """Over the real registry, not a constructed case.

        The whole hard rule in one assertion: whatever any of the 483 modules
        declares today, none of them gets a `verified` default it did not earn.
        """
        import os

        os.environ.pop("FLYTO_ENV", None)
        from core.modules import atomic  # noqa: F401
        from core.modules.registry import ModuleRegistry
        from core.engine.outcome import Outcome, default_for, is_side_effecting

        metadata = ModuleRegistry.get_all_metadata(filter_by_stability=False)
        wrongly_verified = sorted(
            module_id
            for module_id, meta in metadata.items()
            if is_side_effecting(module_id, meta)
            and default_for(module_id, meta) is Outcome.VERIFIED
        )

        assert not wrongly_verified, wrongly_verified


class TestTheStampGoesWhereItSurvives:
    """The other thing the adversarial pass found here.

    `to_legacy_dict` keeps `data` and discards every sibling. The write target
    was `data` when it is a dict and the outer result otherwise — and "otherwise"
    includes a list-shaped `data`, which is precisely the discarded place.
    """

    @pytest.fixture
    def stamp(self, monkeypatch):
        from core.engine.step_executor import executor as executor_module
        from core.modules.registry import ModuleRegistry

        def run(module_id, result, **metadata):
            monkeypatch.setattr(
                ModuleRegistry,
                "get_metadata",
                staticmethod(lambda mid: metadata if mid == module_id else None),
            )
            instance = type("_M", (), {"module_id": module_id})()
            return executor_module._apply_outcome_contract(instance, result)

        return run

    def test_a_dict_data_takes_the_stamp(self, stamp):
        result = stamp("file.write", {"ok": True, "data": {"path": "/tmp/x"}})

        assert result["data"]["outcome"]["rung"] == "dispatched"

    def test_a_flat_result_takes_it_at_the_top_where_it_is_swept_into_data(self, stamp):
        from core.modules.items import wrap_legacy_result

        result = stamp("file.write", {"ok": True, "path": "/tmp/x"})
        surviving = wrap_legacy_result(result).to_legacy_dict()

        assert surviving["data"]["outcome"]["rung"] == "dispatched"

    @pytest.mark.parametrize("payload", [[{"a": 1}], "a string", 7, None])
    def test_a_data_that_cannot_hold_a_mapping_is_left_alone(self, stamp, payload):
        """Silence, rather than a stamp written where it gets thrown away."""
        result = stamp("file.write", {"ok": True, "data": payload})

        assert "outcome" not in result
