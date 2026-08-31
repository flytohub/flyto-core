"""The ladder's own arithmetic.

Small surface, but every one of these is a way the contract could be true in
the type system and false in practice. The two that matter most:

  * off-ladder answers must not acquire an order. `failed` is not below
    `observed`; giving that comparison an answer lets a caller sort, min(), or
    threshold a column that has no order in it, and the first person to write
    `if outcome >= OBSERVED` gets a wrong answer that looks arithmetic.

  * a misspelled rung must not read as a valid one. Nothing validates the field
    this replaces, and `dispatched` is the *safest* claim — so a typo that fell
    back to it would look like conservatism while actually meaning "we have no
    idea what this module said".
"""

import pytest

from core.engine.outcome import (
    ENVELOPE_KEY,
    LADDER,
    SUCCESS_RUNG,
    ClaimBy,
    Outcome,
    cap,
    envelope,
    is_on_ladder,
    outranks,
    read_envelope,
    rung_index,
)


class TestTheLadderIsOrdered:
    def test_the_four_rungs_are_in_the_order_the_contract_states(self):
        assert [rung.value for rung in LADDER] == [
            "dispatched",
            "accepted",
            "observed",
            "verified",
        ]

    @pytest.mark.parametrize(
        "higher,lower",
        [
            (Outcome.VERIFIED, Outcome.OBSERVED),
            (Outcome.OBSERVED, Outcome.ACCEPTED),
            (Outcome.ACCEPTED, Outcome.DISPATCHED),
            (Outcome.VERIFIED, Outcome.DISPATCHED),
        ],
    )
    def test_each_rung_outranks_the_one_below(self, higher, lower):
        assert outranks(higher, lower)
        assert not outranks(lower, higher)

    def test_a_rung_does_not_outrank_itself(self):
        for rung in LADDER:
            assert not outranks(rung, rung)

    def test_only_verified_may_be_rendered_as_success(self):
        """The whole contract in one assertion."""
        assert SUCCESS_RUNG is Outcome.VERIFIED
        assert [r for r in LADDER if r is not SUCCESS_RUNG] == [
            Outcome.DISPATCHED,
            Outcome.ACCEPTED,
            Outcome.OBSERVED,
        ]


class TestOffLadderAnswersHaveNoOrder:
    @pytest.mark.parametrize("off", [Outcome.FAILED, Outcome.INDETERMINATE])
    def test_they_are_not_on_the_ladder(self, off):
        assert not is_on_ladder(off)
        assert rung_index(off) is None

    @pytest.mark.parametrize("off", [Outcome.FAILED, Outcome.INDETERMINATE])
    @pytest.mark.parametrize("rung", LADDER)
    def test_neither_direction_compares(self, off, rung):
        """Not "false because lower" — false because the question has no answer."""
        assert not outranks(off, rung)
        assert not outranks(rung, off)

    def test_failed_and_indeterminate_do_not_compare_with_each_other(self):
        assert not outranks(Outcome.FAILED, Outcome.INDETERMINATE)
        assert not outranks(Outcome.INDETERMINATE, Outcome.FAILED)


class TestCapping:
    def test_a_claim_above_the_ceiling_is_lowered_to_it(self):
        assert cap(Outcome.VERIFIED, Outcome.ACCEPTED) is Outcome.ACCEPTED

    def test_a_claim_at_or_below_the_ceiling_is_untouched(self):
        assert cap(Outcome.DISPATCHED, Outcome.ACCEPTED) is Outcome.DISPATCHED
        assert cap(Outcome.ACCEPTED, Outcome.ACCEPTED) is Outcome.ACCEPTED

    @pytest.mark.parametrize("off", [Outcome.FAILED, Outcome.INDETERMINATE])
    def test_an_off_ladder_answer_survives_any_ceiling(self, off):
        """A module that failed did fail. No declaration makes that an accepted."""
        assert cap(off, Outcome.DISPATCHED) is off


class TestTheEnvelope:
    def test_it_carries_the_five_fields_and_nothing_else(self):
        made = envelope(Outcome.OBSERVED)

        assert set(made) == {
            "rung",
            "claim_by",
            "postcondition",
            "effects",
            "evidence_ref",
        }

    def test_an_undeclared_envelope_says_so_rather_than_omitting_it(self):
        """`postcondition: None` is the thing the ratchet counts."""
        made = envelope(Outcome.ACCEPTED)

        assert made["postcondition"] is None
        assert made["claim_by"] == ClaimBy.NONE.value
        assert made["effects"] == []

    def test_no_field_name_is_eaten_by_the_output_redactor(self):
        """`_redact_sensitive_output` blanks whole values by key name.

        An envelope field called `auth_verified` or `access_token` would arrive
        at every consumer as '[REDACTED]', and the contract would be invisible
        for reasons no one would connect to redaction.
        """
        from core.engine.step_executor.executor import _SENSITIVE_KEY_PATTERN

        made = envelope(Outcome.VERIFIED, postcondition="row exists")
        for key in [ENVELOPE_KEY, *made]:
            assert not _SENSITIVE_KEY_PATTERN.search(key), key

    def test_effects_are_copied_so_a_module_cannot_mutate_them_later(self):
        supplied = [{"kind": "tab_opened"}]
        made = envelope(Outcome.OBSERVED, effects=supplied)
        supplied.append({"kind": "invented_afterwards"})

        assert len(made["effects"]) == 1


class TestReadingAnEnvelope:
    def test_a_well_formed_envelope_is_returned(self):
        payload = {"data": 1, ENVELOPE_KEY: envelope(Outcome.VERIFIED)}

        assert read_envelope(payload)["rung"] == "verified"

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {"nothing": "here"},
            {ENVELOPE_KEY: "verified"},
            {ENVELOPE_KEY: None},
            {ENVELOPE_KEY: ["verified"]},
            "not a dict at all",
            None,
        ],
    )
    def test_anything_that_is_not_an_envelope_reads_as_none(self, payload):
        assert read_envelope(payload) is None

    @pytest.mark.parametrize("typo", ["verifed", "Verified", "VERIFIED", "", None, 4])
    def test_a_misspelled_rung_is_not_an_envelope(self, typo):
        """Not `dispatched` — nothing.

        Falling back to the lowest rung would read as conservative and would in
        fact mean the opposite: that a module reported something the engine did
        not understand, and nobody was told.
        """
        assert read_envelope({ENVELOPE_KEY: {"rung": typo}}) is None

    def test_the_rung_names_do_not_collide_with_the_engines_other_status_words(self):
        """Three status vocabularies already meet on one screen.

        `TraceStatus` and `ExecutionStatus` are both live in core, and cloud has
        two more enums that are literally both called `ExecutionStatus`. A rung
        that shares a spelling with any of them would be read by whichever map
        saw it first.
        """
        from core.engine.trace import TraceStatus
        from core.modules.items import ExecutionStatus

        rungs = {rung.value for rung in Outcome}
        assert rungs.isdisjoint({member.value for member in TraceStatus})
        assert rungs.isdisjoint({member.value for member in ExecutionStatus})
